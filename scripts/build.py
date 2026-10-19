# -*- coding: utf-8 -*-
"""
K-Pop 回归追踪器 —— 数据构建脚本

流程：抓取三个数据源 -> 落 SQLite（历史留存）-> 导出 data.js 供前端加载
设计原则：
  * 纯标准库，零第三方依赖，避免环境差异导致跑不起来
  * 任一数据源失败都不影响整体，保留上一次的成果
  * 增量：Apple Music 艺人 ID 与专辑结果带缓存，避免每天重复打满请求
"""
import os
import re
import sys
import json
import time
import sqlite3
import datetime
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sources  # noqa: E402
import names    # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "kpop.db")
DATA_DIR = os.path.join(ROOT, "data")
OUT_JS = os.path.join(DATA_DIR, "data.js")
LOG_PATH = os.path.join(ROOT, "update.log")

# 历史归档回溯范围（天）
HISTORY_DAYS = 730
# 分片：主文件只装最近这么多天的发行，更早的按年份单独切片，用时再加载
RECENT_DAYS = 365
# Apple Music 请求间隔（秒），避免触发限流
AM_SLEEP = 3.0
# 艺人专辑缓存有效期（天）
AM_CACHE_DAYS = 7
# 网易云补专辑只看「最近这么多天有发行」的活跃艺人，避免全量遍历
NE_ACTIVE_DAYS = 120
# 跨源去重时，同一张专辑的日期能差多少天还认作同一张
# （Apple Music 与网易云的上架时间经常差 1-2 天）
DATE_TOL_DAYS = 3


def log(msg):
    line = f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:                               # noqa: BLE001
        pass


# ------------------------------------------------------------------ 数据库
SCHEMA = """
CREATE TABLE IF NOT EXISTS artists (
    name        TEXT PRIMARY KEY,
    name_ko     TEXT,
    kind        TEXT,
    gender      TEXT,
    agency      TEXT,
    debut_year  INTEGER,
    fandom      TEXT,
    am_id       INTEGER,
    am_url      TEXT,
    am_updated  TEXT
);
CREATE TABLE IF NOT EXISTS releases (
    id          TEXT PRIMARY KEY,
    source      TEXT,
    date        TEXT,
    artist      TEXT,
    title       TEXT,
    rtype       TEXT,
    image       TEXT,
    url         TEXT,
    extra       TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id          TEXT PRIMARY KEY,
    date        TEXT,
    etype       TEXT,
    category    TEXT,
    title       TEXT,
    artist      TEXT,
    description TEXT,
    source_url  TEXT,
    confirmed   INTEGER
);
CREATE TABLE IF NOT EXISTS tracks (
    id          TEXT PRIMARY KEY,
    release_id  TEXT,
    artist      TEXT,
    name        TEXT,
    track_no    INTEGER,
    disc        INTEGER,
    duration_ms INTEGER,
    genre       TEXT,
    preview     TEXT
);
CREATE TABLE IF NOT EXISTS members (
    g   TEXT,          -- 本地艺人名（团体 / solo）
    n   TEXT,          -- 成员名
    alt TEXT,          -- 本名
    b   TEXT,          -- 生日 YYYY-MM-DD
    src TEXT,
    PRIMARY KEY (g, n)
);
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
CREATE INDEX IF NOT EXISTS idx_bili_artist ON bili(artist);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
CREATE INDEX IF NOT EXISTS idx_rel_date ON releases(date);
CREATE INDEX IF NOT EXISTS idx_rel_artist ON releases(artist);
CREATE INDEX IF NOT EXISTS idx_track_rel ON tracks(release_id);
"""


def get_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    # 老库补列：CREATE TABLE IF NOT EXISTS 不会加新字段
    have = {r[1] for r in con.execute("PRAGMA table_info(artists)")}
    if "gender" not in have:
        con.execute("ALTER TABLE artists ADD COLUMN gender TEXT")
        con.commit()
    if "ne_id" not in have:
        con.execute("ALTER TABLE artists ADD COLUMN ne_id INTEGER")
        con.commit()
    if "coed_checked" not in have:
        con.execute("ALTER TABLE artists ADD COLUMN coed_checked INTEGER DEFAULT 0")
        con.commit()
    return con


# -------------------------------------------------------------- 过滤规则
# 用户选定的范围：韩语专辑/单曲回归 + 新团/个人 Solo 出道
# 排除：OST、Remix、Instrumental、日语版等衍生发行
EXCLUDE_PAT = [
    # 只写 "Original Soundtrack" 会漏掉 "Original Television Soundtrack"、
    # "Original Webtoon Soundtrack"、"Soundtrack Compilation" 这些变体，
    # 所以这里直接按 Soundtrack 整体排除——带这个词的一律是原声带。
    r"\bOST\b", r"Soundtrack", r"\bRemix(es)?\b", r"Instrumental",
    r"Japanese\s*Ver", r"\(Japanese", r"Japanese Version", r"日本語",
    r"Chinese\s*Ver", r"Chinese Version", r"Chinese Edition",
    r"English\s*Ver", r"English Version",
    r"Sped Up", r"Slowed", r"Acoustic\s*Ver", r"Live\s*Ver",
    r"Performance\s*Ver", r"Clean\s*Ver", r"Karaoke", r"MR\b",
]
RE_EXCLUDE = [re.compile(p, re.I) for p in EXCLUDE_PAT]
# 韩文/日文字符探测：日文专属假名用于识别日语版
RE_KANA = re.compile(r"[\u3040-\u30ff]")


def subtype_is_explicit(title):
    """
    标题里有没有明确的形态线索。

    用来区分「看标题就知道是 EP」和「实在没线索、只能靠曲目数猜」。
    跨源合并时优先采信前者。
    """
    low = (title or "").lower()
    if re.search(r"-\s*single\b", low) or re.search(r"-\s*ep\b", low):
        return True
    if re.search(r"\b(?:the\s+)?\d+(?:st|nd|rd|th)\s+(?:the\s+)?"
                 r"(?:mini\s+album|single\s+album|studio\s+album|full\s+album|"
                 r"mini|album|ep|single)\b", low):
        return True
    if re.search(r"\bmini\s+album\b|\bsingle\s+album\b|\bep\b|\bsingle\b", low):
        return True
    return False


def is_wanted(title, rtype=""):
    """判断是否符合用户设定的追踪范围。"""
    blob = f"{title} {rtype}"
    for rx in RE_EXCLUDE:
        if rx.search(blob):
            return False
    if RE_KANA.search(title or ""):
        return False
    return True


