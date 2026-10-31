import importlib.util
from pathlib import Path
import tempfile
import unittest

from web_assets import stamp_assets


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

    def test_single_file_generator_still_inlines_versioned_assets(self):
        spec=importlib.util.spec_from_file_location('sync_assets_test',Path(__file__).resolve().parents[1]/'tools'/'sync.py')
        sync=importlib.util.module_from_spec(spec);spec.loader.exec_module(sync)
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


if __name__=='__main__':unittest.main()
