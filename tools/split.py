# -*- coding: utf-8 -*-
"""
从单文件版 知未.html 拆出 core/ 源码（首次迁移用，之后不再需要）。

之后的方向是反过来的：手改 core/ → sync.py 内联生成 知未.html。
"""
import io, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC  = os.path.join(ROOT, "知未.html")
CORE = os.path.join(ROOT, "core")

html = io.open(SRC, encoding="utf-8").read()

m_css = re.search(r"<style>(.*?)</style>", html, re.S)
m_js  = re.search(r"<script>\n(\(function\(\).*?)</script>", html, re.S)
if not m_css or not m_js:
    sys.exit("没找到 style / script 块")

css, js = m_css.group(1), m_js.group(1)

# index.html：把内联块换成外链
page = html[:m_css.start()] + '<link rel="stylesheet" href="app.css">\n' + html[m_css.end():]
page = page.replace('<script>\n' + js + '</script>', '<script src="app.js"></script>')

# 移动端/全屏所需的元信息（对桌面无副作用）
if "viewport-fit" not in page:
    page = page.replace(
        'content="width=device-width,initial-scale=1"',
        'content="width=device-width,initial-scale=1,viewport-fit=cover"')
if 'name="theme-color"' not in page:
    page = page.replace("<title>", '<meta name="theme-color" content="#6d4aff">\n<meta name="apple-mobile-web-app-capable" content="yes">\n<meta name="mobile-web-app-capable" content="yes">\n<meta name="apple-mobile-web-app-status-bar-style" content="default">\n<title>')

os.makedirs(os.path.join(CORE, "data"), exist_ok=True)
io.open(os.path.join(CORE, "index.html"), "w", encoding="utf-8").write(page)
io.open(os.path.join(CORE, "app.css"),    "w", encoding="utf-8").write(css)
io.open(os.path.join(CORE, "app.js"),     "w", encoding="utf-8").write(js)
print(f"index.html {len(page)} / app.css {len(css)} / app.js {len(js)} 字节")