def parse_subtype(title, rtype="", track_count=0):
    """
    推断发行形态：Single / EP / Album。

    网易云不返回形态字段，只能从标题猜，所以这里要尽量细。
    优先级：
      1) 标题后缀（Apple Music 的 "XXX - Single" / "XXX - EP"，最可靠）
      2) 序数专辑写法（The 1st EP / 2nd Mini Album / 3rd Single Album）
      3) 裸关键词（Mini Album / Single Album / EP / Single）
      4) 形态字段（Apple Music collectionType，目前没有调用点传入，留作兜底）
      5) 曲目数启发式（1-2 首=单曲，3-7 首=EP，8 首以上=专辑）
    """
    low = (title or "").lower()

    # 1) 明确后缀
    if re.search(r"-\s*single\b", low):
        return "Single"
    if re.search(r"-\s*ep\b", low):
        return "EP"

    # 2) 序数写法：The 1st EP / 2nd Mini Album / 1st Single Album / 4th Album
    m = re.search(
        r"\b(?:the\s+)?\d+(?:st|nd|rd|th)\s+(?:the\s+)?"
        r"(mini\s+album|single\s+album|studio\s+album|full\s+album|"
        r"mini|album|ep|single)\b", low)
    if m:
        k = re.sub(r"\s+", " ", m.group(1)).strip()
        if k in ("mini album", "mini", "ep"):
            return "EP"
        if k in ("single album", "single"):
            return "Single"
        return "Album"

    # 3) 裸关键词
    if re.search(r"\bmini\s+album\b", low):
        return "EP"
    if re.search(r"\bsingle\s+album\b", low):
        return "Single"
    if re.search(r"\bep\b", low):
        return "EP"
    if re.search(r"\bsingle\b", low):
        return "Single"

    # 4) 形态字段
    rt = (rtype or "").lower()
    if re.search(r"\bmini\b|\bep\b", rt):
        return "EP"
    if re.search(r"\bsingle\b", rt):
        return "Single"
    if re.search(r"\balbum\b", rt):
        return "Album"

    # 5) 曲目数启发式（只有拿不到任何文字线索时才用）
    try:
        n = int(track_count or 0)
    except (TypeError, ValueError):
        n = 0
    if n == 1 or n == 2:
        return "Single"
    if 3 <= n <= 7:
        return "EP"
    if n >= 8:
        return "Album"
    return "Album"


# ---------------------------------------------------------- 各源入库
def step_kpopcal(con):
    log("· 抓取 kpopcal.com（官方确认事件）")
    artists, events = sources.fetch_kpopcal()
    if not artists and not events:
        log("  kpopcal 无数据，跳过")
        return 0
    n_art = 0
    for a in artists:
        name = (a.get("name") or "").strip()
        if not name:
            continue
        con.execute("""INSERT INTO artists(name,name_ko,kind,agency,debut_year,fandom)
                       VALUES(?,?,?,?,?,?)
                       ON CONFLICT(name) DO UPDATE SET
                         name_ko=excluded.name_ko,
                         kind=COALESCE(excluded.kind, artists.kind),
                         agency=COALESCE(excluded.agency, artists.agency),
                         debut_year=COALESCE(excluded.debut_year, artists.debut_year),
                         fandom=COALESCE(excluded.fandom, artists.fandom)""",
                    (name, a.get("name_ko"), a.get("kind"), a.get("agency"),
                     a.get("debut_year"), a.get("fandom")))
        n_art += 1
    n_ev = 0
    for e in events:
        eid = e.get("id") or e.get("slug")
        if not eid:
            continue
        con.execute("""INSERT INTO events(id,date,etype,category,title,artist,
                                          description,source_url,confirmed)
                       VALUES(?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET
                         date=excluded.date, etype=excluded.etype,
                         title=excluded.title, confirmed=excluded.confirmed""",
                    (eid, e.get("date"), e.get("type"), e.get("category"),
                     e.get("title"), e.get("artist_slug"), e.get("description"),
                     e.get("source"), 1 if e.get("confirmed") else 0))
        n_ev += 1
    con.commit()
    log(f"  艺人 {n_art} / 事件 {n_ev}")
    return n_art


def step_kpopping(con, months):
    """抓未来+最近月份日历。返回新增发行数。"""
    log("· 抓取 kpopping.com 日程")
    today = datetime.date.today()
    total = 0
    debut_map = {}
    groups_all, idols_all = set(), set()
    for offset in months:
        y = today.year
        m = today.month + offset
        while m > 12:
            m -= 12
            y += 1
        while m < 1:
            m += 12
            y -= 1
        rels, debs, gs, ids = sources.fetch_kpopping_month(y, m)
        debut_map.update(debs)
        groups_all |= gs
        idols_all |= ids
        cnt = 0
        for r in rels:
            if not r["artist"] or not r["date"]:
                continue
            if not is_wanted(r["title"], r["type"]):
                continue
            rid = f"kp:{r['source_id'] or (r['date'] + r['artist'] + r['title'])}"
            con.execute("""INSERT INTO releases(id,source,date,artist,title,rtype,image,url,extra)
                           VALUES(?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(id) DO UPDATE SET
                             date=excluded.date, title=excluded.title,
                             rtype=excluded.rtype, image=excluded.image""",
                        (rid, "kpopping", r["date"], r["artist"], r["title"],
                         r["type"] or parse_subtype(r["title"]), r["image"], "", ""))
            cnt += 1
        # 艺人入册
        for r in rels:
            nm = r["artist"]
            if nm:
                con.execute("INSERT OR IGNORE INTO artists(name) VALUES(?)", (nm,))
        total += cnt
        log(f"  {y:04d}-{m:02d}: 发行 {cnt}")
        time.sleep(1.0)

    # 团体 / 个人 分类回填（已有分类的不覆盖）
    kmap = {}
    for (nm,) in con.execute("SELECT name FROM artists"):
        kmap[_norm_key(nm)] = nm
    nkind = 0
    for kind, bucket in (("group", groups_all), ("solo", idols_all)):
        for ent in bucket:
            target = kmap.get(_norm_key(ent))
            if not target:
                continue
            cur = con.execute("SELECT kind FROM artists WHERE name=?", (target,)).fetchone()
            if cur and cur[0]:
                continue
            con.execute("UPDATE artists SET kind=? WHERE name=?", (kind, target))
            nkind += 1
    if nkind:
        log(f"  分类回填 团体/个人 {nkind} 条")

    # 出道年回填
    upd = 0
    for name, yr in debut_map.items():
        cur = con.execute("SELECT debut_year FROM artists WHERE name=?", (name,)).fetchone()
        if cur and cur[0] is None:
            con.execute("UPDATE artists SET debut_year=? WHERE name=?", (yr, name))
            upd += 1
    con.commit()
    if upd:
        log(f"  回填出道年 {upd} 条")
    return total


