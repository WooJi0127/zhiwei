# -*- coding: utf-8 -*-
"""
K-Pop 数据源抓取模块（纯 Python 标准库，零第三方依赖）

三个数据源：
  1. kpopping.com   -> 未来回归日程（内嵌 RSC JSON，含封面/类型）
  2. Apple Music    -> 历史专辑归档（iTunes Search/Lookup API，含深链）
  3. kpopcal.com    -> 官方确认事件（CC BY 4.0，带 source 溯源）
"""
import json
import re
import time
import gzip
import random
import unicodedata
import datetime
import urllib.request
import urllib.parse
import urllib.error

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

TIMEOUT = 30
RETRIES = 3


# ---------------------------------------------------------------- HTTP utils
def http_get(url, headers=None, retries=RETRIES, timeout=TIMEOUT):
    """带重试与退避的 GET，返回 bytes。失败返回 None（不抛异常，保证稳定运行）。"""
    hdrs = {"User-Agent": UA,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
            "Accept-Encoding": "gzip"}
    if headers:
        hdrs.update(headers)
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    try:
                        raw = gzip.decompress(raw)
                    except Exception:
                        pass
                return raw
        except Exception as e:                      # noqa: BLE001
            last = e
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1) + random.random())
    print(f"    ! 请求失败 {url[:90]} -> {last}")
    return None


def http_json(url, retries=RETRIES, timeout=TIMEOUT):
    raw = http_get(url, retries=retries, timeout=timeout)
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except Exception as e:                          # noqa: BLE001
        print(f"    ! JSON 解析失败 {url[:90]} -> {e}")
        return None


# --------------------------------------------------------- 1. kpopping 日历
def _unescape_rsc(html):
    """RSC flight payload 里引号被转义成 \\"，先还原。"""
    s = html.replace('\\"', '"')
    s = s.replace('\\u003c', '<').replace('\\u003e', '>').replace('\\u0026', '&')
    return s


def _balanced_slice(s, start):
    """从 start（必须是 [ 或 {）开始，按括号平衡取出完整片段。"""
    open_ch = s[start]
    close_ch = ']' if open_ch == '[' else '}'
    depth = 0
    instr = False
    esc = False
    for j in range(start, len(s)):
        c = s[j]
        if instr:
            if esc:
                esc = False
            elif c == '\\':
                esc = True
            elif c == '"':
                instr = False
            continue
        if c == '"':
            instr = True
        elif c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return s[start:j + 1]
    return None


def fetch_kpopping_month(year, month):
    """
    抓取 kpopping 某月日历。
    返回 (releases, debut_years, groups, idols)
      releases    : [{date, artist, title, type, image}]
      debut_years : {artist: 出道年份}，由 anniversaries 的 isDebut + years 推算
      groups      : 团体名集合，来自 anniversaries 的 group 字段
      idols       : 个人名集合，来自 birthdays 的 name 字段
    """
    url = f"https://kpopping.com/calendar?month={year:04d}-{month:02d}"
    raw = http_get(url)
    if raw is None:
        return [], {}
    html = raw.decode("utf-8", "replace")
    s = _unescape_rsc(html)

    # 日期锚点： "2026-11-15":{
    date_anchors = [(m.start(), m.group(1))
                    for m in re.finditer(r'"(\d{4}-\d{2}-\d{2})":\{', s)]
    if not date_anchors:
        print("    ! kpopping 未找到日期锚点")
        return [], {}, set(), set()

    def date_for(pos):
        owner = None
        for dpos, d in date_anchors:
            if dpos <= pos:
                owner = d
            else:
                break
        return owner

    releases = []
    debut_years = {}
    groups = set()
    idols = set()

    # --- releases ---
    for m in re.finditer(r'"releases":\[', s):
        arr_start = m.end() - 1
        if s[arr_start:arr_start + 2] == '[]':
            continue
        frag = _balanced_slice(s, arr_start)
        if not frag:
            continue
        try:
            items = json.loads(frag)
        except Exception:                           # noqa: BLE001
            continue
        d = date_for(arr_start)
        if not d:
            continue
        for it in items:
            releases.append({
                "date": d,
                "artist": (it.get("artist") or "").strip(),
                "title": (it.get("title") or "").strip(),
                "type": (it.get("type") or "").strip(),
                "image": it.get("image") or "",
                "slug": it.get("slug") or "",
                "source_id": it.get("id") or "",
            })

    # --- anniversaries: 推算出道年 ---
    this_year = datetime.date.today().year
    for m in re.finditer(r'"anniversaries":\[', s):
        arr_start = m.end() - 1
        if s[arr_start:arr_start + 2] == '[]':
            continue
        frag = _balanced_slice(s, arr_start)
        if not frag:
            continue
        try:
            items = json.loads(frag)
        except Exception:                           # noqa: BLE001
            continue
        d = date_for(arr_start)
        if not d:
            continue
        try:
            ev_year = int(d[:4])
        except Exception:                           # noqa: BLE001
            continue
        for it in items:
            gname = (it.get("group") or "").strip()
            if gname:
                groups.add(gname)
            if not it.get("isDebut"):
                continue
            name = (it.get("group") or it.get("artist") or "").strip()
            yrs = it.get("years")
            if name and isinstance(yrs, int):
                debut_years[name] = ev_year - yrs

    # --- birthdays: 过生日的是个人 ---
    for m in re.finditer(r'"birthdays":\[', s):
        arr_start = m.end() - 1
        if s[arr_start:arr_start + 2] == '[]':
            continue
        frag = _balanced_slice(s, arr_start)
        if not frag:
            continue
        try:
            items = json.loads(frag)
        except Exception:                           # noqa: BLE001
            continue
        for it in items:
            nm = (it.get("name") or "").strip()
            if nm:
                idols.add(nm)

    return releases, debut_years, groups, idols


