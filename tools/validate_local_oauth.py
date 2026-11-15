"""Exercita consentimento real com Supabase LOCAL e conta fictícia.

Não simula o SDK ou as respostas do Auth. Só adapta os identificadores públicos
da página em memória para o projeto local e intercepta o callback do cliente de
teste. Acessa somente tabelas locais e ferramentas da versão de homologação; nunca produção.
"""
import argparse
import base64
import hashlib
import http.server
import json
import os
from pathlib import Path
import secrets
import shlex
import subprocess
import threading
import time
import tomllib
import re
import urllib.error
import urllib.parse
import urllib.request

from playwright.sync_api import sync_playwright, expect
from tools.check_mcp_test import NoRedirect, request
from tools.setup_local_test import api

ROOT = Path(__file__).resolve().parents[1]
CALLBACK = 'https://example.invalid/nexo-test/callback'
EDGE_IMAGE = 'supabase/edge-runtime:v1.69.28'


def browser_options():
    options = dict(executable_path=os.environ.get('NEXO_CHROMIUM_EXECUTABLE') or None, headless=True)
    proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
    if proxy:
        parsed = urllib.parse.urlsplit(proxy)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname:
            raise RuntimeError('Rota de proxy do navegador inválida.')
        host = '[' + parsed.hostname + ']' if ':' in parsed.hostname else parsed.hostname
        server = parsed.scheme + '://' + host + (':' + str(parsed.port) if parsed.port else '')
        bypass = os.environ.get('NO_PROXY') or os.environ.get('no_proxy', '')
        options['proxy'] = {'server': server, 'bypass': ','.join(filter(None, [bypass, '127.0.0.1', 'localhost']))}
        if parsed.username:
            options['proxy']['username'] = urllib.parse.unquote(parsed.username)
        if parsed.password:
            options['proxy']['password'] = urllib.parse.unquote(parsed.password)
    return options


def validate_environment(directory):
    private = json.loads((directory / 'private.json').read_text())
    if private.get('api_url') != 'http://127.0.0.1:54321':
        raise RuntimeError('Ambiente de autenticação deve ser exclusivamente local.')
    copied = directory / 'supabase/functions/nexo-mcp-test/index.ts'
    expected = ROOT / 'supabase/functions/nexo-mcp-test/index.ts'
    if copied.read_bytes() != expected.read_bytes():
        raise RuntimeError('Função local diverge da cópia de testes revisada; execute a preparação novamente.')
    network = (directory / 'local-functions.env').read_bytes()
    if (not network.startswith(b'NEXO_TEST_MODE=local\n')
            or hashlib.sha256(network).hexdigest() != private.get('network_env_sha256')):
        raise RuntimeError('Configuração local da função divergente.')


