"""Teste real Auth exclusivamente local; não envia e-mails externos nem lê finanças."""
import argparse
import functools
import http.server
import json
import os
from pathlib import Path
import secrets
import threading
import urllib.request
import urllib.error
from playwright.sync_api import sync_playwright, expect
def request(url, body=None, headers=None, method=None):
    if not url.startswith('http://127.0.0.1:54321/'):
        raise RuntimeError('Somente Supabase local é permitido.')
    payload = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=payload, method=method, headers={
        'Content-Type':'application/json', **(headers or {})})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try: response = opener.open(req, timeout=20)
    except urllib.error.HTTPError as error: response = error
    with response:
        raw = response.read()
        return response.status, response.headers, json.loads(raw) if raw else None


def api(url, key, path, body):
    status, _, result = request(url+path, body, {'apikey':key, 'Authorization':'Bearer '+key})
    if status >= 300: raise RuntimeError('Falha no Auth local: HTTP '+str(status))
    return result

ROOT = Path(__file__).resolve().parents[1]


class Quiet(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.split('?')[0] in ['/recuperar.html', '/confirmar.html']:
            page = ROOT / self.path.split('?')[0].lstrip('/')
            html = page.read_text().replace("connect-src https://*.supabase.co;", "connect-src https://*.supabase.co http://127.0.0.1:*;")
            self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.end_headers(); self.wfile.write(html.encode())
        else:
            super().do_GET()

    def log_message(self, *args):
        pass


def validate(directory):
    state = json.loads((directory / 'private.json').read_text())
    origin = state['api_url']
    if origin != 'http://127.0.0.1:54321':
        raise RuntimeError('Somente Supabase local é permitido.')
    key, admin = state['anon_key'], state['service_role_key']
    headers = {'apikey': key}
    email = 'recovery-' + secrets.token_hex(8) + '@example.invalid'
    old, new = secrets.token_urlsafe(22) + '!Aa1', secrets.token_urlsafe(22) + '!Bb2'
    signup = api(origin, admin, '/auth/v1/admin/generate_link', {'type':'signup', 'email':email, 'password':old})
    identifier = signup.get('user', signup)['id']
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(ROOT)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    site = f'http://127.0.0.1:{server.server_port}'
    try:
        # Admin gera o mesmo token de recuperação, sem simular SMTP ou alegar entrega.
        status, _, unconfirmed = request(origin+'/auth/v1/token?grant_type=password', {'email':email,'password':old}, headers)
        assert status == 400 and unconfirmed.get('error_code') == 'email_not_confirmed', 'Confirmação não foi exigida para a conta temporária'
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv('NEXO_CHROMIUM_EXECUTABLE') or None)
            context = browser.new_context(viewport={'width': 390, 'height': 844})
            def route(r):
                if r.request.url.endswith('/auth-config.js'):
                    c = {'supabaseUrl': origin, 'publishableKey': key}
                    r.fulfill(content_type='text/javascript', body='window.NEXO_AUTH_CONFIG=' + json.dumps(c) + ';')
                elif r.request.url.startswith('https://tznebgdgdqpbhjdrhprb.supabase.co/'):
                    # A aplicação é servida sem alterar o código oficial: transporte local somente.
                    url = origin + r.request.url.split('.supabase.co',1)[1]
                    response = r.fetch(url=url, headers={**r.request.headers,'apikey':key})
                    r.fulfill(response=response)
                elif r.request.url.startswith(site + '/') or r.request.url.startswith(origin + '/'): r.continue_()
                else: r.abort()
            context.route('**/*', route)
            page = context.new_page()
            page.goto(site + '/confirmar.html?type=signup&token_hash=' + signup['hashed_token'])
            expect(page.locator('#message')).to_contain_text('E-mail confirmado com sucesso')
            link = api(origin, admin, '/auth/v1/admin/generate_link', {'type':'recovery','email':email})
            hashed = link['hashed_token']
            page.goto(site + '/recuperar.html?type=recovery&token_hash=' + hashed)
            expect(page.locator('#resetView')).to_be_visible()
            page.locator('[name=password]').fill(new)
            page.locator('[name=confirmation]').fill(new)
            page.locator('#resetForm button').click()
            expect(page.locator('#message')).to_contain_text('Senha alterada com sucesso')
            assert 'token_hash' not in page.url
            page.goto(site + '/recuperar.html?type=recovery&token_hash=' + hashed)
            expect(page.locator('#message')).to_contain_text('já foi utilizado ou expirou')
            # Login real no app, sem tocar em contas existentes.
            page.goto(site + '/index.html')
            page.locator('#auth [name=email]').fill(email)
            page.locator('#auth [name=password]').fill(new)
            page.locator('#auth button[value=login]').click()
            expect(page.locator('#app')).to_be_visible()
            # Inicialização de documento vazio legítimo não pode escrever no banco.
            response, _, login = request(origin+'/auth/v1/token?grant_type=password', {'email':email,'password':new}, headers)
            assert response == 200
            own_headers = {'apikey':key,'Authorization':'Bearer '+login['access_token']}
            status, _, _ = request(origin+'/rest/v1/nexo_data', {'user_id':identifier,'data':{}}, own_headers)
            assert status == 201
            page.locator('#logout').click()
            page.locator('#auth [name=email]').fill(email)
            page.locator('#auth [name=password]').fill(new)
            page.locator('#auth button[value=login]').click()
            expect(page.locator('#app')).to_be_visible()
            status, _, rows = request(origin+'/rest/v1/nexo_data?user_id=eq.'+identifier+'&select=data', headers=own_headers)
            assert status == 200 and rows == [{'data':{}}], 'Documento vazio foi sobrescrito no login'
            # Histórico preexistente e propriedades extras também permanecem intactos.
            saved = {'entries':[{'id':'previous-test','date':'2026-11-15','type':'income','category':'Teste','amount':12.34,'description':'Registro anterior preservado'}],
                     'bills':[],'events':[],'goals':[],'tasks':[],'custom':'preservar'}
            status, _, _ = request(origin+'/rest/v1/nexo_data?user_id=eq.'+identifier, {'data':saved}, own_headers, method='PATCH')
            assert status == 204
            page.locator('#logout').click()
            page.locator('#auth [name=email]').fill(email)
            page.locator('#auth [name=password]').fill(new)
            page.locator('#auth button[value=login]').click()
            expect(page.locator('#app')).to_be_visible()
            page.locator('#nav [data-go=Financeiro]').click()
            expect(page.locator('.dataList .line').filter(has_text='Registro anterior preservado')).to_be_visible()
            status, _, rows = request(origin+'/rest/v1/nexo_data?user_id=eq.'+identifier+'&select=data', headers=own_headers)
            assert status == 200 and rows == [{'data':saved}], 'Histórico foi modificado no login'
            context.close(); browser.close()
        status, _, _ = request(origin + '/auth/v1/token?grant_type=password', {'email': email, 'password': old}, headers)
        assert status == 400, 'Senha antiga não foi recusada'
        status, _, result = request(origin + '/auth/v1/token?grant_type=password', {'email': email, 'password': new}, headers)
        assert status == 200 and result.get('user', {}).get('id') == identifier
        print('PASS Auth local real: conta não confirmada bloqueada, confirmação, recuperação, replay/senha antiga rejeitados, novo login e documentos vazio/financeiro preservados.')
        print('SMTP e confirmação por e-mail não certificados: nenhuma mensagem externa enviada.')
    finally:
        server.shutdown(); server.server_close(); thread.join()
        req = urllib.request.Request(origin + '/auth/v1/admin/users/' + identifier, method='DELETE',
            headers={'apikey': admin, 'Authorization': 'Bearer ' + admin})
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=20):
            pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, required=True)
    validate(parser.parse_args().directory)