def step_kind_fallback(con):
    """内置已知名单兜底：脚本抓不到的分类，用手工名录补。"""
    n = 0
    for (nm,) in con.execute(
            "SELECT name FROM artists WHERE kind IS NULL OR kind=''"):
        k = names.kind_of(nm)
        if k:
            con.execute("UPDATE artists SET kind=? WHERE name=?", (k, nm))
            n += 1
    if n:
        con.commit()
    return n


def step_gender(con):
    """
    补艺人性别，用于「男团 / 女团 / 混声团 / 男歌手 / 女歌手」筛选。
    来源优先级：
      1) kpopping 的四个性别分类页（女团 / 男团 / 女歌手 / 男歌手）
      2) names.GENDER_OVERRIDE 手工补录（只写有把握的）
      3) 团体若在女团、男团名录里都没有，抓详情页简介看是否写了 "co-ed" → 混声团
    只处理 gender 为空的艺人，因此可增量运行。
    """
    log("· 抓取 kpopping 性别分类（女团 / 男团 / 女歌手 / 男歌手）")
    d = sources.fetch_kpopping_gender()
    if not any(d.values()):
        log("  无数据，跳过")
        return 0
    gk = {k: {names.norm_gkey(x) for x in v} for k, v in d.items()}

    # soloist 是历史遗留值，统一成 solo，前端才好判断
    con.execute("UPDATE artists SET kind='solo' WHERE kind='soloist'")

    rows = con.execute(
        "SELECT name,kind,gender,coed_checked FROM artists").fetchall()
    upd = {"F": 0, "M": 0, "X": 0}
    n_kind = 0
    for nm, kind, old_g, coed_done in rows:
        key = names.norm_gkey(nm)
        # kind 为空时两种名录都要试，否则只按现有 kind 试
        g = src = None
        if kind == "group":
            if key in gk["gg"]:
                g, src = "F", "group"
            elif key in gk["bg"]:
                g, src = "M", "group"
        elif kind:
            if key in gk["fi"]:
                g, src = "F", "solo"
            elif key in gk["mi"]:
                g, src = "M", "solo"
        else:
            if key in gk["gg"]:
                g, src = "F", "group"
            elif key in gk["bg"]:
                g, src = "M", "group"
            elif key in gk["fi"]:
                g, src = "F", "solo"
            elif key in gk["mi"]:
                g, src = "M", "solo"

        if g is None:
            g = names.gender_override(nm)
        # 名录里都没有，且看起来是团体 → 抓详情页看有没有 co-ed 徽章（要发请求，只在这里发）
        # 查过就记一笔，下轮不再重复请求
        if g is None and not old_g and kind != "solo" and not coed_done:
            is_x = sources.group_is_coed(nm)
            con.execute("UPDATE artists SET coed_checked=1 WHERE name=?", (nm,))
            if is_x:
                g, src = "X", "group"

        if g and not old_g:
            con.execute("UPDATE artists SET gender=? WHERE name=?", (g, nm))
            upd[g] += 1
        if src and not kind:
            con.execute("UPDATE artists SET kind=? WHERE name=?", (src, nm))
            n_kind += 1
    con.commit()
    log(f"  女 {upd['F']} / 男 {upd['M']} / 混声 {upd['X']}"
        + (f"，顺带补 kind {n_kind} 条" if n_kind else ""))
    return sum(upd.values())


# 已确认漏网的新团体：kpopping 不收（它们面向中国市场），
# 但 Apple Music 和网易云都有。走 SEED 直接补。
SEED_ARTISTS = ["A2O LITE", "A2O MAY", "A2O SOUL"]


def _ne_put(con, artist, alb):
    """把一张网易云专辑写进库。返回 1 表示新增。"""
    title = (alb.get("title") or "").strip()
    date = alb.get("date") or ""
    if not title or not date or not is_wanted(title):
        return 0
    # 网易云会给出很老的老专辑（实测最早到 1992 年），超出追踪窗口的不要
    floor = (datetime.date.today()
             - datetime.timedelta(days=HISTORY_DAYS)).isoformat()
    if date < floor:
        return 0
    rid = "ne:" + str(alb.get("nid") or (date + artist + title))
    con.execute("""INSERT INTO releases(id,source,date,artist,title,rtype,image,url,extra)
                   VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO NOTHING""",
                (rid, "netease", date, artist, title,
                 parse_subtype(title), alb.get("image") or "", "", ""))
    return 1


def step_netease_fill(con, cap=70):
    """
    给已收录艺人补专辑：Apple Music 没上架的，网易云可能有。

    不能全量跑——218 个艺人逐个查要十几分钟。只补**活跃艺人**
    （最近 NE_ACTIVE_DAYS 天有发行的），并按 cap 限流，跑不完下次接着跑。
    ne_id 会缓存进 artists 表，同一个艺人只搜一次。
    """
    log("· 网易云补专辑（Apple Music 缺的）")
    floor = (datetime.date.today()
             - datetime.timedelta(days=NE_ACTIVE_DAYS)).isoformat()
    rows = con.execute(
        "SELECT name,ne_id FROM artists WHERE name IN "
        "(SELECT DISTINCT artist FROM releases WHERE date >= ?) "
        "ORDER BY name", (floor,)).fetchall()
    todo = [r for r in rows if not r[1]][:cap]          # 还没查过网易云的优先
    if not todo:
        todo = rows[:cap]
    log(f"  活跃艺人 {len(rows)} 个，本次处理 {len(todo)} 个")

    added = 0
    for nm, ne_id in todo:
        if not ne_id:
            hit = sources.netease_search_artist(nm)
            if hit:
                ne_id = hit[0]
            con.execute("UPDATE artists SET ne_id=? WHERE name=?", (ne_id, nm))
        if not ne_id:
            continue
        have = {r[0] for r in con.execute(
            "SELECT date FROM releases WHERE artist=?", (nm,)).fetchall()}
        for alb in sources.netease_artist_albums(ne_id):
            if alb["date"] in have:
                continue
            added += _ne_put(con, nm, alb)
        time.sleep(0.15)
    con.commit()
    log(f"  补齐 {added} 张")
    return added


