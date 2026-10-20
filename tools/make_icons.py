# -*- coding: utf-8 -*-
"""
从 assets/icon.svg 生成各平台需要的图标。

  Windows : build/icon.ico（内嵌 16/24/32/48/64/128/256 多个尺寸）
  Android : 各 density 的 ic_launcher.png（含自适应图标前景/背景）
  iOS     : AppIcon 全套尺寸
  Web     : favicon.png / apple-touch-icon.png / og-image.png

用无头 Edge 渲染 SVG 再缩放，不依赖任何第三方库（PIL / cairosvg 都不需要）。
缩放自己做最近邻+双线性，尺寸小、速度够用。
"""
import io
import math
import os
import re
import struct
import subprocess
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")

EDGE = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

# ICO 内嵌的尺寸
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
# Android 各 density 的 launcher 尺寸
ANDROID_SIZES = {"mdpi": 48, "hdpi": 72, "xhdpi": 96,
                 "xxhdpi": 144, "xxxhdpi": 192}
# iOS AppIcon 尺寸（pt × scale）
IOS_SIZES = [20, 29, 40, 58, 60, 76, 80, 87, 120, 152, 167, 180, 1024]


# ---------------------------------------------------------------- 极简 PNG 编解码
class RGBA:
    """一张 RGBA 位图，够用的最小实现。"""

    def __init__(self, w, h, px=None):
        self.w, self.h = w, h
        self.px = px or bytearray(w * h * 4)

    def get(self, x, y):
        if x < 0 or y < 0 or x >= self.w or y >= self.h:
            return (0, 0, 0, 0)
        i = (y * self.w + x) * 4
        return tuple(self.px[i:i + 4])

    def set(self, x, y, c):
        if x < 0 or y < 0 or x >= self.w or y >= self.h:
            return
        i = (y * self.w + x) * 4
        self.px[i:i + 4] = bytes(c)

    def resize(self, nw, nh):
        """双线性缩放（带 alpha 预乘，避免透明边发黑）。"""
        out = RGBA(nw, nh)
        sx, sy = self.w / nw, self.h / nh
        for y in range(nh):
            # 源图上的采样中心
            fy = (y + 0.5) * sy - 0.5
            y0 = int(math.floor(fy))
            ty = fy - y0
            for x in range(nw):
                fx = (x + 0.5) * sx - 0.5
                x0 = int(math.floor(fx))
                tx = fx - x0
                acc = [0.0, 0.0, 0.0, 0.0]
                for dy in (0, 1):
                    for dx in (0, 1):
                        wx = (1 - tx) if dx == 0 else tx
                        wy = (1 - ty) if dy == 0 else ty
                        w = wx * wy
                        if w <= 0:
                            continue
                        p = self.get(x0 + dx, y0 + dy)
                        a = p[3] / 255.0
                        for k in range(3):
                            acc[k] += p[k] * a * w      # 预乘
                        acc[3] += a * w                 # alpha 也按 0~1 累积
                # 注意：acc[3] 必须是 0~1。以前这里写成 p[3] * w（0~255），
                # 再拿 acc[k] / acc[3] 去还原颜色，结果整张图被压成 (1,1,1)。
                a = acc[3]
                if a <= 0:
                    out.set(x, y, (0, 0, 0, 0))
                else:
                    px = [0, 0, 0, 0]
                    for k in range(3):
                        px[k] = max(0, min(255, int(round(acc[k] / a))))
                    px[3] = max(0, min(255, int(round(a * 255))))
                    out.set(x, y, tuple(px))
        return out

    def flatten(self, bg=(255, 255, 255)):
        """把透明部分压成实色。

        iOS 的 App 图标不允许带 alpha 通道（App Store 会以
        「Invalid Image - app icons can't be transparent」拒收），
        所以往 iOS 出图之前必须先压平。
        """
        out = RGBA(self.w, self.h)
        src = self.px
        dst = out.px
        br, bgc, bb = bg
        for i in range(0, len(src), 4):
            a = src[i + 3]
            if a == 255:
                dst[i:i + 4] = src[i:i + 4]
            else:
                f = a / 255.0
                g = 1.0 - f
                dst[i] = int(round(src[i] * f + br * g))
                dst[i + 1] = int(round(src[i + 1] * f + bgc * g))
                dst[i + 2] = int(round(src[i + 2] * f + bb * g))
                dst[i + 3] = 255
        return out

    def to_png(self, opaque=False):
        """opaque=True 时写成 RGB（colortype 2），不带 alpha 通道。

        iOS 的 App 图标不只是「像素不透明」就行，PNG 里**存在 alpha 通道**
        本身就会被 App Store 拒，所以压平之后必须改写 RGB。
        """
        step = 3 if opaque else 4
        raw = bytearray()
        if opaque:
            for y in range(self.h):
                raw.append(0)                      # filter type 0
                row = self.px[y * self.w * 4:(y + 1) * self.w * 4]
                for i in range(0, len(row), 4):
                    raw += row[i:i + 3]
        else:
            for y in range(self.h):
                raw.append(0)
                raw += self.px[y * self.w * 4:(y + 1) * self.w * 4]

        def chunk(tag, data):
            c = struct.pack(">I", len(data)) + tag + data
            return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

        ihdr = struct.pack(">IIBBBBB", self.w, self.h, 8,
                           2 if opaque else 6, 0, 0, 0)
        return (b"\x89PNG\r\n\x1a\n"
                + chunk(b"IHDR", ihdr)
                + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
                + chunk(b"IEND", b""))


