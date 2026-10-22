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
    python scripts/bilibili.py              # 增量：只补库里没有的艺人（按字母序）
    python scripts/bilibili.py --recent 30  # 刷新近 30 天有发行的艺人（每次都重抓）
    python scripts/bilibili.py --force      # 全量重抓
    python scripts/bilibili.py --limit 20   # 先试 20 个
    python scripts/bilibili.py --check      # 只校验已有链接有没有失效

为什么要有 --recent：
    每个艺人抓过一次就会记进 bili_seen，之后不再重抓。MV 是「以后才发」的
    东西，只抓一次等于永远停在第一次抓到的那天——首页「热门 MV」因此常年
    显示「本月还没有收录」。--recent 挑近 N 天有发行的艺人强制重抓，
    新专的官方 MV 才追得回来。每日任务跑的就是这个模式。
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
PAGES = 2                      # 按艺人搜：播放量排序 2 页（历史热门用）
NEW_PAGES = 2                  # 按艺人搜：发布时间排序再 2 页（捞新发的）
REL_PAGES = 2                  # 按发行条目搜：命中就停，最多翻 2 页

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


def tokens(s):
    """按非字母数字切开：「A2O MAY」→ ['a2o','may']。
    官方号常常只挂公司/厂牌名（A2O MAY 的 MV 在 A2O_WORLD 上），
    按整名比对必然漏，按词比对才抓得到。
    注意顺序：必须先按原始字符串切再逐段 norm——norm 会把空格一起削掉，
    先 norm 的话「A2O MAY」会变成一整个 a2omay，永远对不上 A2O_WORLD。"""
    return [norm(t) for t in re.split(r"[^0-9A-Za-z\u4e00-\u9fff]+", s or "") if norm(t)]


def related(name, uname, desc):
    n = norm(name)
    if not n:
        return False
    un = norm(uname or "")
    u = norm((uname or "") + " " + (desc or ""))

    # 短名（IVE / XG / TWS）是重灾区：「give」「live」「five」里都有 ive，
    # 拿去做子串比对会误判一堆无关号。所以短名只认 UP 主名字本身，
    # 而且必须是开头或独立成词（IVEofficial 认，pcyxjy 不认）。
    if len(n) <= 4:
        if not un:
            return False
        return un.startswith(n) or n in tokens(uname or "")

    if n in u:
        return True
    for t in tokens(name):               # A2O MAY → A2O_WORLD 这类
        if len(t) >= 3 and t in u:
            return True
    for c in COMPANY:
        cn = norm(c)
        if cn and cn in u:
            return True
    return False


# 标题里带这些就不是正片：预告、花絮、幕后、reaction、练习室……首页只要主打 MV
BAD = [
    "teaser", "preview", "making", "behind", "spoiler", "trailer",
    "花絮", "幕后", "预告", "拍摄", "reaction", "react", "练习室",
    "dance practice", "编舞", "shorts", "巡演", "直播", "cut",
    "一起看", "观看", "reaction to", "vgm", "first time",
]


def looks_like_mv(title, artist):
    """只要官方 MV 正片。命中 BAD 关键词的一律丢掉——否则首页会出现
    「MV 花絮」「MV Teaser」这种占位垃圾，比没有还难看。"""
    t = title.upper()
    # 官方号未必写 MV：A2O LITE 的《NEON》就叫 "Official Video"，
    # 只认 MV 会把它整条漏掉
    if not any(k in t for k in ("MV", "M/V", "MUSIC VIDEO", "OFFICIAL VIDEO")):
        return False
    low = title.lower()
    for b in BAD:
        if b in low:
            return False
    return True


def search_videos(kw, page, order="click"):
    url = ("https://api.bilibili.com/x/web-interface/search/type?search_type=video"
           f"&keyword={urllib.parse.quote(kw)}&order={order}&page={page}")
    d = api(url)
    if not d or d.get("code") != 0:
        return []
    return (d.get("data") or {}).get("result") or []