def step_netease_tracks(con, cap=400):
    """
    补网易云专辑的曲目。

    网易云的专辑列表接口不返回曲目，详情页才有，每张专辑要单独请求一次。
    因此只补**没补过**的（用 extra.ne_detail 标记），跑过一遍之后每天只需请求新增的几张。
    extra.trackCount 顺便给形态判断提供曲目数线索。
    """
    log("· 网易云补曲目")
    rows = [r for r in con.execute(
        "SELECT id,extra FROM releases WHERE source='netease'").fetchall()
        if "ne_detail" not in (r[1] or "")]
    todo = rows[:cap]
    if not todo:
        log("  均已补齐，跳过")
        return 0

    n_tr = 0
    done = 0
    for rid, extra in todo:
        nid = rid.split(":", 1)[1] if ":" in rid else ""
        try:
            extra = json.loads(extra) if extra else {}
        except Exception:                           # noqa: BLE001
            extra = {}
        det = sources.netease_album_detail(nid)
        if det:
            tracks = det.get("tracks") or []
            for i, t in enumerate(tracks, 1):
                tid = f"{rid}:{i}"
                con.execute("""INSERT INTO tracks(id,release_id,artist,name,
                                   track_no,disc,duration_ms,genre,preview)
                               VALUES(?,?,?,?,?,?,?,?,?)
                               ON CONFLICT(id) DO UPDATE SET
                                 name=excluded.name,
                                 duration_ms=excluded.duration_ms""",
                            (tid, rid, "",
                             t.get("name") or "", t.get("no") or i,
                             t.get("disc") or 1, t.get("ms") or 0, "", ""))
            extra["trackCount"] = det.get("size") or len(tracks)
            extra["company"] = det.get("company") or ""
            n_tr += len(tracks)
        extra["ne_detail"] = 1
        con.execute("UPDATE releases SET extra=? WHERE id=?",
                    (json.dumps(extra, ensure_ascii=False), rid))
        done += 1
        if done % 20 == 0:
            con.commit()
        time.sleep(0.12)
    con.commit()
    log(f"  补齐 {done} 张专辑 / {n_tr} 首曲目")
    return n_tr


RE_CJK_ONLY = re.compile(r"^[\u4e00-\u9fff·\s]+$")


def _am_put(con, aname, a):
    """把一张 Apple Music 专辑写进库（发现新团时用，后面全量阶段会补曲目）。"""
    if not a.get("date") or not is_wanted(a.get("title") or ""):
        return 0
    rid = "am:" + str(a.get("collectionId") or (a["date"] + aname + a["title"]))
    con.execute("""INSERT INTO releases(id,source,date,artist,title,rtype,image,url,extra)
                   VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO NOTHING""",
                (rid, "apple", a["date"], aname, a["title"],
                 parse_subtype(a["title"]), a.get("image") or "", "", ""))
    return 1


def step_netease_discover(con, deep=False):
    """
    发现 kpopping 没收录的团体。两条路：

    1) SEED_ARTISTS：已经确认漏网的团（比如 A2O 系列），直接补。
       这条路必走，因为实测它们在新碟榜里翻不到。
    2) deep=True 时再扫网易云新碟榜。新碟榜噪音大（OST、中文歌、独立音乐），
       所以命中新名字后要用 Apple Music 的 primaryGenreName 验一下是不是 K-Pop。
    """
    log("· 网易云：发现新团体" + ("（含新碟榜扫描）" if deep else "（仅已确认名单）"))
    known = {names.norm_gkey(r[0]) for r in
             con.execute("SELECT name FROM artists")}
    cands = {}
    for s in SEED_ARTISTS:
        if names.norm_gkey(s) not in known:
            cands.setdefault(s, [])

    if deep:
        for area in ("KR", "ALL"):
            for alb in sources.netease_new_albums(area=area, pages=2):
                an = (alb.get("artist") or "").strip()
                if (not an or names.norm_gkey(an) in known
                        or RE_CJK_ONLY.match(an)          # 纯中文名，多半不是 K-pop 偶像
                        or not is_wanted(alb.get("title") or "")):
                    continue
                cands.setdefault(an, []).append(alb)
        # 新碟榜一次能冒出上百个陌生名字，限流，不然一次跑不完
        if len(cands) > 40:
            keep = {k: cands[k] for k in list(cands)[:40]}
            cands = keep

    def fill_artist(aname, aid, albs):
        """给一个艺人把三个来源的专辑都补上。返回新增张数。"""
        n = 0
        for alb in albs:                                  # 新碟榜里冒出来的
            n += _ne_put(con, aname, alb)
        ne = sources.netease_search_artist(aname)         # 网易云全量
        if ne:
            con.execute("UPDATE artists SET ne_id=? WHERE name=?", (ne[0], aname))
            for alb in sources.netease_artist_albums(ne[0]):
                n += _ne_put(con, aname, alb)
        for a in (sources.itunes_lookup_albums(aid) or []):   # Apple Music
            n += _am_put(con, aname, a)
        return n

    added = n_art = 0
    for an, albs in cands.items():
        hit = sources.itunes_find_kpop(an)
        if not hit:
            continue                                      # Apple Music 都不认作 K-Pop，跳过
        aid, aname, _genre = hit
        con.execute("INSERT OR IGNORE INTO artists(name,am_id) VALUES(?,?)", (aname, aid))
        n_art += 1
        added += fill_artist(aname, aid, albs)
        time.sleep(0.25)

    # 兜底：已经入册但一张专辑都没有的艺人（多半是上一轮刚发现的新团）。
    # 它们不在「活跃艺人」里（没有发行），补专辑那步会漏掉，这里补一次。
    orphans = [r[0] for r in con.execute(
        "SELECT name FROM artists WHERE am_id IS NOT NULL AND name NOT IN "
        "(SELECT DISTINCT artist FROM releases)")]
    if orphans:
        log(f"  补 {len(orphans)} 个还没专辑的艺人")
    for nm in orphans:
        aid = con.execute("SELECT am_id FROM artists WHERE name=?", (nm,)).fetchone()
        if not aid or not aid[0]:
            continue
        added += fill_artist(nm, aid[0], [])
        time.sleep(0.25)

    if added or n_art:
        con.commit()
    log(f"  新收录艺人 {n_art} 个 / 专辑 {added} 张")
    return n_art


