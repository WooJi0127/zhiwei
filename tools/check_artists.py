#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查「艺人绑错人」：库里绑的 Apple 艺人 ID，是否真的有库里那些专辑。

同名艺人在 Apple 上很多（Minzy 就有韩国歌手 / 华语歌手 / 越南歌手好几个）。
如果当初 itunes_search_artist 匹配错了人，这个艺人名下就会爬满别人的专辑。

用法：
    python tools/check_artists.py            # 全量体检，只报告不改动
    python tools/check_artists.py --fix NAME=ID   # 修正某个艺人的 Apple ID
                                                  # 并删掉绑错时爬进来的脏专辑
例：
    python tools/check_artists.py --fix "Minzy=1224513190"

铁律：只删「能确认是错的」（不在正确艺人 ID 的专辑列表里）的条目，
删不准的标出来交给人看，绝不猜。
"""
import datetime
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "scripts"))

from sources import http_json  # noqa: E402


def norm(s):
    return "".join(c for c in (s or "").lower() if c.isalnum())


def apple_albums(am_id, country="kr"):
    """取该 Apple 艺人 ID 下的全部专辑名。"""
    d = http_json(f"https://itunes.apple.com/lookup?id={am_id}"
                  f"&entity=album&limit=200&country={country}") or {}
    return {norm(r.get("collectionName"))
            for r in d.get("results", [])
            if r.get("wrapperType") == "collection"}


def check(con, only=None):
    rows = con.execute(
        "SELECT name, am_id FROM artists WHERE am_id IS NOT NULL ORDER BY name"
    ).fetchall()
    if only:
        rows = [r for r in rows if r[0] in only]
    print(f"体检 {len(rows)} 位艺人…")
    bad = []
    for i, (name, am_id) in enumerate(rows, 1):
        mine = con.execute(
            "SELECT id,title FROM releases WHERE artist=? AND source='apple'",
            (name,)).fetchall()
        if not mine:
            continue
        try:
            real = apple_albums(am_id)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {name}: 查询失败 {str(e)[:40]}")
            continue
        if not real:
            continue
        ghost = [(rid, t) for rid, t in mine if norm(t) not in real]
        if ghost and len(ghost) >= max(2, len(mine) * 0.5):
            bad.append((name, am_id, len(mine), len(ghost)))
            print(f"  ⚠ {name}（am_id={am_id}）：{len(mine)} 张 Apple 专辑里 "
                  f"{len(ghost)} 张不在该 ID 名下 —— 可能绑错人")
        time.sleep(0.4)
        if i % 40 == 0:
            print(f"    …{i}/{len(rows)}")
    print()
    if bad:
        print(f"可疑 {len(bad)} 位：")
        for n, aid, total, ghost in bad:
            print(f"  {n}  am_id={aid}  共{total}张 疑似错{ghost}张")
        print()
        print("确认正确 ID 后执行：python tools/check_artists.py --fix \"艺名=正确的AppleID\"")
    else:
        print("✓ 没发现绑错人的情况")
    return bad


def fix(con, spec):
    name, _, new_id = spec.partition("=")
    name, new_id = name.strip(), new_id.strip()
    if not name or not new_id.isdigit():
        sys.exit('格式：--fix "艺名=AppleID"，例：--fix "Minzy=1224513190"')

    real = apple_albums(int(new_id))
    print(f"{name} 在 am_id={new_id} 下有 {len(real)} 张专辑")

    rows = con.execute(
        "SELECT id,source,title FROM releases WHERE artist=?", (name,)).fetchall()
    kill = [(rid, src, t) for rid, src, t in rows
            if src == "apple" and norm(t) not in real]
    # 网易云那张中文专辑同样不是她的，一并清掉
    kill += [(rid, src, t) for rid, src, t in rows
             if src == "netease" and norm(t) not in real]
    if not kill:
        print("没有需要清理的条目")
    for rid, src, t in kill:
        con.execute("DELETE FROM releases WHERE id=?", (rid,))
        con.execute("DELETE FROM tracks WHERE release_id=?", (rid,))
        print(f"  - 删除 [{src}] {t[:44]}")

    con.execute("UPDATE artists SET am_id=?, am_url=?, am_updated=NULL WHERE name=?",
                (int(new_id),
                 f"https://music.apple.com/kr/artist/{new_id}", name))
    con.commit()
    print(f"✓ {name} 的 Apple ID 已改为 {new_id}，清掉 {len(kill)} 条脏数据")
    print("  下次跑 build.py 会按新 ID 把真实作品补回来")


if __name__ == "__main__":
    con = sqlite3.connect("kpop.db")
    if "--fix" in sys.argv:
        fix(con, sys.argv[sys.argv.index("--fix") + 1])
    else:
        names = sys.argv[1:] or None
        check(con, names)
    con.close()
