"""Offline iCal export regressions using only a temporary database and files."""
import contextlib
import datetime
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build


class FixedDate(datetime.date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 31)


class FixedDateTime(datetime.datetime):
    @classmethod
    def now(cls, tz=None):
        local = cls(2026, 10, 31, 2, 3, 4,
                    tzinfo=datetime.timezone(datetime.timedelta(hours=8)))
        return local.replace(tzinfo=None) if tz is None else local.astimezone(tz)


class ICalExportTests(unittest.TestCase):
    def setUp(self):
        temp_root = Path(__file__).resolve().parents[1] / ".build-logs"
        temp_root.mkdir(exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=temp_root)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.output = self.root / "zhiwei.ics"
        self.db = sqlite3.connect(self.root / "test.db")
        self.addCleanup(self.db.close)
        self.db.executescript(build.SCHEMA)
        for target, name, value in (
                (build, "ICS_FILE", str(self.output)),
                (build, "LOG_PATH", str(self.root / "test.log")),
                (build.datetime, "date", FixedDate),
                (build.datetime, "datetime", FixedDateTime)):
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def add_release(self, rid="release-1", date="2026-10-31",
                    artist="Example Group", title="Example Album", rtype="EP"):
        self.db.execute(
            "INSERT INTO releases (id,date,artist,title,rtype) VALUES (?,?,?,?,?)",
            (rid, date, artist, title, rtype))

    def export(self):
        with contextlib.redirect_stdout(io.StringIO()):
            count = build.export_ics(self.db)
        self.assertTrue(self.output.is_file(), "An empty feed must also be written")
        raw = self.output.read_bytes()
        self.assertTrue(raw.startswith(b"BEGIN:VCALENDAR\r\n"))
        self.assertTrue(raw.endswith(b"END:VCALENDAR\r\n"))
        self.assertEqual(raw.count(b"BEGIN:VEVENT\r\n"), count)
        return count, raw

    def test_stamp_uses_utc_even_when_local_date_is_already_tomorrow(self):
        self.add_release()
        _, raw = self.export()
        self.assertIn(b"DTSTAMP:20261030T180304Z\r\n", raw)

    def test_empty_database_replaces_stale_subscription(self):
        self.output.write_text("stale events", encoding="utf-8")
        count, raw = self.export()
        self.assertEqual(count, 0)
        self.assertNotIn(b"stale events", raw)
        self.assertNotIn(b"BEGIN:VEVENT", raw)

    def test_empty_database_still_creates_a_calendar(self):
        count, _ = self.export()
        self.assertEqual(count, 0)

    def test_export_creates_missing_output_directory(self):
        self.add_release()
        self.output = self.root / "new" / "data" / "zhiwei.ics"
        with patch.object(build, "ICS_FILE", str(self.output)):
            self.export()

    def test_crlf_cr_and_lf_are_escaped_without_new_calendar_properties(self):
        self.add_release(artist="A", title="B\r\nC\rD\nE,;\\F")
        _, raw = self.export()
        unfolded = raw.replace(b"\r\n ", b"").decode("utf-8")
        self.assertIn("SUMMARY:A · B\\nC\\nD\\nE\\,\\;\\\\F\r\n", unfolded)
        without_line_endings = raw.replace(b"\r\n", b"")
        self.assertNotIn(b"\r", without_line_endings)
        self.assertNotIn(b"\n", without_line_endings)

    def test_invalid_dates_are_skipped_without_losing_valid_events(self):
        self.add_release()
        self.add_release(rid="bad-day", date="2026-11-31")
        self.add_release(rid="bad-format", date="2026-11-01junk")
        self.add_release(rid="week-date", date="2026-W01-1")
        count, raw = self.export()
        self.assertEqual(count, 1)
        self.assertIn(b"UID:release-1@mywooji.cn\r\n", raw)
        self.assertNotIn(b"UID:bad-", raw)
        self.assertNotIn(b"UID:week-date", raw)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM releases").fetchone()[0], 4)

    def test_calendar_window_includes_boundaries_only(self):
        for rid, date in (("too-old", "2026-08-31"), ("first", "2026-09-01"),
                          ("last", "2027-04-29"), ("too-new", "2027-04-30")):
            self.add_release(rid=rid, date=date)
        count, raw = self.export()
        self.assertEqual(count, 2)
        self.assertIn(b"UID:first@mywooji.cn\r\n", raw)
        self.assertIn(b"UID:last@mywooji.cn\r\n", raw)
        self.assertNotIn(b"UID:too-", raw)

    def test_all_day_event_ends_on_next_date_at_year_boundary(self):
        self.add_release(date="2026-12-31")
        _, raw = self.export()
        self.assertIn(b"DTSTART;VALUE=DATE:20261231\r\n", raw)
        self.assertIn(b"DTEND;VALUE=DATE:20270101\r\n", raw)

    def test_long_unicode_text_folds_without_corruption(self):
        title = "知未한글🎵" * 40
        self.add_release(artist="A", title=title)
        _, raw = self.export()
        for line in raw.split(b"\r\n"):
            self.assertLessEqual(len(line), 75)
            line.decode("utf-8")
        unfolded = raw.replace(b"\r\n ", b"").decode("utf-8")
        self.assertIn("SUMMARY:A · " + title + "\r\n", unfolded)


if __name__ == "__main__":
    unittest.main()
