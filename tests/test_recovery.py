"""Recuperação isolada: todas as requisições externas são interceptadas."""
import functools
import http.server
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from playwright.sync_api import sync_playwright, expect
from tools.build_homolog import build

ROOT = Path(__file__).resolve().parents[1]


class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / 'homolog'))
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.site = f'http://127.0.0.1:{cls.server.server_port}'
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=os.getenv('NEXO_CHROMIUM_EXECUTABLE') or None)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls.pw.stop(); cls.server.shutdown(); cls.server.server_close(); cls.thread.join()

    def setUp(self):
        self.context = self.browser.new_context(viewport={'width': 390, 'height': 844})
        self.page = self.context.new_page()
        self.calls, self.errors = [], []
        self.page.on('pageerror', lambda e: self.errors.append(str(e)))
        self.response, self.code = {}, 200
        def route(r):
            if r.request.url.endswith('/config.js'):
                r.fulfill(content_type='text/javascript', body='window.NEXO_HOMOLOG={supabaseUrl:"https://testisolated.supabase.co",publishableKey:"sb_publishable_test"};')
            elif r.request.url.startswith(self.site): r.continue_()
            elif r.request.url.startswith('https://testisolated.supabase.co/auth/v1/'):
                self.calls.append({'url': r.request.url, 'method': r.request.method, 'body': r.request.post_data_json, 'headers': r.request.headers})
                if '/verify' in r.request.url and self.code == 200:
                    data = {'access_token': 'recovery-test-secret', 'expires_in': 3600, 'user': {'id': 'own-test-account'}}
                else: data = self.response
                r.fulfill(status=self.code, content_type='application/json', body=json.dumps(data))
            else: r.abort()
        self.context.route('**/*', route)

    def tearDown(self):
        self.assertEqual(self.errors, [])
        self.context.close()

    def open(self, suffix=''):
        self.page.goto('about:blank')
        self.page.goto(self.site + '/recuperar.html' + suffix)

    def verified(self):
        self.open('?type=recovery&token_hash=' + 'a' * 64)
        expect(self.page.locator('#resetView')).to_be_visible()

    def submit(self, password='NovaSenha!12345', confirmation=None):
        self.page.locator('[name=password]').fill(password)
        self.page.locator('[name=confirmation]').fill(confirmation or password)
        self.page.locator('#resetForm button').click()

    def test_request_generic_and_fixed_redirect(self):
        self.open('?next=https://evil.invalid')
        self.page.locator('[name=email]').fill('conta@example.invalid')
        self.page.locator('#requestForm button').click()
        expect(self.page.locator('#message')).to_contain_text('Se houver uma conta')
        call = self.calls[-1]
        self.assertEqual(call['body'], {'email': 'conta@example.invalid'})
        self.assertIn('redirect_to=http%3A%2F%2F127.0.0.1', call['url'])
        self.assertNotIn('evil', call['url'])

    def test_valid_link_clean_url_and_no_storage(self):
        self.verified()
        self.assertNotIn('token_hash', self.page.url)
        self.assertEqual(self.page.evaluate('Object.keys(localStorage).length+Object.keys(sessionStorage).length'), 0)
        self.assertEqual(self.calls[0]['body']['type'], 'recovery')

    def test_reset_updates_and_revokes(self):
        self.verified(); self.submit()
        expect(self.page.locator('#message')).to_contain_text('Senha alterada com sucesso')
        self.assertEqual([c['method'] for c in self.calls], ['POST', 'PUT', 'POST'])
        self.assertTrue(self.calls[-1]['url'].endswith('logout?scope=global'))
        self.assertEqual(self.calls[1]['headers']['authorization'], 'Bearer recovery-test-secret')
        self.assertTrue(all('/rest/' not in c['url'] for c in self.calls))
        self.assertEqual(self.page.locator('[name=password]').input_value(), '')

    def test_weak_password_and_mismatch(self):
        for password, confirm in [('abcdefghijkl', None), ('NovaSenha!12345', 'OutraSenha!12345')]:
            with self.subTest(password=password):
                self.verified(); self.submit(password, confirm)
                expect(self.page.locator('#message')).to_have_class('error')
                self.assertFalse(any(c['method'] == 'PUT' for c in self.calls))

    def test_invalid_links_make_no_requests(self):
        for query in ['?type=signup&token_hash='+'a'*64, '?type=recovery&token_hash=x',
                      '#access_token=secret&type=recovery', '?error=expired',
                      '?type=recovery&type=signup&token_hash='+'a'*64]:
            with self.subTest(query=query):
                self.open(query)
                expect(self.page.locator('#message')).to_have_class('error')
                self.assertEqual(self.calls, [])
                expect(self.page.locator('#resetView')).to_be_hidden()
                self.assertNotIn('secret', self.page.url)

    def test_expired_used_link(self):
        self.code = 403; self.response = {'error_code': 'otp_expired'}
        self.open('?type=recovery&token_hash='+'b'*64)
        expect(self.page.locator('#message')).to_contain_text('já foi utilizado ou expirou')
        expect(self.page.locator('#resetView')).to_be_hidden()

    def test_rate_limit(self):
        self.code = 429
        self.open(); self.page.locator('[name=email]').fill('a@example.invalid')
        self.page.locator('#requestForm button').click()
        expect(self.page.locator('#message')).to_contain_text('Muitas tentativas')
        expect(self.page.locator('#requestForm button')).to_be_enabled()

    def test_password_policy_from_server(self):
        self.verified(); self.code = 422; self.response = {'error_code': 'weak_password'}
        self.submit(); expect(self.page.locator('#message')).to_contain_text('senha forte')
        expect(self.page.locator('#resetView')).to_be_visible()

    def test_revocation_failure_does_not_claim_success(self):
        self.verified()
        self.page.route('**/logout?scope=global', lambda r: r.fulfill(status=500, body='{}'))
        self.submit(); expect(self.page.locator('#message')).to_contain_text('Não foi possível confirmar')

    def test_mobile_and_desktop_layout(self):
        self.verified()
        for width in [320, 390, 1280]:
            self.page.set_viewport_size({'width': width, 'height': 844})
            self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
            expect(self.page.locator('#resetForm button')).to_be_visible()

    def test_network_failure(self):
        self.page.route('**/auth/v1/recover?*', lambda r: r.abort())
        self.open(); self.page.locator('[name=email]').fill('a@example.invalid')
        self.page.locator('#requestForm button').click()
        expect(self.page.locator('#message')).to_contain_text('Verifique sua conexão')

    def test_unconfigured_closed(self):
        self.page.route('**/config.js', lambda r: r.fulfill(content_type='text/javascript', body='window.NEXO_HOMOLOG=null;'))
        self.open(); self.page.locator('[name=email]').fill('a@example.invalid')
        self.page.locator('#requestForm button').click()
        expect(self.page.locator('#message')).to_contain_text('não foi configurada')
        self.assertEqual(self.calls, [])

    def test_official_project_rejected(self):
        self.page.route('**/config.js', lambda r: r.fulfill(content_type='text/javascript', body='window.NEXO_HOMOLOG={supabaseUrl:"https://tznebgdgdqpbhjdrhprb.supabase.co",publishableKey:"sb_publishable_test"};'))
        self.open(); self.page.locator('[name=email]').fill('a@example.invalid')
        self.page.locator('#requestForm button').click()
        expect(self.page.locator('#message')).to_contain_text('não foi configurada')
        self.assertEqual(self.calls, [])

    def test_session_expiry(self):
        self.page.clock.install()
        self.verified()
        self.page.clock.fast_forward(15 * 60 * 1000 + 1)
        expect(self.page.locator('#resetView')).to_be_hidden()
        expect(self.page.locator('#message')).to_contain_text('prazo')

    def test_rejected_update_session(self):
        self.verified(); self.code = 401
        self.submit()
        expect(self.page.locator('#resetView')).to_be_hidden()
        expect(self.page.locator('#message')).to_contain_text('inválido')

    def test_login_link(self):
        self.page.goto(self.site + '/index.html')
        self.page.get_by_role('link', name='Esqueci minha senha').click()
        expect(self.page.locator('#requestForm')).to_be_visible()


class BuildTests(unittest.TestCase):
    def test_no_production_or_admin_key(self):
        for url, key in [('https://tznebgdgdqpbhjdrhprb.supabase.co', 'sb_publishable_test'),
                         ('https://isolated.supabase.co', 'sb_secret_forbidden'), ('', '')]:
            with patch.dict(os.environ, NEXO_HOMOLOG_SUPABASE_URL=url, NEXO_HOMOLOG_SUPABASE_PUBLISHABLE_KEY=key):
                with self.assertRaises(ValueError): build()

    def test_isolated_build(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,
                NEXO_HOMOLOG_SUPABASE_URL='https://isolated.supabase.co', NEXO_HOMOLOG_SUPABASE_PUBLISHABLE_KEY='sb_publishable_test'):
            build(directory)
            self.assertIn('isolated.supabase.co', Path(directory, 'config.js').read_text())
            self.assertNotIn('tznebgdgdqpbhjdrhprb', Path(directory, 'index.html').read_text())
