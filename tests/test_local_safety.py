from unittest import TestCase
from unittest.mock import patch

from tools.setup_local_test import ROOT, api, setup
from tools.validate_local_oauth import validate_environment
import json
from pathlib import Path
import tempfile
import hashlib


class LocalSafetyTests(TestCase):
    def test_setup_refuses_checkout(self):
        with patch('tools.setup_local_test.install') as install:
            with self.assertRaises(RuntimeError):
                setup(ROOT)
            install.assert_not_called()

    def test_setup_refuses_checkout_subdirectory(self):
        with patch('tools.setup_local_test.install') as install:
            with self.assertRaises(RuntimeError):
                setup(ROOT / 'would-contain-secrets')
            install.assert_not_called()

    def test_setup_refuses_system_roots_and_checkout_parents(self):
        for directory in [Path('/tmp'), Path('/'), ROOT.parent]:
            with self.subTest(directory=str(directory)), patch('tools.setup_local_test.install') as install:
                with self.assertRaises(RuntimeError):
                    setup(directory)
                install.assert_not_called()

    def test_live_validation_rejects_remote_environment_before_startup(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'private.json').write_text(json.dumps({'api_url': 'https://example.invalid'}))
            with self.assertRaises(RuntimeError):
                validate_environment(directory)

    def test_live_validation_rejects_changed_function(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'private.json').write_text(json.dumps({'api_url': 'http://127.0.0.1:54321'}))
            function = directory / 'supabase/functions/nexo-mcp-test/index.ts'
            function.parent.mkdir(parents=True)
            function.write_text('unreviewed source')
            with self.assertRaises(RuntimeError):
                validate_environment(directory)

    def test_live_validation_rejects_modified_private_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            original = b'NEXO_TEST_MODE=local\n'
            (directory / 'private.json').write_text(json.dumps({
                'api_url': 'http://127.0.0.1:54321',
                'network_env_sha256': hashlib.sha256(original).hexdigest()}))
            function = directory / 'supabase/functions/nexo-mcp-test/index.ts'
            function.parent.mkdir(parents=True)
            function.write_bytes((ROOT / 'supabase/functions/nexo-mcp-test/index.ts').read_bytes())
            (directory / 'local-functions.env').write_bytes(original + b'UNREVIEWED_SETTING=yes\n')
            with self.assertRaises(RuntimeError):
                validate_environment(directory)

    def test_admin_api_refuses_remote_target(self):
        with patch('urllib.request.build_opener') as opener:
            with self.assertRaises(RuntimeError):
                api('https://tznebgdgdqpbhjdrhprb.supabase.co', 'dummy-test-key',
                    '/auth/v1/admin/users', {'email': 'test@example.invalid'})
            opener.assert_not_called()