# ------------------------------------------- 1b. kpopping 艺人名录（团体/个人）
def fetch_kpopping_roster():
    """
    抓 /groups 与 /idols 两个列表页，得到团体集合与个人集合。
    页面里链接形如 /group/ILLIT、/idol/Karina，slug 去掉连字符即为显示名。
    用于给艺人补 kind（group / solo）。
    """
    groups, idols = set(), set()
    for url, bucket in (("https://kpopping.com/groups", groups),
                        ("https://kpopping.com/idols", idols)):
        raw = http_get(url)
        if raw is None:
            continue
        h = raw.decode("utf-8", "ignore")
        for m in re.finditer(r'/group/([A-Za-z0-9\-\.%]+)|/idol/([A-Za-z0-9\-\.%]+)', h):
            slug = urllib.parse.unquote(m.group(1) or m.group(2) or "")
            if not slug:
                continue
            bucket.add(slug)
            bucket.add(slug.replace("-", " ").strip())
        time.sleep(0.8)
    return groups, idols


def fetch_kpopping_gender():
    """
    抓 kpopping 的四个性别分类页，返回
    {"gg": 女团集合, "bg": 男团集合, "fi": 女歌手集合, "mi": 男歌手集合}。

    页面链接形如 /profiles/group/TWICE、/profiles/idol/Karina。
    坑：slug 可能带数字后缀做同名去重（Yena2、Tomorrow-X-Together2），
        所以比对前要用 names.norm_gkey() 去掉尾部数字。
    """
    out = {"gg": set(), "bg": set(), "fi": set(), "mi": set()}
    pages = (("gg", "https://kpopping.com/groups/girl-groups", "group"),
             ("bg", "https://kpopping.com/groups/boy-groups", "group"),
             ("fi", "https://kpopping.com/idols/female", "idol"),
             ("mi", "https://kpopping.com/idols/male", "idol"))
    for key, url, kind in pages:
        raw = http_get(url)
        if raw is None:
            continue
        h = raw.decode("utf-8", "ignore")
        for m in re.finditer(r'/profiles/' + kind + r'/([A-Za-z0-9\-\.%]+)', h):
            slug = urllib.parse.unquote(m.group(1) or "")
            if not slug:
                continue
            out[key].add(slug)
            out[key].add(slug.replace("-", " ").strip())
        time.sleep(0.8)
    return out


def group_is_coed(name):
    """
    判断一个团体是不是混声团（男女都有）。
    kpopping 没有混声团分类页，但团体详情页简介里会写 "co-ed"。
    只有女团/男团名录里都查不到的团体才需要调用，量很小。
    """
    slug = re.sub(r"\s+", "-", (name or "").strip())
    if not slug:
        return False
    # IRISÉ 这类带重音的名字，kpopping 的 slug 往往去掉了重音，两个都试一遍
    plain = "".join(
        c for c in unicodedata.normalize("NFKD", slug) if not unicodedata.combining(c))
    cands = [slug] if plain == slug else [slug, plain]
    for s in cands:
        if not s:
            continue
        # 404 是常态（多数团体在名录里就已经匹配上了，只有少数走到这里），
        # 用 retries=1 快速失败，否则 3 次退避重试能把一轮跑挂
        raw = http_get("https://kpopping.com/profiles/group/" + urllib.parse.quote(s),
                       retries=1)
        if raw is None:
            continue
        h = raw.decode("utf-8", "ignore")
        # 详情页有个明确的分类徽章（>co-ed group<），认徽章比认正文里的词更可靠
        if re.search(r">\s*co-?ed group\s*<", h, re.I):
            return True
    return False


