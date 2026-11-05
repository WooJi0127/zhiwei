from contextlib import contextmanager, redirect_stdout
from io import BytesIO, StringIO
from pathlib import Path
import tempfile
import unittest

import publish_site


class MemorySftp:
    def __init__(self, files):
        self.files = files.copy()
        self.directories = {'/', '/root', publish_site.REMOTE}
        self.replacements = []
        self.fail_target = None

    def stat(self, path):
        if path not in self.directories:
            raise FileNotFoundError(path)

    def mkdir(self, path):
        self.directories.add(path)

    @contextmanager
    def open(self, path, mode):
        if mode == 'rb' and path not in self.files:
            raise FileNotFoundError(path)
        stream = BytesIO(self.files[path] if mode == 'rb' else b'')
        yield stream
        if mode == 'wb':
            self.files[path] = stream.getvalue()

    def chmod(self, path, mode):
        pass

    def remove(self, path):
        if path not in self.files:
            raise FileNotFoundError(path)
        del self.files[path]

    def posix_rename(self, source, target):
        if target == self.fail_target:
            raise OSError('simulated upload failure')
        self.files[target] = self.files.pop(source)
        self.replacements.append(target)


class FakeSsh:
    def __init__(self, status=0):
        self.status = status
        self.commands = []
        self.channel = self

    def exec_command(self, command, **kwargs):
        self.commands.append(command)
        return (None, self, self)

    def recv_exit_status(self):
        return self.status


class PublishSiteTests(unittest.TestCase):
    resident = '/root/server_sync.sh'
    backup = '/root/zhiwei-backups/example'
    paths = ('app.css', 'app.js', 'data/data.js', 'index.html', 'release-manifest.tsv', 'version.txt')

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.site = Path(temp.name)
        for path in self.paths:
            file = self.site / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(('new ' + path).encode())
        original = {f'{publish_site.REMOTE}/{path}': ('old ' + path).encode() for path in self.paths}
        self.sftp = MemorySftp({**original, self.resident: b'old script'})
        self.ssh = FakeSsh()

    def publish(self):
        with redirect_stdout(StringIO()):
            publish_site.publish_release(self.sftp, self.ssh, self.site, self.backup, 'example', b'old script', b'new script')

    def test_publication_places_version_last_then_replaces_backed_up_resident(self):
        self.publish()
        self.assertEqual(self.sftp.replacements, [f'{publish_site.REMOTE}/{path}' for path in self.paths] + [self.resident])
        self.assertEqual(self.sftp.files[self.backup + '/server_sync.sh'], b'old script')
        self.assertEqual(self.sftp.files[self.backup + '/app.js'], b'old app.js')
        self.assertEqual(self.sftp.files[self.resident], b'new script')
        self.assertTrue(any('bash -n' in command for command in self.ssh.commands))

    def test_invalid_resident_syntax_stops_before_touching_live_files(self):
        self.ssh.status = 1
        original = self.sftp.files.copy()
        with self.assertRaisesRegex(RuntimeError, 'syntax'):
            self.publish()
        self.assertEqual(self.sftp.files, original)
        self.assertEqual(self.sftp.replacements, [])

    def test_failed_asset_publication_does_not_replace_resident_or_version(self):
        self.sftp.fail_target = publish_site.REMOTE + '/app.js'
        with self.assertRaises(OSError):
            self.publish()
        self.assertEqual(self.sftp.files[self.resident], b'old script')
        self.assertEqual(self.sftp.files[publish_site.REMOTE + '/version.txt'], b'old version.txt')
        self.assertEqual(self.sftp.files[publish_site.REMOTE + '/release-manifest.tsv'], b'old release-manifest.tsv')
        self.assertFalse(any('.upload-' in path for path in self.sftp.files))


if __name__ == '__main__':
    unittest.main()
