import hashlib
import json
import os
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import patch

from tools.container_network import prepare


class ContainerNetworkTests(TestCase):
    def test_reuses_docker_route_and_ca_without_registry_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config = directory / 'docker'
            config.mkdir()
            (config / 'config.json').write_text(json.dumps({
                'auths': {'example.invalid': {'auth': 'unused-registry-secret'}},
                'proxies': {'default': {'httpsProxy': 'http://container-proxy.invalid:8080',
                                        'noProxy': 'preserved.internal'}}}))
            certificate = directory / 'ca.pem'
            certificate.write_text('test public CA bundle')
            with patch.dict(os.environ, {'DOCKER_CONFIG': str(config), 'SSL_CERT_FILE': str(certificate),
                                         'HTTPS_PROXY': 'http://host-proxy.invalid:8080'}, clear=True):
                fingerprint = prepare(directory)
            content = (directory / 'local-functions.env').read_text()
            self.assertIn('container-proxy.invalid', content)
            self.assertNotIn('host-proxy.invalid', content)
            self.assertNotIn('unused-registry-secret', content)
            self.assertIn('preserved.internal', content)
            self.assertIn('kong', content)
            self.assertIn('DENO_CERT=', content)
            self.assertEqual(fingerprint, hashlib.sha256(content.encode()).hexdigest())
            self.assertEqual((directory / 'local-functions.env').stat().st_mode & 0o777, 0o600)

    def test_does_not_disable_tls_when_ca_is_missing(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with patch.dict(os.environ, {'DOCKER_CONFIG': str(directory / 'absent'),
                                         'SSL_CERT_FILE': str(directory / 'missing.pem')}, clear=True):
                with self.assertRaises(RuntimeError):
                    prepare(directory)
            self.assertFalse((directory / 'local-functions.env').exists())

    def test_private_key_is_never_copied(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / 'wrong.pem'
            source.write_text('-----BEGIN PRIVATE KEY-----')
            with patch.dict(os.environ, {'DOCKER_CONFIG': str(directory / 'absent'),
                                         'SSL_CERT_FILE': str(source)}, clear=True):
                with self.assertRaises(RuntimeError):
                    prepare(directory)
            self.assertFalse((directory / 'supabase/functions/.session-ca.pem').exists())
