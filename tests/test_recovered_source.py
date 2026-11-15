import hashlib
from pathlib import Path
import unittest


class RecoveredSourceTests(unittest.TestCase):
    def test_original_attachment_is_preserved(self):
        source = Path(__file__).parent / 'fixtures/nexo-mcp-test-v2.ts'
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),
                         '70eb6c1a53de3c2770ec2f91319aece2e76f98f083d5818d5c5df443254e206d')
