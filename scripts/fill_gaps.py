#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补数据缺口：专辑类型 / 曲目 / 艺人资料。

三个子命令，各跑各的，互不依赖：
    python scripts/fill_gaps.py --types     # 回填缺失的专辑类型（网易云）
    python scripts/fill_gaps.py --tracks    # 补全缺失的曲目（Apple）
    python scripts/fill_gaps.py --artists   # 补团体公司 / 粉丝名 / 出道年（kpopping 明确字段）

铁律：
- 拿不到就留空，绝不猜、绝不填默认值（parse_subtype 那种启发式只用于
  已经拿到官方 type 之后的细分，不用于凭空造类型）
- 每个网络请求单独 try/except，一个挂了不影响后面
- 艺人资料那段依赖 kpopping.com，国内网络常常超时；本地跑不通没关系，
  脚本会如实报错并跳过（云端 GitHub Actions 里能跑通）
"""
import datetime
import sqlite3
import sys
import time
from html.parser import HTMLParser

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])

from sources import (  # noqa: E402
    http_get, http_json, netease_search_artist, netease_artist_albums,
    netease_album_detail, itunes_search_artist_any, itunes_lookup_albums,
)

DB = "kpop.db"
PAUSE = 0.6          # 每个请求之间歇一下，别把对方打疼
LOG_EVERY = 20


def log(m):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {m}", flush=True)


def con():
    return sqlite3.connect(DB)


# ---------------------------------------------------------------- 类型回填
def norm(s):
    return "".join(c for c in (s or "").lower() if c.isalnum())


def fill_types(limit=None):
    """对 rtype 为空的发行，去网易云找同名专辑拿 type（Single / EP / 专辑）。"""
    c = con()
    rows = c.execute(
        "SELECT id,artist,title FROM releases "
        "WHERE rtype IS NULL OR rtype='' ORDER BY date DESC").fetchall()
    if limit:
        rows = rows[:limit]
    log(f"类型回填：待处理 {len(rows)} 张")

    # 先按艺人分组，一个艺人只查一次专辑列表，省掉大量请求
    cache = {}
    done = hit = 0
    for rid, artist, title in rows:
        try:
            if artist not in cache:
                cache[artist] = None
                found = netease_search_artist(artist)   # 返回 (id, name) 元组
                aid = found[0] if isinstance(found, (tuple, list)) else found
                if aid:
                    albums = netease_artist_albums(aid, limit=100) or []
                    cache[artist] = {norm(a.get("title")): a for a in albums}
                time.sleep(PAUSE)
            m = (cache[artist] or {}).get(norm(title))
            if not m:
                done += 1
                continue
            nid = m.get("nid")          # 网易云专辑列表里叫 nid，不是 id
            if not nid:
                done += 1
                continue
            d = netease_album_detail(nid) or {}
            t = d.get("type")
            if t:
                # 只写 rtype_src（源生标注），最终 rtype 交给 build.py 的
                # step_retype 统一归类 —— 这样才不会绕过「网易云优先」的优先级规则
                c.execute("UPDATE releases SET rtype_src=? WHERE id=?", (t, rid))
                hit += 1
            time.sleep(PAUSE)
        except Exception as e:  # noqa: BLE001
            log(f"  ! {artist} / {title}: {str(e)[:60]}")
        done += 1
        if done % LOG_EVERY == 0:
            c.commit()
            log(f"  … {done}/{len(rows)}，已补 {hit} 张")
    c.commit()
    left = c.execute("SELECT COUNT(*) FROM releases WHERE rtype IS NULL OR rtype=''").fetchone()[0]
    log(f"类型回填完成：本次补上 {hit} 张，库里仍缺 {left} 张")
    c.close()


# ---------------------------------------------------------------- 曲目补全
def fill_tracks(limit=None):
    """对没有曲目的发行，去 Apple 找同名专辑拿曲目列表。"""
    c = con()
    have = {r[0] for r in c.execute("SELECT DISTINCT release_id FROM tracks")}
    rows = [r for r in c.execute(
        "SELECT id,artist,title FROM releases ORDER BY date DESC")
        if r[0] not in have]
    if limit:
        rows = rows[:limit]
    log(f"曲目补全：待处理 {len(rows)} 张")

    cache, done, hit = {}, 0, 0
    for rid, artist, title in rows:
        try:
            if artist not in cache:
                cache[artist] = None
                found = itunes_search_artist_any(artist)  # 有的分支返回元组
                aid = found[0] if isinstance(found, (tuple, list)) else found
                if aid:
                    albums = itunes_lookup_albums(aid, limit=200) or []
                    cache[artist] = {norm(a.get("collectionName")): a for a in albums}
                time.sleep(PAUSE)
            m = (cache[artist] or {}).get(norm(title))
            cid = (m or {}).get("collectionId")
            if not cid:
                done += 1
                continue
            data = http_json(f"https://itunes.apple.com/lookup?id={cid}"
                             f"&entity=song&limit=200") or {}
            songs = [r for r in data.get("results", [])
                     if r.get("wrapperType") == "track"
                     and r.get("kind") == "song"]
            n = 0
            for s in songs:
                if not s.get("trackName"):
                    continue
                c.execute("""INSERT OR REPLACE INTO tracks
                             (id,release_id,artist,name,track_no,disc,duration_ms,genre,preview)
                             VALUES(?,?,?,?,?,?,?,?,?)""",
                          (f"{rid}:{s.get('trackId')}", rid, artist,
                           s.get("trackName"), s.get("trackNumber") or 0,
                           s.get("discNumber") or 1,
                           s.get("trackTimeMillis") or 0,
                           s.get("primaryGenreName") or "",
                           s.get("previewUrl") or ""))
                n += 1
            if n:
                hit += 1
            time.sleep(PAUSE)
        except Exception as e:  # noqa: BLE001
            log(f"  ! {artist} / {title}: {str(e)[:60]}")
        done += 1
        if done % LOG_EVERY == 0:
            c.commit()
            log(f"  … {done}/{len(rows)}，已补 {hit} 张")
    c.commit()
    log(f"曲目补全完成：本次补上 {hit} 张专辑的曲目")
    c.close()


# ---------------------------------------------------------------- 艺人资料
def _text(html):
    import html as html_lib
    import re
    if isinstance(html, bytes):
        html = html.decode("utf-8", "replace")
    t = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    t = html_lib.unescape(re.sub(r"<[^>]+>", "\n", t))
    return "\n".join(" ".join(line.split()) for line in t.splitlines() if line.strip())


class _ProfileHTML(HTMLParser):
    """Keep sibling elements so empty profile values never consume another label."""
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = {"tag": "root", "children": []}
        self.stack = [self.root]
        self.nodes = [self.root]
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "children": []}
        self.stack[-1]["children"].append(node)
        self.nodes.append(node)
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input",
                       "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index]["tag"] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1]["children"].append(data)


def _node_text(node):
    if isinstance(node, str):
        return node
    if node["tag"] in {"script", "style"}:
        return ""
    if node["tag"] in {"br", "hr"}:
        return "\n"
    text = "".join(_node_text(child) for child in node["children"])
    if node["tag"] in {"div", "p", "li", "ul", "ol", "section", "article"}:
        return "\n" + text + "\n"
    return text


def _profile_field(html, labels):
    """Read explicit definition/table pairs; unsupported layouts stay blank."""
    import re
    parser = _ProfileHTML(html)
    values = set()
    pairs = {"dt": {"dd"}, "th": {"td"}}
    for parent in parser.nodes:
        children = [child for child in parent["children"]
                    if not isinstance(child, str) or child.strip()]
        for label, value in zip(children, children[1:]):
            if isinstance(label, str) or isinstance(value, str):
                continue
            if value["tag"] not in pairs.get(label["tag"], set()):
                continue
            label_text = " ".join(_node_text(label).split())
            if re.fullmatch(r"(?:" + labels + r")[ \t]*[:：]?", label_text, re.I):
                values.add(" ".join(_node_text(value).split()))
    if len(values) != 1:
        return None
    value = values.pop()
    if value.casefold().rstrip(":：") in {"", "tba", "tbd", "n/a", "none", "unknown", "-", "—",
                            "debut", "fandom", "fandom name", "fan club", "fan club name",
                            "company", "agency", "label", "members", "company history", "active years"}:
        return None
    return value


def fill_artists(limit=None):
    """补团体的公司 / 粉丝名 / 出道年（kpopping 团体页）。

    依赖 kpopping.com：国内网络经常超时，本地跑不动很正常，交给云端跑。
    只认标题匹配的 Group Info 中明确配对的定义列表/表格字段；未知布局不猜。
    不覆盖已有字段；个人艺人、公司历史和不确定的页面留待单独核对。
    """
    import re
    import urllib.parse
    c = con()
    cols = [r[1] for r in c.execute("PRAGMA table_info(artists)")]
    rows = c.execute(
        "SELECT name,agency,fandom,debut_year FROM artists "
        "WHERE (kind IS NULL OR kind='' OR kind='group') "
        "AND (agency IS NULL OR agency='' "
        "OR fandom IS NULL OR fandom='' OR debut_year IS NULL OR debut_year='') "
        "ORDER BY name").fetchall()
    if limit:
        rows = rows[:limit]
    log(f"艺人资料：待处理 {len(rows)} 位团体（kpopping，国内可能超时）")

    done = hit = 0
    for name, old_agency, old_fandom, old_debut in rows:
        try:
            slug = re.sub(r"\s+", "-", name.strip())
            url = "https://kpopping.com/profiles/group/" + urllib.parse.quote(slug, safe="")
            raw = http_get(url)
            if not raw:
                done += 1
                continue
            html = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
            heading = re.search(r"<h1\b[^>]*>(.*?)</h1>", html, re.S | re.I)
            section = re.search(r"<h2\b[^>]*>\s*Group Info\s*</h2>(.*?)(?=<h2\b|\Z)",
                                html, re.S | re.I)
            if not heading or norm(_text(heading.group(1))) != norm(name) or not section:
                done += 1
                continue
            txt = section.group(1)
            agency = _profile_field(txt, r"Company|Agency|Label")
            fandom = _profile_field(txt, r"Fandom(?: Name)?|Fan club(?: Name)?")
            debut_value = _profile_field(txt, r"Debut")
            debut = None
            if debut_value and re.fullmatch(r"(?:19|20)\d{2}(?:-\d{2}-\d{2})?", debut_value):
                debut = debut_value[:4]
            if not (agency or fandom or debut):
                done += 1
                continue
            sets, vals = [], []
            if agency and old_agency in (None, "") and "agency" in cols:
                sets.append("agency=?"); vals.append(agency)
            if fandom and old_fandom in (None, "") and "fandom" in cols:
                sets.append("fandom=?"); vals.append(fandom)
            if debut and old_debut in (None, "") and "debut_year" in cols:
                sets.append("debut_year=?"); vals.append(int(debut))
            if sets:
                vals.append(name)
                c.execute("UPDATE artists SET " + ",".join(sets) + " WHERE name=?", vals)
                hit += 1
            time.sleep(PAUSE)
        except Exception as e:  # noqa: BLE001
            log(f"  ! {name}: {str(e)[:60]}")
        done += 1
        if done % 5 == 0:
            c.commit()
            log(f"  … {done}/{len(rows)}，已补 {hit} 位")
    c.commit()
    log(f"艺人资料完成：本次补上 {hit} 位")
    c.close()


if __name__ == "__main__":
    a = sys.argv
    if "--types" in a:
        fill_types(int(a[a.index("--limit") + 1]) if "--limit" in a else None)
    elif "--tracks" in a:
        fill_tracks(int(a[a.index("--limit") + 1]) if "--limit" in a else None)
    elif "--artists" in a:
        fill_artists(int(a[a.index("--limit") + 1]) if "--limit" in a else None)
    else:
        print(__doc__)
