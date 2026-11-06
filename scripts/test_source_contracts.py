"""Offline source contracts exercised at the collector boundary."""
from contextlib import closing
import datetime
import json
import sqlite3
import unittest
from unittest.mock import patch

import sources


class KpoppingCalendarTests(unittest.TestCase):
    def test_failed_request_is_not_a_successful_empty_calendar(self):
        with patch.object(sources, 'http_get', return_value=None):
            with self.assertRaisesRegex(sources.CalendarFetchError, 'kpopping.*2026-11'):
                sources.fetch_kpopping_month(2026, 11)

    def test_page_without_calendar_reports_source_failure(self):
        with patch.object(sources, 'http_get', return_value=b'<html></html>'):
            with self.assertRaisesRegex(sources.CalendarFetchError, 'kpopping.*2026-11'):
                sources.fetch_kpopping_month(2026, 11)

    def test_valid_empty_requested_month_is_successful(self):
        calendar = b'{"2026-11-09":{"releases":[],"anniversaries":[],"birthdays":[]}}'
        with patch.object(sources, 'http_get', return_value=calendar):
            result = sources.fetch_kpopping_month(2026, 11)
        self.assertEqual(result, ([], {}, set(), set()))

    def test_another_month_does_not_prove_requested_month_was_fetched(self):
        calendar = b'{"2026-10-09":{"releases":[],"anniversaries":[],"birthdays":[]}}'
        with patch.object(sources, 'http_get', return_value=calendar):
            with self.assertRaisesRegex(sources.CalendarFetchError, 'kpopping.*2026-11'):
                sources.fetch_kpopping_month(2026, 11)

    def test_missing_or_malformed_requested_day_is_not_silently_skipped(self):
        for calendar in (
                b'{"2026-11-09":{"views":42}}',
                b'{"2026-11-09":{"releases":{}}}',
                b'{"2026-11-09":{"releases":[null]}}',
                b'{"2026-11-09":{"releases":[{"title":"Missing artist"}]}}',
                b'{"2026-11-09":{"releases":[],"anniversaries":null}}',
                b'{"2026-11-09":{"releases":[],"anniversaries":[{"group":12}]}}',
                b'{"2026-11-09":{"releases":[],"birthdays":[{"name":12}]}}',
                b'{"2026-11-31":{"releases":[]}}',
                b'{"2026-11-09":{"releases":[{"artist":"A2O SOUL"}'):
            with self.subTest(calendar=calendar), \
                    patch.object(sources, 'http_get', return_value=calendar):
                with self.assertRaisesRegex(sources.CalendarFetchError, 'kpopping.*2026-11'):
                    sources.fetch_kpopping_month(2026, 11)

    def test_one_valid_day_does_not_hide_another_malformed_day(self):
        calendar = b'{"2026-11-09":{"releases":[]},"2026-11-10":null}'
        with patch.object(sources, 'http_get', return_value=calendar):
            with self.assertRaisesRegex(sources.CalendarFetchError, 'kpopping.*2026-11'):
                sources.fetch_kpopping_month(2026, 11)

    def test_release_outside_day_object_is_not_assigned_nearest_date(self):
        calendar = (
            b'{"2026-11-09":{"releases":[]},"recommendations":'
            b'{"releases":[{"artist":"Unrelated","title":"Not scheduled"}]}}'
        )
        with patch.object(sources, 'http_get', return_value=calendar):
            releases, _, _, _ = sources.fetch_kpopping_month(2026, 11)
        self.assertEqual(releases, [])

    def test_adjacent_month_release_does_not_enter_requested_month(self):
        calendar = (
            b'{"2026-10-31":{"releases":[{"artist":"Adjacent","title":"Old"}]},'
            b'"2026-11-09":{"releases":[]}}'
        )
        with patch.object(sources, 'http_get', return_value=calendar):
            releases, _, _, _ = sources.fetch_kpopping_month(2026, 11)
        self.assertEqual(releases, [])

    def test_flight_payload_preserves_quoted_titles_and_day_metadata(self):
        calendar = json.dumps({'2026-11-09': {
            'releases': [{'id': 'soul-ep', 'artist': 'A2O SOUL',
                          'title': 'SUPERSTAR "Day One"', 'type': 'EP',
                          'image': '', 'slug': '2026-superstar'}],
            'anniversaries': [{'group': 'A2O SOUL', 'isDebut': True, 'years': 0}],
            'birthdays': [{'name': 'Member'}],
        }}, separators=(',', ':'))
        # Next.js may split one calendar object across multiple flight chunks.
        midpoint = len(calendar) // 2
        page = ''.join('<script>self.__next_f.push(' + json.dumps([1, chunk])
                       + ')</script>' for chunk in [calendar[:midpoint], calendar[midpoint:]])
        with patch.object(sources, 'http_get', return_value=page.encode()):
            releases, debuts, groups, idols = sources.fetch_kpopping_month(2026, 11)
        self.assertEqual(releases, [{
            'date': '2026-11-09', 'artist': 'A2O SOUL', 'title': 'SUPERSTAR "Day One"',
            'type': 'EP', 'image': '', 'slug': '2026-superstar', 'source_id': 'soul-ep',
        }])
        self.assertEqual(debuts, {'A2O SOUL': 2026})
        self.assertEqual(groups, {'A2O SOUL'})
        self.assertEqual(idols, {'Member'})

    def test_failed_month_does_not_prevent_collecting_next_month(self):
        import build

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
            class FixedDate(datetime.date):
                @classmethod
                def today(cls):
                    return cls(2026, 11, 6)

            with patch.object(sources, 'http_get', side_effect=[None, calendar]), \
                    patch.object(build.datetime, 'date', FixedDate), \
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