def _norm_key(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def step_roster(con):
    """用 kpopping 名录补艺人类型（group / solo）。kpopcal 只覆盖 52 个，太稀疏。"""
    log("· 抓取 kpopping 艺人名录（团体 / 个人）")
    groups, idols = sources.fetch_kpopping_roster()
    if not groups and not idols:
        log("  无数据，跳过")
        return 0
    kmap = {}
    for (nm,) in con.execute("SELECT name FROM artists"):
        kmap[_norm_key(nm)] = nm

    upd = {"group": 0, "solo": 0}
    for kind, bucket in (("group", groups), ("solo", idols)):
        for ent in bucket:
            target = kmap.get(_norm_key(ent))
            if not target:
                continue
            cur = con.execute("SELECT kind FROM artists WHERE name=?", (target,)).fetchone()
            if cur and cur[0]:
                continue                       # 已有分类的不覆盖
            con.execute("UPDATE artists SET kind=? WHERE name=?", (kind, target))
            upd[kind] += 1
    con.commit()
    log(f"  团体 {upd['group']} / 个人 {upd['solo']}")
    return upd["group"] + upd["solo"]


def step_normalize_artists(con):
    """
    把韩文艺人名反查成英文官方名（kpopping 日历里带韩文名，Apple Music 韩国区也用韩文）。
    用 Apple Music 搜韩文名，取返回的 artistName（通常是英文规范名）。
    查不到的保留韩文——按用户设定的优先级，韩文是最后手段。
    """
    log("· 归一韩文艺人名（反查 Apple Music）")
    ko_names = set()
    for (nm,) in con.execute("SELECT name FROM artists WHERE name GLOB '*[가-힣]*'"):
        ko_names.add(nm)
    for (nm,) in con.execute("SELECT DISTINCT artist FROM releases WHERE artist GLOB '*[가-힣]*'"):
        if nm:
            ko_names.add(nm)
    todo = []
    for nm in sorted(ko_names):
        r = con.execute("SELECT am_id FROM artists WHERE name=?", (nm,)).fetchone()
        if r and r[0]:
            continue
        todo.append(nm)
    if not todo:
        log("  无需处理")
        return 0

    fixed = 0
    for nm in todo:
        try:
            # --- 组合名（含 & 或 , ）：逐段归一后重组 ---
            parts = [p.strip() for p in names.RE_SPLIT.split(nm) if p.strip()]
            if len(parts) > 1:
                new_parts, changed = [], False
                for p in parts:
                    if not names.has_hangul(p):
                        new_parts.append(p)
                        continue
                    if p in names.ARTIST_KO:
                        new_parts.append(names.ARTIST_KO[p])
                        changed = True
                        continue
                    gp = sources.itunes_search_artist_any(p)
                    time.sleep(AM_SLEEP)
                    if gp and gp[1] and not names.has_hangul(gp[1]):
                        new_parts.append(gp[1].strip())
                        changed = True
                    else:
                        new_parts.append(p)
                if changed:
                    new_name = " & ".join(new_parts[:3])
                    con.execute("UPDATE releases SET artist=? WHERE artist=?", (new_name, nm))
                    con.execute("UPDATE tracks SET artist=? WHERE artist=?", (new_name, nm))
                    if con.execute("SELECT 1 FROM artists WHERE name=?", (nm,)).fetchone():
                        con.execute("DELETE FROM artists WHERE name=?", (nm,))
                    con.commit()
                    fixed += 1
                continue

            got = sources.itunes_search_artist_any(nm)
            time.sleep(AM_SLEEP)
            if not got:
                continue
            aid, en = got
            if not en or names.has_hangul(en) or en.strip() == nm:
                continue
            en = names.norm_artist(en.strip())
            exist = con.execute("SELECT 1 FROM artists WHERE name=?", (en,)).fetchone()
            if exist:
                con.execute("UPDATE releases SET artist=? WHERE artist=?", (en, nm))
                con.execute("UPDATE tracks SET artist=? WHERE artist=?", (en, nm))
                con.execute("DELETE FROM artists WHERE name=?", (nm,))
            else:
                # am_updated 置空，让后续 Apple Music 步骤重新拉专辑与曲目
                con.execute("UPDATE artists SET name=?, am_id=?, am_updated=NULL WHERE name=?",
                            (en, aid, nm))
                con.execute("UPDATE releases SET artist=? WHERE artist=?", (en, nm))
                con.execute("UPDATE tracks SET artist=? WHERE artist=?", (en, nm))
            con.commit()
            fixed += 1
        except Exception:                           # noqa: BLE001
            continue
    log(f"  归一 {fixed} / {len(todo)} 个")
    return fixed


def step_apple_music(con, limit_artists=None, force=False):
    """为艺人补齐 Apple Music ID 与历史专辑。返回新增专辑数。"""
    log("· 抓取 Apple Music 历史专辑")
    rows = con.execute(
        "SELECT name FROM artists ORDER BY name").fetchall()
    artist_names = [r[0] for r in rows]
    if limit_artists:
        artist_names = artist_names[:limit_artists]

    cutoff = (datetime.date.today()
              - datetime.timedelta(days=HISTORY_DAYS)).isoformat()
    fresh = ((datetime.datetime.now() - datetime.timedelta(days=AM_CACHE_DAYS))
             .strftime("%Y-%m-%d %H:%M:%S"))

    added = 0
    processed = 0
    for name in artist_names:
        try:
            rec = con.execute(
                "SELECT am_id, am_url, am_updated FROM artists WHERE name=?",
                (name,)).fetchone()
            am_id, am_url = (rec[0], rec[1]) if rec else (None, None)
            am_updated = rec[2] if rec else None

            if am_id:
                if not force and am_updated and am_updated >= fresh:
                    continue        # 缓存新鲜，跳过
            else:
                got = sources.itunes_search_artist(name)
                time.sleep(AM_SLEEP)
                if not got:
                    continue
                am_id, am_name = got
                con.execute("UPDATE artists SET am_id=?, am_updated=? WHERE name=?",
                            (am_id, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), name))
                con.commit()

            # 主艺人英文名（不用 API 返回的 artistName，韩国区会返回韩文）
            main_artist = names.norm_artist(name)

            albums = sources.itunes_lookup_albums(am_id)
            time.sleep(AM_SLEEP)
            if not albums:
                continue

            kept_colls = set()
            for a in albums:
                title = (a.get("collectionName") or "").strip()
                if not title:
                    continue
                rel_date = (a.get("releaseDate") or "")[:10]
                if not rel_date or rel_date < cutoff:
                    continue
                if not is_wanted(title, ""):
                    continue
                cid = str(a.get("collectionId"))
                rid = f"am:{cid}"
                extra = {
                    "genre": a.get("primaryGenreName") or "",
                    "copyright": (a.get("copyright") or "").strip(),
                    "trackCount": a.get("trackCount") or 0,
                }
                con.execute("""INSERT INTO releases(id,source,date,artist,title,rtype,image,url,extra)
                               VALUES(?,?,?,?,?,?,?,?,?)
                               ON CONFLICT(id) DO UPDATE SET
                                 date=excluded.date, artist=excluded.artist,
                                 title=excluded.title,
                                 image=excluded.image, url=excluded.url,
                                 extra=excluded.extra""",
                            (rid, "apple", rel_date, main_artist, title,
                             parse_subtype(title), a.get("artworkUrl100") or "",
                             a.get("collectionViewUrl") or "",
                             json.dumps(extra, ensure_ascii=False)))
                kept_colls.add(cid)
                added += 1

            # 曲目：iTunes 按 collectionId 查 entity=song 返回空，
            # 只能按 artistId 查，一次请求拿该艺人全部曲目再按专辑归组
            if kept_colls:
                songs = sources.itunes_lookup_songs(am_id)
                time.sleep(AM_SLEEP)
                for s in songs:
                    cid = str(s.get("collectionId"))
                    if cid not in kept_colls:
                        continue
                    tid = str(s.get("trackId") or "")
                    if not tid:
                        continue
                    con.execute("""INSERT INTO tracks(id,release_id,artist,name,
                                       track_no,disc,duration_ms,genre,preview)
                                   VALUES(?,?,?,?,?,?,?,?,?)
                                   ON CONFLICT(id) DO UPDATE SET
                                     name=excluded.name,
                                     duration_ms=excluded.duration_ms,
                                     genre=excluded.genre""",
                                (tid, f"am:{cid}", main_artist,
                                 (s.get("trackName") or "").strip(),
                                 s.get("trackNumber"), s.get("discNumber"),
                                 s.get("trackTimeMillis"),
                                 s.get("primaryGenreName") or "",
                                 s.get("previewUrl") or ""))

            if not am_url:
                for a in albums:
                    u = a.get("artistViewUrl") or a.get("collectionViewUrl")
                    if u and "/artist/" in u:
                        con.execute("UPDATE artists SET am_url=? WHERE name=?",
                                    (u.split("?")[0], name))
                        break
            con.execute("UPDATE artists SET am_updated=? WHERE name=?",
                        (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), name))
            con.commit()
            processed += 1
        except Exception:                           # noqa: BLE001
            log(f"  ! 艺人 {name} 处理异常: {traceback.format_exc(limit=1).strip()}")
            continue

    log(f"  处理艺人 {processed} / 专辑记录 {added}")
    return added


