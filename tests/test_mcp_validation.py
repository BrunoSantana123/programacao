import os
import unittest
from unittest.mock import patch

from tools.check_mcp_test import CheckFailed, check, validate_target

REF = 'abcdefghijklmnopqrst'
ORIGIN = 'https://' + REF + '.supabase.co'
URL = ORIGIN + '/functions/v1/nexo-mcp-test'
ISSUER = ORIGIN + '/auth/v1'


def discovery():
    return [
        (401, {'WWW-Authenticate': 'Bearer resource_metadata="' + URL + '/.well-known/oauth-protected-resource"'}, None),
        (200, {}, dict(resource=URL, authorization_servers=[ISSUER])),
        (200, {}, dict(issuer=ISSUER, authorization_endpoint=ISSUER + '/oauth/authorize',
                       token_endpoint=ISSUER + '/oauth/token', code_challenge_methods_supported=['S256']))]


class MCPValidationTests(unittest.TestCase):
    def test_production_blocked_before_network(self):
        with patch('tools.check_mcp_test.request') as request:
            with self.assertRaises(CheckFailed):
                check('https://tznebgdgdqpbhjdrhprb.supabase.co/functions/v1/nexo-mcp-test',
                      'tznebgdgdqpbhjdrhprb')
            request.assert_not_called()

    def test_unsafe_targets_rejected(self):
        for url in ['http://' + REF + '.supabase.co/functions/v1/test', URL + '?token=x',
                    URL.replace(REF + '.supabase.co', 'evil.invalid'), URL + '#x']:
            with self.subTest(url=url), self.assertRaises(CheckFailed):
                validate_target(url, REF)

    def test_discovery_without_credentials(self):
        with patch('tools.check_mcp_test.request', side_effect=discovery()) as request:
            self.assertEqual(check(URL, REF), dict(discovery='passed', authenticated='not_run'))
            self.assertEqual(request.call_count, 3)

    def test_missing_challenge(self):
        with patch('tools.check_mcp_test.request', return_value=(401, {}, None)):
            with self.assertRaises(CheckFailed):
                check(URL, REF)

    def test_external_metadata_rejected(self):
        with patch('tools.check_mcp_test.request', return_value=(401, {
                'WWW-Authenticate': 'Bearer resource_metadata="https://evil.invalid"'}, None)) as request:
            with self.assertRaises(CheckFailed):
                check(URL, REF)
            self.assertEqual(request.call_count, 1)

    def test_missing_credentials(self):
        with patch.dict(os.environ, {}, clear=True), patch('tools.check_mcp_test.request', side_effect=discovery()):
            with self.assertRaises(CheckFailed):
                check(URL, REF, True)

    def test_wrong_user_blocks_mcp(self):
        with patch.dict(os.environ, NEXO_TEST_OAUTH_ACCESS_TOKEN='test-only', NEXO_TEST_USER_ID='test-user'), \
                patch('tools.check_mcp_test.request', side_effect=discovery() + [(200, {}, {'sub': 'other-user'})]) as request:
            with self.assertRaises(CheckFailed):
                check(URL, REF, True)
            self.assertEqual(request.call_count, 4)

    def authenticated_responses(self, tools):
        return discovery() + [
            (200, {}, {'sub': 'test-user'}),
            (200, {'Mcp-Session-Id': 'test-session'}, dict(id=2, result={
                'protocolVersion': '2025-03-26', 'capabilities': {'tools': {}}})),
            (202, {}, None), (200, {}, dict(id=3, result={'tools': tools}))]

    def test_authenticated_discovery_never_calls_tools(self):
        with patch.dict(os.environ, NEXO_TEST_OAUTH_ACCESS_TOKEN='test-only', NEXO_TEST_USER_ID='test-user'), \
                patch('tools.check_mcp_test.request', side_effect=self.authenticated_responses([
                    {'name': 'example', 'inputSchema': {'type': 'object'}}])) as request:
            self.assertEqual(check(URL, REF, True)['tool_count'], 1)
            bodies = [c.args[1] for c in request.call_args_list if len(c.args) > 1]
            self.assertEqual([b['method'] for b in bodies], [
                'initialize', 'initialize', 'notifications/initialized', 'tools/list'])
            self.assertEqual(request.call_args_list[-1].args[2]['Mcp-Session-Id'], 'test-session')

    def test_empty_tools_not_success(self):
        with patch.dict(os.environ, NEXO_TEST_OAUTH_ACCESS_TOKEN='test-only', NEXO_TEST_USER_ID='test-user'), \
                patch('tools.check_mcp_test.request', side_effect=self.authenticated_responses([])):
            with self.assertRaises(CheckFailed):
                check(URL, REF, True)
