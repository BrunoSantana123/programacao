from unittest import TestCase
from unittest.mock import patch

from tools.setup_local_test import ROOT, api, setup


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

    def test_admin_api_refuses_remote_target(self):
        with patch('urllib.request.build_opener') as opener:
            with self.assertRaises(RuntimeError):
                api('https://tznebgdgdqpbhjdrhprb.supabase.co', 'dummy-test-key',
                    '/auth/v1/admin/users', {'email': 'test@example.invalid'})
            opener.assert_not_called()
