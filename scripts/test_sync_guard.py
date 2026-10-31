import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from sync_guard import GUARD,upgrade_sync


class SyncGuardTests(unittest.TestCase):
    def test_preserves_server_settings_and_publishes_html_last(self):
        original=(Path(__file__).resolve().parents[1]/'tools'/'server_sync.sh').read_bytes()
        original=original.replace(b'TARGET="/www/wwwroot/mywooji.cn"',b'TARGET="/custom/site"')
        revised=upgrade_sync(original)
        self.assertIn(b'TARGET="/custom/site"',revised)
        files=re.search(rb'(?ms)^FILES="\n(.*?)^"',revised)[1].strip().splitlines()
        self.assertEqual(files[-1],b'index.html');self.assertIn(b'zhiwei.ics',files)
        self.assertEqual(upgrade_sync(revised),revised)
        self.assertIn(b'! zw_assets_match "$ZW_STAGE/index.html" "$ZW_STAGE"',revised)

    def test_unknown_layout_is_not_overwritten(self):
        with self.assertRaises(ValueError):upgrade_sync(b'#!/bin/bash\necho custom\n')

    def test_shell_gate_accepts_only_matching_js_and_css(self):
        git_bash=Path(r'C:\Program Files\Git\bin\bash.exe')
        bash=str(git_bash) if git_bash.exists() else shutil.which('bash')
        if not bash:self.skipTest('bash unavailable')
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            js=b'window.version=1;\r\n';css=b'body{color:green}\n'
            (folder/'app.js').write_bytes(js);(folder/'app.css').write_bytes(css)
            def version(value):return hashlib.sha256(value.replace(b'\r\n',b'\n')).hexdigest()[:16]
            (folder/'index.html').write_text('<link href="app.css?v='+version(css)+'"><script src="app.js?v='+version(js)+'"></script>',encoding='utf-8')
            # Use cwd-relative paths so the same check runs on Windows Git Bash and Linux CI.
            script=folder/'check.sh';script.write_text('TARGET=.\n'+GUARD+'\nzw_assets_match index.html\n',encoding='utf-8',newline='\n')
            def run():return subprocess.run([bash,'check.sh'],cwd=folder,capture_output=True).returncode
            self.assertEqual(run(),0)
            (folder/'app.js').write_text('old cached script',encoding='utf-8');self.assertNotEqual(run(),0)
            (folder/'app.js').write_bytes(js);(folder/'app.css').write_text('old CSS',encoding='utf-8');self.assertNotEqual(run(),0)
            (folder/'app.css').write_bytes(css);(folder/'index.html').write_text('<script src="app.js"></script>',encoding='utf-8');self.assertNotEqual(run(),0)

    def test_failed_staged_release_keeps_all_three_live_files(self):
        git_bash=Path(r'C:\Program Files\Git\bin\bash.exe')
        bash=str(git_bash) if git_bash.exists() else shutil.which('bash')
        if not bash:self.skipTest('bash unavailable')
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);staged=folder/'staged';staged.mkdir()
            js=b'window.current=2;\n';css=b'body{color:green}\n'
            version=lambda value:hashlib.sha256(value).hexdigest()[:16]
            html=('<link href="app.css?v='+version(css)+'"><script src="app.js?v='+version(js)+'"></script>').encode()
            for name in ['app.js','app.css','index.html']:(folder/name).write_bytes(b'previous '+name.encode())
            (staged/'app.js').write_bytes(b'stale mirror');(staged/'app.css').write_bytes(css);(staged/'index.html').write_bytes(html)
            (folder/'check.sh').write_text('TARGET=.\n'+GUARD+'\nzw_publish_assets staged\n',encoding='utf-8',newline='\n')
            run=lambda:subprocess.run([bash,'check.sh'],cwd=folder,capture_output=True).returncode
            self.assertNotEqual(run(),0)
            for name in ['app.js','app.css','index.html']:self.assertEqual((folder/name).read_bytes(),b'previous '+name.encode())
            (staged/'app.js').write_bytes(js);self.assertEqual(run(),0)
            for name,value in [('app.js',js),('app.css',css),('index.html',html)]:self.assertEqual((folder/name).read_bytes(),value)


if __name__=='__main__':unittest.main()
