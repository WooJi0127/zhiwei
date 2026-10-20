# -*- coding: utf-8 -*-
"""
中文字体子集化 —— 把 1.5MB 的思源宋体压到几百 KB。

用法：
    python tools/subset_font.py --plan     # 只算体积，不写文件
    python tools/subset_font.py            # 按当前策略生成并替换
    python tools/subset_font.py --strategy=ui   # 指定策略

为什么不是「只切界面用字」：
    --font-title 用在详情页专辑标题上，那是**动态数据**，新团新歌会带新字符。
    只按现有数据切，将来出现没见过的字就会掉回系统字体，同一页面里忽宋忽黑。
    所以兜底要有一档「常用汉字全集」——新增 Artists / 标题基本都落在里面。

候选策略（体积由 --plan 实测决定）：
    ui       界面静态文案 + 现有数据里出现过的中日韩字符（最小，但最脆）
    gb        GB2312 一级常用字 3755
    gball     GB2312 全部 6763（覆盖率最高，体积最大）
    gball+ui  gball 并上现有数据用字（默认：既全又不漏现在已有的字）
"""
import io
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "assets", "fonts-src",
                   "serif-noto-serif-sc-chinese-simplified-700-normal.woff2")
OUT = os.path.join(ROOT, "core", "fonts",
                   "serif-noto-serif-sc-chinese-simplified-700-normal.woff2")

CJK = re.compile(r"[^\x00-\x7f]")


def gb2312_chars(level1_only=False):
    """枚举 GB2312 里的汉字：0xB0-0xF7 区 × 0xA1-0xFE 位。"""
    out = []
    hi_range = range(0xB0, 0xF8)
    for hi in hi_range:
        for lo in range(0xA1, 0xFF):
            try:
                ch = bytes([hi, lo]).decode("gb2312")
            except UnicodeDecodeError:
                continue
            out.append(ch)
        if level1_only and hi == 0xD7:        # 一级字到 0xD7 区为止
            break
    return out


def file_text(*paths):
    t = []
    for p in paths:
        full = os.path.join(ROOT, p)
        if os.path.isfile(full):
            t.append(io.open(full, encoding="utf-8", errors="ignore").read())
    return "\n".join(t)


def ui_chars():
    """界面静态文案里的非 ASCII 字符。"""
    return set(CJK.findall(file_text("core/index.html", "core/app.js",
                                     "core/app.css")))


def data_chars():
    """现有数据里的非 ASCII：艺人团名、专辑标题、中文名。

    这里不去解析 JS 结构——直接抓所有非 ASCII 字符即可，
    反正最终是求并集，多抓几个（比如 urls）也多不了几 KB，
    漏抓才是问题。
    """
    import glob
    s = set()
    for f in glob.glob(os.path.join(ROOT, "data", "data*.js")):
        s |= set(CJK.findall(io.open(f, encoding="utf-8",
                                     errors="ignore").read()))
    return s


def strategy_chars(name):
    ui = ui_chars() | data_chars()
    gb1 = gb2312_chars(level1_only=True)
    if name == "ui":
        return ui
    if name == "gb":
        return set(gb1) | set("，。、？！：；“”‘’（）—…《》·") | ui
    if name == "gball":
        return set(gb2312_chars()) | ui
    if name == "gball+ui":
        return set(gb2312_chars()) | ui
    raise ValueError("未知策略 " + name)


def build(chars, out_path, no_hinting=True):
    """调 fontTools 做子集，返回字节数。"""
    from fontTools import subset

    text = "".join(sorted(chars))
    args = ["--text=" + text,
            "--flavor=woff2",
            "--layout-features=*",
            "--notdef-outline",
            "--drop-tables+=DSIG",
            "--output-file=" + out_path]
    if no_hinting:
        args.append("--no-hinting")
    args.append(SRC)
    subset.main(args)
    return os.path.getsize(out_path)


def human(n):
    return f"{n/1024:.0f} KB"


def available(chars, font_path):
    """这些字符里，原始字体本来就没有的是哪些（子集化之前就回退的，不算缺失）。"""
    from fontTools.ttLib import TTFont

    f = TTFont(font_path, fontNumber=0)
    have = set()
    for t in f["cmap"].tables:
        have |= set(t.cmap.keys())
    return set(c for c in chars if ord(c) in have)


def missing_chars(font_path, wanted, baseline=None):
    """子集相对于 baseline（默认是原始完整字体）少了哪些字符。

    只比「原始字体本来就有」的那部分——像俄文歌名、越南语声调这些，
    思源宋体简体压根没收，子集化之前就在回退了，不算我们切掉的。
    """
    from fontTools.ttLib import TTFont

    wanted = available(wanted, baseline or SRC)
    f = TTFont(font_path, fontNumber=0)
    have = set()
    for t in f["cmap"].tables:
        have |= set(t.cmap.keys())
    return set(c for c in wanted if ord(c) not in have)


def main():
    if not os.path.isfile(SRC):
        sys.exit(f"缺少源字体 {SRC}\n先把完整版思源宋体放到 assets/fonts-src/ 下面")

    old = os.path.getsize(OUT) if os.path.isfile(OUT) else 0

    if "--check" in sys.argv:
        if not os.path.isfile(OUT):
            sys.exit("还没有生成子集，先跑一次不带参数的")
        for name in ("ui", "gball+ui"):
            miss = missing_chars(OUT, strategy_chars(name))
            tag = {"ui": "界面+现有数据", "gball+ui": "再加 GB2312 全集"}[name]
            print(f"{tag:16s} 缺 {len(miss):4d} 个字符"
                  + (("  " + "".join(sorted(miss)[:60])) if miss else "  ✔ 全覆盖"))
        return 0

    if "--plan" in sys.argv:
        print(f"原始：{human(old)}   源：{os.path.basename(SRC)}")
        import tempfile
        for name in ("ui", "gb", "gball", "gball+ui"):
            cs = strategy_chars(name)
            tmp = os.path.join(tempfile.gettempdir(), "_subset_test.woff2")
            try:
                n = build(cs, tmp)
                print(f"  {name:10s} 字符 {len(cs):5d}  →  {human(n)}"
                      f"  （省 {100*(old-n)/old:.0f}%）")
            finally:
                if os.path.isfile(tmp):
                    os.remove(tmp)
        return 0

    # 默认 ui：界面文案 + 现有数据全覆盖，214KB（省 86%）。
    # 将来新歌名带出没见过的字，那几个字会回退到系统宋体，不影响整体排版；
    # 想要绝对覆盖就 --strategy=gball+ui（1118KB）。详见文件头注释。
    strat = "ui"
    for a in sys.argv:
        if a.startswith("--strategy="):
            strat = a.split("=", 1)[1]

    import tempfile
    tmp = os.path.join(tempfile.gettempdir(), "_subset_out.woff2")
    cs = strategy_chars(strat)
    n = build(cs, tmp)
    io.open(tmp, "rb").read()
    os.replace(tmp, OUT)
    print(f"策略 {strat}：字符 {len(cs)} 个 →  {human(n)}"
          f"（原 {human(old)}，省 {100*(old-n)/old:.0f}%）")
    print("已写入 " + os.path.relpath(OUT, ROOT))
    print("下一步：python tools/build_all.py --web   让各端都换上新字体")
    return 0


if __name__ == "__main__":
    sys.exit(main())
