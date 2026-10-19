# -*- coding: utf-8 -*-
"""
分类勘误：补齐 artists 表里缺失的 kind（团体 / solo）和 gender（男 / 女）

两个来源，都不猜，查不到就留空（宁缺毋滥）：
  1. kpopping 的团体分类页 /groups/girl-groups 与 /groups/boy-groups
     → 团体是男团还是女团
  2. kpopping 的 idol 档案页 JSON-LD 里的 Person.gender（Male / Female）
     → solo 歌手的性别

用法：
    python scripts/fixkind.py
"""
import os
import re
import sys
import json
import time
import sqlite3
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sources    # noqa: E402
import birthdays  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "kpop.db")

LIST_URL = "https://kpopping.com/groups/{slug}"
MAX_PAGE = 12
SLEEP = 0.4


def log(m):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {m}")


def group_names(kind_slug):
    """翻 kpopping 的分类页，收集该分类下所有团体 slug。"""
    out, seen = [], set()
    for page in range(1, MAX_PAGE + 1):
        url = LIST_URL.format(slug=kind_slug) + (f"?page={page}" if page > 1 else "")
        raw = sources.http_get(url)
        if not raw:
            break
        h = raw.decode("utf-8", "replace")
        slugs = re.findall(r'/profiles/group/([A-Za-z0-9\-_.%]+)', h)
        new = [s for s in slugs if s not in seen]
        if not new:
            break
        for s in new:
            seen.add(s)
            out.append(s)
        time.sleep(SLEEP)
    return out


def gender_from_idol(slug):
    raw = sources.http_get("https://kpopping.com/profiles/idol/" + slug)
    if not raw:
        return None
    h = raw.decode("utf-8", "replace")
    m = re.search(r'"gender"\s*:\s*"([^"]+)"', h)
    if not m:
        return None
    g = m.group(1).lower()
    return "F" if g.startswith("f") else ("M" if g.startswith("m") else None)


def main():
    con = sqlite3.connect(DB_PATH)
    todo = con.execute(
        "SELECT name,kind,gender FROM artists "
        "WHERE kind IS NULL OR kind='' OR gender IS NULL OR gender='' "
        "ORDER BY name").fetchall()
    if not todo:
        log("· 分类：没有待补的艺人")
        return
    log(f"· 分类：待补 {len(todo)} 个艺人")

    log("  … 抓 kpopping 团体分类页")
    girls = set(birthdays.norm(s) for s in group_names("girl-groups"))
    boys = set(birthdays.norm(s) for s in group_names("boy-groups"))
    log(f"  女团 {len(girls)} 个 / 男团 {len(boys)} 个")

    idx = birthdays.slug_index()
    nkind = ngender = 0
    for name, kind, gender in todo:
        key = birthdays.norm(name)
        newkind, newgender = kind, gender

        if not kind:
            if key in girls or key in boys:
                newkind = "group"
            elif idx.get(key, ("", ""))[0] == "idol":
                newkind = "solo"

        if not gender:
            if key in girls:
                newgender = "F"
            elif key in boys:
                newgender = "M"
            else:
                hit = idx.get(key) or idx.get(birthdays.ALIAS.get(key, ""))
                if hit and hit[0] == "idol":
                    newgender = gender_from_idol(hit[1].rstrip("/").split("/")[-1])
                    time.sleep(SLEEP)

        if newkind != kind or newgender != gender:
            con.execute("UPDATE artists SET kind=?, gender=? WHERE name=?",
                        (newkind, newgender, name))
            if newkind != kind:
                nkind += 1
            if newgender != gender:
                ngender += 1

    con.commit()
    left = con.execute(
        "SELECT COUNT(*) FROM artists "
        "WHERE kind IS NULL OR kind='' OR gender IS NULL OR gender=''").fetchone()[0]
    log(f"· 分类：补了 kind {nkind} 个 / gender {ngender} 个；仍缺 {left} 个（查不到，留空）")
    con.close()


if __name__ == "__main__":
    main()
