"""Recuperação isolada: todas as requisições externas são interceptadas."""
import functools
import http.server
import json
import os
from pathlib import Path
import threading
import unittest
from playwright.sync_api import sync_playwright, expect


ROOT = Path(__file__).resolve().parents[1]


class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
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
        self.user_response = {'id':'own-test-account', 'email_confirmed_at':'2026-11-15T00:00:00Z'}
        def route(r):
            if r.request.url.endswith('/auth-config.js'):
                r.fulfill(content_type='text/javascript', body='window.NEXO_AUTH_CONFIG={supabaseUrl:"https://testisolated.supabase.co",publishableKey:"sb_publishable_test"};')
            elif r.request.url.startswith(self.site): r.continue_()
            elif any(r.request.url.startswith(host + '/auth/v1/') for host in ['https://testisolated.supabase.co','https://tznebgdgdqpbhjdrhprb.supabase.co']):
                self.calls.append({'url': r.request.url, 'method': r.request.method, 'body': r.request.post_data_json, 'headers': r.request.headers})
                if r.request.method == 'GET' and '/user' in r.request.url and self.code == 200:
                    data = self.user_response
                elif '/verify' in r.request.url and self.code == 200:
                    data = {'access_token': 'recovery-test-secret', 'expires_in': 3600, 'user': self.user_response}
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
        expect(self.page.locator('#message')).to_contain_text('sua conexão')

    def test_unconfigured_closed(self):
        self.page.route('**/auth-config.js', lambda r: r.fulfill(content_type='text/javascript', body='window.NEXO_AUTH_CONFIG=null;'))
        self.open(); self.page.locator('[name=email]').fill('a@example.invalid')
        self.page.locator('#requestForm button').click()
        expect(self.page.locator('#message')).to_contain_text('não foi configurado')
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

    def test_standard_recovery_link_verified_by_server(self):
        self.open('#type=recovery&access_token=aaa.bbb.ccc&expires_in=3600&refresh_token=never-store')
        expect(self.page.locator('#resetView')).to_be_visible()
        self.assertEqual(self.calls[0]['method'], 'GET')
        self.assertTrue(self.calls[0]['url'].endswith('/user'))
        self.assertNotIn('access_token', self.page.url)
        self.assertEqual(self.page.evaluate('Object.keys(localStorage).length+Object.keys(sessionStorage).length'), 0)

    def test_forged_standard_link_rejected_by_server(self):
        self.code = 401
        self.open('#type=recovery&access_token=aaa.bbb.ccc&expires_in=3600')
        expect(self.page.locator('#resetView')).to_be_hidden()
        expect(self.page.locator('#message')).to_contain_text('inválido')
        self.assertEqual(len(self.calls), 1)

    def test_standard_signup_confirmation(self):
        self.page.goto(self.site + '/confirmar.html#type=signup&access_token=aaa.bbb.ccc&expires_in=3600')
        expect(self.page.locator('#message')).to_contain_text('E-mail confirmado com sucesso')
        self.assertNotIn('access_token', self.page.url)
        self.assertTrue(self.calls[-1]['url'].endswith('logout?scope=local'))

    def test_unconfirmed_user_not_reported_confirmed(self):
        self.user_response = {'id':'own-test-account'}
        self.page.goto(self.site + '/confirmar.html#type=signup&access_token=aaa.bbb.ccc&expires_in=3600')
        expect(self.page.locator('#message')).to_contain_text('inválido')

    def test_hash_signup_confirmation(self):
        self.page.goto(self.site + '/confirmar.html?type=signup&token_hash='+'d'*64)
        expect(self.page.locator('#message')).to_contain_text('E-mail confirmado com sucesso')
        self.assertEqual(self.calls[0]['body']['type'], 'signup')

    def test_signup_requires_strong_password_and_sends_redirect(self):
        self.page.goto(self.site + '/index.html')
        self.page.locator('#auth [name=email]').fill('new@example.invalid')
        self.page.locator('#auth [name=password]').fill('12345678')
        self.page.locator('button[value=signup]').click()
        expect(self.page.locator('#authMsg')).to_contain_text('senha forte')
        self.assertEqual(self.calls, [])
        self.page.locator('#auth [name=email]').fill('new@example.invalid')
        self.page.locator('#auth [name=password]').fill('NewPassword!12345')
        self.page.locator('button[value=signup]').click()
        expect(self.page.locator('#authMsg')).to_contain_text('e-mail de confirmação')
        self.assertIn('/signup?redirect_to=', self.calls[0]['url'])
        self.assertIn('confirmar.html', self.calls[0]['url'])
        expect(self.page.locator('#app')).to_be_hidden()

    def test_resend_confirmation(self):
        self.page.goto(self.site + '/index.html')
        self.page.locator('#auth [name=email]').fill('pending@example.invalid')
        self.page.locator('#resendConfirmation').click()
        expect(self.page.locator('#authMsg')).to_contain_text('Se houver uma confirmação pendente')
        self.assertEqual(self.calls[-1]['body'], {'type':'signup','email':'pending@example.invalid'})
        self.assertIn('redirect_to=', self.calls[-1]['url'])

    def test_email_not_confirmed_translated(self):
        self.code = 400; self.response = {'error_code':'email_not_confirmed'}
        self.page.goto(self.site + '/index.html')
        self.page.locator('#auth [name=email]').fill('pending@example.invalid')
        self.page.locator('#auth [name=password]').fill('old123')
        self.page.locator('button[value=login]').click()
        expect(self.page.locator('#authMsg')).to_contain_text('Confirme seu e-mail')

    def test_default_site_url_callback_routes_to_recovery(self):
        self.page.goto(self.site + '/index.html#type=recovery&access_token=aaa.bbb.ccc&expires_in=3600')
        expect(self.page.locator('#resetView')).to_be_visible()
        self.assertTrue(self.page.url.endswith('/recuperar.html'))

    def test_no_secret_in_shared_config(self):
        text = (ROOT/'auth-config.js').read_text()
        self.assertNotIn('sb_secret_', text)
        self.assertIn('sb_publishable_', text)
