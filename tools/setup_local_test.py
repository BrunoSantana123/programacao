"""Prepara somente Supabase local em Docker, fora do checkout; nunca usa link/push/reset.

Uso: python tools/setup_local_test.py --directory /workspace/nexo-test-environment
O arquivo private.json contém credenciais LOCAIS e não deve ser publicado.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tarfile
import urllib.error
import urllib.request

from tools.prepare_vfs_postgres import prepare as prepare_vfs_postgres
from tools.container_network import prepare as prepare_container_network

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2.67.3'
EXCLUDE = 'realtime,storage-api,imgproxy,mailpit,postgres-meta,studio,edge-runtime,logflare,vector,supavisor'


def cli(directory, *args):
    result = subprocess.run([str(directory / 'bin/supabase'), *args], cwd=directory,
                            env={**os.environ, 'SUPABASE_INTERNAL_IMAGE_REGISTRY': 'docker.io'},
                            capture_output=True, text=True)
    if result.returncode:
        # Saída do CLI pode conter chaves locais. Guardar somente no diretório privado.
        log = directory / 'setup-private.log'
        log.write_text(result.stdout + result.stderr)
        log.chmod(0o600)
        print('Etapa CLI local recusada:', args[0], 'exit', result.returncode)
        if 'no space left on device' in (result.stdout + result.stderr).lower():
            print('Diagnóstico: espaço insuficiente para as imagens Docker.')
        raise RuntimeError('CLI falhou; diagnóstico está no arquivo privado do ambiente local.')
    return result.stdout


def api(url, key, path, body):
    if url != 'http://127.0.0.1:54321':
        raise RuntimeError('Esta API administrativa é exclusivamente local.')
    req = urllib.request.Request(url + path, data=json.dumps(body).encode(), headers={
        'Content-Type': 'application/json', 'apikey': key, 'Authorization': 'Bearer ' + key})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=20) as response:
        return json.load(response)


def install(directory):
    binary = directory / 'bin/supabase'
    if binary.exists():
        if cli(directory, '--version').strip() != VERSION:
            raise RuntimeError('CLI existente tem versão diferente; não foi sobrescrito.')
        return
    binary.parent.mkdir(exist_ok=True)
    base = f'https://github.com/supabase/cli/releases/download/v{VERSION}/'
    checksums = urllib.request.urlopen(base + f'supabase_{VERSION}_checksums.txt', timeout=30).read().decode()
    name = 'supabase_linux_amd64.tar.gz'
    checksum = next(line.split()[0] for line in checksums.splitlines() if line.split()[-1] == name)
    data = urllib.request.urlopen(base + name, timeout=60).read()
    if hashlib.sha256(data).hexdigest() != checksum:
        raise RuntimeError('Checksum do CLI inválido.')
    archive = binary.parent / name
    archive.write_bytes(data)
    with tarfile.open(archive) as tar:
        member = next(m for m in tar.getmembers() if m.name == 'supabase' and m.isfile())
        binary.write_bytes(tar.extractfile(member).read())
    binary.chmod(0o700)


def setup(directory):
    directory = directory.resolve()
    if (len(directory.parts) < 3 or directory == ROOT or ROOT in directory.parents
            or directory in ROOT.parents):
        raise RuntimeError('O ambiente e suas credenciais devem ficar fora do checkout.')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    install(directory)
    prepare_vfs_postgres(directory)
    config = directory / 'supabase/config.toml'
    if not config.exists():
        cli(directory, 'init')
    # Somente configuração LOCAL gerada pelo CLI; nenhuma política de produção.
    original = config.read_text()
    text = original
    # PostgreSQL 15 é suportado pelo CLI e suficiente para Auth/MCP sem tabelas
    # financeiras; usa imagem oficial menor para ambientes Docker com driver vfs.
    text = text.replace('major_version = 17', 'major_version = 15')
    start = text.index('[auth.oauth_server]')
    end = text.find('\n[', start + 1)
    end = len(text) if end == -1 else end
    block = text[start:end].replace('enabled = false', 'enabled = true', 1)
    text = text[:start] + block + text[end:]
    text = text.replace('authorization_url_path = "/oauth/consent"',
                        'authorization_url_path = "/oauth-consent.html"')
    if not (directory / 'supabase/signing_keys.json').exists():
        # Chaves assimétricas locais para exercitar a validação ES256 original do MCP.
        generated = json.loads(cli(directory, 'gen', 'signing-key', '--algorithm', 'ES256'))
        signing_path = directory / 'supabase/signing_keys.json'
        signing_path.write_text(json.dumps([generated]))
        signing_path.chmod(0o600)
    text = text.replace('# signing_keys_path = "./signing_keys.json"',
                        'signing_keys_path = "./signing_keys.json"')
    # Remover somente o bloco gerado na preparação anterior com CLI serve.
    # O modo main-service usa o verificador original da própria função e não
    # necessita de opção para desativar a verificação de JWT do roteador do CLI.
    text = text.replace('\n[functions.nexo-mcp-test]\nverify_jwt = false\n', '\n')
    config.write_text(text)
    function = directory / 'supabase/functions/nexo-mcp-test'
    function.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / 'tests/integration/nexo-mcp-test/index.ts', function / 'index.ts')
    network_fingerprint = prepare_container_network(directory)
    if text != original:
        # Aplicar mudanças de OAuth/chaves também na segunda execução, sem reset.
        # stop atua somente sobre o projeto LOCAL desse diretório e conserva dados.
        cli(directory, 'stop')
    cli(directory, 'start', '-x', EXCLUDE)
    status = json.loads(cli(directory, 'status', '-o', 'json'))
    url = status['API_URL']
    if url != 'http://127.0.0.1:54321':
        raise RuntimeError('API local inesperada; nenhuma conta foi criada.')
    path = directory / 'private.json'
    state = json.loads(path.read_text()) if path.exists() else {
        'email': 'nexo-test@example.invalid', 'password': secrets.token_urlsafe(32)}
    path.write_text(json.dumps(state))
    path.chmod(0o600)
    try:
        user = api(url, status['SERVICE_ROLE_KEY'], '/auth/v1/admin/users', {
            'email': state['email'], 'password': state['password'], 'email_confirm': True,
            'user_metadata': {'purpose': 'isolated-nexo-test'}})
        state['user_id'] = user['id']
    except urllib.error.HTTPError as exc:
        if exc.code not in (422, 400):
            raise
        # Reutilização só é aceita se o login com a senha local guardada funcionar.
    session = api(url, status['ANON_KEY'], '/auth/v1/token?grant_type=password', {
        'email': state['email'], 'password': state['password']})
    if state.get('user_id') and session['user']['id'] != state['user_id']:
        raise RuntimeError('Identidade da conta local divergente.')
    state.update(user_id=session['user']['id'], api_url=url,
                 anon_key=status['ANON_KEY'], service_role_key=status['SERVICE_ROLE_KEY'],
                 network_env_sha256=network_fingerprint)
    path.write_text(json.dumps(state))
    path.chmod(0o600)
    shutil.copyfile(ROOT / 'tests/fixtures/nexo-synthetic.json', directory / 'nexo-synthetic.json')
    print('PASS: Supabase Docker local, OAuth habilitado e login da conta fictícia verificado.')
    print('Fixture fictícia preparada em arquivo; não importada em tabelas sem esquema confirmado.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        setup(args.directory)
    except Exception as exc:
        import traceback
        if hasattr(exc, 'private_diagnostic'):
            diagnostic = args.directory / 'image-tools-private.log'
            diagnostic.write_text(exc.private_diagnostic)
            diagnostic.chmod(0o600)
        positions = traceback.extract_tb(exc.__traceback__)
        print('Diagnóstico seguro:', type(exc).__name__, 'HTTP', getattr(exc, 'code', '-'),
              [(Path(p.filename).name, p.lineno) for p in positions
               if p.filename.endswith(('setup_local_test.py', 'prepare_vfs_postgres.py'))])
        # Erros HTTP podem carregar senhas ou chaves; não imprimir exceções brutas.
        raise SystemExit('Preparação local bloqueada; consulte a documentação e os diagnósticos privados.')
