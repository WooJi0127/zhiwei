#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""历史缺口回填 —— 近期全量重扫 + 每日限量补漏。

为什么需要它（2026-11-09）：
  每日 build.py 只翻「本月 + 下月」的日程，翻过去的月份不再回头看；
  _ne_put / _am_put 以前又是 ON CONFLICT DO NOTHING，一条专辑第一次入库时
  没拿到封面，以后就算重扫到也补不回来 —— 「一次缺，永远缺」。

两段工作：
  1) rescan：把近几个月的日程源重新拉一遍（--full 时开启），
     借 build.py 已修好的「只补空」upsert 补回漏掉的条目与封面。
  2) refill：对近期仍有空字段的发行，按艺人去网易云重查专辑列表，
     标题**精确匹配**才采纳，补 image / rtype_src / 曲目；查不到就留空。

铁律：
  - 只补空、不覆盖；不猜、不填默认值（项目「宁缺毋滥」）
  - 每个网络请求单独 try/except，一个源挂了不影响整体
  - 请求预算 + 请求间隔 + 失败冷却，避免风控与自动任务超时
  - 可中断、可重跑、幂等；--dry-run 只看不写

用法：
    python scripts/backfill.py --full --days 90          # 一次性全量重扫
    python scripts/backfill.py --daily                  # 每日限量补漏（挂自动任务）
    python scripts/backfill.py --full --dry-run         # 预演，不写库
