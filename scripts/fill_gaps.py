#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补数据缺口：专辑类型 / 曲目 / 艺人资料。

三个子命令，各跑各的，互不依赖：
    python scripts/fill_gaps.py --types     # 回填缺失的专辑类型（网易云）
    python scripts/fill_gaps.py --tracks    # 补全缺失的曲目（Apple）
    python scripts/fill_gaps.py --artists   # 补艺人公司 / 粉丝名 / 出道年（kpopping）

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
    import re
    t = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t)


def fill_artists(limit=None):
    """补艺人的公司 / 粉丝名 / 出道年（kpopping 团体页）。

    依赖 kpopping.com：国内网络经常超时，本地跑不动很正常，交给云端跑。
    """
    import re
    import urllib.parse
    c = con()
    cols = [r[1] for r in c.execute("PRAGMA table_info(artists)")]
    rows = c.execute(
        "SELECT name FROM artists WHERE agency IS NULL OR agency='' "
        "OR fandom IS NULL OR fandom='' OR debut_year IS NULL OR debut_year='' "
        "ORDER BY name").fetchall()
    names = [r[0] for r in rows]
    if limit:
        names = names[:limit]
    log(f"艺人资料：待处理 {len(names)} 位（kpopping，国内可能超时）")

    done = hit = 0
    for name in names:
        try:
            url = "https://kpopping.com/profiles/group/" + urllib.parse.quote(name)
            raw = http_get(url)
            if not raw:
                done += 1
                continue
            txt = _text(raw)
            agency = fandom = debut = None
            m = re.search(r"(?:Company|Agency|Label)\s*[:：]?\s*([A-Za-z0-9&.\- ]{2,40})", txt)
            if m:
                agency = m.group(1).strip()
            m = re.search(r"(?:Fandom|Fan\s*club)\s*(?:Name)?\s*[:：]?\s*([A-Za-z0-9 ]{2,30})", txt)
            if m:
                fandom = m.group(1).strip()
            m = re.search(r"Debut\s*[:：]?\s*(\d{4})", txt)
            if m:
                debut = m.group(1)
            if not (agency or fandom or debut):
                done += 1
                continue
            sets, vals = [], []
            if agency and "agency" in cols:
                sets.append("agency=?"); vals.append(agency)
            if fandom and "fandom" in cols:
                sets.append("fandom=?"); vals.append(fandom)
            if debut and "debut_year" in cols:
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
            log(f"  … {done}/{len(names)}，已补 {hit} 位")
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
