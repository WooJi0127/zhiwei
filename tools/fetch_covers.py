#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""封面图本地化 —— 只搬「国内拉不到」的那部分。

为什么不全搬：全站 4700 张全搬要 150MB+，会撑爆 Cloudflare Workers 的部署体积。
实测下来真正拉不动的只有 kpopping（403 防盗链），Apple 和网易云在国内都能显示。
所以这里只处理黑名单域名上的图，配合前端「本地优先 + 失败回退外链」，
既能显示又不拖垮仓库。

用法：
    python tools/fetch_covers.py --probe   # 先探测各图床域名通不通
    python tools/fetch_covers.py           # 下载黑名单域名的图并压缩
    python tools/fetch_covers.py --all     # 强制把所有图都搬回来（慎用，体积大）
"""
import concurrent.futures as cf
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import urllib.request

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "covers")   # 放项目根：site/ 会被 sync 重建，不能放那儿
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# 实测 403（防盗链）的图床 —— 这些必须本地化
BAD_HOSTS = {"cdn.kpopping.com"}
WIDTH = 400          # 封面统一缩到 400px 宽
QUALITY = 82


def cover_name(rid):
    """前端按同一个规则算文件名，数据文件里不用额外存字段。"""
    return re.sub(r"[^a-zA-Z0-9]", "_", rid or "") + ".jpg"


def probe():
    """探测 data.js 里出现过的图床域名，各自通不通。"""
    seen = {}
    for fn in sorted(os.listdir(os.path.join(ROOT, "data"))):
        if not fn.endswith(".js"):
            continue
        s = io.open(os.path.join(ROOT, "data", fn), encoding="utf-8",
                    errors="ignore").read()
        for u in re.findall(r'"image":"(https?://[^"]+)"', s):
            seen.setdefault(u.split("/")[2], u)
    print(f"共 {len(seen)} 个图床域名")
    for host, u in seen.items():
        r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                            "--connect-timeout", "8", "--max-time", "15", u],
                           capture_output=True, text=True)
        print(f"  {r.stdout or 'ERR':>4}  {host}")
    return seen


def collect(all_hosts=False):
    """扫 data/ 下所有 js，收集需要本地化的 (release_id, image_url)。"""
    need = {}
    for fn in sorted(os.listdir(os.path.join(ROOT, "data"))):
        if not fn.endswith(".js"):
            continue
        s = io.open(os.path.join(ROOT, "data", fn), encoding="utf-8",
                    errors="ignore").read()
        for m in re.finditer(r'"id":"([^"]+)".*?"image":"(https?://[^"]+)"', s):
            rid, url = m.group(1), m.group(2)
            host = url.split("/")[2]
            if all_hosts or host in BAD_HOSTS:
                need.setdefault(rid, url)
    return need


def fetch_one(item):
    rid, url = item
    dst = os.path.join(OUT, cover_name(rid))
    if os.path.exists(dst) and os.path.getsize(dst) > 1000:
        return (rid, "skip")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                   "Referer": "https://kpopping.com/"})
        with urllib.request.urlopen(req, timeout=25) as r:
            raw = r.read()
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        if im.width > WIDTH:
            im = im.resize((WIDTH, round(im.height * WIDTH / im.width)),
                           Image.LANCZOS)
        im.save(dst, "JPEG", quality=QUALITY, optimize=True)
        return (rid, f"{os.path.getsize(dst)//1024}KB")
    except Exception as e:  # noqa: BLE001
        return (rid, "FAIL:" + str(e)[:40])


def main():
    if "--probe" in sys.argv:
        probe()
        return
    os.makedirs(OUT, exist_ok=True)
    need = collect("--all" in sys.argv)
    print(f"待下载封面：{len(need)} 张（黑名单域名：{', '.join(BAD_HOSTS)}）")
    ok = skip = fail = 0
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for rid, res in ex.map(fetch_one, list(need.items())):
            if res == "skip":
                skip += 1
            elif res.startswith("FAIL"):
                fail += 1
                print(f"  ! {rid}: {res}")
            else:
                ok += 1
            if (ok + skip + fail) % 50 == 0:
                print(f"  … {ok + skip + fail}/{len(need)}")
    print(f"完成：新下载 {ok}，已有 {skip}，失败 {fail}")
    total = sum(os.path.getsize(os.path.join(OUT, f))
                for f in os.listdir(OUT)) / 1048576
    print(f"covers 目录：{len(os.listdir(OUT))} 张，共 {total:.1f} MB")


if __name__ == "__main__":
    main()