def itunes_find_kpop(name, retries=1):
    """
    一步到位的验证：搜艺人，**只认 K-Pop** 的结果。
    返回 (artistId, artistName, genre)，没有 K-Pop 结果则返回 None。
    用于新团发现——新碟榜噪音大，拿它当过滤器，一次请求就够了。
    """
    url = ("https://itunes.apple.com/search?term=" + urllib.parse.quote(name)
           + "&entity=musicArtist&limit=10&country=KR")
    data = http_json(url, retries=retries)
    for a in (data or {}).get("results") or []:
        g = a.get("primaryGenreName") or ""
        if "k-pop" in g.lower() or "kpop" in g.lower():
            return a.get("artistId"), a.get("artistName"), g
    return None


# ------------------------------------------------------- 2.5 网易云音乐
# 为什么需要它：kpopping 主要覆盖韩国本土向的团体，像 A2O 系列（中国背景、
# 面向中国市场）它就不收；而 Apple Music 虽然收录了，却只能给「已知艺人名」
# 补数据，没有枚举新团的入口。网易云这边有两个可用接口：
#   - 按艺人名搜（type=100）→ 拿 artist id
#   - 按 artist id 取专辑列表
# 实测：搜索和专辑接口都通；QQ 音乐的公开接口已废弃（搜 IVE 都返回空），不用。
NE_HEADERS = {"Referer": "https://music.163.com/"}


def netease_json(url):
    raw = http_get(url, headers=NE_HEADERS)
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8", "ignore"))
    except Exception:                                   # noqa: BLE001
        return None


def netease_search_artist(name):
    """
    按名字搜艺人，返回 (artist_id, 艺人名)。

    **只接受完全同名**。别用「取第一个结果」兜底——实测会严重错配：
    搜 Woojin 会返回 WOOJIN of LNGSHOT / 우진 / Woojinee / WOOJIN / Woojin. / Woojin 六个，
    搜 Lara 会返回梁心颐 / LARA / Lara Fabian……取第一个等于拿别人的专辑塞进库里。
    我们是从已知艺人名出发的，匹配不上就宁可不要。
    """
    if not name:
        return None
    url = ("https://music.163.com/api/search/get?s="
           + urllib.parse.quote(name) + "&type=100&limit=20")
    d = netease_json(url)
    arts = ((d or {}).get("result") or {}).get("artists") or []
    want = re.sub(r"[^a-z0-9\uac00-\ud7a3\u4e00-\u9fff]", "", name.lower())
    for a in arts:
        got = re.sub(r"[^a-z0-9\uac00-\ud7a3\u4e00-\u9fff]", "",
                     (a.get("name") or "").lower())
        if got == want:
            return (a.get("id"), a.get("name"))
    return None


def netease_artist_albums(artist_id, limit=60):
    """取艺人专辑列表，返回 [{title,date,image,nid}]。"""
    if not artist_id:
        return []
    d = netease_json(f"https://music.163.com/api/artist/albums/{artist_id}"
                     f"?limit={limit}&offset=0")
    out = []
    for a in ((d or {}).get("hotAlbums") or []):
        ts = a.get("publishTime") or 0
        if not ts:
            continue
        out.append({
            "title": a.get("name") or "",
            "date": datetime.date.fromtimestamp(ts / 1000).isoformat(),
            "image": a.get("picUrl") or "",
            "nid": a.get("id"),
        })
    return out


def netease_album_detail(nid):
    """
    专辑详情：曲目、时长、唱片公司、曲目数。

    用 /api/v1/album/{id}——老的 /api/album/{id} 会返回 code=-462（需要风控参数）。
    album.type 只有「Single / 专辑」两档，区分不出 EP，所以类型还是交给标题判断；
    这里的 value 主要在 size（曲目数）和 songs（曲目列表）。
    """
    if not nid:
        return None
    d = netease_json(f"https://music.163.com/api/v1/album/{nid}")
    if not d:
        return None
    alb = d.get("album") or {}
    songs = []
    for i, s in enumerate(d.get("songs") or [], 1):
        nm = (s.get("name") or "").strip()
        if not nm:
            continue
        songs.append({
            "name": nm,
            "ms": s.get("dt") or 0,
            "no": s.get("no") or i,
            "disc": s.get("cd") or 1,
            "artists": [a.get("name") or "" for a in (s.get("ar") or [])],
        })
    return {
        "title": alb.get("name") or "",
        "type": alb.get("type") or "",       # Single / 专辑
        "subtype": alb.get("subType") or "",  # 录音室版 / 现场版 ...
        "size": alb.get("size") or len(songs),
        "company": (alb.get("company") or "").strip(),
        "desc": (alb.get("briefDesc") or "").strip(),
        "tracks": songs,
    }