def runtime_command(directory, client_id=None):
    project = tomllib.loads((directory / 'supabase/config.toml').read_text())['project_id']
    if not re.fullmatch(r'[A-Za-z0-9_-]+', project):
        raise RuntimeError('Identificador do projeto local inválido.')
    network = 'supabase_network_' + project
    # Recusar concorrência com outro runtime sem encerrar processos alheios.
    result = subprocess.run(['docker', 'network', 'inspect', network], capture_output=True, text=True, check=True)
    members = json.loads(result.stdout)[0].get('Containers', {})
    for identifier in members:
        result = subprocess.run(['docker', 'inspect', identifier, '--format',
                                 '{{json .NetworkSettings.Networks}}'], capture_output=True, text=True, check=True)
        aliases = json.loads(result.stdout).get(network, {}).get('Aliases') or []
        if 'edge_runtime' in aliases or 'supabase_edge_runtime_' + project in aliases:
            raise RuntimeError('Já existe um Edge Runtime nessa rede; não será encerrado pelo teste.')
    allowed = {'NEXO_TEST_MODE', 'HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'http_proxy',
               'https_proxy', 'no_proxy', 'DENO_CERT', 'SSL_CERT_FILE', 'DENO_TLS_CA_STORE'}
    values = {}
    for line in (directory / 'local-functions.env').read_text().splitlines():
        key, separator, quoted = line.partition('=')
        decoded = shlex.split(quoted)
        if not separator or key not in allowed or len(decoded) != 1:
            raise RuntimeError('Variável inesperada no ambiente privado da função.')
        values[key] = decoded[0]
    private_path = directory / 'private.json'
    if private_path.exists():
        state = json.loads(private_path.read_text())
        values['SUPABASE_ANON_KEY'] = state['anon_key']
        values['NEXO_OAUTH_CLIENT_IDS'] = client_id or ''
    name = 'nexo-mcp-runtime-' + secrets.token_hex(6)
    functions = directory / 'supabase/functions'
    command = ['docker', 'run', '--rm', '--name', name, '--network', network,
               '--network-alias', 'edge_runtime', '--network-alias',
               'supabase_edge_runtime_' + project, '--mount',
               f'type=bind,src={functions},dst={functions},readonly',
               '--volume', 'nexo_mcp_deno_cache_' + project + ':/root/.cache/deno']
    for key in values:
        # Somente nomes nos argumentos; valores privados vêm do ambiente do processo.
        command.extend(['--env', key])
    command.extend(['--entrypoint', 'edge-runtime', EDGE_IMAGE, 'start',
                    '--main-service=' + str(functions / 'nexo-mcp-test'), '--port=8081'])
    return command, {**os.environ, **values}, name


def verify_mcp(private, token, password_token, directory):
    """Somente a ferramenta inofensiva do fonte recuperado é executada."""
    origin = private['api_url']
    url = origin + '/functions/v1/nexo-mcp-test'
    status, _, metadata = request(url + '/.well-known/oauth-protected-resource')
    assert status == 200 and metadata['resource'] == url
    assert metadata['authorization_servers'] == [origin + '/auth/v1']
    initialize = dict(jsonrpc='2.0', id=1, method='initialize', params={
        'protocolVersion': '2025-03-26', 'capabilities': {},
        'clientInfo': {'name': 'nexo-local-integration', 'version': '1.0'}})
    for bearer in [None, 'invalid-token', password_token]:
        status, headers, _ = request(url, initialize, {'Authorization': 'Bearer ' + bearer} if bearer else {})
        assert status == 401 and 'resource_metadata=' in headers.get('WWW-Authenticate', '')
    parts = token.split('.')
    parts[2] = ('A' if parts[2][0] != 'A' else 'B') + parts[2][1:]
    status, _, _ = request(url, initialize, {'Authorization': 'Bearer ' + '.'.join(parts)})
    assert status == 401
    auth = {'Authorization': 'Bearer ' + token}
    status, _, result = request(url, initialize, auth)
    assert status == 200 and result['result']['capabilities'] == {'tools': {}}
    status, _, _ = request(url, dict(jsonrpc='2.0', method='notifications/initialized'), auth)
    assert status == 202
    status, _, listing = request(url, dict(jsonrpc='2.0', id=2, method='tools/list'), auth)
    assert status == 200
    tools = listing['result']['tools']
    assert [t['name'] for t in tools] == ['testar_conexao', 'registrar_lancamento']
    assert tools[0]['annotations']['readOnlyHint'] is True
    status, _, result = request(url, dict(jsonrpc='2.0', id=3, method='tools/call',
                                        params={'name': 'testar_conexao', 'arguments': {}}), auth)
    assert status == 200 and result['result']['content'][0]['type'] == 'text'
    assert 'Nenhum dado financeiro' in result['result']['content'][0]['text']
    status, _, result = request(url, dict(jsonrpc='2.0', id=4, method='tools/call',
                                        params={'name': 'nonexistent_test_tool', 'arguments': {}}), auth)
    assert status == 200 and result['error']['code'] == -32601

    # Tokens adversariais assinados exclusivamente pela chave PRIVADA LOCAL.
    # Não se altera o verificador da função para fazer os testes passarem.
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    def decode(value):
        return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
    def encode(value):
        return base64.urlsafe_b64encode(value).rstrip(b'=').decode()
    claims = json.loads(decode(token.split('.')[1]))
    jwk = json.loads((directory / 'supabase/signing_keys.json').read_text())[0]
    key = ec.derive_private_key(int.from_bytes(decode(jwk['d']), 'big'), ec.SECP256R1())
    header = encode(json.dumps(dict(alg='ES256', typ='JWT', kid=jwk['kid'])).encode())
    for field, value in [('exp', 1), ('aud', 'wrong-audience'), ('iss', 'https://example.invalid'),
                         ('role', 'service_role'), ('client_id', None), ('sub', None), ('client_id', '00000000-0000-4000-8000-000000000000')]:
        modified = {**claims, field: value}
        if value is None:
            modified.pop(field)
        content = header + '.' + encode(json.dumps(modified).encode())
        r, s = decode_dss_signature(key.sign(content.encode(), ec.ECDSA(hashes.SHA256())))
        signature = encode(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))
        status, _, _ = request(url, initialize, {'Authorization': 'Bearer ' + content + '.' + signature})
        assert status == 401
    print('PASS: MCP local real — descoberta, OAuth JWT, lista, ferramenta inofensiva e rejeição de claims/cliente inválidos.')


