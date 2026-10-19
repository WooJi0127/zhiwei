# -*- coding: utf-8 -*-
"""
成员生日抓取（kpopping.com）

数据源：kpopping 档案页内嵌的 JSON-LD（schema.org）
  - /profiles/group/<slug>  → MusicGroup.member[] 里就带每个成员的 birthDate
  - /profiles/idol/<slug>   → Person.birthDate

关键好处：**一个团体页就带齐全部成员生日**，不用逐个抓成员页
（kpopping 有上万个 idol 页，逐个抓既不现实也没必要）。

用法：
    python scripts/birthdays.py            # 增量：只抓库里还缺的
    python scripts/birthdays.py --force    # 全量重抓
    python scripts/birthdays.py --limit 20 # 先试 20 个看效果
"""
import os
import re
import sys
import json
import time
import sqlite3
import datetime
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sources  # noqa: E402

try:
    import names  # noqa: E402
except Exception:  # noqa: BLE001
    names = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "kpop.db")

BASE = "https://kpopping.com"
SITEMAP = BASE + "/sitemap.xml?type={t}"
# 请求间隔：kpopping 是公益站，别打太猛
SLEEP = 0.35

MEMBERS_DDL = """
CREATE TABLE IF NOT EXISTS members (
    g   TEXT,          -- 本地艺人名（团体名 / solo 名）
    n   TEXT,          -- 成员名（solo 时等于艺人名）
    alt TEXT,          -- 本名（alternateName）
    b   TEXT,          -- 生日 YYYY-MM-DD
    src TEXT,          -- 来源
    PRIMARY KEY (g, n)
);
"""


def log(msg):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}")


def norm(s):
    """slug 归一：去音标 + 小写 + 只留字母数字。
    "Girls' Generation" / "Girls-Generation" -> "girlgeneration"；"ADÉLA" / "ADELA" -> "adela" """
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s.lower())


# 本地艺人名（已 norm）在 kpopping 上用了另一个 slug 的，写死在这里。
# 只对「能明确对上号」的才加，猜不准的一律留空，宁缺毋滥。
ALIAS = {
    "tomorrowxtogether": "tomorrowxtogether2",   # TXT 在 kpopping 的 slug 带了后缀
}


def sitemap_urls(kind):
    raw = sources.http_get(SITEMAP.format(t=kind))
    if not raw:
        log(f"  ! sitemap {kind} 拉取失败")
        return []
    return re.findall(r"<loc>([^<]+)</loc>", raw.decode("utf-8", "replace"))


def slug_index():
    """{norm(slug): (kind, url)}，idol 优先于 group（同名时 solo 更可能是人）"""
    idx = {}
    for kind in ("groups", "idols"):
        for u in sitemap_urls(kind):
            slug = u.rstrip("/").split("/")[-1]
            k = norm(slug)
            if not k:
                continue
            if kind == "idols":
                idx[k] = ("idol", u)
            else:
                idx.setdefault(k, ("group", u))
    return idx


LD_RE = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S)


def parse_ld(html):
    """返回 (members, person)：
       members = [(name, alt, birthDate)...]  person = (name, alt, birthDate) | None"""
    members, person = [], None
    for m in LD_RE.finditer(html):
        try:
            d = json.loads(m.group(1))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(d, dict):
            continue
        t = d.get("@type")
        if t == "MusicGroup":
            for mem in (d.get("member") or []):
                if isinstance(mem, dict) and mem.get("birthDate"):
                    members.append((mem.get("name") or "",
                                    mem.get("alternateName") or "",
                                    mem.get("birthDate")))
        elif t == "Person" and d.get("birthDate"):
            person = (d.get("name") or "", d.get("alternateName") or "", d.get("birthDate"))
    return members, person


def is_valid_date(s):
    if not s or not re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return False
    try:
        datetime.date.fromisoformat(s)
        return True
    except Exception:  # noqa: BLE001
        return False


