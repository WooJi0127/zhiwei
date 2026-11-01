"""Malformed catalog keys and failed detail requests must remain uncompleted."""
import json
import re
import sqlite3
import unittest
from unittest.mock import patch

import build
import sources


DETAIL = json.dumps({
    'code': 200,
    'album': {'id': 123, 'name': 'Known Album', 'type': 'Single',
              'subType': '', 'size': 2, 'company': 'Verified Label', 'briefDesc': ''},
    'songs': [
        {'id': 11, 'name': 'First', 'dt': 123000, 'no': 1, 'cd': '1', 'ar': [{'name': 'Known Group'}]},
        {'id': 12, 'name': 'Second', 'dt': 145000, 'no': 2, 'cd': '1', 'ar': [{'name': 'Known Group'}]},
    ],
}).encode('utf-8')


class NeteaseDetailRetryTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(':memory:')
        self.addCleanup(self.con.close)
        self.con.executescript(build.SCHEMA)
        self.logs = []

    def add_release(self, rid, extra='{"verified":"keep"}'):
        self.con.execute('INSERT INTO releases(id,source,artist,title,date,extra) VALUES(?,?,?,?,?,?)',
                         (rid, 'netease', 'Known Group', 'Known Album', '2026-10-01', extra))

    def collect(self, response, cap=600):
        with patch.object(sources, 'http_get', return_value=response), \
                patch.object(build.time, 'sleep'), patch.object(build, 'log', self.logs.append):
            return build.step_netease_tracks(self.con, cap=cap)

    def test_malformed_ids_never_request_or_consume_cap_and_keep_existing_rows(self):
        with patch.object(sources, 'http_get', side_effect=AssertionError('Invalid ID reached HTTP')):
            for nid in (None, '', 0, -1, '0', '-1', '123x', '１２３', ' 123 ', '12/34',
                        '2026-10-12HEZIIN미안해하지 마요'):
                with self.subTest(nid=nid):
                    self.assertIsNone(sources.netease_album_detail(nid))

        bad_id = 'ne:2026-10-12HEZIIN미안해하지 마요'
        original_extra = '{"trackCount":3,"verified":"keep exactly"}'
        self.add_release(bad_id, original_extra)
        self.add_release('ne:123')

        def fetch(url, **kwargs):
            self.assertEqual(url, 'https://music.163.com/api/v1/album/123')
            return DETAIL

        with patch.object(sources, 'http_get', side_effect=fetch), \
                patch.object(build.time, 'sleep'), patch.object(build, 'log', self.logs.append):
            self.assertEqual(build.step_netease_tracks(self.con, cap=1), 2)
        self.assertEqual(self.con.execute('SELECT extra FROM releases WHERE id=?', (bad_id,)).fetchone()[0],
                         original_extra)
        self.assertEqual(self.con.execute('SELECT count(*) FROM releases').fetchone()[0], 2)
        self.assertEqual(self.con.execute('SELECT DISTINCT release_id FROM tracks').fetchall(), [('ne:123',)])

    def test_failed_valid_request_keeps_state_and_can_retry_successfully(self):
        original_extra = '{ "verified": "keep", "trackCount": 2 }'
        self.add_release('ne:123', original_extra)
        for response in (None, b'{"code":500,"message":"temporary failure"}'):
            with self.subTest(response=response):
                self.assertEqual(self.collect(response), 0)
                self.assertEqual(self.con.execute('SELECT extra,rtype_src FROM releases').fetchone(),
                                 (original_extra, None))
                self.assertEqual(self.con.execute('SELECT count(*) FROM tracks').fetchone()[0], 0)
                self.assertEqual(re.search(r'补齐 (\d+) 张专辑', self.logs[-1]).group(1), '0')
        self.assertEqual(self.collect(DETAIL), 2)
        self.assertEqual(json.loads(self.con.execute('SELECT extra FROM releases').fetchone()[0])['ne_detail'], 1)

    def test_successful_numeric_detail_still_imports_tracks_and_explicit_type(self):
        with patch.object(sources, 'http_get', return_value=DETAIL):
            self.assertEqual(sources.netease_album_detail(123)['type'], 'Single')
        self.add_release('ne:123')
        self.assertEqual(self.collect(DETAIL), 2)
        extra, kind = self.con.execute('SELECT extra,rtype_src FROM releases').fetchone()
        self.assertEqual(kind, 'Single')
        self.assertEqual(json.loads(extra), {'verified': 'keep', 'trackCount': 2,
                         'company': 'Verified Label', 'srcType': 'Single', 'ne_detail': 1})
        self.assertEqual(self.con.execute(
            'SELECT id,release_id,name,track_no,duration_ms FROM tracks ORDER BY id').fetchall(), [
                ('ne:123:1', 'ne:123', 'First', 1, 123000),
                ('ne:123:2', 'ne:123', 'Second', 2, 145000),
            ])


if __name__ == '__main__':
    unittest.main()
