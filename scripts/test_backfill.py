#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回填脚本回归测试：只补空、精确匹配、冷却、预算、预演不写库。"""
import datetime
import json
import os
import sqlite3
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backfill  # noqa: E402
import build  # noqa: E402

TODAY = datetime.date(2026, 11, 9)


class Helpers(unittest.TestCase):
    def test_title_key_ignores_case_and_punctuation(self):
        self.assertEqual(backfill.title_key("Love Me - Single"),
                         backfill.title_key("loveme single"))

    def test_title_key_keeps_korean(self):
        self.assertEqual(backfill.title_key("미안해하지 마요"),
                         backfill.title_key("미안해하지마요"))

    def test_parse_extra_tolerates_broken_json(self):
        self.assertEqual(backfill.parse_extra("{oops"), {})
        self.assertEqual(backfill.parse_extra(None), {})

    def test_retry_cools_down_after_three_failures(self):
        extra = {"bf_tries": 3, "bf_at": "2026-11-08"}
        self.assertFalse(backfill.should_retry(extra, TODAY))
        self.assertTrue(backfill.should_retry(extra, TODAY + datetime.timedelta(days=8)))
        self.assertTrue(backfill.should_retry({"bf_tries": 2}, TODAY))


class Refill(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.executescript(build.SCHEMA)
        cols = [r[1] for r in self.con.execute("PRAGMA table_info(artists)")]
        if "ne_id" not in cols:
            self.con.execute("ALTER TABLE artists ADD COLUMN ne_id INTEGER")
        self.con.execute("INSERT INTO artists(name,ne_id) VALUES('HEZIIN',1234)")
        self.con.execute(
            "INSERT INTO releases(id,source,date,artist,title,rtype,image,url,extra,rtype_src)"
            " VALUES('ne:missing','netease','2026-10-12','HEZIIN','미안해하지 마요',"
            "'','','','{}','')")
        self.con.execute(
            "INSERT INTO releases(id,source,date,artist,title,rtype,image,url,extra,rtype_src)"
            " VALUES('ne:hasimage','netease','2026-10-13','HEZIIN','다른 앨범',"
            "'','https://old.example/keep.jpg','','{}','')")
        self.con.commit()

    def tearDown(self):
        self.con.close()

    def _albums(self):
        return [
            {"title": "미안해하지 마요", "image": "https://cdn.example/a.jpg",
             "nid": 99001, "date": "2026-10-12"},
            {"title": "다른 앨범", "image": "https://cdn.example/b.jpg",
             "nid": 99002, "date": "2026-10-13"},
        ]

    def _detail(self):
        return {"type": "Single", "size": 1,
                "tracks": [{"name": "미안해하지 마요", "no": 1, "disc": 1, "ms": 200000}]}

    def _run(self, albums=None, dry_run=False, max_requests=50):
        with mock.patch.object(backfill.sources, "netease_artist_albums",
                               return_value=albums if albums is not None else self._albums()), \
             mock.patch.object(backfill.sources, "netease_album_detail",
                               return_value=self._detail()), \
             mock.patch.object(backfill.sources, "netease_search_artist",
                               return_value=(1234, "HEZIIN")), \
             mock.patch.object(backfill.time, "sleep", return_value=None):
            return backfill.refill(self.con, 90, max_requests, 0, dry_run, TODAY)

    def test_fills_empty_image_but_never_overwrites(self):
        stats = self._run()
        rows = dict((r[0], r[1]) for r in self.con.execute(
            "SELECT id,image FROM releases"))
        self.assertEqual(rows["ne:missing"], "https://cdn.example/a.jpg")
        self.assertEqual(rows["ne:hasimage"], "https://old.example/keep.jpg")
        self.assertEqual(stats["image"], 1)

    def test_fills_type_source_and_tracks(self):
        self._run()
        row = self.con.execute(
            "SELECT rtype_src FROM releases WHERE id='ne:missing'").fetchone()
        self.assertEqual(row[0], "Single")
        tracks = self.con.execute(
            "SELECT COUNT(*) FROM tracks WHERE release_id='ne:missing'").fetchone()[0]
        self.assertEqual(tracks, 1)

    def test_unmatched_title_stays_empty_and_is_not_fabricated(self):
        stats = self._run(albums=[{"title": "전혀 다른 제목", "image": "x", "nid": 1}])
        row = self.con.execute(
            "SELECT image,extra FROM releases WHERE id='ne:missing'").fetchone()
        self.assertEqual(row[0], "")
        self.assertEqual(json.loads(row[1]).get("bf_tries"), 1)
        self.assertEqual(stats["image"], 0)

    def test_dry_run_writes_nothing(self):
        self._run(dry_run=True)
        row = self.con.execute(
            "SELECT image FROM releases WHERE id='ne:missing'").fetchone()
        self.assertEqual(row[0], "")

    def test_request_budget_is_respected(self):
        stats = self._run(max_requests=1)
        self.assertLessEqual(stats["requests"], 1)

    def test_future_releases_are_not_treated_as_gaps(self):
        self.con.execute(
            "INSERT INTO releases(id,source,date,artist,title,rtype,image,url,extra,rtype_src)"
            " VALUES('ne:future','netease','2026-12-20','HEZIIN','미안해하지 마요',"
            "'','','','{}','')")
        self.con.commit()
        rows = backfill.candidate_rows(self.con, 90, TODAY)
        self.assertNotIn("ne:future", [r["id"] for r in rows])


if __name__ == "__main__":
    unittest.main()
