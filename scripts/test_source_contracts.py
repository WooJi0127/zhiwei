"""Offline source contracts exercised at the collector boundary."""
from contextlib import closing
import sqlite3
import unittest
from unittest.mock import patch

import build
import sources


class KpoppingCalendarTests(unittest.TestCase):
    def test_failed_request_returns_all_four_empty_collections(self):
        with patch.object(sources, 'http_get', return_value=None):
            result = sources.fetch_kpopping_month(2026, 11)
        self.assertEqual(result, ([], {}, set(), set()))

    def test_page_without_calendar_returns_all_four_empty_collections(self):
        with patch.object(sources, 'http_get', return_value=b'<html></html>'):
            result = sources.fetch_kpopping_month(2026, 11)
        self.assertEqual(result, ([], {}, set(), set()))

    def test_failed_month_does_not_prevent_collecting_next_month(self):
        calendar = (
            b'{"2026-12-01":{"releases":[{"id":"verified-calendar-id",'
            b'"artist":"Test Group","title":"Test Release","type":"Single",'
            b'"image":"","slug":"test-release"}],"anniversaries":[],"birthdays":[]}}'
        )
        with closing(sqlite3.connect(':memory:')) as con:
            con.executescript(build.SCHEMA)
            con.execute("INSERT INTO artists(name) VALUES('Existing Group')")
            con.execute("INSERT INTO releases(id,artist,title,date) "
                        "VALUES('existing','Existing Group','Existing Release','2026-10-01')")
            with patch.object(sources, 'http_get', side_effect=[None, calendar]), \
                    patch.object(build.time, 'sleep'), patch.object(build, 'log'):
                count = build.step_kpopping(con, [0, 1])
            self.assertEqual(count, 1)
            self.assertEqual(con.execute(
                'SELECT id,artist,title FROM releases ORDER BY id').fetchall(), [
                    ('existing', 'Existing Group', 'Existing Release'),
                    ('kp:verified-calendar-id', 'Test Group', 'Test Release'),
                ])


if __name__ == '__main__':
    unittest.main()
