from contextlib import redirect_stdout
import hashlib
import importlib.util
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from web_assets import stamp_assets


def load_sync():
    path = Path(__file__).resolve().parents[1] / 'tools' / 'sync.py'
    spec = importlib.util.spec_from_file_location('sync_assets_test', path)
    sync = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync)
    return sync


def release_fixture(root):
    core = root / 'core'
    data = root / 'data'
    (core / 'data').mkdir(parents=True)
    data.mkdir()
    (core / 'index.html').write_bytes(
        b'<link rel="stylesheet" href="app.css">\r\n'
        b'<script src="data/data.js"></script>\r\n<script src="app.js"></script>\r\n'
    )
    (core / 'app.js').write_bytes(b'window.example=1;\r\n')
    (core / 'app.css').write_bytes(b'body{color:green}\n')
    (core / 'backup.js').write_bytes(b'window.backup=true;\n')
    (core / 'robots.txt').write_bytes(b'User-agent: *\r\n')
    (core / 'sitemap.xml').write_bytes(b'<urlset/>\n')
    (core / 'data' / 'data.js').write_bytes(b'previous preview copy\n')
    payload = {
        'generated': '2026-11-05 10:01:08',
        'releases': [],
        'years': {'2020': 1},
        'olderCount': 1,
    }
    main = ('window.__KPOP_DATA__ = ' + json.dumps(payload) + ';\r\n').encode()
    (data / 'data.js').write_bytes(main)
    (data / 'data-2020.js').write_bytes(
        b'window.__KPOP_CHUNK_2020__ = {"y":"2020","releases":[{"id":"old"}]};\n'
    )
    (data / 'zhiwei.ics').write_bytes(b'BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n')
    return core, data


class WebAssetsTests(unittest.TestCase):
    def test_version_changes_only_when_source_changes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);core=root/'core';core.mkdir()
            (core/'index.html').write_text('<link rel="stylesheet" href="app.css">\n<script src="app.js"></script>',encoding='utf-8')
            (core/'app.js').write_text('window.example=1;',encoding='utf-8')
            (core/'app.css').write_text('body{color:green}',encoding='utf-8')
            stamp_assets(root);first=(core/'index.html').read_text(encoding='utf-8')
            self.assertRegex(first,r'app\.js\?v=[a-f0-9]{16}')
            self.assertRegex(first,r'app\.css\?v=[a-f0-9]{16}')
            stamp_assets(root);self.assertEqual(first,(core/'index.html').read_text(encoding='utf-8'))
            (core/'app.js').write_text('window.example=2;',encoding='utf-8')
            stamp_assets(root);second=(core/'index.html').read_text(encoding='utf-8')
            self.assertNotEqual(first,second)
            self.assertEqual(first.splitlines()[0],second.splitlines()[0])
            self.assertFalse((core/'release-manifest.tsv').exists())

    def test_single_file_generator_still_inlines_versioned_assets(self):
        sync=load_sync()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);core=root/'core';core.mkdir()
            (core/'index.html').write_text('<link rel="stylesheet" href="app.css?v=abc">\n<script src="app.js?v=def"></script>',encoding='utf-8')
            (core/'app.js').write_text('window.example=1;',encoding='utf-8')
            (core/'app.css').write_text('body{color:green}',encoding='utf-8')
            sync.ROOT=str(root);sync.CORE=str(core)
            output,_=sync.build_single_file()
            html=Path(output).read_text(encoding='utf-8')
            self.assertIn('<style>',html);self.assertIn('window.example=1;',html)
            self.assertNotIn('src="app.js',html)

    def test_sync_uses_authoritative_data_and_publishes_matching_manifest(self):
        sync = load_sync()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            core, data = release_fixture(root)
            site = root / 'site'
            with patch.multiple(sync, ROOT=str(root), CORE=str(core), DATA=str(data / 'data.js'),
                                TARGETS={'site': str(site)}):
                with patch.object(sys, 'argv', ['sync.py']), patch.object(sys, 'path', sys.path.copy()), redirect_stdout(StringIO()):
                    self.assertEqual(sync.main(), 0)
            main = (data / 'data.js').read_bytes().replace(b'\r\n', b'\n')
            script = '<script src="data/data.js?v=' + hashlib.sha256(main).hexdigest()[:16] + '"></script>'
            html = (site / 'index.html').read_text(encoding='utf-8')
            self.assertIn(script, html)
            offline = (root / '知未.html').read_text(encoding='utf-8')
            self.assertIn(script, offline)
            self.assertIn('window.example=1;', offline)

            lines = (site / 'release-manifest.tsv').read_text(encoding='utf-8').splitlines()
            self.assertEqual(lines[0], 'zhiwei-release-v1\t2026-11-05 10:01:08')
            listed = dict(line.split('\t', 1)[::-1] for line in lines[1:])
            self.assertEqual(set(listed), {
                'index.html', 'app.js', 'app.css', 'data/data.js',
                'data/data-2020.js', 'zhiwei.ics', 'backup.js', 'robots.txt', 'sitemap.xml',
            })
            for name, digest in listed.items():
                content = (site / name).read_bytes().replace(b'\r\n', b'\n')
                self.assertEqual(digest, hashlib.sha256(content).hexdigest(), name)

    def test_missing_archive_cannot_publish_partial_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            core, data = release_fixture(root)
            (data / 'data-2020.js').unlink()
            original = (core / 'index.html').read_bytes()
            with self.assertRaises(FileNotFoundError):
                stamp_assets(root)
            self.assertEqual((core / 'index.html').read_bytes(), original)
            self.assertFalse((core / 'release-manifest.tsv').exists())


if __name__=='__main__':unittest.main()
