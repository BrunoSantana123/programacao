"""Reutiliza proxy e confiança fornecidos ao Docker, sem alterar política ou daemon.

Valores de proxy podem conter credenciais: nunca imprimir, versionar ou incluir
em imagens. Esta configuração é privada, temporária e deve ser renovada por tarefa.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil


def prepare(directory):
    config_path = Path(os.environ.get('DOCKER_CONFIG', str(Path.home() / '.docker'))) / 'config.json'
    proxies = {}
    if config_path.is_file():
        # Não ler nem utilizar o campo auths de credenciais de registros.
        configured = json.loads(config_path.read_text()).get('proxies', {})
        proxies = configured.get(os.environ.get('DOCKER_HOST'), configured.get('default', {}))
    fields = {'httpProxy': 'HTTP_PROXY', 'httpsProxy': 'HTTPS_PROXY', 'noProxy': 'NO_PROXY'}
    values = {}
    for field, variable in fields.items():
        value = proxies.get(field) or os.environ.get(variable) or os.environ.get(variable.lower())
        if value:
            values[variable] = value
            values[variable.lower()] = value
    if 'HTTP_PROXY' in values or 'HTTPS_PROXY' in values:
        existing = values.get('NO_PROXY', '')
        local = ['127.0.0.1', 'localhost', 'kong', 'db', 'auth', 'rest']
        merged = ','.join(dict.fromkeys([item for item in existing.split(',') if item] + local))
        values['NO_PROXY'] = values['no_proxy'] = merged
    certificate = os.environ.get('SSL_CERT_FILE') or os.environ.get('CODEX_PROXY_CERT')
    if certificate:
        source = Path(certificate)
        if not source.is_file():
            raise RuntimeError('Bundle de certificados fornecido está indisponível; TLS não será desativado.')
        if b'PRIVATE KEY' in source.read_bytes():
            raise RuntimeError('Arquivo de confiança contém chave privada; não será copiado.')
        target = directory / 'supabase/functions/.session-ca.pem'
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(0o600)
        # O CLI monta functions no mesmo caminho absoluto, em modo somente leitura.
        values.update(DENO_CERT=str(target), SSL_CERT_FILE=str(target), DENO_TLS_CA_STORE='mozilla,system')
    lines = ['NEXO_TEST_MODE=local']
    for key, value in values.items():
        if '\n' in value or '\r' in value:
            raise RuntimeError('Configuração de rede inválida; arquivo privado não foi gravado.')
        quoted = value.replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$')
        lines.append(key + '="' + quoted + '"')
    content = '\n'.join(lines) + '\n'
    path = directory / 'local-functions.env'
    path.write_text(content)
    path.chmod(0o600)
    return hashlib.sha256(content.encode()).hexdigest()