def fetch_birthdays(con, force=False, limit=None, sleep=SLEEP):
    """抓艺人的成员生日写进 members 表，返回统计字典。"""
    con.execute(MEMBERS_DDL)
    con.commit()

    rows = con.execute("SELECT name, kind FROM artists ORDER BY name").fetchall()
    if limit:
        rows = rows[:limit]

    have = set()
    if not force:
        for (g,) in con.execute("SELECT DISTINCT g FROM members").fetchall():
            have.add(g)

    todo = [r for r in rows if force or r[0] not in have]
    if not todo:
        log(f"· 生日：{len(rows)} 个艺人已全部抓过，跳过（--force 可重抓）")
        return {"artists": len(rows), "todo": 0}

    log(f"· 生日：待抓 {len(todo)} / 共 {len(rows)} 个艺人，先取 sitemap…")
    idx = slug_index()
    if not idx:
        log("  ! sitemap 为空，放弃")
        return {"artists": len(rows), "todo": len(todo), "ok": 0}
    log(f"  sitemap 索引 {len(idx)} 条")

    stat = {"artists": len(rows), "todo": len(todo), "hit": 0, "miss": 0,
            "rows": 0, "nobirth": 0}
    misses = []

    for i, (name, kind) in enumerate(todo, 1):
        key = norm(name)
        if not key:
            stat["miss"] += 1
            misses.append(name)
            continue

        # 1) 直接按艺人名匹配  2) 别名兜底
        hit = idx.get(key) or idx.get(ALIAS.get(key, ""))
        if not hit:
            stat["miss"] += 1
            misses.append(name)
            if i % 20 == 0:
                log(f"  … {i}/{len(todo)}")
            continue

        kind_kp, url = hit
        raw = sources.http_get(url)
        if not raw:
            stat["miss"] += 1
            misses.append(name)
            time.sleep(sleep)
            continue

        members, person = parse_ld(raw.decode("utf-8", "replace"))
        saved = 0

        if kind_kp == "group" and members:
            for (n, alt, b) in members:
                if not n or not is_valid_date(b):
                    continue
                con.execute("INSERT OR REPLACE INTO members(g,n,alt,b,src) VALUES(?,?,?,?,?)",
                            (name, n, alt or None, b, "kpopping"))
                saved += 1
        elif person:
            n, alt, b = person
            if n and is_valid_date(b):
                con.execute("INSERT OR REPLACE INTO members(g,n,alt,b,src) VALUES(?,?,?,?,?)",
                            (name, n, alt or None, b, "kpopping"))
                saved += 1

        if saved:
            stat["hit"] += 1
            stat["rows"] += saved
        else:
            stat["nobirth"] += 1
            misses.append(name)

        if i % 10 == 0:
            con.commit()
            log(f"  … {i}/{len(todo)} 已存 {stat['rows']} 条")

        time.sleep(sleep)

    con.commit()

    total = con.execute("SELECT COUNT(*) FROM members").fetchone()[0]
    log(f"· 生日：命中 {stat['hit']} 个艺人，存 {stat['rows']} 条，"
        f"未匹配 {stat['miss']}，无生日数据 {stat['nobirth']}；members 表共 {total} 条")
    if misses:
        log(f"  未覆盖（前 25）: {', '.join(misses[:25])}")

    stat["total"] = total
    stat["misses"] = misses
    return stat


def fetch_all_groups(con, limit=None, sleep=SLEEP):
    """抓 kpopping **全部团体页**（sitemap 里约 891 个），覆盖面远超本地艺人。

    为什么需要它：本地只追踪 223 个「有发行记录」的活跃艺人，而 kpopping 的
    生日库涵盖上万个 idol（含已解散团、小众团）。只抓本地艺人时，
    首页「今天生日」会经常是空的（实测某天 kpopping 有 19 人，我们 0 人）。
    """
    con.execute(MEMBERS_DDL)
    con.commit()

    urls = [u for u in sitemap_urls("groups") if "/profiles/group/" in u]
    if limit:
        urls = urls[:limit]
    log(f"· 生日（全量团体）：{len(urls)} 个团体页")

    idx = {norm(u.rstrip("/").split("/")[-1]) for u in urls}
    saved = 0
    empty = 0
    for i, u in enumerate(urls, 1):
        # 本地艺人名已经抓过的，跳过（避免重复请求）
        gname = u.rstrip("/").split("/")[-1]
        raw = sources.http_get(u)
        if not raw:
            empty += 1
            continue

        members, person = parse_ld(raw.decode("utf-8", "replace"))
        # 团体名以页面里的为准（可能与 URL slug 大小写不同）
        gname = None
        m = re.search(r'"@type"\s*:\s*"MusicGroup"', raw.decode("utf-8", "replace"))
        try:
            for mm in LD_RE.finditer(raw.decode("utf-8", "replace")):
                d = json.loads(mm.group(1))
                if isinstance(d, dict) and d.get("@type") == "MusicGroup" and d.get("name"):
                    gname = d["name"]
                    break
        except Exception:  # noqa: BLE001
            pass
        if not gname:
            gname = u.rstrip("/").split("/")[-1]

        n = 0
        for (nm, alt, b) in members:
            if not nm or not is_valid_date(b):
                continue
            con.execute("INSERT OR REPLACE INTO members(g,n,alt,b,src) VALUES(?,?,?,?,?)",
                        (gname, nm, alt or None, b, "kpopping"))
            n += 1
        if n:
            saved += n
        else:
            empty += 1

        if i % 25 == 0:
            con.commit()
            log(f"  … {i}/{len(urls)} 已存 {saved}")
        time.sleep(sleep)

    con.commit()
    total = con.execute("SELECT COUNT(*) FROM members").fetchone()[0]
    log(f"· 生日（全量团体）：新增/更新 {saved} 条，无数据 {empty} 个；members 表共 {total} 条")
    return {"saved": saved, "total": total}


def main():
    force = "--force" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        try:
            limit = int(sys.argv[sys.argv.index("--limit") + 1])
        except Exception:  # noqa: BLE001
            limit = None

    con = sqlite3.connect(DB_PATH)
    con.executescript(MEMBERS_DDL)
    if "--all" in sys.argv:
        fetch_all_groups(con, limit=limit)
    else:
        fetch_birthdays(con, force=force, limit=limit)
    con.close()


if __name__ == "__main__":
    main()
