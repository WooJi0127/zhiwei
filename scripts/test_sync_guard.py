import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

import sync_guard
from sync_guard import GUARD,upgrade_sync


class SyncGuardTests(unittest.TestCase):
    def test_release_upgrade_preserves_prelude_and_replaces_only_managed_tail(self):
        root = Path(__file__).resolve().parents[1]
        tail = b'# ZHIWEI_RELEASE_SYNC_V1\necho new-release\n'
        for path in (root / 'tools/server_sync.sh', root / 'scripts/server_sync.sh'):
            original = path.read_bytes().replace(b'\r\n', b'\n')
            original = original.replace(b'TARGET="/www/wwwroot/mywooji.cn"', b'TARGET="/custom/site"')
            original = original.replace(b'        mv -f "$TARGET/$f.tmp" "$TARGET/$f"',
                                        b'        mv "$TARGET/$f.tmp" "$TARGET/$f"')
            boundary = b'# ZHIWEI_ASSET_GUARD_V2\n' if b'# ZHIWEI_ASSET_GUARD_V2\n' in original else b'FILES="\n'
            with self.subTest(path=path):
                revised = sync_guard.upgrade_release_sync(original, tail)
                self.assertEqual(revised, original.split(boundary, 1)[0] + tail)
                self.assertEqual(sync_guard.upgrade_release_sync(revised, tail), revised)
                newer = tail.replace(b'new-release', b'next-release')
                self.assertEqual(sync_guard.upgrade_release_sync(revised, newer), revised.replace(tail, newer))

    def test_release_upgrade_rejects_custom_legacy_tail(self):
        root = Path(__file__).resolve().parents[1]
        tail = b'# ZHIWEI_RELEASE_SYNC_V1\necho new-release\n'
        legacy = (root / 'scripts/server_sync.sh').read_bytes().replace(b'\r\n', b'\n')
        custom = legacy + b'\necho user-command\n'
        with self.assertRaisesRegex(ValueError, 'refusing'):
            sync_guard.upgrade_release_sync(custom, tail)
        with self.assertRaisesRegex(ValueError, 'refusing'):
            sync_guard.upgrade_release_sync(legacy, b'echo missing-marker\n')

    def test_release_upgrade_accepts_compact_resident_v2(self):
        root = Path(__file__).resolve().parents[1]
        legacy = (root / 'tools/server_sync.sh').read_text(encoding='utf-8')
        prelude, managed = legacy.split('# ZHIWEI_ASSET_GUARD_V2\n', 1)
        managed = managed.replace('  d="$TARGET/$(dirname "$f")"\n  mkdir -p "$d"',
                                  '  mkdir -p "$TARGET/$(dirname "$f")"')
        managed = managed.replace('  if [ $got -eq 0 ]; then\n'
                                  '    fail=$((fail+1)); echo "  ! 所有镜像都失败: $f"\n  fi',
                                  '  [ $got -eq 0 ] && { fail=$((fail+1)); echo "  ! 所有镜像都失败: $f"; }')
        managed = managed.replace('（version.txt 没拉到）', '（没拉到）')
        managed = managed.replace('# 留一份日志，哪天没更新时打开这个文件就知道是网络还是别的原因\n', '')
        managed = managed.split('if [ $fail -gt 0 ]; then', 1)[0]
        compact = (prelude + '# ZHIWEI_ASSET_GUARD_V2\n' + managed).encode()
        new_tail = b'# ZHIWEI_RELEASE_SYNC_V1\necho new-release\n'
        self.assertEqual(sync_guard.upgrade_release_sync(compact, new_tail), prelude.encode() + new_tail)
        with self.assertRaisesRegex(ValueError, 'refusing'):
            sync_guard.upgrade_release_sync(compact + b'echo user-command\n', new_tail)

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

    def test_resident_move_without_force_flag_is_supported(self):
        # Actual resident script uses mv without -f; keep that harmless variation supported.
        legacy=b'#!/bin/bash\nTARGET="/custom/site"\nFILES="\nindex.html\napp.css\napp.js\n"\nok=0; fail=0; USED=""\nfor f in $FILES; do\n        mv "$TARGET/$f.tmp" "$TARGET/$f"\ndone\n'
        revised=upgrade_sync(legacy)
        self.assertIn(b'zw_publish_assets "$ZW_STAGE"',revised)
        self.assertNotIn(b'        mv "$TARGET/$f.tmp" "$TARGET/$f"',revised)
        self.assertEqual(upgrade_sync(revised),revised)

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
