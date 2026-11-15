"""Testes isolados: nenhum acesso ao Supabase ou a dados reais.

Executar: python3 -m unittest discover -s tests -v
Requer Playwright Python e Chromium (disponíveis no ambiente de desenvolvimento).
"""
import functools
import http.server
import json
import os
import pathlib
import threading
import unittest

from playwright.sync_api import sync_playwright, expect

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
        cls.browser = cls.pw.chromium.launch(
            executable_path=os.environ.get('NEXO_CHROMIUM_EXECUTABLE') or None, headless=True)

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
        self.details_error = False
        self.records = []
        self.page.expose_function('recordCall', lambda call: self.records.append(call))
        self.redirect = CALLBACK + '?code=test-code&state=test-state'
        self.calls = []
        self.destinations = []

        def sdk(route):
            payload = dict(details=self.details, loginError=self.login_error,
                           decisionError=self.decision_error, redirect=self.redirect, detailsError=self.details_error)
            route.fulfill(content_type='text/javascript', body='''
const fixture = %s;
export function createClient(project, key, options) {
  window.sdkOptions = options;
  const decide = async (name, id, options) => {
    await window.recordCall({name, id, options});
    return fixture.decisionError ? {error: {message:'failure'}} : {data: {redirect_url:fixture.redirect}};
  };
  return {auth: {
    signInWithPassword: async (credentials) => {
      await window.recordCall({name:'login', credentials});
      return fixture.loginError ? {error:{message:'failure'}} : {data:{user:{id:'test-user',email:'test@example.invalid'}}};
    },
    oauth: {
      getAuthorizationDetails: async (id) => {
        await window.recordCall({name:'details', id});
        return fixture.detailsError ? {error:{message:'expired'}} : {data:fixture.details};
      },
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
        self.page.wait_for_function("!document.getElementById('login') || document.getElementById('login').hidden || !document.querySelector('#login button').disabled")

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
        self.assertEqual(self.records, [
            dict(name='login', credentials=dict(email='test@example.invalid', password='test-password')),
            dict(name='details', id=REQUEST),
            dict(name='approve', id=REQUEST, options=dict(skipBrowserRedirect=True))])

    def test_deny(self):
        self.redirect = CALLBACK + '?error=access_denied&state=test-state'
        self.login()
        self.page.locator('#deny').click()
        self.page.wait_for_url(CALLBACK + '**')
        self.assertEqual(self.destinations, [self.redirect])
        self.assertEqual(self.records[-1], dict(name='deny', id=REQUEST, options=dict(skipBrowserRedirect=True)))

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
        expect(self.page.locator('#status')).to_contain_text('Destino não autorizado')
        self.assertEqual(self.destinations, [])

    def test_decision_failure(self):
        self.decision_error = True
        self.login()
        self.page.locator('#approve').click()
        expect(self.page.locator('#status')).to_contain_text('Não foi possível concluir')
        expect(self.page.locator('#approve')).to_be_enabled()
        self.assertEqual(self.destinations, [])

    def test_previously_consented(self):
        self.details = dict(redirect_url=self.redirect)
        self.login()
        self.page.wait_for_url(CALLBACK + '**')
        self.assertEqual(self.destinations, [self.redirect])

    def test_expired_request(self):
        self.details_error = True
        self.login()
        expect(self.page.locator('#status')).to_contain_text('expirada')
        self.assertTrue(self.page.locator('#consent').is_hidden())
        self.assertEqual([c['name'] for c in self.records], ['login', 'details'])

    def test_missing_details(self):
        self.details = None
        self.login()
        expect(self.page.locator('#status')).to_contain_text('expirada')
        self.assertTrue(self.page.locator('#consent').is_hidden())

    def test_untrusted_previously_consented_redirect(self):
        self.details = dict(redirect_url='https://example.invalid/?code=test')
        self.login()
        expect(self.page.locator('#status')).to_contain_text('Destino não autorizado')
        self.assertEqual(self.destinations, [])

    def test_untrusted_names_are_plain_text(self):
        self.details['client']['name'] = '<img src=x onerror="window.injected=true">'
        self.login()
        self.assertEqual(self.page.locator('#client').inner_text(), self.details['client']['name'])
        self.assertEqual(self.page.locator('#client img').count(), 0)
        self.assertFalse(self.page.evaluate('Boolean(window.injected)'))

    def assert_load_failure(self):
        self.open()
        expect(self.page.locator('#status')).to_contain_text('Não foi possível carregar')
        self.assertTrue(self.page.locator('#login').is_hidden())
        self.assertTrue(self.page.locator('#consent').is_hidden())
        self.assertEqual(self.records, [])

    def test_config_network_failure(self):
        self.context.route('**/oauth-config.js', lambda r: r.abort())
        self.assert_load_failure()

    def test_policy_404(self):
        self.context.route('**/oauth-policy.js', lambda r: r.fulfill(status=404, body='Not found'))
        self.assert_load_failure()

    def test_invalid_module(self):
        self.context.route('**/oauth-policy.js', lambda r: r.fulfill(
            content_type='text/javascript', body='invalid syntax !'))
        self.assert_load_failure()

    def test_sdk_network_failure(self):
        self.context.route('https://cdn.jsdelivr.net/**', lambda r: r.abort())
        self.assert_load_failure()

    def test_module_timeout(self):
        self.page.clock.install()
        self.context.route('**/oauth-policy.js', lambda r: r.fulfill(
            content_type='text/javascript', body='await new Promise(() => {});'))
        self.page.goto(self.base + '/oauth-consent.html?authorization_id=' + REQUEST)
        self.page.clock.fast_forward(16000)
        expect(self.page.locator('#status')).to_contain_text('Não foi possível carregar')
        self.assertTrue(self.page.locator('#login').is_hidden())
        self.assertEqual(self.records, [])

    def test_no_browser_session_storage(self):
        self.login()
        self.assertEqual(self.page.evaluate('Object.keys(localStorage)'), [])
        self.assertEqual(self.page.evaluate('Object.keys(sessionStorage)'), [])

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

    def test_second_registered_client_is_allowed(self):
        second='11111111-1111-4111-8111-111111111111'
        callback='https://chatgpt.com/connector/oauth/second-test'
        self.details['client']['id']=second
        self.details['redirect_uri']=callback
        config='export const TRUSTED_CLIENTS='+json.dumps([{'clientId':CLIENT,'callback':CALLBACK},{'clientId':second,'callback':callback}])+';'
        self.page.route('**/oauth-config.js',lambda r:r.fulfill(content_type='text/javascript',body=config))
        self.open()
        self.login()
        expect(self.page.locator('#consent')).to_be_visible()

    def test_second_client_cannot_use_first_callback(self):
        second='11111111-1111-4111-8111-111111111111'
        self.details['client']['id']=second
        config='export const TRUSTED_CLIENTS='+json.dumps([{'clientId':CLIENT,'callback':CALLBACK},{'clientId':second,'callback':'https://chatgpt.com/connector/oauth/second-test'}])+';'
        self.page.route('**/oauth-config.js',lambda r:r.fulfill(content_type='text/javascript',body=config))
        self.open()
        self.login()
        expect(self.page.locator('#consent')).to_be_hidden()
        expect(self.page.locator('#status')).to_contain_text('não autorizado')


if __name__ == '__main__':
    unittest.main()