"""
import argparse
import datetime
import json
import os
import re
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sources  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "kpop.db")

# 失败冷却：连续 3 次没匹配到就先停 7 天，避免每天反复骚扰同一个接口
MAX_TRIES = 3
COOLDOWN_DAYS = 7
# 标题归一化：只留字母 / 数字 / 韩文 / 中文，避免空白、大小写、标点造成错配
TITLE_STRIP = re.compile(r"[^a-z0-9\uac00-\ud7a3\u4e00-\u9fff]")


def log(msg):
    print("[%s] %s" % (datetime.datetime.now().strftime("%H:%M:%S"), msg), flush=True)


def title_key(s):
    return TITLE_STRIP.sub("", (s or "").lower())


def parse_extra(raw):
    try:
        value = json.loads(raw) if raw else {}
    except Exception:  # noqa: BLE001
        return {}
    return value if isinstance(value, dict) else {}


def dump_extra(data):
    return json.dumps(data, ensure_ascii=False)


def should_retry(extra, today, max_tries=MAX_TRIES, cooldown=COOLDOWN_DAYS):
    """失败多次后先冷却，别无限重试同一个查不到的条目。"""
    tries = extra.get("bf_tries") or 0
    if tries < max_tries:
        return True
    try:
        last = datetime.date.fromisoformat(extra.get("bf_at") or "")
    except ValueError:
        return True
    return (today - last).days >= cooldown


def mark_failed(con, rid, raw_extra, today, dry_run):
    if dry_run:
        return
    extra = parse_extra(raw_extra)
    extra["bf_tries"] = (extra.get("bf_tries") or 0) + 1
    extra["bf_at"] = today.isoformat()
    con.execute("UPDATE releases SET extra=? WHERE id=?",
                (dump_extra(extra), rid))


def mark_done(con, rid, raw_extra, dry_run):
    """补到数据后清掉失败计数，下次有别的缺口还能重试。"""
    if dry_run:
        return
    extra = parse_extra(raw_extra)
    extra.pop("bf_tries", None)
    extra.pop("bf_at", None)
    con.execute("UPDATE releases SET extra=? WHERE id=?",
                (dump_extra(extra), rid))


def candidate_rows(con, days, today):
    """近期条目里，仍有空字段且没在冷却期内的，才值得重新查。"""
    cut = (today - datetime.timedelta(days=days)).isoformat()
    have_tracks = {r[0] for r in con.execute(
        "SELECT DISTINCT release_id FROM tracks")}
    con.row_factory = sqlite3.Row
    # 只看「已发行」的：还没发行的专辑本来就不会有封面，不该当缺口反复重试。
    rows = con.execute(
        "SELECT id,source,date,artist,title,image,rtype,rtype_src,extra "
        "FROM releases WHERE date>=? AND date<=? ORDER BY date DESC",
        (cut, today.isoformat())).fetchall()
    out = []
    for r in rows:
        extra = parse_extra(r["extra"])
        blank_image = not (r["image"] or "").strip()
        blank_type = (not (r["rtype"] or "").strip()
                      and not (r["rtype_src"] or "").strip())
        no_tracks = r["id"] not in have_tracks and "ne_detail" not in extra
        if not (blank_image or blank_type or no_tracks):
            continue
        if not should_retry(extra, today):
            continue
        out.append(dict(r))
    return out


def rescan_schedules(con, dry_run=False):
    """重拉近 4 个月 + 下月的日程源，补回当时漏掉的条目与封面。"""
    if dry_run:
        log("· 预演：跳过日程源重扫")
        return
    import build  # noqa: E402  延迟导入，避免 --daily 时也加载整套采集模块
    log("· 重扫近 4 个月日程源")
    try:
        build.step_schedules(con, [-3, -2, -1, 0, 1])
    except Exception as exc:  # noqa: BLE001
        log("  ! 日程重扫失败（不影响后续补漏）：%s" % str(exc)[:100])
    con.commit()


def refill(con, days, max_requests, pause, dry_run, today):
    rows = candidate_rows(con, days, today)
    log("· 待回填 %d 张（近 %d 天）" % (len(rows), days))
    groups = {}
    for r in rows:
        groups.setdefault(r["artist"], []).append(r)

    stats = {"requests": 0, "image": 0, "type": 0, "tracks": 0,
             "matched": 0, "missed": 0}
    used = 0
    # 缺封面的最优先（用户最直观的「信息不全」），其次按最近发行日期。
    # 否则预算会先被「只缺曲目」的老条目吃光，缺图的一张都轮不到。
    ordered = sorted(
        groups.items(),
        key=lambda kv: (max(1 if not (x["image"] or "").strip() else 0
                            for x in kv[1]),
                        max(x["date"] for x in kv[1])),
        reverse=True)

    for artist, items in ordered:
        if used >= max_requests:
            break
        cached = con.execute("SELECT ne_id FROM artists WHERE name=?",
                             (artist,)).fetchone()
        aid = cached[0] if cached else None
        if not aid:
            used += 1
            try:
                hit = sources.netease_search_artist(artist)
            except Exception:  # noqa: BLE001
                hit = None
            if hit:
                aid = hit[0]
                if not dry_run:
                    con.execute("UPDATE artists SET ne_id=? WHERE name=?",
                                (aid, artist))
            time.sleep(pause)
        if not aid:
            for r in items:
                stats["missed"] += 1
                mark_failed(con, r["id"], r["extra"], today, dry_run)
            continue

        used += 1
        try:
            albums = sources.netease_artist_albums(aid, limit=100) or []
        except Exception:  # noqa: BLE001
            albums = []
        time.sleep(pause)
        by_title = {}
        for a in albums:
            key = title_key(a.get("title"))
            if key and key not in by_title:
                by_title[key] = a

        for r in items:
            album = by_title.get(title_key(r["title"]))
            if not album or not album.get("nid"):
                stats["missed"] += 1
                mark_failed(con, r["id"], r["extra"], today, dry_run)
                continue
            stats["matched"] += 1
            extra = parse_extra(r["extra"])
            extra["ne_nid"] = album["nid"]   # 真实网易云编号，方便以后直接查详情
            changed = False

            url = (album.get("image") or "").strip()
            if url and not (r["image"] or "").strip():
                if not dry_run:
                    con.execute("UPDATE releases SET image=? WHERE id=? "
                                "AND (image IS NULL OR image='')", (url, r["id"]))
                stats["image"] += 1
                changed = True

            need_detail = (not (r["rtype"] or "").strip()
                           and not (r["rtype_src"] or "").strip()) or (
                               con.execute("SELECT 1 FROM tracks WHERE release_id=? LIMIT 1",
                                           (r["id"],)).fetchone() is None)
            if need_detail and used < max_requests:
                used += 1
                try:
                    detail = sources.netease_album_detail(str(album["nid"]))
                except Exception:  # noqa: BLE001
                    detail = None
                time.sleep(pause)
                if detail:
                    raw_type = (detail.get("type") or "").strip()
                    if raw_type and not (r["rtype_src"] or "").strip():
                        if not dry_run:
                            con.execute("UPDATE releases SET rtype_src=? WHERE id=? "
                                        "AND (rtype_src IS NULL OR rtype_src='')",
                                        (raw_type, r["id"]))
                        extra["srcType"] = raw_type
                        stats["type"] += 1
                        changed = True
                    songs = detail.get("tracks") or []
                    if songs and con.execute(
                            "SELECT 1 FROM tracks WHERE release_id=? LIMIT 1",
                            (r["id"],)).fetchone() is None:
                        for i, t in enumerate(songs, 1):
                            if not dry_run:
                                con.execute(
                                    "INSERT OR IGNORE INTO tracks"
                                    "(id,release_id,artist,name,track_no,disc,"
                                    " duration_ms,genre,preview) VALUES(?,?,?,?,?,?,?,?,?)",
                                    ("%s:%d" % (r["id"], i), r["id"], "",
                                     t.get("name") or "", t.get("no") or i,
                                     t.get("disc") or 1, t.get("ms") or 0, "", ""))
                        extra["ne_detail"] = 1
                        extra["trackCount"] = detail.get("size") or len(songs)
                        stats["tracks"] += len(songs)
                        changed = True
            if changed:
                mark_done(con, r["id"], dump_extra(extra), dry_run)
            else:
                mark_failed(con, r["id"], dump_extra(extra), today, dry_run)

    if not dry_run:
        con.commit()
    stats["requests"] = used
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=90, help="回溯天数（默认 90）")
    ap.add_argument("--full", action="store_true", help="一次性全量重扫（含日程源）")
    ap.add_argument("--daily", action="store_true", help="每日限量补漏模式")
    ap.add_argument("--max-requests", type=int, default=500, help="请求预算")
    ap.add_argument("--pause", type=float, default=0.4, help="请求间隔秒")
    ap.add_argument("--dry-run", action="store_true", help="只看不写")
    args = ap.parse_args()

    if args.daily:
        args.max_requests = min(args.max_requests, 60)
        args.days = min(args.days, 90)

    today = datetime.date.today()
    con = sqlite3.connect(DB_PATH)
    try:
        if args.full and not args.daily:
            rescan_schedules(con, args.dry_run)
        stats = refill(con, args.days, args.max_requests, args.pause,
                       args.dry_run, today)
    finally:
        con.close()

    log("完成：请求 %(requests)d / 匹配 %(matched)d / 未匹配 %(missed)d / "
        "补图 %(image)d / 补类型 %(type)d / 补曲目 %(tracks)d" % stats)
    if args.dry_run:
        log("（预演模式，未写库）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