def netease_new_albums(area="KR", pages=3):
    """新碟上架，用于发现 kpopping 没收录的团体。"""
    out = []
    for p in range(pages):
        d = netease_json(f"https://music.163.com/api/album/new?area={area}"
                         f"&offset={p*30}&limit=30")
        for a in ((d or {}).get("albums") or []):
            ts = a.get("publishTime") or 0
            out.append({
                "artist": ((a.get("artist") or {}).get("name") or "").strip(),
                "artist_id": (a.get("artist") or {}).get("id"),
                "title": a.get("name") or "",
                "date": datetime.date.fromtimestamp(ts / 1000).isoformat() if ts else "",
            })
        time.sleep(0.4)
    return out


# ------------------------------------------------------- 2. Apple Music API
def itunes_search_artist(name, country="KR"):
    """按名字找 Apple Music 艺人，返回最佳 (artistId, artistName)。同名时选 K-Pop 且作品最多的。"""
    url = ("https://itunes.apple.com/search?term="
           + urllib.parse.quote(name)
           + f"&entity=musicArtist&limit=8&country={country}")
    data = http_json(url)
    if not data:
        return None
    cands = data.get("results") or []
    if not cands:
        return None
    lower = name.strip().lower()

    def score(a):
        an = (a.get("artistName") or "").strip().lower()
        s = 0
        if an == lower:
            s += 100
        elif an.startswith(lower) or lower.startswith(an):
            s += 40
        genre = (a.get("primaryGenreName") or "").lower()
        if "k-pop" in genre or "kpop" in genre:
            s += 30
        elif "pop" in genre:
            s += 5
        return s

    cands.sort(key=score, reverse=True)
    best = cands[0]
    if score(best) < 40:
        return None
    return best.get("artistId"), best.get("artistName")


def itunes_search_artist_any(name, country="KR"):
    """
    宽松版艺人搜索：用于把韩文艺人名反查成英文名。
    不要用严格评分——用韩文名搜，返回的 artistName 是英文，跟查询词根本不像。
    优先取 K-Pop 分类的结果。
    """
    url = ("https://itunes.apple.com/search?term="
           + urllib.parse.quote(name)
           + f"&entity=musicArtist&limit=10&country={country}")
    data = http_json(url)
    if not data:
        return None
    cands = data.get("results") or []
    if not cands:
        return None
    for a in cands:
        g = (a.get("primaryGenreName") or "").lower()
        if "k-pop" in g or "kpop" in g:
            return a.get("artistId"), a.get("artistName")
    return cands[0].get("artistId"), cands[0].get("artistName")


def itunes_lookup_albums(artist_id, country="KR", limit=200):
    """拉取某艺人的全部专辑/单曲。返回原始 collection 列表。"""
    url = (f"https://itunes.apple.com/lookup?id={artist_id}"
           f"&entity=album&limit={limit}&country={country}")
    data = http_json(url)
    if not data:
        return []
    return [x for x in (data.get("results") or [])
            if x.get("wrapperType") == "collection"]


def itunes_lookup_songs(artist_id, country="KR", limit=200):
    """
    拉取某艺人的曲目（含所属专辑），用于详情页曲目列表。
    注意：iTunes 只支持按 artistId 拿曲目；按 collectionId 查 entity=song 返回空。
    返回原始 track 列表，字段含 trackName/trackNumber/trackTimeMillis/
    primaryGenreName/collectionId/previewUrl，实测完整度 100%。
    """
    url = (f"https://itunes.apple.com/lookup?id={artist_id}"
           f"&entity=song&limit={limit}&country={country}")
    data = http_json(url)
    if not data:
        return []
    return [x for x in (data.get("results") or [])
            if x.get("wrapperType") == "track"]


# ------------------------------------------------------------- 3. kpopcal
def fetch_kpopcal():
    """返回 (artists, events)。"""
    data = http_json("https://kpopcal.com/api/events.json")
    if not data:
        return [], []
    return data.get("artists") or [], data.get("events") or []