def clean_title(t):
    """发行名去掉「- EP」「- Single」这类后缀：搜「IVE Looks Can Kill - Single」
    B 站基本搜不到东西，搜「IVE Looks Can Kill」才准。"""
    return re.sub(r"\s*[-–—]\s*(ep|single|album|mini|ost|repackage|dl|cd)\s*$",
                  "", t or "", flags=re.I).strip()


def pick(con, name, videos, seen):
    """从一批搜索结果里挑官方 MV：UP 主要和艺人对得上 + 官方认证 + 是正片。"""
    out = []
    for v in videos:
        bvid = v.get("bvid")
        if not bvid or bvid in seen:
            continue
        seen.add(bvid)
        # 先用视频里带的 UP 主名字粗筛，省掉九成 card 接口请求
        if not related(name, v.get("author") or "", ""):
            continue
        ok, uname, udesc = is_official(con, v.get("mid"))
        if not ok or not related(name, uname, udesc):
            continue
        title = clean(v.get("title"))
        if not looks_like_mv(title, name):
            continue
        out.append({
            "bvid": bvid, "mid": str(v.get("mid")), "uname": uname,
            "title": title, "play": v.get("play") or 0,
            "pubdate": v.get("pubdate") or 0,
            "pic": ("https:" + v["pic"]) if (v.get("pic") or "").startswith("//")
                   else (v.get("pic") or ""),
        })
    return out


def save(con, name, got):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for g in got:
        con.execute("""INSERT OR REPLACE INTO bili
                       (bvid,artist,mid,uname,title,play,pubdate,pic,dead,updated)
                       VALUES(?,?,?,?,?,?,?,?,0,?)""",
                    (g["bvid"], name, g["mid"], g["uname"], g["title"],
                     g["play"], g["pubdate"], g["pic"], now))
    con.commit()
    return len(got)


def fetch_release(con, artist, title, lead=None):
    """按「艺人 + 主打曲 / 专辑名」搜官方 MV —— 这才是首页要的东西。

    只搜艺人名是不够的：B 站搜索按播放量排，艺人名的结果前几页会被老 MV、
    饭拍、打歌舞台占满，新专主打挤不进去（NMIXX、IVE 都因此漏掉）。

    关键词先主打曲、后专辑名：主打曲常常和专辑名不一样
    （NMIXX 专辑叫 Strange Muse，主打叫 긴 소원 / Birthday Wish），
    只用专辑名搜就会整个漏掉。命中一个就收工，省请求。"""
    kws = []
    if lead and clean_title(lead) and norm(lead) != norm(title):
        kws.append((artist + " " + clean_title(lead)).strip())
    kws.append((artist + " " + clean_title(title)).strip())

    for kw in kws:
        got, seen = [], set()
        for pg in range(1, REL_PAGES + 1):
            got += pick(con, artist, search_videos(kw, pg, "click"), seen)
            if got:
                break                  # 第一页就命中就别翻了
            time.sleep(SLEEP)
        if got:
            return save(con, artist, got)
    return 0


