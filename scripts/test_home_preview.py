import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
START = "<!-- home-preview:start -->"
END = "<!-- home-preview:end -->"
TEMPLATE = f"<main>\n  {START}\n  Old preview\n  {END}\n  <p>Outside</p>\n</main>"
GENERATED = "2026-11-05 03:17:50"


def preview(releases):
    from home_preview import render_home_preview
    return render_home_preview(TEMPLATE, {"generated": GENERATED, "releases": releases})


class HomePreviewTests(unittest.TestCase):
    def test_initial_homepage_describes_the_application(self):
        source = (ROOT / "core" / "index.html").read_text(encoding="utf-8")
        home = re.search(r'<div\b[^>]*\bid="homeView"[^>]*>', source)
        self.assertIsNotNone(home)
        self.assertNotRegex(home[0], r'\bhidden\b|display\s*:\s*none')
        self.assertEqual(re.findall(r'<h1\b[^>]*>(.*?)</h1>', source, re.S), ["知未"])
        self.assertIn("K-POP 回归日历", source[home.end():source.index('<div id="listView"')])
        self.assertIn('<link rel="canonical" href="https://mywooji.cn/">', source)
        self.assertIn('<link rel="icon" type="image/png" href="site-icon.png">', source)
        descriptions = re.findall(r'<meta (?:name|property)="(?:description|og:description)" content="([^"]+)"', source)
        self.assertEqual(len(descriptions), 2)
        self.assertTrue(all("249" not in text and "5000" not in text for text in descriptions))
        schema = re.search(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', source, re.S)
        self.assertIsNotNone(schema)
        self.assertEqual(json.loads(schema[1]), {
            "@context": "https://schema.org", "@type": "WebSite",
            "name": "知未", "alternateName": "知未日历", "url": "https://mywooji.cn/",
        })

    def test_preview_uses_the_snapshot_window_and_escapes_records(self):
        releases = [
            {"date": "2026-11-12", "artist": "Endpoint", "title": "Last Day"},
            {"date": "2026-11-04", "artist": "Previous", "title": "Previous Release"},
            {"date": "2026-11-13", "artist": "Next", "title": "Out of Range"},
            {"date": "", "artist": "Unknown", "title": "Date Not Known"},
            {"date": "2026-11-31", "artist": "Invalid", "title": "Invalid Date"},
            {"date": "2026-11-05", "artist": "A < B", "title": "<script>alert(1)</script>"},
        ]
        out = preview(releases)
        self.assertIn('数据日期 <time datetime="2026-11-05">', out)
        self.assertEqual(out.count("<li>"), 2)
        self.assertLess(out.index("A &lt; B"), out.index("Endpoint"))
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", out)
        self.assertNotIn("<script>", out)
        for excluded in ("Previous Release", "Out of Range", "Date Not Known", "Invalid Date", "Old preview"):
            self.assertNotIn(excluded, out)
        self.assertIn("<p>Outside</p>", out)

    def test_preview_caps_rows_and_is_idempotent(self):
        from home_preview import render_home_preview
        releases = [{"date": "2026-11-06", "artist": "Artist", "title": f"Edition {i:02}"} for i in range(15)]
        out = preview(releases)
        self.assertEqual(out.count("<li>"), 12)
        self.assertNotIn("Edition 12", out)
        self.assertEqual(render_home_preview(out, {"generated": GENERATED, "releases": releases}), out)

    def test_empty_and_non_preview_templates(self):
        from home_preview import render_home_preview
        self.assertIn("暂未收录", preview([]))
        self.assertEqual(render_home_preview("<html></html>", {}), "<html></html>")
        with self.assertRaises(ValueError):
            render_home_preview(START, {})
