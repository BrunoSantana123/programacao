import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from tools.validate_local_oauth import EDGE_IMAGE, browser_options, runtime_command


class RuntimeLaunchTests(TestCase):
    def prepare_files(self, directory):
        (directory / 'supabase').mkdir()
        (directory / 'supabase/config.toml').write_text('project_id = "nexo-test-environment"\n')
        (directory / 'local-functions.env').write_text(
            'NEXO_TEST_MODE=local\nHTTPS_PROXY="http://container-proxy.invalid:8080"\n')

    def test_gateway_contract_and_no_secret_values_in_arguments(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.prepare_files(directory)
            result = SimpleNamespace(stdout=json.dumps([{'Containers': {}}]))
            with patch('tools.validate_local_oauth.subprocess.run', return_value=result), \
                    patch.dict(os.environ, {'GH_TOKEN': 'host-only-secret'}, clear=True):
                command, environment, name = runtime_command(directory)
            self.assertIn(EDGE_IMAGE, command)
            self.assertIn('--port=8081', command)
            self.assertIn('supabase_edge_runtime_nexo-test-environment', command)
            self.assertTrue(any(arg.startswith('--main-service=') for arg in command))
            self.assertTrue(any(arg.endswith(',readonly') for arg in command))
            self.assertNotIn('--privileged', command)
            self.assertNotIn('--publish', command)
            self.assertNotIn('GH_TOKEN', command)
            self.assertNotIn('host-only-secret', ' '.join(command))
            self.assertNotIn('container-proxy.invalid', ' '.join(command))
            self.assertEqual(environment['NEXO_TEST_MODE'], 'local')
            self.assertTrue(name.startswith('nexo-mcp-runtime-'))

    def test_existing_runtime_is_never_stopped(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.prepare_files(directory)
            results = [SimpleNamespace(stdout=json.dumps([{'Containers': {'other': {}}}])),
                       SimpleNamespace(stdout=json.dumps({'supabase_network_nexo-test-environment': {
                           'Aliases': ['edge_runtime']}}))]
            with patch('tools.validate_local_oauth.subprocess.run', side_effect=results) as run:
                with self.assertRaises(RuntimeError):
                    runtime_command(directory)
                self.assertFalse(any('rm' in call.args[0] or 'stop' in call.args[0] for call in run.call_args_list))

    def test_browser_reuses_proxy_without_disabling_certificate_checks(self):
        with patch.dict(os.environ, {'HTTPS_PROXY': 'http://proxy-test.invalid:8080',
                                     'NO_PROXY': 'preserved.internal'}, clear=True):
            options = browser_options()
        self.assertEqual(options['proxy']['server'], 'http://proxy-test.invalid:8080')
        self.assertIn('preserved.internal', options['proxy']['bypass'])
        self.assertIn('127.0.0.1', options['proxy']['bypass'])
        self.assertFalse(options.get('ignore_https_errors', False))
        self.assertFalse(any('ignore-certificate' in value for value in options.get('args', [])))