def load_png(data):
    """只解析我们自己产出的 / Edge 截的 PNG：8-bit RGBA，非隔行。"""
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "不是 PNG"
    pos, idat, w = 8, bytearray(), None
    while pos < len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        if tag == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
            assert depth == 8 and interlace == 0, "只支持 8-bit 非隔行 PNG"
            assert ctype in (2, 6), f"不支持的颜色类型 {ctype}"
            nch = 4 if ctype == 6 else 3
        elif tag == b"IDAT":
            idat += body
        elif tag == b"IEND":
            break
        pos += 12 + ln

    raw = zlib.decompress(bytes(idat))
    stride = w * nch
    out = RGBA(w, h)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        ft = raw[p]; p += 1
        line = bytearray(raw[p:p + stride]); p += stride
        if ft == 1:
            for i in range(nch, stride):
                line[i] = (line[i] + line[i - nch]) & 0xFF
        elif ft == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ft == 3:
            for i in range(stride):
                a = line[i - nch] if i >= nch else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif ft == 4:
            for i in range(stride):
                a = line[i - nch] if i >= nch else 0
                b = prev[i]
                c = prev[i - nch] if i >= nch else 0
                pp = a + b - c
                pa, pb, pc = abs(pp - a), abs(pp - b), abs(pp - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        for x in range(w):
            i = x * nch
            if nch == 4:
                out.set(x, y, tuple(line[i:i + 4]))
            else:
                out.set(x, y, (line[i], line[i + 1], line[i + 2], 255))
        prev = line
    return out


# ---------------------------------------------------------------- 渲染 SVG
def render_svg(svg_path, size, transparent=True, svg_text=None):
    """用无头 Edge 把 SVG 渲染成 RGBA 位图。svg_text 传入时直接用，不读文件。"""
    edge = next((p for p in EDGE if os.path.isfile(p)), None)
    if not edge:
        sys.exit("找不到 Microsoft Edge，无法渲染图标")

    tmp = os.path.join(ROOT, "assets", "_icon_tmp")
    os.makedirs(tmp, exist_ok=True)
    html = os.path.join(tmp, "icon.html")
    svg = svg_text if svg_text is not None else io.open(svg_path, encoding="utf-8").read()
    io.open(html, "w", encoding="utf-8").write(
        '<html><head><meta charset="utf-8"><style>'
        'html,body{margin:0;padding:0;width:%dpx;height:%dpx;overflow:hidden;'
        'background:transparent}svg{display:block;width:%dpx;height:%dpx}'
        '</style></head><body>%s</body></html>' % (size, size, size, size, svg))

    out = os.path.join(tmp, "shot.png")
    cmd = [edge, "--headless=new", "--disable-gpu", "--no-sandbox",
           "--hide-scrollbars", f"--window-size={size},{size}",
           "--virtual-time-budget=4000",
           f"--user-data-dir={os.path.join(tmp, 'prof')}"]
    if transparent:
        cmd.append("--default-background-color=00000000")
    cmd += [f"--screenshot={out}", "file:///" + html.replace("\\", "/")]
    subprocess.run(cmd, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=120)
    if not os.path.isfile(out):
        sys.exit("Edge 截图失败")
    return load_png(io.open(out, "rb").read())


def write_ico(images, path):
    """images: [(size, png_bytes)] → 合成一个 ICO。"""
    n = len(images)
    head = struct.pack("<HHH", 0, 1, n)
    entries, blobs, off = b"", b"", 6 + 16 * n
    for size, png in images:
        b = 0 if size >= 256 else size          # 256 在 ICO 里记作 0
        entries += struct.pack("<BBBBHHII", b, b, 0, 0, 1, 32, len(png), off)
        blobs += png
        off += len(png)
    io.open(path, "wb").write(head + entries + blobs)


def main():
    svg = os.path.join(ASSETS, "icon.svg")
    if not os.path.isfile(svg):
        sys.exit("缺少 assets/icon.svg")

    print("· 渲染 512×512 母图")

    def master(path, bleed):
        """渲染一张 512 母图。bleed=True 时把四周留白抹掉铺满画布——
        给 iOS / Android 用：系统自己会做圆角遮罩，图标里不该再自带透明边距，
        否则压平后透明角会被填成白色，装到手机上就是一圈白边。"""
        txt = io.open(path, encoding="utf-8").read()
        if bleed:
            txt = re.sub(r'<rect x="3" y="3" width="94" height="94" rx="20"',
                         '<rect x="0" y="0" width="100" height="100"',
                         txt, count=1)
        img = render_svg(path, 512, svg_text=txt)
        return img if img.w == 512 else img.resize(512, 512)

    svg_mini = os.path.join(ASSETS, "icon-mini.svg")
    full = master(svg, False)               # 完整版（带钟面数字）
    mini = master(svg_mini, False)          # 简化版（≤64px 用，数字会糊）
    full_b = master(svg, True)              # 满幅出血版
    mini_b = master(svg_mini, True)
    print("· 完整版 / 简化版 / 出血版母图就绪")
    MINI_MAX = 64

    def scaled(n, bleed=False):
        """小尺寸走简化母图，大尺寸走完整母图；OS 图标走出血版。"""
        if bleed:
            base = full_b if n > MINI_MAX else mini_b
        else:
            base = full if n > MINI_MAX else mini
        return base if n == 512 else base.resize(n, n)

    def save(rel, img, opaque=False):
        p = os.path.join(ROOT, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        io.open(p, "wb").write(img.to_png(opaque=opaque))
        return p

    # --- Windows ---
    icons = [(s, scaled(s).to_png()) for s in ICO_SIZES]
    p = os.path.join(ROOT, "desktop", "build", "icon.ico")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    write_ico(icons, p)
    print(f"· Windows  desktop\\build\\icon.ico  {len(icons)} 个尺寸")

    # --- Android（系统会遮圆角，用出血版）---
    for d, s in ANDROID_SIZES.items():
        save(f"mobile/android/app/src/main/res/mipmap-{d}/ic_launcher.png", scaled(s, bleed=True))
        save(f"mobile/android/app/src/main/res/mipmap-{d}/ic_launcher_round.png", scaled(s, bleed=True))
        save(f"mobile/android/app/src/main/res/mipmap-{d}/ic_launcher_foreground.png", scaled(s, bleed=True))
    print(f"· Android  5 档密度 × 3 种图标")

    # --- iOS ---
    # Xcode 14 之后 AppIcon.appiconset 默认只认一张 1024 的 "AppIcon-512@2x.png"，
    # 多尺寸那套是旧写法。两套都生成，新旧 Xcode 都能用。
    # 苹果拒收带 alpha 的 App 图标，所以这里全部压到白底；出血版保证压平后没有白角。
    icon_dir = "mobile/ios/App/App/Assets.xcassets/AppIcon.appiconset"
    save(f"{icon_dir}/AppIcon-512@2x.png", scaled(1024, bleed=True).flatten(), opaque=True)
    for s in IOS_SIZES:
        save(f"{icon_dir}/Icon-{s}.png", scaled(s, bleed=True).flatten(), opaque=True)
    print(f"· iOS      1024 主图 + {len(IOS_SIZES)} 个兼容尺寸（白底 RGB，无 alpha）")

    # --- Web ---
    # 浏览器标签页 favicon 用带留白的圆角方块（缩小后更好认）；
    # apple-touch / PWA 是系统级图标，iOS 会自己遮圆角，用出血版。
    save("site/favicon.png", scaled(64))
    save("site/apple-touch-icon.png", scaled(180, bleed=True).flatten(), opaque=True)
    save("site/app/icon.png", scaled(192, bleed=True))
    print("· Web      favicon / apple-touch-icon / pwa-192")

    print("\n完成")


if __name__ == "__main__":
    main()
