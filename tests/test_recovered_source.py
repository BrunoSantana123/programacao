import hashlib
from pathlib import Path
import unittest


class RecoveredSourceTests(unittest.TestCase):
    def test_original_attachment_is_preserved(self):
        source = Path(__file__).parent / 'fixtures/nexo-mcp-test-v2.ts'
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),
                         '70eb6c1a53de3c2770ec2f91319aece2e76f98f083d5818d5c5df443254e206d')

    def test_local_adaptation_only_changes_configuration(self):
        root = Path(__file__).parent
        source = (root / 'fixtures/nexo-mcp-test-v2.ts').read_text()
        expected = source.replace(
            'const issuer = "https://tznebgdgdqpbhjdrhprb.supabase.co/auth/v1";',
            '// Adaptação EXCLUSIVA para testes locais. Autenticação JWT original preservada.\n'
            'if (Deno.env.get("NEXO_TEST_MODE") !== "local") throw new Error("Local test mode required");\n'
            'const issuer = "http://127.0.0.1:54321/auth/v1";')
        expected = expected.replace(
            'const resource = "https://tznebgdgdqpbhjdrhprb.supabase.co/functions/v1/nexo-mcp-test";',
            'const resource = "http://127.0.0.1:54321/functions/v1/nexo-mcp-test";')
        expected = expected.replace('new URL(issuer + "/.well-known/jwks.json")',
                                    'new URL("http://kong:8000/auth/v1/.well-known/jwks.json")')
        self.assertEqual((root / 'integration/nexo-mcp-test/index.ts').read_text(), expected)
