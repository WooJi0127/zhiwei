# -*- coding: utf-8 -*-
"""
把 core/ 源码同步到各个端，并生成离线单文件版。

这是整个项目唯一的「分发」入口：
    改代码 → 只改 core/ → 跑一次 sync.py → 网页版 / 桌面端 / 手机端 / 下载站 全部更新

用法：
    python tools/sync.py            # 同步全部
    python tools/sync.py --web      # 只生成 知未.html
"""
import datetime
import io
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, "core")
DATA = os.path.join(ROOT, "data", "data.js")

# 各端的 web 资源目录
TARGETS = {
    "desktop": os.path.join(ROOT, "desktop", "app"),
    "mobile":  os.path.join(ROOT, "mobile", "www"),
    # 站点根目录直接就是应用本身：打开域名就用，不再经过营销落地页
    # （落地页 site/index.html 已于 2026-10-28 移除，用户拍板）
    "site":    os.path.join(ROOT, "site"),
}

# 同步时会被覆盖重建的目录（data 由 data/data.js 单独复制）
# downloads 与几个图标是站点自己的东西，不能被镜像 core/ 时清掉
SKIP = {"data", "downloads", "covers", "favicon.png", "apple-touch-icon.png"}


def read(p):
    return io.open(p, encoding="utf-8").read()


def write(p, s):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    io.open(p, "w", encoding="utf-8").write(s)


def build_single_file():
    """core/index.html → 知未.html（把 css / js 内联，双击即用）。"""
    page = read(os.path.join(CORE, "index.html"))
    css = read(os.path.join(CORE, "app.css"))
    js = read(os.path.join(CORE, "app.js"))

    n = 0
    page, n = re.subn(r'<link rel="stylesheet" href="app\.css(?:\?[^"<>]*)?">',
                      lambda m: "<style>\n" + css + "\n</style>", page)
    if not n:
        sys.exit("index.html 里没找到 app.css 的外链")

    page, n = re.subn(r'<script src="app\.js(?:\?[^"<>]*)?"></script>',
                      lambda m: "<script>\n" + js + "\n</script>", page)
    if not n:
        sys.exit("index.html 里没找到 app.js 的外链")

    # 离线单文件版的 CSS 里写的是 fonts/xxx.woff2，它跟 知未.html 同级，
    # 所以根目录也得放一份字体，否则离线版会掉回系统字体。
    src_fonts = os.path.join(CORE, "fonts")
    if os.path.isdir(src_fonts):
        dst_fonts = os.path.join(ROOT, "fonts")
        os.makedirs(dst_fonts, exist_ok=True)
        for name in os.listdir(src_fonts):
            shutil.copy2(os.path.join(src_fonts, name), os.path.join(dst_fonts, name))

    out = os.path.join(ROOT, "知未.html")
    write(out, page)
    return out, len(page)


def sync_dir(dst):
    """把 core/ 整个目录镜像到目标端。"""
    if os.path.isdir(dst):
        for name in os.listdir(dst):
            if name in SKIP:
                continue
            p = os.path.join(dst, name)
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    os.makedirs(dst, exist_ok=True)

    for name in os.listdir(CORE):
        if name in SKIP:
            continue
        s, d = os.path.join(CORE, name), os.path.join(dst, name)
        shutil.copy2(s, d) if os.path.isfile(s) else shutil.copytree(s, d)

    # 数据文件统一来自 data/，保证各端数据一致。
    # data.js 是主文件（近一年），data-<年>.js 是按需加载的年份切片，全都要带上。
    if os.path.isfile(DATA):
        dd = os.path.join(dst, "data")
        os.makedirs(dd, exist_ok=True)
        return copy_data(dd)
    return 0


def copy_data(dd):
    """把 data/ 下的 data.js + 所有年份切片复制到目标 data 目录，返回主文件字节数。"""
    src = os.path.dirname(DATA)
    os.makedirs(dd, exist_ok=True)
    total = 0
    for name in os.listdir(src):
        if not name.endswith(".js"):
            continue
        shutil.copy2(os.path.join(src, name), os.path.join(dd, name))
        if name == "data.js":
            total = os.path.getsize(os.path.join(src, name))
    return total


def write_version(dst):
    """写一份版本标记：同步完能一眼看出服务器拿到的是不是最新代码。"""
    import subprocess
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001
        sha = ""
    txt = (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
           + ("  commit " + sha if sha else ""))
    io.open(os.path.join(dst, "version.txt"), "w", encoding="utf-8").write(txt + "\n")
    return txt


def copy_ics(dst):
    """iCal 订阅文件：跟数据一起每天更新，放到站点根供日历 App 订阅。"""
    src = os.path.join(ROOT, "data", "zhiwei.ics")
    if not os.path.isfile(src):
        return False
    shutil.copy2(src, os.path.join(dst, "zhiwei.ics"))
    return True


def copy_covers(dst):
    """本地化的封面：从项目根 covers/ 分发到站点（site/ 每次同步会被重建）。"""
    src = os.path.join(ROOT, "covers")
    if not os.path.isdir(src):
        return 0
    d = os.path.join(dst, "covers")
    os.makedirs(d, exist_ok=True)
    n = 0
    for name in os.listdir(src):
        s0, d0 = os.path.join(src, name), os.path.join(d, name)
        if os.path.isfile(s0):
            shutil.copy2(s0, d0)
            n += 1
    return n


def main():
    only_web = "--web" in sys.argv

    if not os.path.isfile(os.path.join(CORE, "index.html")):
        sys.exit("core/index.html 不存在")

    # Keep the existing daily/manual entry point; version all generated web pages.
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from web_assets import stamp_assets
    stamp_assets(ROOT)
    out, size = build_single_file()
    print(f"· 离线单文件版  {os.path.relpath(out, ROOT)}  {size/1024:.0f} KB")

    if only_web:
        return 0

    if not os.path.isfile(DATA):
        print("  ! 未找到 data/data.js，跳过数据同步（先跑一次 build.py）")
    else:
        # core 自己也放一份，直接双击 core/index.html 就能预览
        copy_data(os.path.join(CORE, "data"))
        copy_ics(CORE)          # 本地预览（core/index.html）也能测订阅链接

    for name, dst in TARGETS.items():
        os.makedirs(dst, exist_ok=True)
        dsz = sync_dir(dst)
        # 本地化的封面只发给站点：桌面/移动是离线包，外链图在它们那边
        # 由 WebView 直接取，塞 2.8MB 图进离线包不划算
        cn = copy_covers(dst) if name == "site" else 0
        ic = copy_ics(dst) if name in ("site", "core") else False
        if name == "site":
            ver = write_version(dst)
        print(f"· {name:<8} {os.path.relpath(dst, ROOT)}"
              + (f"  数据 {dsz/1024:.0f} KB" if dsz else "")
              + (f"  封面 {cn} 张" if cn else "")
              + ("  +ics" if ic else "")
              + (f"  版本 {ver}" if name == "site" else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
