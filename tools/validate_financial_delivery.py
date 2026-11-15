"""Ensaios essenciais com dados fictícios, chamados pela validação OAuth local."""
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
import uuid
from zoneinfo import ZoneInfo

from playwright.sync_api import expect
from tools.check_mcp_test import NoRedirect, request
from tools.setup_local_test import api

CALLBACK = 'https://example.invalid/nexo-test/callback'


def verify(browser, site, private, oauth_token, client_id):
    origin, key = private['api_url'], private['anon_key']
    assert origin == 'http://127.0.0.1:54321'
    session = api(origin, key, '/auth/v1/token?grant_type=password', {
        'email': private['email'], 'password': private['password']})
    owner = session['user']['id']
    owner_headers = {'apikey': key, 'Authorization': 'Bearer ' + session['access_token'],
                     'Prefer': 'return=representation'}
    mcp_headers = {'Authorization': 'Bearer ' + oauth_token}
    today = datetime.now(ZoneInfo('America/Sao_Paulo')).date().isoformat()

    def rpc(args, headers=mcp_headers):
        status, _, response = request(origin + '/functions/v1/nexo-mcp-test', {
            'jsonrpc': '2.0', 'id': 100, 'method': 'tools/call',
            'params': {'name': 'registrar_lancamento', 'arguments': args}}, headers)
        assert status == 200 and 'result' in response
        return response['result']

    def rows(headers, identifier):
        status, _, result = request(origin + '/rest/v1/nexo_data?select=user_id,data,updated_at&user_id=eq.' + identifier,
                                    headers=headers)
        assert status == 200 and isinstance(result, list)
        return result

    def entry(kind, cents, description):
        return {'id': str(uuid.uuid5(uuid.NAMESPACE_URL, owner + today + description)),
                'tipo': kind, 'valor_centavos': cents, 'categoria': 'Homologação',
                'descricao': description, 'data': today}

    def route_local(route):
        if route.request.url.startswith(site + '/') or route.request.url.startswith(origin + '/'):
            route.continue_()
        else:
            route.abort()

    contexts, second_id = [], None
    try:
        desktop = browser.new_context(viewport={'width': 1280, 'height': 800})
        contexts.append(desktop)
        desktop.route('**/*', route_local)
        page = desktop.new_page()
        page.goto(site + '/index.html')
        page.locator('#auth [name=email]').fill(private['email'])
        page.locator('#auth [name=password]').fill(private['password'])
        page.locator('#auth button[value=login]').click()
        expect(page.locator('#app')).to_be_visible()
        page.locator('#nav [data-go=Financeiro]').click()

        before = rows(owner_headers, owner)
        income = entry('receita', 15000, 'Receita fictícia via ChatGPT ' + today)
        expense = entry('despesa', 3250, 'Despesa fictícia equivalente a ditado ' + today)
        for args in [income, expense]:
            saved = rpc(args)
            assert not saved.get('isError'), 'Gravação MCP não confirmada'
            actual = saved['structuredContent']['lancamento']
            assert round(actual['amount'] * 100) == args['valor_centavos']
            assert actual['type'] == ('income' if args['tipo'] == 'receita' else 'expense')
        # A tela deve refletir as gravações externas, sem recarregamento manual.
        for description, amount in [(income['descricao'], '150,00'), (expense['descricao'], '32,50')]:
            line = page.locator('.dataList .line').filter(has_text=description)
            expect(line).to_be_visible(timeout=22000)
            expect(line).to_contain_text(amount)
        after = rows(owner_headers, owner)[0]
        ids = [e.get('id') for e in after['data']['entries']]
        assert ids.count(income['id']) == 1 and ids.count(expense['id']) == 1
        if before:
            for old in before[0]['data'].get('entries', []):
                assert old in after['data']['entries']
            for field, value in before[0]['data'].items():
                if field not in ('entries', 'categories'):
                    assert after['data'].get(field) == value
        repeated = rpc(expense)
        assert repeated['structuredContent']['repetido'] is True
        assert len(rows(owner_headers, owner)[0]['data']['entries']) == len(after['data']['entries'])
        assert rpc({**expense, 'valor_centavos': 1}).get('isError')
        assert rpc({**expense, 'id': str(uuid.uuid4()), 'valor_centavos': -1}).get('isError')
        assert rpc({**expense, 'user_id': str(uuid.uuid4())}).get('isError')

        # Duas conversas concorrentes não podem perder lançamentos entre si.
        concurrent = [entry('receita', 100, 'Concorrência fictícia A'),
                      entry('despesa', 100, 'Concorrência fictícia B')]
        for args in concurrent:
            args['id'] = str(uuid.uuid4())
        stale = rows(owner_headers, owner)[0]
        with ThreadPoolExecutor(max_workers=2) as executor:
            assert all(not result.get('isError') for result in executor.map(rpc, concurrent))
        current = rows(owner_headers, owner)[0]
        assert all(any(e.get('id') == args['id'] for e in current['data']['entries']) for args in concurrent)
        # O PATCH antigo do aplicativo deve falhar no CAS, preservando o MCP.
        patch = urllib.request.Request(origin + '/rest/v1/nexo_data?user_id=eq.' + owner +
            '&updated_at=eq.' + urllib.parse.quote(stale['updated_at'], safe=''),
            method='PATCH', data=json.dumps({'data': stale['data']}).encode(),
            headers={**owner_headers, 'Content-Type': 'application/json'})
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(patch) as response:
            assert json.load(response) == []
        assert rows(owner_headers, owner)[0]['data'] == current['data']
        print('PASS: receitas/despesas MCP aparecem no NEXO; centavos, idempotência, preservação e concorrência conferidos.')

        mobile = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
        contexts.append(mobile)
        mobile.route('**/*', route_local)
        second = mobile.new_page()
        email, password = 'nexo-homolog-' + secrets.token_hex(8) + '@example.com', secrets.token_urlsafe(24)
        second.goto(site + '/index.html')
        second.locator('#auth [name=email]').fill(email)
        second.locator('#auth [name=password]').fill(password)
        second.locator('#auth button[value=signup]').click()
        expect(second.locator('#app')).to_be_visible(timeout=15000)
        second_session = api(origin, key, '/auth/v1/token?grant_type=password', {'email': email, 'password': password})
        second_id = second_session['user']['id']
        other_headers = {'apikey': key, 'Authorization': 'Bearer ' + second_session['access_token'],
                         'Prefer': 'return=representation'}
        assert rows(other_headers, owner) == []
        # O default {} da tabela existente também deve permitir entrar no app.
        status, _, _ = request(origin + '/rest/v1/nexo_data', {'user_id': second_id}, other_headers)
        assert status == 201
        second.reload()
        second.locator('#auth [name=email]').fill(email)
        second.locator('#auth [name=password]').fill(password)
        second.locator('#auth button[value=login]').click()
        expect(second.locator('#app')).to_be_visible()
        second.locator('#nav [data-go=Financeiro]').click()
        expect(second.locator('#view')).not_to_contain_text(income['descricao'])

        # O segundo usuário obtém seu próprio grant OAuth, jamais um token forjado.
        verifier, state = secrets.token_urlsafe(48), secrets.token_urlsafe(24)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        params = dict(client_id=client_id, redirect_uri=CALLBACK, response_type='code', scope='openid',
                      state=state, code_challenge=challenge, code_challenge_method='S256')
        req = urllib.request.Request(origin + '/auth/v1/oauth/authorize?' + urllib.parse.urlencode(params), headers={'apikey': key})
        try:
            response = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(req)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            assert response.status in (302, 303, 307)
            authorization_id = urllib.parse.parse_qs(urllib.parse.urlsplit(response.headers['Location']).query)['authorization_id'][0]
        path = origin + '/auth/v1/oauth/authorizations/' + authorization_id
        status, _, details = request(path, headers=other_headers)
        assert status == 200 and details['user']['id'] == second_id
        status, _, granted = request(path + '/consent', {'action': 'approve'}, other_headers)
        assert status == 200 and granted['redirect_url'].startswith(CALLBACK + '?')
        returned = urllib.parse.parse_qs(urllib.parse.urlsplit(granted['redirect_url']).query)
        assert returned['state'] == [state]
        second_oauth = api(origin, key, '/auth/v1/oauth/token', {'grant_type': 'authorization_code',
            'code': returned['code'][0], 'client_id': client_id, 'redirect_uri': CALLBACK, 'code_verifier': verifier})
        own = {**expense, 'descricao': 'Despesa exclusiva da segunda conta'}
        own.pop('data')  # Confere o padrão de hoje em São Paulo.
        saved = rpc(own, {'Authorization': 'Bearer ' + second_oauth['access_token']})
        assert not saved.get('isError') and saved['structuredContent']['lancamento']['date'] == today
        other_row = rows(other_headers, second_id)[0]
        assert len(other_row['data']['entries']) == 1
        assert rows(owner_headers, second_id) == []
        assert rows(owner_headers, owner)[0]['data'] == current['data']
        second.bring_to_front()
        expect(second.locator('.dataList')).to_contain_text(own['descricao'], timeout=22000)

        # RLS também precisa impedir gravação direta na conta de outra pessoa.
        for method in ['PATCH', 'DELETE']:
            body = json.dumps({'data': {}}).encode() if method == 'PATCH' else None
            req = urllib.request.Request(origin + '/rest/v1/nexo_data?user_id=eq.' + owner,
                method=method, data=body, headers={**other_headers, 'Content-Type': 'application/json'})
            with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(req) as response:
                assert json.load(response) == []
        req = urllib.request.Request(origin + '/rest/v1/nexo_data', method='POST',
            data=json.dumps({'user_id': owner, 'data': {}}).encode(),
            headers={**other_headers, 'Content-Type': 'application/json'})
        try:
            urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(req)
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
        else:
            raise AssertionError('RLS permitiu inserir em outra conta')
        status, _, anonymous = request(origin + '/rest/v1/nexo_data?select=data', headers={'apikey': key})
        assert status in (401, 403) or (status == 200 and anonymous == [])
        assert rows(owner_headers, owner)[0]['data'] == current['data']
        page.bring_to_front()
        held = []
        def hold_refresh(route):
            held.append((route, route.fetch(max_redirects=0)))
        page.route('**/auth/v1/token?grant_type=refresh_token', hold_refresh)
        page.evaluate('session.expires_at=0; void syncExternal()')
        for _ in range(100):
            if held:
                break
            page.wait_for_timeout(50)
        assert held, 'Não foi exercitada a renovação de sessão'
        page.locator('#logout').click()
        expect(page.locator('#gate')).to_be_visible()
        page.locator('#auth [name=email]').fill(email)
        page.locator('#auth [name=password]').fill(password)
        page.locator('#auth button[value=login]').click()
        expect(page.locator('#app')).to_be_visible()
        page.locator('#nav [data-go=Financeiro]').click()
        expect(page.locator('#view')).not_to_contain_text(income['descricao'])
        expect(page.locator('.dataList')).to_contain_text(own['descricao'])
        for route, response in held:
            route.fulfill(response=response)
        page.unroute('**/auth/v1/token?grant_type=refresh_token', hold_refresh)
        page.evaluate('syncExternal()')
        expect(page.locator('.dataList')).to_contain_text(own['descricao'])
        expect(page.locator('#view')).not_to_contain_text(income['descricao'])
        print('PASS: cadastro no celular, OAuth de duas contas e RLS de leitura/escrita isolados por usuário.')
    finally:
        for context in contexts:
            context.close()
        if second_id:
            req = urllib.request.Request(origin + '/auth/v1/admin/users/' + second_id, method='DELETE', headers={
                'apikey': private['service_role_key'], 'Authorization': 'Bearer ' + private['service_role_key']})
            with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(req):
                pass