def run(directory, client_id):
    private = json.loads((directory / 'private.json').read_text())
    origin, key = private['api_url'], private['anon_key']
    if origin != 'http://127.0.0.1:54321':
        raise RuntimeError('Somente o Supabase local é permitido.')
    admin_key = private['service_role_key']
    password_session = api(origin, key, '/auth/v1/token?grant_type=password', {
        'email': private['email'], 'password': private['password']})


    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            path = urllib.parse.urlsplit(self.path).path
            if path == '/oauth-config.js':
                text = ('export const TRUSTED_CLIENT_ID=' + json.dumps(client_id) + ';\n'
                        'export const TRUSTED_CALLBACK=' + json.dumps(CALLBACK) + ';')
                content_type = 'text/javascript'
            elif path == '/oauth-policy.js':
                text = (ROOT / 'oauth-policy.js').read_text()
                content_type = 'text/javascript'
            elif path in ('/index.html', '/nexo-teste.html'):
                text = (ROOT / path.lstrip('/')).read_text()
                text = text.replace("const SB_URL='https://tznebgdgdqpbhjdrhprb.supabase.co';", 'const SB_URL=' + json.dumps(origin) + ';')
                start = text.index('const SB_KEY=')
                end = text.index(';', start)
                text = text[:start] + 'const SB_KEY=' + json.dumps(key) + text[end:]
                content_type = 'text/html'
            elif path == '/oauth-consent.html':
                text = (ROOT / 'oauth-consent.html').read_text()
                text = text.replace("const PROJECT = 'https://tznebgdgdqpbhjdrhprb.supabase.co';",
                                    'const PROJECT = ' + json.dumps(origin) + ';')
                start = text.index('const PUBLISHABLE_KEY = ')
                end = text.index(';', start)
                text = text[:start] + 'const PUBLISHABLE_KEY = ' + json.dumps(key) + text[end:]
                content_type = 'text/html'
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', content_type + '; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(text.encode())

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    local_site = 'http://127.0.0.1:' + str(server.server_port)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(**browser_options())
            try:
                for decision in ['deny', 'approve', 'previous', 'bad-pkce']:
                    verifier = secrets.token_urlsafe(48)
                    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
                    state = secrets.token_urlsafe(24)
                    params = dict(client_id=client_id, redirect_uri=CALLBACK, response_type='code',
                                  scope='openid', state=state, code_challenge=challenge, code_challenge_method='S256')
                    req = urllib.request.Request(origin + '/auth/v1/oauth/authorize?' + urllib.parse.urlencode(params),
                                                 headers={'apikey': key})
                    try:
                        response = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(req, timeout=20)
                    except urllib.error.HTTPError as exc:
                        response = exc
                    with response:
                        if response.status not in (302, 303, 307):
                            raise RuntimeError('Auth não iniciou o consentimento.')
                        request_id = urllib.parse.parse_qs(urllib.parse.urlsplit(
                            response.headers['Location']).query)['authorization_id'][0]
                    context = browser.new_context(viewport={'width':390,'height':844} if decision in ('deny','previous') else {'width':1280,'height':800}, is_mobile=decision in ('deny','previous'), has_touch=decision in ('deny','previous'))
                    redirects, failures, network_failures = [], [], []

                    def route_request(route):
                        url = route.request.url
                        if url.startswith(CALLBACK + '?'):
                            redirects.append(url)
                            route.fulfill(content_type='text/html', body='Local test callback')
                        elif url.startswith('https://cdn.jsdelivr.net/'):
                            # Bytes reais do SDK, obtidos pelo cliente HTTPS do
                            # Playwright com a CA da sessão fornecida ao Node.
                            # Não desativar TLS nem simular respostas do SDK.
                            try:
                                route.fulfill(response=route.fetch(max_redirects=0))
                            except Exception:
                                failures.append('Falha no download HTTPS verificado do SDK')
                                route.abort()
                        elif any(url.startswith(base + '/') for base in [origin, local_site]):
                            route.continue_()
                        else:
                            failures.append('Destino não autorizado bloqueado')
                            route.abort()

                    context.route('**/*', route_request)
                    try:
                        page = context.new_page()
                        page.on('pageerror', lambda _: failures.append('Erro JavaScript'))
                        page.on('requestfailed', lambda req: network_failures.append((
                            urllib.parse.urlsplit(req.url).hostname,
                            re.search(r'net::[A-Z_]+', req.failure or '').group()
                            if re.search(r'net::[A-Z_]+', req.failure or '') else 'request_failed')))
                        page.goto(local_site + '/oauth-consent.html?authorization_id=' + urllib.parse.quote(request_id))
                        expect(page.locator('#login')).to_be_visible(timeout=30000)
                        page.locator('[name=email]').fill(private['email'])
                        page.locator('[name=password]').fill(private['password'])
                        page.locator('#login button').click()
                        if decision in ('deny', 'approve'):
                            expect(page.locator('#consent')).to_be_visible(timeout=15000)
                            page.locator('#' + decision).click()
                        page.wait_for_url(CALLBACK + '**', timeout=15000)
                        if failures or len(redirects) != 1:
                            raise RuntimeError('Falha de navegação ou JavaScript.')
                        returned = urllib.parse.parse_qs(urllib.parse.urlsplit(redirects[0]).query)
                        if returned.get('state') != [state]:
                            raise RuntimeError('Estado OAuth divergente.')
                        if decision == 'deny':
                            if returned.get('error') != ['access_denied'] or 'code' in returned:
                                raise RuntimeError('Recusa não preservada.')
                        else:
                            token_body = {
                                'grant_type': 'authorization_code', 'code': returned['code'][0],
                                'client_id': client_id, 'redirect_uri': CALLBACK, 'code_verifier': verifier}
                            if decision == 'bad-pkce':
                                token_body['code_verifier'] = secrets.token_urlsafe(48)
                                try:
                                    api(origin, key, '/auth/v1/oauth/token', token_body)
                                except urllib.error.HTTPError as exc:
                                    if exc.code not in (400, 401):
                                        raise
                                else:
                                    raise RuntimeError('PKCE divergente foi aceito.')
                                print('PASS: OAuth local real — PKCE divergente recusado.')
                                continue
                            token = api(origin, key, '/auth/v1/oauth/token', token_body)
                            user_req = urllib.request.Request(origin + '/auth/v1/oauth/userinfo', headers={
                                'apikey': key, 'Authorization': 'Bearer ' + token['access_token']})
                            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(user_req, timeout=20) as user_response:
                                if json.load(user_response).get('sub') != private['user_id']:
                                    raise RuntimeError('Identidade OAuth divergente.')
                            if decision == 'approve':
                                verify_mcp(private, token['access_token'], password_session['access_token'], directory)
                                from tools.validate_financial_delivery import verify
                                verify(browser, local_site, private, token['access_token'], client_id)
                                try:
                                    api(origin, key, '/auth/v1/oauth/token', token_body)
                                except urllib.error.HTTPError as exc:
                                    if exc.code not in (400, 401):
                                        raise
                                else:
                                    raise RuntimeError('Reutilização do código foi aceita.')
                                print('PASS: OAuth local real — reutilização do código recusada.')
                        print('PASS: OAuth local real — ' + decision + ' (SDK, state e retorno conferidos).')
                    except Exception:
                        # Somente domínio e código de transporte, nunca URL, senha ou token.
                        print('Fase OAuth local:', decision, 'falhas de rede:', network_failures)
                        raise
                    finally:
                        context.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True, type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    try:
        validate_environment(directory)
    except Exception:
        raise SystemExit('Ambiente local não corresponde à preparação revisada; nenhum serviço foi iniciado.')
    # Executar diretamente o fonte fornecido no modo main-service oficialmente
    # suportado, sem reconstruir roteador ou funções ausentes e sem importar o
    # template genérico do CLI que depende de deno.land. JWT permanece no fonte.
    os.umask(0o077)
    log_path = directory / 'functions-private.log'
    private = json.loads((directory / 'private.json').read_text())
    client = api(private['api_url'], private['service_role_key'], '/auth/v1/admin/oauth/clients', {
        'client_name': 'NEXO homologação isolada', 'redirect_uris': [CALLBACK],
        'grant_types': ['authorization_code', 'refresh_token'], 'response_types': ['code'],
        'token_endpoint_auth_method': 'none'})
    client_id = client['client_id']
    with log_path.open('w') as log:
        command, environment, container_name = runtime_command(directory, client_id)
        process = subprocess.Popen(command, cwd=directory, stdout=log, stderr=log, env=environment)
        try:
            ready = False
            for _ in range(360):
                if process.poll() is not None:
                    break
                try:
                    with urllib.request.urlopen('http://127.0.0.1:54321/functions/v1/nexo-mcp-test/.well-known/oauth-protected-resource', timeout=2) as response:
                        ready = response.status == 200
                except (urllib.error.URLError, TimeoutError):
                    pass
                if ready:
                    break
                time.sleep(0.5)
            if not ready:
                raise RuntimeError('Edge Runtime local não ficou pronto.')
            run(directory, client_id)
        except Exception as exc:
            import traceback
            # Somente tipo, HTTP status e posições no código; nunca valores de variáveis.
            positions = traceback.extract_tb(exc.__traceback__)
            print('Diagnóstico seguro:', type(exc).__name__, 'HTTP', getattr(exc, 'code', '-'),
                  [(Path(p.filename).name, p.lineno) for p in positions if 'programacao' in p.filename])
            raise SystemExit('Validação OAuth/MCP LOCAL falhou; respostas, credenciais e códigos não foram registrados.')
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            # Nome aleatório criado por esta execução; nunca remover outro serviço.
            subprocess.run(['docker', 'rm', '--force', container_name], capture_output=True)
            req = urllib.request.Request(private['api_url'] + '/auth/v1/admin/oauth/clients/' + client_id,
                method='DELETE', headers={'apikey':private['service_role_key'], 'Authorization':'Bearer ' + private['service_role_key']})
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=20):
                pass