def fetch_artist(con, name):
    """按艺人名捞历史热门 MV（首页其实只用近一个月，这条留作补全历史）。

    两个排序各搜一遍：click 捞热门，pubdate 捞新发的——新 MV 播放量低，
    只按播放量排会一直沉在后面。"""
    got, seen = [], set()
    for order, pages in [("click", PAGES), ("pubdate", NEW_PAGES)]:
        for pg in range(1, pages + 1):
            got += pick(con, name, search_videos(name, pg, order), seen)
            time.sleep(SLEEP)
    return save(con, name, got)


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

    recent_days = None
    if "--recent" in sys.argv:
        try:
            recent_days = int(sys.argv[sys.argv.index("--recent") + 1])
        except Exception:  # noqa: BLE001
            recent_days = 30

    # --releases N：按发行条目抓近 N 天的专辑（默认再往后看 7 天——
    # MV 常常比专辑先发，只盯已发行的会漏掉「预告期就爆了」的那批）
    rel_days = None
    rel_ahead = 7
    if "--releases" in sys.argv:
        try:
            rel_days = int(sys.argv[sys.argv.index("--releases") + 1])
        except Exception:  # noqa: BLE001
            rel_days = 30
    if "--ahead" in sys.argv:
        try:
            rel_ahead = int(sys.argv[sys.argv.index("--ahead") + 1])
        except Exception:  # noqa: BLE001
            rel_ahead = 7
    skip_have = "--skip-have" in sys.argv

    if recent_days:
        # 近期「已经发行」过的艺人优先，且每次都重抓（不查 bili_seen）——
        # 新 MV 才追得上。注意必须排除未来档期：库里存着几个月后才会发的专辑，
        # 只按 MAX(date) 排会把 12 月才回归的艺人排在最前面，而他们的 MV 还不存在。
        today = datetime.date.today().isoformat()
        cut = (datetime.date.today() - datetime.timedelta(days=recent_days)).isoformat()
        rows = [r[0] for r in con.execute(
            "SELECT artist FROM releases WHERE date>=? AND date<=? GROUP BY artist"
            " ORDER BY MAX(date) DESC", (cut, today)).fetchall()]
    else:
        rows = [r[0] for r in con.execute("SELECT name FROM artists ORDER BY name").fetchall()]
    if limit:
        rows = rows[:limit]
    have = set()
    if not force and not recent_days:
        have = {r[0] for r in con.execute("SELECT artist FROM bili_seen").fetchall()}

    todo = [n for n in rows if force or n not in have]
    # --releases 不看 bili_seen（每次都要重抓，才能追到新 MV 和最新播放量），
    # 所以「都抓过了」的提前返回对它不成立
    if not todo and rel_days is None:
        log(f"· B 站：{len(rows)} 个艺人都抓过了，跳过（--force 重抓）")
        con.close()
        return

    cookie()

    # ---- 模式二：按「发行条目」抓（首页「热门 MV」的主力通道）----
    if rel_days is not None:
        today = datetime.date.today()
        lo = (today - datetime.timedelta(days=rel_days)).isoformat()
        hi = (today + datetime.timedelta(days=rel_ahead)).isoformat()
        rels = con.execute(
            "SELECT r.artist, r.title,"
            "  (SELECT t.name FROM tracks t WHERE t.release_id = r.id"
            "   ORDER BY t.track_no LIMIT 1) AS lead"
            " FROM releases r WHERE r.date>=? AND r.date<=?"
            " GROUP BY r.artist, r.title ORDER BY r.date DESC", (lo, hi)).fetchall()
        if limit:
            rels = rels[:limit]
        have = {}
        if skip_have:
            for a, t in con.execute("SELECT artist,title FROM bili WHERE dead=0"):
                have.setdefault(a, []).append((t or "").lower())

        log(f"· B 站：按发行条目抓 {len(rels)} 条（{lo} ~ {hi}）"
            + ("，已收录的跳过" if skip_have else ""))
        total, hit, skipped = 0, 0, 0
        for i, (artist, title, lead) in enumerate(rels, 1):
            if skip_have:
                key = clean_title(lead or title).lower()
                if key and any(key in t for t in have.get(artist, [])):
                    skipped += 1
                    continue
            try:
                n = fetch_release(con, artist, title, lead)
            except Exception as e:  # noqa: BLE001
                log(f"  ! {artist} / {title} 失败: {str(e)[:50]}")
                n = 0
            total += n
            if n:
                hit += 1
            if i % 20 == 0:
                log(f"  … {i}/{len(rels)} 命中 {hit} 条发行，共 {total} 个 MV")
            time.sleep(SLEEP)
        allrows = con.execute("SELECT COUNT(*) FROM bili WHERE dead=0").fetchone()[0]
        log(f"· B 站：{hit}/{len(rels) - skipped} 条发行有 MV（跳过已收录 {skipped} 条），"
            f"本次 {total} 个；库里有效共 {allrows} 条")
        con.close()
        return

    # ---- 模式一：按艺人抓 ----
    log(f"· B 站：待抓 {len(todo)} / 共 {len(rows)} 个艺人")
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
