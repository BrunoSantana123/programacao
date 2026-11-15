"""Validação MCP de leitura. Nunca chama tools/call ou acessa tabelas financeiras.

Uso: python tools/check_mcp_test.py --url URL --test-project-ref REF [--authenticated]
O modo autenticado exige um token OAuth da conta exclusiva de testes em variável
segura; não aceita tokens pela linha de comando e não imprime respostas remotas.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

PROTECTED_PROJECT = 'tznebgdgdqpbhjdrhprb'


class CheckFailed(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def validate_target(url, project_ref):
    parsed = urllib.parse.urlsplit(url)
    if (not re.fullmatch(r'[a-z]{20}', project_ref) or project_ref == PROTECTED_PROJECT
            or parsed.scheme != 'https' or parsed.netloc != project_ref + '.supabase.co'
            or parsed.query or parsed.fragment
            or not re.fullmatch(r'/functions/v1/[a-zA-Z0-9_-]+', parsed.path)):
        raise CheckFailed('Destino inválido: use somente um projeto Supabase exclusivo de testes.')
    return parsed.scheme + '://' + parsed.netloc


def request(url, body=None, headers=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={
        'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream',
        **(headers or {})})
    handlers = [NoRedirect()]
    if urllib.parse.urlsplit(url).hostname == '127.0.0.1':
        handlers.append(urllib.request.ProxyHandler({}))
    try:
        response = urllib.request.build_opener(*handlers).open(req, timeout=20)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        content_type = response.headers.get('Content-Type', '')
        try:
            if 'text/event-stream' in content_type:
                size, lines, payload = 0, [], None
                for raw_line in response:
                    size += len(raw_line)
                    if size > 2_000_000:
                        raise CheckFailed('Resposta excedeu o limite de validação.')
                    line = raw_line.decode().rstrip('\r\n')
                    if line.startswith('data:'):
                        lines.append(line[5:].lstrip())
                    elif not line and lines:
                        message = json.loads('\n'.join(lines))
                        lines = []
                        if message.get('id') == (body or {}).get('id'):
                            payload = message
                            break
            else:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise CheckFailed('Resposta excedeu o limite de validação.')
                payload = json.loads(raw) if raw else None
        except (ValueError, UnicodeError):
            raise CheckFailed('Resposta remota inválida.') from None
        return response.status, response.headers, payload


def check(url, project_ref, authenticated=False):
    origin = validate_target(url, project_ref)
    status, headers, _ = request(url, dict(jsonrpc='2.0', id=1, method='initialize', params={
        'protocolVersion': '2025-03-26', 'capabilities': {},
        'clientInfo': {'name': 'nexo-isolated-test', 'version': '1.0'}}))
    if status != 401:
        raise CheckFailed('MCP deve exigir autenticação antes da inicialização.')
    challenge = headers.get('WWW-Authenticate', '')
    match = re.search(r'resource_metadata="([^"]+)"', challenge)
    if not challenge.lower().startswith('bearer ') or not match:
        raise CheckFailed('Desafio OAuth ausente ou incompleto.')
    metadata_url = match[1]
    if not metadata_url.startswith(url + '/'):
        raise CheckFailed('Metadados apontam para destino não autorizado.')
    status, _, metadata = request(metadata_url)
    issuer = origin + '/auth/v1'
    if (status != 200 or not isinstance(metadata, dict) or metadata.get('resource') != url
            or metadata.get('authorization_servers') != [issuer]):
        raise CheckFailed('Metadados do recurso incompatíveis.')
    status, _, config = request(issuer + '/.well-known/oauth-authorization-server')
    if (status != 200 or not isinstance(config, dict) or config.get('issuer') != issuer
            or config.get('authorization_endpoint') != issuer + '/oauth/authorize'
            or config.get('token_endpoint') != issuer + '/oauth/token'
            or 'S256' not in config.get('code_challenge_methods_supported', [])):
        raise CheckFailed('Descoberta OAuth ou PKCE S256 incompatível.')
    if not authenticated:
        return {'discovery': 'passed', 'authenticated': 'not_run'}

    token = os.environ.get('NEXO_TEST_OAUTH_ACCESS_TOKEN')
    expected_user = os.environ.get('NEXO_TEST_USER_ID')
    if not token or not expected_user:
        raise CheckFailed('Configure token OAuth e identificador da conta de teste em variáveis seguras.')
    auth = {'Authorization': 'Bearer ' + token}
    status, _, user = request(issuer + '/oauth/userinfo', headers=auth)
    if status != 200 or not isinstance(user, dict) or user.get('sub') != expected_user:
        raise CheckFailed('Token não corresponde à conta OAuth de teste esperada.')
    status, response_headers, init = request(url, dict(jsonrpc='2.0', id=2, method='initialize', params={
        'protocolVersion': '2025-03-26', 'capabilities': {},
        'clientInfo': {'name': 'nexo-isolated-test', 'version': '1.0'}}), auth)
    if status != 200 or not isinstance(init, dict) or init.get('id') != 2 or 'result' not in init:
        raise CheckFailed('Inicialização MCP autenticada falhou.')
    protocol = init['result'].get('protocolVersion')
    if protocol != '2025-03-26' or 'tools' not in init['result'].get('capabilities', {}):
        raise CheckFailed('Protocolo ou capacidade de ferramentas incompatível.')
    auth['MCP-Protocol-Version'] = protocol
    if response_headers.get('Mcp-Session-Id'):
        auth['Mcp-Session-Id'] = response_headers['Mcp-Session-Id']
    status, _, _ = request(url, dict(jsonrpc='2.0', method='notifications/initialized'), auth)
    if status not in (200, 202, 204):
        raise CheckFailed('Confirmação de inicialização recusada.')
    total, cursor, seen = 0, None, set()
    for index in range(20):
        body = dict(jsonrpc='2.0', id=index + 3, method='tools/list', params={})
        if cursor:
            body['params']['cursor'] = cursor
        status, _, listing = request(url, body, auth)
        if (status != 200 or not isinstance(listing, dict) or listing.get('id') != index + 3
                or not isinstance(listing.get('result', {}).get('tools'), list)):
            raise CheckFailed('Listagem MCP autenticada falhou.')
        tools = listing['result']['tools']
        if any(not isinstance(t, dict) or not t.get('name') or not isinstance(t.get('inputSchema'), dict)
               for t in tools):
            raise CheckFailed('Definição de ferramenta inválida.')
        total += len(tools)
        cursor = listing['result'].get('nextCursor')
        if not cursor:
            if not total:
                raise CheckFailed('MCP não disponibilizou ferramentas.')
            return {'discovery': 'passed', 'authenticated': 'passed', 'tool_count': total}
        if not isinstance(cursor, str) or cursor in seen:
            break
        seen.add(cursor)
    raise CheckFailed('Paginação MCP não terminou dentro do limite.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--test-project-ref', required=True)
    parser.add_argument('--authenticated', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.url, args.test_project_ref, args.authenticated)))
    except CheckFailed as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception:
        # Não incluir exceções HTTP: podem conter URLs, tokens ou dados remotos.
        print('Falha de transporte ou formato; nenhum conteúdo remoto foi registrado.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