def step_purge_scope(con):
    """
    清掉不符合追踪范围的条目。

    排除规则会随版本收紧（比如发现 OST 变体没被拦住），
    老数据里已经混进去的就得回头清一次，否则规则改了等于没改。
    """
    doomed = []
    for rid, title in con.execute("SELECT id,title FROM releases"):
        if not is_wanted(title):
            doomed.append(rid)
    if not doomed:
        return 0
    for rid in doomed:
        con.execute("DELETE FROM tracks WHERE release_id=?", (rid,))
        con.execute("DELETE FROM releases WHERE id=?", (rid,))
    con.commit()
    log(f"  清掉越界条目 {len(doomed)} 条（OST / Remix / 伴奏等）")
    return len(doomed)


def step_retype(con):
    """
    用当前规则重算所有发行的形态（Single / EP / Album）。

    规则升级后老数据的分类会过时，这里统一刷一遍。
    Apple Music 的专辑把 trackCount 存在 extra 里，可以当兜底线索；
    网易云没有曲目数，只能靠标题。
    """
    rows = list(con.execute("SELECT id,title,extra,rtype FROM releases"))
    changed = 0
    for rid, title, extra, old in rows:
        n = 0
        if extra:
            try:
                n = int((json.loads(extra) or {}).get("trackCount") or 0)
            except Exception:                       # noqa: BLE001
                n = 0
        new = parse_subtype(title, "", n)
        if new != old:
            con.execute("UPDATE releases SET rtype=? WHERE id=?", (new, rid))
            changed += 1
    if changed:
        con.commit()
        log(f"  重新归类 {changed} 条发行")
    return changed


