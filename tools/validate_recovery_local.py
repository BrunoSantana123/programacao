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
from tools.setup_local_test import api
from tools.check_mcp_test import request

ROOT = Path(__file__).resolve().parents[1]


class Quiet(http.server.SimpleHTTPRequestHandler):
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
    user = api(origin, admin, '/auth/v1/admin/users', {'email': email, 'password': old, 'email_confirm': True})
    identifier = user['id']
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(ROOT / 'homolog')))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    site = f'http://127.0.0.1:{server.server_port}'
    try:
        # Admin gera o mesmo token de recuperação, sem simular SMTP ou alegar entrega.
        link = api(origin, admin, '/auth/v1/admin/generate_link', {'type': 'recovery', 'email': email})
        hashed = link['hashed_token']
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv('NEXO_CHROMIUM_EXECUTABLE') or None)
            context = browser.new_context(viewport={'width': 390, 'height': 844})
            def route(r):
                if r.request.url.endswith('/config.js'):
                    c = {'supabaseUrl': origin, 'publishableKey': key}
                    r.fulfill(content_type='text/javascript', body='window.NEXO_HOMOLOG=' + json.dumps(c) + ';')
                elif r.request.url.startswith(site + '/') or r.request.url.startswith(origin + '/'): r.continue_()
                else: r.abort()
            context.route('**/*', route)
            page = context.new_page()
            page.goto(site + '/recuperar.html?type=recovery&token_hash=' + hashed)
            expect(page.locator('#resetView')).to_be_visible()
            page.locator('[name=password]').fill(new)
            page.locator('[name=confirmation]').fill(new)
            page.locator('#resetForm button').click()
            expect(page.locator('#message')).to_contain_text('Senha alterada com sucesso')
            assert 'token_hash' not in page.url
            page.goto(site + '/recuperar.html?type=recovery&token_hash=' + hashed)
            expect(page.locator('#message')).to_contain_text('já foi utilizado ou expirou')
            context.close(); browser.close()
        status, _, _ = request(origin + '/auth/v1/token?grant_type=password', {'email': email, 'password': old}, headers)
        assert status == 400, 'Senha antiga não foi recusada'
        status, _, result = request(origin + '/auth/v1/token?grant_type=password', {'email': email, 'password': new}, headers)
        assert status == 200 and result.get('user', {}).get('id') == identifier
        print('PASS Supabase real local: link recovery, nova senha, replay rejeitado, senha antiga rejeitada e novo login.')
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
