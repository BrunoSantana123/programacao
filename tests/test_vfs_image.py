import hashlib
import json
from pathlib import Path
import tarfile
import tempfile
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from tools.prepare_vfs_postgres import IMAGE, prepare


class VFSImageTests(TestCase):
    def test_normal_storage_is_not_modified(self):
        with patch('tools.prepare_vfs_postgres.command', return_value='overlay2\n') as command, \
                patch('tools.prepare_vfs_postgres.subprocess.run') as run:
            prepare(Path('/unused'))
            self.assertEqual(command.call_count, 1)
            run.assert_not_called()

    def test_existing_image_is_not_replaced(self):
        with patch('tools.prepare_vfs_postgres.command', return_value='vfs\n') as command, \
                patch('tools.prepare_vfs_postgres.subprocess.run', return_value=SimpleNamespace(returncode=0)):
            prepare(Path('/unused'))
            self.assertEqual(command.call_count, 1)

    def test_derived_image_preserves_runtime_config_and_pins_source(self):
        original = dict(architecture='amd64', os='linux', config={
            'Entrypoint': ['/entrypoint'], 'Cmd': ['postgres'], 'Env': ['PGDATA=/data'],
            'Healthcheck': {'Test': ['CMD', 'pg_isready']}, 'StopSignal': 'SIGINT'},
            rootfs={'type': 'layers', 'diff_ids': ['sha256:original']})
        digest = 'sha256:' + 'a' * 64
        calls, derived = [], {}
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'bin').mkdir()
            (directory / 'bin/crane').write_text('test executable placeholder')
            (directory / 'bin/umoci').write_text('test executable placeholder')

            def command(*args):
                calls.append(args)
                if args[:2] == ('docker', 'info'):
                    return 'vfs\n'
                if '--version' in args:
                    return 'umoci version 0.6.0\nimage spec: 1.1.1\nruntime spec: 1.2.1\ngo: go1.25.1\n'
                if 'version' in args:
                    return 'v0.22.1\n'
                if 'digest' in args:
                    return digest
                if 'config' in args:
                    self.assertTrue(args[-1].endswith('@' + digest))
                    return json.dumps(original)
                if 'pull' in args:
                    self.assertTrue(args[-2].endswith('@' + digest))
                    layout = Path(args[-1])
                    layout.mkdir()
                    (layout / 'index.json').write_text(json.dumps({'manifests': [{'digest': digest}]}))
                    return ''
                if args[:2] == ('docker', 'run'):
                    self.assertIn('none', args)
                    self.assertNotIn('--privileged', args)
                    with tarfile.open(directory / 'flat-postgres/layer.tar', 'w'):
                        pass
                    return ''
                if args[:2] == ('docker', 'load'):
                    with tarfile.open(args[-1]) as tar:
                        manifest = json.load(tar.extractfile('manifest.json'))
                        self.assertEqual(manifest[0]['RepoTags'], [IMAGE])
                        derived.update(json.load(tar.extractfile(manifest[0]['Config'])))
                        layer = tar.extractfile('layer.tar').read()
                        self.assertEqual(derived['rootfs']['diff_ids'], ['sha256:' + hashlib.sha256(layer).hexdigest()])
                    return ''
                if args[:3] == ('docker', 'image', 'inspect'):
                    return json.dumps([{'Config': derived['config'], 'Id': 'sha256:derived'}])
                raise AssertionError(args)

            with patch('tools.prepare_vfs_postgres.command', side_effect=command), patch('builtins.print'), \
                    patch('tools.prepare_vfs_postgres.subprocess.run', return_value=SimpleNamespace(returncode=1)):
                prepare(directory)
            self.assertEqual(derived['config'], original['config'])
            self.assertFalse(any('push' in call or 'flatten' in call for call in calls))
            provenance = json.loads((directory / 'postgres-image-provenance.json').read_text())
            self.assertTrue(provenance['runtime_config_verified'])
            self.assertTrue(provenance['source'].endswith('@' + digest))
            self.assertFalse((directory / 'flat-postgres/docker-image.tar').exists())