# -------------------------------------------------------------- 导出 data.js
def export_data(con):
    log("· 导出 data.js")

    # --- 艺人名归一：清掉韩文，界面上不出现韩文 ---
    fixes = {}
    for (nm,) in con.execute("SELECT DISTINCT artist FROM releases").fetchall():
        if nm and names.has_hangul(nm):
            nn = names.clean_mixed(nm) or names.norm_artist(nm)
            if nn and nn != nm:
                fixes[nm] = nn
    if fixes:
        for old, new in fixes.items():
            con.execute("UPDATE releases SET artist=? WHERE artist=?", (new, old))
            con.execute("UPDATE tracks SET artist=? WHERE artist=?", (new, old))
        con.commit()
        log(f"  归一韩文艺人名 {len(fixes)} 个")

    artists = []
    for r in con.execute("""SELECT name,name_ko,kind,gender,agency,debut_year,fandom
                            FROM artists ORDER BY name"""):
        artists.append({
            "name": r[0], "zh": names.zh_of(r[0]), "name_ko": r[1],
            "kind": r[2], "gender": r[3], "agency": r[4],
            "parent": names.parent_agency(r[4]) if r[4] else None,
            "debut_year": r[5], "fandom": r[6],
        })

    # --- 曲目：按专辑归组 ---
    tmap = {}
    for r in con.execute("""SELECT release_id,name,track_no,disc,duration_ms,genre
                            FROM tracks"""):
        tmap.setdefault(r[0], []).append({
            "n": r[1], "no": r[2], "disc": r[3], "ms": r[4], "g": r[5],
        })
    for k in tmap:
        tmap[k].sort(key=lambda x: ((x["disc"] or 1), (x["no"] or 0)))

    # 合作曲归主艺人：'Alok, 나연 & TWICE' -> 'TWICE'
    known = set(a["name"] for a in artists)
    known_lower = {}
    for n in known:
        known_lower.setdefault(n.lower(), n)
    n_rec = [0]

    def reconcile(nm):
        if not nm:
            return nm
        if nm in known:
            return nm
        hit = known_lower.get(nm.lower())      # 大小写不同视为同一艺人
        if hit:
            n_rec[0] += 1
            return hit
        out = names.reconcile_artist(nm, known)
        if out != nm:
            n_rec[0] += 1
        return out

    today = datetime.date.today()
    floor = (today - datetime.timedelta(days=HISTORY_DAYS)).isoformat()
    releases = []
    for r in con.execute("""SELECT id,source,date,artist,title,rtype,image,url,extra
                            FROM releases
                            WHERE date >= ? ORDER BY date DESC""", (floor,)):
        extra = {}
        try:
            extra = json.loads(r[8]) if r[8] else {}
        except Exception:                           # noqa: BLE001
            pass
        rel = {
            "id": r[0], "source": r[1], "date": r[2], "artist": reconcile(r[3]),
            "title": r[4], "rtype": r[5], "image": r[6],
            "genre": extra.get("genre") or "",
            "copyright": extra.get("copyright") or "",
            "trackCount": extra.get("trackCount") or 0,
        }
        tr = tmap.get(r[0])
        if tr:
            rel["tracks"] = tr
            rel["trackTotal"] = len(tr)
            rel["durationMs"] = sum((t["ms"] or 0) for t in tr)
        releases.append(rel)

    # --- 去重：kpopping / Apple Music / 网易云可能收录同一张专辑 ---
    # 跨源的坑比想象中多：
    #   标题写法不同  "PAPARAZZI ARRIVE"        vs "PAPARAZZI ARRIVE - The 1st EP"
    #   合作标注不同  "B.B.B"                    vs "B.B.B (feat. A2O LTG)"
    #   日期差几天    Apple 2026-07-17           vs 网易云 2026-07-16
    # 所以不能拿 (艺人, 标题, 日期) 直接当键，要先归一再按日期就近合并。
    def norm_title(t):
        t = (t or "").lower().strip()
        # 合作标注：(feat. X) / (ft. X) / (with X)
        t = re.sub(r"[\(（]\s*(?:feat\.?|ft\.?|with)\s+[^)）]*[)）]", " ", t)
        # 序数后缀："- The 1st EP" / "- 2nd Mini Album"
        t = re.sub(r"\s*[-–—]\s*(?:the\s+)?\d+(?:st|nd|rd|th)\s+"
                   r"(?:mini\s+album|single\s+album|studio\s+album|full\s+album|"
                   r"album|ep|single)\s*$", " ", t)
        # 普通后缀："- Single" / "- EP" / "- Mini Album"
        t = re.sub(r"\s*[-–—]\s*(?:digital\s+single|single\s+album|mini\s+album|"
                   r"studio\s+album|album|single|ep)\s*$", " ", t)
        return re.sub(r"[^0-9a-z\uac00-\ud7a3]+", "", t)

    def _score(r):
        """同一张专辑有多份时留哪份：有曲目 > 有曲目数 > Apple Music。"""
        return (1 if r.get("tracks") else 0,
                1 if (r.get("trackCount") or 0) else 0,
                1 if r["source"] == "apple" else 0)

    def _near(d1, d2):
        """跨源日期会差一两天（时区、上架时间不同），容忍 DATE_TOL_DAYS 天。"""
        if not d1 or not d2:
            return False
        try:
            a = datetime.date.fromisoformat(d1)
            b = datetime.date.fromisoformat(d2)
        except ValueError:
            return d1 == d2
        return abs((a - b).days) <= DATE_TOL_DAYS

    groups = {}
    for rel in releases:
        groups.setdefault((rel["artist"], norm_title(rel["title"])), []).append(rel)

    dedup = []
    for items in groups.values():
        items.sort(key=_score, reverse=True)
        clusters = []
        for rel in items:                       # 按日期就近聚成若干簇
            hit = None
            for c in clusters:
                if _near(c[0]["date"], rel["date"]):
                    hit = c
                    break
            if hit is None:
                clusters.append([rel])
            else:
                hit.append(rel)
        for c in clusters:
            best = c[0]
            # 形态以「标题里带明确线索」的那份为准。
            # 否则会出现同一个 EP，Apple 的裸标题靠曲目数猜成正规专、
            # 网易云的 "The 1st EP" 才是对的，两边打架。
            for r in c:
                if subtype_is_explicit(r["title"]):
                    best = dict(best)
                    best["rtype"] = parse_subtype(
                        r["title"], "", r.get("trackCount") or 0)
                    break
            dedup.append(best)
    n_dup = len(releases) - len(dedup)
    if n_dup:
        log(f"  合并重复收录 {n_dup} 条")
    releases = dedup

    events = []
    for r in con.execute("""SELECT id,date,etype,category,title,artist,description,confirmed
                            FROM events ORDER BY date"""):
        events.append({
            "id": r[0], "date": r[1], "etype": r[2], "category": r[3],
            "title": r[4], "artist": r[5], "description": r[6],
            "confirmed": r[7],
        })

    amap = {a["name"]: a for a in artists}
    for rel in releases:
        a = amap.get(rel["artist"])
        rel["debut_year"] = a["debut_year"] if a else None
        rel["agency"] = (a["parent"] or a["agency"]) if a else None
        rel["kind"] = a["kind"] if a else None
        rel["gender"] = a["gender"] if a else None
        rel["fandom"] = a["fandom"] if a else None
        rel["zh"] = a["zh"] if a else None

    # --- 成员生日（首页「今天生日」用；没有也不影响其它功能）---
    members = []
    try:
        for r in con.execute("SELECT g,n,b FROM members ORDER BY g,n"):
            if r[1] and r[2]:
                members.append({"g": r[0], "n": r[1], "b": r[2]})
    except Exception:                               # noqa: BLE001
        members = []

    # --- 分片：主文件只留最近 RECENT_DAYS 天，更早的按年份切片 ---
    cutoff = (datetime.date.today() - datetime.timedelta(days=RECENT_DAYS)).isoformat()
    recent, by_year = [], {}
    for r in releases:
        if r.get("date") and r["date"] >= cutoff:
            recent.append(r)
        else:
            by_year.setdefault((r.get("date") or "0000")[:4], []).append(r)
    years = {y: len(v) for y, v in sorted(by_year.items(), reverse=True)}
    n_old = len(releases) - len(recent)

    # --- B 站官方 MV（只收官方账号发布且校验过没失效的）---
    mvs = []
    try:
        for r in con.execute("""SELECT bvid,artist,uname,title,play,pubdate,pic
                                FROM bili WHERE dead=0 AND play>0
                                ORDER BY play DESC"""):
            mvs.append({"v": r[0], "a": r[1], "u": r[2], "t": r[3],
                        "p": r[4], "d": r[5], "i": r[6] or ""})
    except Exception:                               # noqa: BLE001
        mvs = []

    payload = {
        "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "artists": artists,
        "releases": recent,
        "events": events,
        "members": members,
        "mvs": mvs,
        "years": years,          # {"2025": 523, ...} 供前端显示「加载某年」
        "recentDays": RECENT_DAYS,
        "olderCount": n_old,
    }
    blob = ("window.__KPOP_DATA__ = "
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            + ";\n")

    # 年份切片：全局变量带年份后缀，避免并发加载时互相覆盖
    for y, lst in by_year.items():
        cblob = ("window.__KPOP_CHUNK_%s__ = " % y
                 + json.dumps({"y": y, "releases": lst},
                              ensure_ascii=False, separators=(",", ":"))
                 + ";\n")
        cpath = os.path.join(DATA_DIR, "data-%s.js" % y)
        ctmp = cpath + ".tmp"
        with open(ctmp, "w", encoding="utf-8") as f:
            f.write(cblob)
        if os.path.exists(cpath):
            os.remove(cpath)
        os.replace(ctmp, cpath)

    tmp = OUT_JS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(blob)
    if os.path.exists(OUT_JS):
        os.remove(OUT_JS)
    os.replace(tmp, OUT_JS)          # 原子替换，避免写一半被读到
    n_tracks = sum(len(r.get("tracks", [])) for r in releases)
    n_zh = sum(1 for a in artists if a.get("zh"))
    log(f"  艺人 {len(artists)}（中文名 {n_zh}）/ 发行 {len(releases)} / "
        f"曲目 {n_tracks} / 事件 {len(events)} / 成员生日 {len(members)} / 官方MV {len(mvs)}"
        + (f"（合作曲归主艺人 {n_rec[0]}）" if n_rec[0] else ""))
    log(f"  分片：主文件 {len(recent)} 张（近 {RECENT_DAYS} 天）"
        f" + {len(by_year)} 个年份切片共 {n_old} 张"
        f" -> 主 {os.path.getsize(OUT_JS)/1024:.0f} KB"
        + (f"，切片 {dict(list(years.items())[:4])}" if years else ""))
    return payload


