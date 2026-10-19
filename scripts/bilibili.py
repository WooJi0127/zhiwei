# -*- coding: utf-8 -*-
"""
B 站官方 MV 抓取（只收官方账号发布的，粉丝站 / 二创一律不要）

为什么用「视频搜索」而不是「空间视频列表」：
  空间列表接口（/x/space/wbi/arc/search）要 wbi 签名，本机过不了风控（-352）；
  搜索接口只要先访问一次 bilibili.com 拿到 buvid3 这个 cookie 就能用，
  而且直接支持按播放量排序，正好是首页「本月 MV」要的顺序。

官方账号判定（card 接口 official_verify.type）：
    0 / 1 = 官方认证（0 团体官方号，1 公司/机构号，如 SMTOWN、HYBE）
   -1 / 127 = 普通用户 / 粉丝站，一律丢弃

用法：
    python scripts/bilibili.py              # 增量：只补库里没有的艺人
    python scripts/bilibili.py --force      # 全量重抓
    python scripts/bilibili.py --limit 20   # 先试 20 个
    python scripts/bilibili.py --check      # 只校验已有链接有没有失效
"""
import os
import re
import sys
import json
import time
import sqlite3
import datetime
import html
import unicodedata
import urllib.parse
import urllib.request
import http.cookiejar
import gzip

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "kpop.db")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
SLEEP = 1.5                    # B 站风控较严：请求太快会 412，宁慢勿封
PAGES = 2                      # 每个艺人搜 2 页（约 40 条），够覆盖热门 MV

DDL = """
CREATE TABLE IF NOT EXISTS bili (
    bvid    TEXT PRIMARY KEY,
    artist  TEXT,
    mid     TEXT,
    uname   TEXT,
    title   TEXT,
    play    INTEGER,
    pubdate INTEGER,
    pic     TEXT,
    dead    INTEGER DEFAULT 0,
    updated TEXT
);
CREATE TABLE IF NOT EXISTS bili_mid (
    mid      TEXT PRIMARY KEY,
    name     TEXT,
    official INTEGER,
    fans     INTEGER
);
-- 抓过的艺人（哪怕一条都没抓到）。没有它，没官方 MV 的艺人会被反复重试。
CREATE TABLE IF NOT EXISTS bili_seen (
    artist TEXT PRIMARY KEY,
    n      INTEGER DEFAULT 0,
    at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_bili_artist ON bili(artist);
"""


def log(m):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {m}")


# ------------------------------------------------------------------ HTTP
_CJ = None


def cookie():
    """B 站搜索接口没有 buvid3 会直接 412，先访问首页拿一下。"""
    global _CJ
    if _CJ:
        return _CJ
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", UA)]
    try:
        op.open("https://www.bilibili.com/", timeout=15).read(4000)
    except Exception:  # noqa: BLE001
        pass
    _CJ = "; ".join(f"{c.name}={c.value}" for c in cj)
    return _CJ


def api(url, retries=2):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Referer": "https://www.bilibili.com/",
                "Accept": "application/json, text/plain, */*",
                "Cookie": cookie(),
            })
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(raw.decode("utf-8", "replace"))
        except Exception as e:  # noqa: BLE001
            if i == retries - 1:
                log(f"    ! 请求失败 {url[:70]} -> {str(e)[:50]}")
                return None
            time.sleep(1.5)
    return None


# ------------------------------------------------------------- 官方号判定
_MIDCACHE = {}


def is_official(con, mid):
    """账号基本信息 + 是否官方认证。注意这里**不判断**和哪个艺人有关，
       相关性由调用方用 related() 单独判（一个账号可能对应多个艺人）。"""
    if not mid:
        return False, "", ""
    mid = str(mid)
    if mid in _MIDCACHE:
        return _MIDCACHE[mid]
    row = con.execute("SELECT name,official FROM bili_mid WHERE mid=?", (mid,)).fetchone()
    if row:
        _MIDCACHE[mid] = (row[1] == 1, row[0], row[0])
        return _MIDCACHE[mid]

    d = api(f"https://api.bilibili.com/x/web-interface/card?mid={mid}&photo=false")
    c = ((d or {}).get("data") or {}).get("card") or {}
    ov = c.get("official_verify") or {}
    ok = ov.get("type") in (0, 1)
    name = c.get("name") or ""
    desc = ov.get("desc") or c.get("description") or ""
    try:
        con.execute("INSERT OR REPLACE INTO bili_mid(mid,name,official,fans) VALUES(?,?,?,?)",
                    (mid, name, 1 if ok else 0, c.get("fans") or 0))
    except Exception:  # noqa: BLE001
        pass
    _MIDCACHE[mid] = (ok, name, desc)
    time.sleep(SLEEP * 0.5)
    return _MIDCACHE[mid]


# ------------------------------------------------------------------- 抓取
TAG = re.compile(r"<[^>]+>")


def clean(s):
    return html.unescape(TAG.sub("", s or "")).strip()


def norm(s):
    """去音标 + 小写 + 只留字母数字，用于「账号名里有没有艺人名」的模糊匹配。"""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s.lower())


