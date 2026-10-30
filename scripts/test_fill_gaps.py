"""Offline regression tests for artist enrichment; never touches the project DB."""
import contextlib
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fill_gaps


def profile(name="Example Group", agency="Example Entertainment", fandom="Fans", debut="2020-01-01"):
    return (f"<h1>{name}</h1><h2>Group Info</h2><dl>"
            f"<dt>Company:</dt><dd>{agency}</dd>"
            f"<dt>Fandom Name:</dt><dd>{fandom}</dd>"
            f"<dt>Debut:</dt><dd>{debut}</dd></dl>").encode("utf-8")


class ArtistEnrichmentTests(unittest.TestCase):
    def setUp(self):
        temp_root = Path(__file__).resolve().parents[1] / ".build-logs"
        temp_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temp_root)
        self.addCleanup(self.temp.cleanup)
        self.db = str(Path(self.temp.name) / "test.db")
        with contextlib.closing(sqlite3.connect(self.db)) as db, db:
            db.execute("CREATE TABLE artists (name TEXT PRIMARY KEY, kind TEXT, agency TEXT, fandom TEXT, debut_year INTEGER)")
            db.execute("INSERT INTO artists VALUES ('Example Group','group',NULL,NULL,NULL)")

    def run_enrichment(self, response):
        with patch.object(fill_gaps, "DB", self.db), \
             patch.object(fill_gaps, "http_get", return_value=response), \
             patch.object(fill_gaps, "PAUSE", 0), \
             contextlib.redirect_stdout(io.StringIO()):
            fill_gaps.fill_artists()
        with contextlib.closing(sqlite3.connect(self.db)) as db:
            return db.execute("SELECT agency,fandom,debut_year FROM artists").fetchone()

    def test_http_bytes_populate_exact_fields_without_adjacent_labels(self):
        self.assertEqual(self.run_enrichment(profile()), ("Example Entertainment", "Fans", 2020))

    def test_existing_verified_fields_are_preserved(self):
        with contextlib.closing(sqlite3.connect(self.db)) as db, db:
            db.execute("UPDATE artists SET agency='Verified Agency',debut_year=2019")
        self.assertEqual(self.run_enrichment(profile()), ("Verified Agency", "Fans", 2019))

    def test_unicode_and_html_entities_are_preserved(self):
        self.assertEqual(self.run_enrichment(profile(agency="에이전시 &amp; Co.", fandom="별빛!")),
                         ("에이전시 & Co.", "별빛!", 2020))

    def test_unmatched_heading_does_not_change_database(self):
        self.assertEqual(self.run_enrichment(profile(name="Another Group")), (None, None, None))

    def test_company_history_is_not_an_agency_name(self):
        page = b'<h1>Example Group</h1><h2>Group Info</h2><div>Company History</div><p>Old Label</p>'
        self.assertEqual(self.run_enrichment(page), (None, None, None))

    def test_unknown_placeholders_remain_missing(self):
        self.assertEqual(self.run_enrichment(profile(agency="TBA", fandom="N/A", debut="Unknown")),
                         (None, None, None))

    def test_empty_fields_do_not_consume_the_next_label(self):
        self.assertEqual(self.run_enrichment(profile(agency="", fandom="")), (None, None, 2020))

    def test_nested_value_text_is_kept_together(self):
        self.assertEqual(self.run_enrichment(profile(agency="Example <strong>Entertainment</strong>")),
                         ("Example Entertainment", "Fans", 2020))

    def test_line_breaks_in_values_do_not_merge_words(self):
        self.assertEqual(self.run_enrichment(profile(agency="Example<br>Entertainment")),
                         ("Example Entertainment", "Fans", 2020))

    def test_untyped_adjacent_divs_are_not_treated_as_profile_fields(self):
        page = (b'<h1>Example Group</h1><h2>Group Info</h2>'
                b'<div>Company:</div><div>Genres:</div><div>K-pop</div>')
        self.assertEqual(self.run_enrichment(page), (None, None, None))

    def test_solo_artist_is_not_enriched_from_group_page(self):
        with contextlib.closing(sqlite3.connect(self.db)) as db, db:
            db.execute("UPDATE artists SET kind='solo'")
        self.assertEqual(self.run_enrichment(profile()), (None, None, None))

    def test_failed_request_leaves_database_unchanged(self):
        self.assertEqual(self.run_enrichment(None), (None, None, None))


if __name__ == "__main__":
    unittest.main()
