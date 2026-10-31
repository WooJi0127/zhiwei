"""Generate the inline homepage QR with OpenCV; no runtime dependency or network request."""
import re
from pathlib import Path
import cv2

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'core/app.js').read_text(encoding='utf-8')
url = re.search(r'var SITE_URL = "([^"]+)";', source).group(1)
matrix = cv2.QRCodeEncoder_create().encode(url)
matrix = cv2.copyMakeBorder(matrix, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
decoded, _, _ = cv2.QRCodeDetector().detectAndDecode(cv2.resize(matrix, None, fx=10, fy=10, interpolation=cv2.INTER_NEAREST))
if decoded != url:
    raise RuntimeError('QR round trip failed')
size = matrix.shape[0]
commands = []
for y, row in enumerate(matrix):
    for x, pixel in enumerate(row):
        if pixel == 0:
            commands.append(f'M{x} {y}h1v1h-1z')
svg = f'<svg class="share-qr" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" role="img" aria-label="知未网站二维码" shape-rendering="crispEdges"><rect width="{size}" height="{size}" fill="#FAF6EE"/><path fill="#33473A" d="{"".join(commands)}"/></svg>'
index = ROOT / 'core/index.html'
page = index.read_text(encoding='utf-8')
page, count = re.subn(r'(?<=<!-- BEGIN SITE SHARE QR -->).*?(?=<!-- END SITE SHARE QR -->)', '\n  ' + svg + '\n  ', page, flags=re.S)
if count != 1:
    raise RuntimeError('Missing or duplicate QR markers')
index.write_text(page, encoding='utf-8')
print(f'Inline QR verified: {decoded} ({size}x{size})')
