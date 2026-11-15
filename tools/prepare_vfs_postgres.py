"""Deriva uma imagem LOCAL de camada única para Docker vfs com poucos recursos.

Não publica imagens. Verifica o binário oficial crane, fixa o manifesto de origem
por digest e preserva integralmente a configuração de execução da imagem oficial.
crane e umoci validam os blobs OCI. umoci aplica as camadas em ordem, preservando
hardlinks Nix mesmo quando seu nome original foi removido em uma camada posterior.
Docker load valida o diff_id derivado. Somente o alias LOCAL usado pelo CLI muda.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import urllib.request

VERSION = '0.22.1'
UMOCI_VERSION = '0.6.0'
IMAGE = 'supabase/postgres:15.8.1.085'
REGISTRY_IMAGE = 'registry-1.docker.io/' + IMAGE


def command(*args):
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode:
        error = RuntimeError('Ferramenta de imagem local falhou; nenhuma saída remota foi exibida.')
        error.private_diagnostic = result.stdout + result.stderr
        raise error
    return result.stdout


def prepare(directory):
    if command('docker', 'info', '--format', '{{.Driver}}').strip() != 'vfs':
        return
    # Nunca sobrescrever uma imagem já existente, oficial ou derivada.
    exists = subprocess.run(['docker', 'image', 'inspect', IMAGE], capture_output=True)
    if exists.returncode == 0:
        return
    directory = Path(directory)
    binary = directory / 'bin/crane'
    if not binary.exists():
        base = f'https://github.com/google/go-containerregistry/releases/download/v{VERSION}/'
        name = 'go-containerregistry_Linux_x86_64.tar.gz'
        sums = urllib.request.urlopen(base + 'checksums.txt', timeout=30).read().decode()
        expected = next(line.split()[0] for line in sums.splitlines() if line.split()[-1] == name)
        data = urllib.request.urlopen(base + name, timeout=60).read()
        if hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError('Checksum crane inválido.')
        archive = directory / 'bin' / name
        archive.write_bytes(data)
        with tarfile.open(archive) as tar:
            item = next(m for m in tar.getmembers() if m.name == 'crane' and m.isfile())
            binary.write_bytes(tar.extractfile(item).read())
        binary.chmod(0o700)
    elif command(str(binary), 'version').strip().lstrip('v') != VERSION:
        raise RuntimeError('crane existente tem versão inesperada.')
    digest = command(str(binary), 'digest', '--platform', 'linux/amd64', REGISTRY_IMAGE).strip()
    if not digest.startswith('sha256:') or len(digest) != 71:
        raise RuntimeError('Digest de origem inválido.')
    source = REGISTRY_IMAGE.split(':')[0] + '@' + digest
    original = json.loads(command(str(binary), 'config', '--platform', 'linux/amd64', source))
    if original.get('architecture') != 'amd64' or original.get('os') != 'linux':
        raise RuntimeError('Plataforma de origem incompatível.')
    work = directory / 'flat-postgres'
    work.mkdir(exist_ok=True)
    layer = work / 'layer.tar'
    umoci = directory / 'bin/umoci'
    if not umoci.exists():
        base = f'https://github.com/opencontainers/umoci/releases/download/v{UMOCI_VERSION}/'
        name = 'umoci.linux.amd64'
        sums = urllib.request.urlopen(base + 'umoci.sha256sum', timeout=30).read().decode()
        expected = next(line.split()[0] for line in sums.splitlines()
                        if len(line.split()) >= 2 and line.split()[-1].lstrip('*').rsplit('/', 1)[-1] == name)
        data = urllib.request.urlopen(base + name, timeout=60).read()
        if hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError('Checksum umoci inválido.')
        umoci.write_bytes(data)
        umoci.chmod(0o700)
    elif command(str(umoci), '--version').splitlines()[0].strip() != 'umoci version ' + UMOCI_VERSION:
        raise RuntimeError('umoci existente tem versão inesperada.')
    # Não usar crane flatten (publica imagens) nem seu export direto: no Postgres
    # Nix, export pode deixar hardlinks sem alvo quando nomes foram removidos.
    layout = work / 'oci'
    if not (layout / 'oci-layout').is_file():
        command(str(binary), 'pull', '--platform', 'linux/amd64', '--format=oci', source, str(layout))
    index_path = layout / 'index.json'
    index = json.loads(index_path.read_text())
    if len(index['manifests']) != 1 or index['manifests'][0]['digest'] != digest:
        raise RuntimeError('Layout OCI não corresponde ao manifesto oficial fixado.')
    index['manifests'][0]['annotations'] = {'org.opencontainers.image.ref.name': 'nexo-original'}
    index_path.write_text(json.dumps(index))
    helper = 'registry-1.docker.io/library/debian'
    helper_digest = command(str(binary), 'digest', '--platform', 'linux/amd64', helper + ':bookworm-slim').strip()
    if not helper_digest.startswith('sha256:') or len(helper_digest) != 71:
        raise RuntimeError('Digest do empacotador inválido.')
    # Container sem rede, sem privilégios adicionais e sem acesso a credenciais.
    # GNU tar registra o conteúdo real dos hardlinks, uid/gid, ACLs e xattrs.
    command('docker', 'run', '--rm', '--network', 'none', '--user', '0:0',
            '--mount', f'type=bind,src={work},dst=/work',
            '--mount', f'type=bind,src={umoci},dst=/usr/local/bin/umoci,readonly',
            helper + '@' + helper_digest, 'sh', '-ec',
            'test ! -e /work/bundle; trap "rm -rf /work/bundle" EXIT; '
            'umoci unpack --image /work/oci:nexo-original /work/bundle; '
            'tar --format=pax --xattrs --xattrs-include="*" --acls --numeric-owner '
            '-cf /work/layer.tar -C /work/bundle/rootfs .; rm -rf /work/bundle')
    hasher = hashlib.sha256()
    with layer.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(chunk)
    layer_digest = hasher.hexdigest()
    config = {**original, 'rootfs': {'type': 'layers', 'diff_ids': ['sha256:' + layer_digest]},
              'history': [{'created_by': 'NEXO local test: verified OCI unpack of ' + source}]}
    config_data = json.dumps(config, separators=(',', ':')).encode()
    config_name = hashlib.sha256(config_data).hexdigest() + '.json'
    (work / config_name).write_bytes(config_data)
    manifest = [{'Config': config_name, 'RepoTags': [IMAGE], 'Layers': ['layer.tar']}]
    (work / 'manifest.json').write_text(json.dumps(manifest))
    archive = work / 'docker-image.tar'
    with tarfile.open(archive, 'w') as tar:
        for name in [config_name, 'manifest.json', 'layer.tar']:
            tar.add(work / name, arcname=name)
    command('docker', 'load', '--input', str(archive))
    actual = json.loads(command('docker', 'image', 'inspect', IMAGE))[0]
    for key, value in original['config'].items():
        # O Engine pode normalizar null em valores vazios; sem alterar semântica.
        if actual['Config'].get(key) != value and not (not actual['Config'].get(key) and not value):
            # Alias não existia antes e acaba de ser criado por esta execução.
            # Não deixar uma derivação reprovada disponível para a próxima tarefa.
            command('docker', 'image', 'rm', IMAGE)
            raise RuntimeError('Configuração derivada divergiu da oficial; não iniciar serviços.')
    (directory / 'postgres-image-provenance.json').write_text(json.dumps({
        'source': source, 'derived_local_image_id': actual['Id'],
        'derived_diff_id': 'sha256:' + layer_digest, 'runtime_config_verified': True,
        'packaging_helper': helper + '@' + helper_digest}))
    archive.unlink()
    layer.unlink()
    print('PASS: imagem Postgres derivada somente localmente, origem por digest e configuração verificadas.')