# ------------------------------------------------------------------ 主流程
def step_birthdays(con):
    """成员生日（kpopping 档案页 JSON-LD）。增量：只补库里还缺的艺人。"""
    import birthdays  # noqa: PLC0415
    birthdays.fetch_birthdays(con)


def main():
    full = "--full" in sys.argv
    con = get_db()
    log("=" * 56)
    log("开始更新 K-Pop 数据" + (" （全量）" if full else ""))

    # --export-only：跳过所有网络抓取，只用现有数据库重新生成 data.js
    if "--export-only" in sys.argv:
        log("· 仅导出模式，跳过网络抓取")
        try:
            step_normalize_artists(con)
        except Exception:                           # noqa: BLE001
            pass
        try:
            step_purge_scope(con)
        except Exception:                           # noqa: BLE001
            log("  ! 清理越界条目失败: " + traceback.format_exc(limit=1).strip())
        try:
            step_retype(con)
        except Exception:                           # noqa: BLE001
            log("  ! 重新归类失败: " + traceback.format_exc(limit=1).strip())
        export_data(con)
        con.close()
        log("更新完成")
        return 0

    ok_any = False
    try:
        step_kpopcal(con)
        ok_any = True
    except Exception:                               # noqa: BLE001
        log("  ! kpopcal 阶段失败: " + traceback.format_exc(limit=1).strip())

    try:
        months = [-1, 0, 1, 2] if full else [0, 1]
        step_kpopping(con, months)
        ok_any = True
    except Exception:                               # noqa: BLE001
        log("  ! kpopping 阶段失败: " + traceback.format_exc(limit=1).strip())

    lim = None
    if "--limit" in sys.argv:
        i = sys.argv.index("--limit")
        if i + 1 < len(sys.argv):
            lim = int(sys.argv[i + 1])

    if "--quick" not in sys.argv:
        try:
            step_roster(con)
        except Exception:                           # noqa: BLE001
            log("  ! 艺人名录失败: " + traceback.format_exc(limit=1).strip())
        try:
            step_normalize_artists(con)
        except Exception:                           # noqa: BLE001
            log("  ! 艺人名归一失败: " + traceback.format_exc(limit=1).strip())

    # 先去网易云新碟榜找找有没有 kpopping 漏掉的新团，
    # 再走 Apple Music，这样新发现的团能直接拿到曲目
    try:
        # 新碟榜扫描比较慢，只在 --full 时做；平时只补已确认名单
        step_netease_discover(con, deep=full)
    except Exception:                           # noqa: BLE001
        log("  ! 网易云发现失败: " + traceback.format_exc(limit=1).strip())

    if "--quick" in sys.argv:
        log("· 跳过 Apple Music（--quick 模式）")
    else:
        try:
            step_apple_music(con, limit_artists=lim, force=full)
            ok_any = True
        except Exception:                           # noqa: BLE001
            log("  ! Apple Music 阶段失败: " + traceback.format_exc(limit=1).strip())

    try:
        step_netease_fill(con)
    except Exception:                               # noqa: BLE001
        log("  ! 网易云补专辑失败: " + traceback.format_exc(limit=1).strip())

    if "--quick" in sys.argv:
        log("· 跳过网易云补曲目（--quick 模式）")
    else:
        try:
            step_netease_tracks(con)
        except Exception:                           # noqa: BLE001
            log("  ! 网易云补曲目失败: " + traceback.format_exc(limit=1).strip())

    try:
        n = step_kind_fallback(con)
        if n:
            log(f"  已知名单补分类 {n} 条")
    except Exception:                               # noqa: BLE001
        pass

    try:
        step_gender(con)
    except Exception:                               # noqa: BLE001
        log("  ! 性别分类失败: " + traceback.format_exc(limit=1).strip())

    try:
        step_birthdays(con)
    except Exception:                               # noqa: BLE001
        log("  ! 生日抓取失败: " + traceback.format_exc(limit=1).strip())

    try:
        step_purge_scope(con)
    except Exception:                               # noqa: BLE001
        log("  ! 清理越界条目失败: " + traceback.format_exc(limit=1).strip())

    try:
        step_retype(con)
    except Exception:                               # noqa: BLE001
        log("  ! 重新归类失败: " + traceback.format_exc(limit=1).strip())

    if not ok_any:
        log("所有数据源均失败，保留上一次数据")
        if not os.path.exists(OUT_JS):
            log("错误：无任何可展示数据")
        return 2

    export_data(con)
    con.close()
    log("更新完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
