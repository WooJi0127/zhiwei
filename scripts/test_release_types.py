"""A prerelease single must never lend its type to a later namesake EP."""
import sqlite3
import unittest
from unittest.mock import patch

import build


class ReleaseTypeTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(':memory:')
        self.addCleanup(self.con.close)
        self.con.executescript(build.SCHEMA)

    def add(self, rid, date, title='SUPERSTAR', subtype=None):
        self.con.execute('INSERT INTO releases(id,artist,title,date,rtype_src) VALUES(?,?,?,?,?)',
                         (rid, 'A2O SOUL', title, date, subtype))

    def types(self):
        with patch.object(build, 'log'):
            build.step_retype(self.con)
        return dict(self.con.execute('SELECT id,rtype FROM releases'))

    def test_october_netease_single_does_not_overwrite_november_official_ep(self):
        self.add('ne:single', '2026-10-13', subtype='Single')
        self.add('official:ep', '2026-11-09', subtype='EP')
        self.assertEqual(self.types(), {'ne:single': 'Single', 'official:ep': 'EP'})

    def test_later_namesake_without_type_remains_unknown(self):
        self.add('am:single', '2026-10-13', 'SUPERSTAR - Single')
        self.add('kp:unknown', '2026-11-09')
        self.assertEqual(self.types()['kp:unknown'], None)

    def test_same_release_with_timezone_difference_can_borrow(self):
        self.add('ne:ep', '2026-11-08', subtype='EP')
        self.add('kp:ep', '2026-11-09')
        self.assertEqual(self.types()['kp:ep'], 'EP')

    def test_conflicting_nearby_types_remain_unknown(self):
        self.add('ne:one', '2026-11-08', subtype='Single')
        self.add('ne:two', '2026-11-09', subtype='EP')
        self.add('kp:unknown', '2026-11-09')
        self.assertIsNone(self.types()['kp:unknown'])

    def test_invalid_date_is_not_used_to_link_releases(self):
        self.add('ne:single', 'not-a-date', subtype='Single')
        self.add('kp:unknown', '2026-11-09')
        self.assertIsNone(self.types()['kp:unknown'])

    def test_announcement_date_does_not_block_later_netease_catalog_entry(self):
        self.con.execute('ALTER TABLE artists ADD COLUMN ne_id INTEGER')
        self.con.execute("INSERT INTO artists(name,ne_id) VALUES('A2O SOUL',123)")
        self.add('official:ep', '2026-11-09', subtype='EP')
        albums = [{'nid': 987, 'date': '2026-11-09', 'title': 'SUPERSTAR',
                   'image': 'https://example.com/verified-album-cover.jpg'}]
        class FixedDate(build.datetime.date):
            @classmethod
            def today(cls):
                return cls(2026, 11, 9)
        with patch.object(build.sources, 'netease_artist_albums', return_value=albums), \
                patch.object(build.datetime, 'date', FixedDate), \
                patch.object(build.time, 'sleep'), patch.object(build, 'log'):
            self.assertEqual(build.step_netease_fill(self.con), 1)
            self.assertEqual(build.step_netease_fill(self.con), 0)
        self.assertEqual(self.con.execute('SELECT id FROM releases ORDER BY id').fetchall(),
                         [('ne:987',), ('official:ep',)])


if __name__ == '__main__':
    unittest.main()
