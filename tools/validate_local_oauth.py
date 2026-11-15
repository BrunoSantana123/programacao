"""Exercita consentimento real com Supabase LOCAL e conta fictícia.

Não simula o SDK ou as respostas do Auth. Só adapta os identificadores públicos
da página em memória para o projeto local e intercepta o callback do cliente de
teste. Não acessa produção, tabelas financeiras ou ferramentas MCP.
"""
import argparse
import base64
import hashlib
import http.server
import json
import os
from pathlib import Path
import secrets
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from playwright.sync_api import sync_playwright, expect
from tools.check_mcp_test import NoRedirect, request
from tools.setup_local_test import api

ROOT = Path(__file__).resolve().parents[1]
CALLBACK = 'https://example.invalid/nexo-test/callback'


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
    assert [t['name'] for t in tools] == ['testar_conexao']
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
                         ('role', 'service_role'), ('client_id', None), ('sub', None)]:
        modified = {**claims, field: value}
        if value is None:
            modified.pop(field)
        content = header + '.' + encode(json.dumps(modified).encode())
        r, s = decode_dss_signature(key.sign(content.encode(), ec.ECDSA(hashes.SHA256())))
        signature = encode(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))
        status, _, _ = request(url, initialize, {'Authorization': 'Bearer ' + content + '.' + signature})
        assert status == 401
    print('PASS: MCP local real — descoberta, OAuth JWT, lista, ferramenta inofensiva e 6 rejeições de claims.')


def run(directory):
    private = json.loads((directory / 'private.json').read_text())
    origin, key = private['api_url'], private['anon_key']
    if origin != 'http://127.0.0.1:54321':
        raise RuntimeError('Somente o Supabase local é permitido.')
    admin_key = private['service_role_key']
    password_session = api(origin, key, '/auth/v1/token?grant_type=password', {
        'email': private['email'], 'password': private['password']})
    client = api(origin, admin_key, '/auth/v1/admin/oauth/clients', {
        'client_name': 'NEXO local isolated validation', 'redirect_uris': [CALLBACK],
        'grant_types': ['authorization_code', 'refresh_token'], 'response_types': ['code'],
        'token_endpoint_auth_method': 'none'})
    client_id = client['client_id']

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
            browser = pw.chromium.launch(
                executable_path=os.environ.get('NEXO_CHROMIUM_EXECUTABLE') or None, headless=True)
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
                    context = browser.new_context()
                    redirects, failures = [], []

                    def route_request(route):
                        url = route.request.url
                        if url.startswith(CALLBACK + '?'):
                            redirects.append(url)
                            route.fulfill(content_type='text/html', body='Local test callback')
                        elif any(url.startswith(base + '/') for base in [origin, local_site, 'https://cdn.jsdelivr.net']):
                            route.continue_()
                        else:
                            failures.append('Destino não autorizado bloqueado')
                            route.abort()

                    context.route('**/*', route_request)
                    try:
                        page = context.new_page()
                        page.on('pageerror', lambda _: failures.append('Erro JavaScript'))
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
                                try:
                                    api(origin, key, '/auth/v1/oauth/token', token_body)
                                except urllib.error.HTTPError as exc:
                                    if exc.code not in (400, 401):
                                        raise
                                else:
                                    raise RuntimeError('Reutilização do código foi aceita.')
                                print('PASS: OAuth local real — reutilização do código recusada.')
                        print('PASS: OAuth local real — ' + decision + ' (SDK, state e retorno conferidos).')
                    finally:
                        context.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        req = urllib.request.Request(origin + '/auth/v1/admin/oauth/clients/' + client_id,
                                     method='DELETE', headers={'apikey': admin_key, 'Authorization': 'Bearer ' + admin_key})
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=20):
            pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True, type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    # O CLI inicia o Edge Runtime local; encerrar somente o processo desta execução.
    os.umask(0o077)
    log_path = directory / 'functions-private.log'
    with log_path.open('w') as log:
        process = subprocess.Popen([str(directory / 'bin/supabase'), 'functions', 'serve',
                                    'nexo-mcp-test', '--env-file', str(directory / 'local-functions.env')],
                                   cwd=directory, stdout=log, stderr=log,
                                   env={**os.environ, 'SUPABASE_INTERNAL_IMAGE_REGISTRY': 'docker.io'})
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
            run(directory)
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