# 光是「机构认证」还不够——B 站上认证的大 V 一大堆（游戏、数码、搞笑博主）。
# 官方号必须和这个艺人有关：账号名/简介里带艺人名，或者是唱片/经纪公司的官方号。
COMPANY = [
    "smtown", "sm entertainment", "hybe", "bighit", "yg entertainment", "ygent",
    "jyp", "starship", "cube entertainment", "pledis", "ador", "belift",
    "source music", "wakeone", "kq entertainment", "rbw", "fnc", "mystic",
    "wm entertainment", "yuehua", "乐华", "时代峰峻", "ist", "fantagio",
]


def related(name, uname, desc):
    n = norm(name)
    if not n:
        return False
    u = norm((uname or "") + " " + (desc or ""))
    if n and n in u:
        return True
    for c in COMPANY:
        cn = norm(c)
        if cn and cn in u:
            return True
    return False


def looks_like_mv(title, artist):
    """只要官方 MV / 官方舞蹈版之类，排除花絮、直播回放、综艺片段。"""
    t = title.upper()
    if "MV" in t or "M/V" in t or "MUSIC VIDEO" in t:
        return True
    return False


def search_videos(kw, page):
    url = ("https://api.bilibili.com/x/web-interface/search/type?search_type=video"
           f"&keyword={urllib.parse.quote(kw)}&order=click&page={page}")
    d = api(url)
    if not d or d.get("code") != 0:
        return []
    return (d.get("data") or {}).get("result") or []


def fetch_artist(con, name):
    """抓一个艺人的官方 MV，返回存了几条。"""
    got = []
    seen = set()
    for pg in range(1, PAGES + 1):
        for v in search_videos(name, pg):
            bvid = v.get("bvid")
            if not bvid or bvid in seen:
                continue
            seen.add(bvid)
            # 先用视频里带的 UP 主名字粗筛：名字里既没有艺人名也不像公司官方号的，
            # 直接丢掉，不去查 card 接口。这一步能把请求量砍掉九成。
            if not related(name, v.get("author") or "", ""):
                continue
            ok, uname, udesc = is_official(con, v.get("mid"))
            if not ok or not related(name, uname, udesc):
                continue
            title = clean(v.get("title"))
            if not looks_like_mv(title, name):
                continue
            got.append({
                "bvid": bvid, "mid": str(v.get("mid")), "uname": uname,
                "title": title, "play": v.get("play") or 0,
                "pubdate": v.get("pubdate") or 0,
                "pic": ("https:" + v["pic"]) if (v.get("pic") or "").startswith("//")
                       else (v.get("pic") or ""),
            })
        time.sleep(SLEEP)

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for g in got:
        con.execute("""INSERT OR REPLACE INTO bili
                       (bvid,artist,mid,uname,title,play,pubdate,pic,dead,updated)
                       VALUES(?,?,?,?,?,?,?,?,0,?)""",
                    (g["bvid"], name, g["mid"], g["uname"], g["title"],
                     g["play"], g["pubdate"], g["pic"], now))
    con.commit()
    return len(got)


def check_dead(con):
    """校验已收录的链接有没有失效（视频下架 B 站会返回 -404）。"""
    rows = con.execute("SELECT bvid FROM bili WHERE dead=0").fetchall()
    log(f"· B 站链接校验：{len(rows)} 条")
    n = 0
    for (bvid,) in rows:
        d = api(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}")
        code = (d or {}).get("code")
        if code is not None and code != 0:
            con.execute("UPDATE bili SET dead=1 WHERE bvid=?", (bvid,))
            n += 1
        time.sleep(SLEEP * 0.6)
    con.commit()
    log(f"· 失效 {n} 条，已标记（不会导出）")


def main():
    con = sqlite3.connect(DB_PATH)
    con.executescript(DDL)

    if "--check" in sys.argv:
        check_dead(con)
        con.close()
        return

    force = "--force" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        try:
            limit = int(sys.argv[sys.argv.index("--limit") + 1])
        except Exception:  # noqa: BLE001
            limit = None

    rows = [r[0] for r in con.execute("SELECT name FROM artists ORDER BY name").fetchall()]
    if limit:
        rows = rows[:limit]
    have = set()
    if not force:
        have = {r[0] for r in con.execute("SELECT artist FROM bili_seen").fetchall()}

    todo = [n for n in rows if force or n not in have]
    if not todo:
        log(f"· B 站：{len(rows)} 个艺人都抓过了，跳过（--force 重抓）")
        con.close()
        return

    log(f"· B 站：待抓 {len(todo)} / 共 {len(rows)} 个艺人")
    cookie()
    total, hit = 0, 0
    for i, name in enumerate(todo, 1):
        try:
            n = fetch_artist(con, name)
        except Exception as e:  # noqa: BLE001
            log(f"  ! {name} 失败: {str(e)[:50]}")
            n = 0
        total += n
        if n:
            hit += 1
        try:
            con.execute("INSERT OR REPLACE INTO bili_seen(artist,n,at) VALUES(?,?,?)",
                        (name, n, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        except Exception:  # noqa: BLE001
            pass
        if i % 10 == 0:
            con.commit()
            log(f"  … {i}/{len(todo)} 命中 {hit} 个艺人，共 {total} 条")
        time.sleep(SLEEP)
    con.commit()

    allrows = con.execute("SELECT COUNT(*) FROM bili WHERE dead=0").fetchone()[0]
    log(f"· B 站：命中 {hit} 个艺人，本次 {total} 条；库里有效共 {allrows} 条")
    con.close()


if __name__ == "__main__":
    main()
