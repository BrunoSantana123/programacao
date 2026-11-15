"""Testes isolados: nenhum acesso ao Supabase ou a dados reais.

Executar: python3 -m unittest discover -s tests -v
Requer Playwright Python e Chromium (disponíveis no ambiente de desenvolvimento).
"""
import functools
import http.server
import json
import pathlib
import threading
import unittest

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLIENT = '451c10f2-5062-45a7-b4df-94664ecf212c'
CALLBACK = 'https://chatgpt.com/connector/oauth/jtfRMxXsq31B'
REQUEST = 'test-authorization'


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class OAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(
            ('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(ROOT)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path='/usr/bin/chromium', headless=True,
                                           args=['--no-sandbox'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda e: self.errors.append(str(e)))
        self.details = dict(authorization_id=REQUEST, redirect_uri=CALLBACK,
                            client=dict(id=CLIENT, name='NEXO Test'),
                            user=dict(id='test-user'), scope='openid')
        self.login_error = False
        self.decision_error = False
        self.redirect = CALLBACK + '?code=test-code&state=test-state'
        self.calls = []
        self.destinations = []

        def sdk(route):
            payload = dict(details=self.details, loginError=self.login_error,
                           decisionError=self.decision_error, redirect=self.redirect)
            route.fulfill(content_type='text/javascript', body='''
const fixture = %s;
export function createClient(project, key, options) {
  window.sdkOptions = options;
  const decide = async (name, id, options) => {
    window.decisions = [...(window.decisions || []), {name, id, options}];
    return fixture.decisionError ? {error: {message:'failure'}} : {data: {redirect_url:fixture.redirect}};
  };
  return {auth: {
    signInWithPassword: async () => fixture.loginError ? {error:{message:'failure'}} : {data:{user:{id:'test-user',email:'test@example.invalid'}}},
    oauth: {
      getAuthorizationDetails: async () => ({data:fixture.details}),
      approveAuthorization: (id, options) => decide('approve', id, options),
      denyAuthorization: (id, options) => decide('deny', id, options)
    }
  }};
}
''' % json.dumps(payload))

        def route_all(route):
            url = route.request.url
            if url.startswith(self.base + '/'):
                route.continue_()
            elif url.startswith('https://cdn.jsdelivr.net/npm/@supabase/supabase-js@'):
                self.calls.append('sdk')
                sdk(route)
            elif url.startswith(CALLBACK):
                self.destinations.append(url)
                route.fulfill(content_type='text/html', body='Test callback')
            else:
                route.abort()

        self.context.route('**/*', route_all)

    def tearDown(self):
        self.assertEqual(self.errors, [])
        self.context.close()

    def open(self, query='?authorization_id=' + REQUEST):
        self.page.goto(self.base + '/oauth-consent.html' + query)
        self.page.wait_for_function("!document.getElementById('status').textContent.includes('Verificando')")

    def login(self):
        self.open()
        self.page.locator('[name=email]').fill('test@example.invalid')
        self.page.locator('[name=password]').fill('test-password')
        self.page.locator('#login button').click()

    def test_missing_request(self):
        self.open('')
        self.assertTrue(self.page.locator('#login').is_hidden())
        self.assertEqual(self.calls, [])

    def test_invalid_request(self):
        self.open('?authorization_id=%3Cscript%3E')
        self.assertIn('inválida', self.page.locator('#status').inner_text())
        self.assertEqual(self.calls, [])

    def test_unconfigured_client_fails_closed(self):
        self.context.route('**/oauth-config.js', lambda r: r.fulfill(
            content_type='text/javascript', body="export const TRUSTED_CLIENT_ID=''; export const TRUSTED_CALLBACK='';"))
        self.open()
        self.assertTrue(self.page.locator('#login').is_hidden())
        self.assertEqual(self.calls, [])

    def test_login_failure(self):
        self.login_error = True
        self.login()
        self.assertTrue(self.page.locator('#consent').is_hidden())
        self.assertEqual(self.page.locator('[name=password]').input_value(), '')

    def test_approve(self):
        self.login()
        self.assertTrue(self.page.locator('#consent').is_visible())
        self.assertEqual(self.page.locator('#client').inner_text(), 'NEXO Test')
        self.assertEqual(self.page.evaluate('sdkOptions.auth'), dict(
            persistSession=False, autoRefreshToken=False, detectSessionInUrl=False))
        self.page.locator('#approve').click()
        self.page.wait_for_url(CALLBACK + '**')
        self.assertEqual(self.destinations, [self.redirect])

    def test_deny(self):
        self.redirect = CALLBACK + '?error=access_denied&state=test-state'
        self.login()
        self.page.locator('#deny').click()
        self.page.wait_for_url(CALLBACK + '**')
        self.assertEqual(self.destinations, [self.redirect])

    def test_client_mismatch(self):
        self.details['client']['id'] = 'another-client'
        self.login()
        self.assertTrue(self.page.locator('#consent').is_hidden())

    def test_user_mismatch(self):
        self.details['user']['id'] = 'another-user'
        self.login()
        self.assertTrue(self.page.locator('#consent').is_hidden())

    def test_request_mismatch(self):
        self.details['authorization_id'] = 'another-request'
        self.login()
        self.assertTrue(self.page.locator('#consent').is_hidden())

    def test_registered_redirect_mismatch(self):
        self.details['redirect_uri'] = CALLBACK + '?unexpected=1'
        self.login()
        self.assertTrue(self.page.locator('#consent').is_hidden())

    def test_decision_redirect_rejected(self):
        self.redirect = 'https://example.invalid/callback?code=test'
        self.login()
        self.page.locator('#approve').click()
        self.assertIn('Destino não autorizado', self.page.locator('#status').inner_text())
        self.assertEqual(self.destinations, [])

    def test_decision_failure(self):
        self.decision_error = True
        self.login()
        self.page.locator('#approve').click()
        self.assertTrue(self.page.locator('#approve').is_enabled())
        self.assertEqual(self.destinations, [])

    def test_previously_consented(self):
        self.details = dict(redirect_url=self.redirect)
        self.login()
        self.page.wait_for_url(CALLBACK + '**')
        self.assertEqual(self.destinations, [self.redirect])

    def test_callback_policy(self):
        self.page.goto(self.base + '/oauth-consent.html')
        results = self.page.evaluate('''async ({callback}) => {
          const {sameCallback, validCallback} = await import('./oauth-policy.js');
          return [
            sameCallback(callback, callback),
            sameCallback(callback+'?code=ok&state=s', callback, true),
            sameCallback(callback+'?error=access_denied&state=s', callback, true),
            ...[
              callback+'?unexpected=1&code=x', callback+'?code=a&code=b',
              callback+'?code=a&error=bad', callback+'#fragment',
              callback+'/?code=a', callback.replace('https:', 'http:')+'?code=a',
              callback.replace('chatgpt.com','chatgpt.com.evil.invalid')+'?code=a',
              callback.replace('https://','https://user@')+'?code=a', callback
            ].map(url => !sameCallback(url, callback, true)),
            !sameCallback(callback+'?tenant=wrong&code=a', callback+'?tenant=right', true),
            sameCallback(callback+'?tenant=right&code=a', callback+'?tenant=right', true),
            !validCallback('javascript:alert(1)')
          ];
        }''', dict(callback=CALLBACK))
        self.assertTrue(all(results), results)


if __name__ == '__main__':
    unittest.main()
