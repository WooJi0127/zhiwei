"""Reviewed announcements survive rebuilds without replacing catalog details."""
from contextlib import closing
import datetime
import importlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

SCHEMA = """
CREATE TABLE artists(name TEXT PRIMARY KEY, agency TEXT, debut_year INTEGER);
CREATE TABLE releases(id TEXT PRIMARY KEY, source TEXT, date TEXT, artist TEXT,
                      title TEXT, rtype TEXT, image TEXT, url TEXT, extra TEXT,
                      rtype_src TEXT);
CREATE TABLE tracks(id TEXT PRIMARY KEY, release_id TEXT, name TEXT, track_no INTEGER);
"""


class VerifiedAnnouncementTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('announcements'),
                             'Reviewed-announcement replay is not implemented')
        self.announcements = importlib.import_module('announcements')
        self.con = sqlite3.connect(':memory:')
        self.addCleanup(self.con.close)
        self.con.executescript(SCHEMA)
        self.item = {
            'id': 'official:test-group-debut-ep',
            'artist': 'Test Group', 'title': 'First Light',
            'date': '2026-11-09', 'subtype': 'EP',
            'source_urls': ['https://example.org/official-announcement'],
            'reason': 'Official announcement confirms the debut EP and release date.',
            'verified_on': '2026-11-06', 'track_count': 5,
        }

    def apply(self, items):
        # Keep the database real; substitute only the on-disk review ledger.
        with patch.object(Path, 'read_text', return_value=json.dumps(items)):
            return self.announcements.apply_verified_announcements(self.con, 'review.json')

    def test_checked_in_debut_replays_into_each_fresh_database(self):
        for _ in range(2):
            with self.subTest(rebuild=_), closing(sqlite3.connect(':memory:')) as con:
                con.executescript(SCHEMA)
                self.announcements.apply_verified_announcements(con)
                row = con.execute(
                    "SELECT id,source,date,title,rtype,rtype_src,image,extra FROM releases "
                    "WHERE artist='A2O SOUL' AND date='2026-11-09'").fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row[:7], ('official:a2o-soul-superstar-debut-ep',
                                          'official', '2026-11-09', 'SUPERSTAR',
                                          'EP', 'EP', ''))
                extra = json.loads(row[7])
                self.assertEqual(extra['trackCount'], 5)
                self.assertEqual(extra['verified_announcement']['verified_on'], '2026-11-06')
                self.assertTrue(extra['verified_announcement']['source_urls'])
                self.assertEqual(con.execute('SELECT count(*) FROM tracks').fetchone()[0], 0)
                self.assertIsNotNone(con.execute(
                    "SELECT name FROM artists WHERE name='A2O SOUL'").fetchone())

    def test_replay_is_idempotent_and_preserves_october_single(self):
        self.con.execute("INSERT INTO releases(id,source,date,artist,title,rtype,rtype_src) "
                         "VALUES('am:october','apple','2026-10-13','A2O SOUL',"
                         "'SUPERSTAR - Single','Single','Single')")
        self.announcements.apply_verified_announcements(self.con)
        before = list(self.con.execute('SELECT * FROM releases ORDER BY id'))
        self.announcements.apply_verified_announcements(self.con)
        self.assertEqual(list(self.con.execute('SELECT * FROM releases ORDER BY id')), before)
        self.assertEqual(self.con.execute(
            "SELECT date,rtype FROM releases WHERE artist='A2O SOUL' ORDER BY date").fetchall(),
            [('2026-10-13', 'Single'), ('2026-11-09', 'EP')])

    def test_date_correction_updates_same_stable_id(self):
        self.assertEqual(self.apply([self.item]), 1)
        changed = dict(self.item, date='2026-11-12', verified_on='2026-11-07')
        self.assertEqual(self.apply([changed]), 1)
        self.assertEqual(self.con.execute('SELECT id,date FROM releases').fetchall(),
                         [('official:test-group-debut-ep', '2026-11-12')])

    def test_replay_preserves_richer_artwork_tracks_and_artist_details(self):
        self.apply([self.item])
        self.con.execute("UPDATE artists SET agency='Verified Agency', debut_year=2026")
        self.con.execute("UPDATE releases SET image='https://example.org/cover.jpg',extra=?",
                         (json.dumps({'genre': 'Pop', 'copyright': 'Verified copyright',
                                      'other_source_id': 'album-123'}),))
        self.con.execute("INSERT INTO tracks(id,release_id,name,track_no) VALUES(?,?,?,?)",
                         ('track:one', self.item['id'], 'First Light', 1))
        self.apply([self.item])
        row = self.con.execute('SELECT image,extra FROM releases').fetchone()
        self.assertEqual(row[0], 'https://example.org/cover.jpg')
        extra = json.loads(row[1])
        self.assertEqual(extra['genre'], 'Pop')
        self.assertEqual(extra['copyright'], 'Verified copyright')
        self.assertEqual(extra['other_source_id'], 'album-123')
        self.assertEqual(extra['trackCount'], 5)
        self.assertEqual(self.con.execute('SELECT name,track_no FROM tracks').fetchall(),
                         [('First Light', 1)])
        self.assertEqual(self.con.execute('SELECT agency,debut_year FROM artists').fetchone(),
                         ('Verified Agency', 2026))

    def test_unknown_subtype_stays_empty_without_guessing(self):
        self.apply([dict(self.item, subtype=None)])
        self.assertEqual(self.con.execute('SELECT rtype,rtype_src FROM releases').fetchone(),
                         (None, None))

    def test_unknown_fields_do_not_erase_later_catalog_enrichment(self):
        self.apply([self.item])
        unknown = dict(self.item, subtype=None)
        unknown.pop('track_count')
        self.apply([unknown])
        row = self.con.execute('SELECT rtype,rtype_src,extra FROM releases').fetchone()
        self.assertEqual(row[:2], ('EP', 'EP'))
        self.assertEqual(json.loads(row[2])['trackCount'], 5)

    def test_invalid_entry_rejects_entire_ledger_before_any_write(self):
        changes = [
            {'date': '2026-02-30'}, {'date': '20261109'}, {'date': '2026-11-9'},
            {'verified_on': '2026-11-31'}, {'artist': '  '}, {'title': None},
            {'subtype': 'Mini Album'}, {'subtype': []}, {'id': 'kp:unreviewed'},
            {'source_urls': []}, {'source_urls': ['http://example.org/news']},
            {'source_urls': ['https:///news']}, {'source_urls': 'https://example.org/news'},
            {'reason': ' '}, {'track_count': -1}, {'track_count': True},
        ]
        for change in changes:
            with self.subTest(change=change):
                invalid = dict(self.item, id='official:second-entry')
                invalid.update(change)
                with self.assertRaises(ValueError):
                    self.apply([self.item, invalid])
                self.assertEqual(self.con.execute('SELECT count(*) FROM releases').fetchone()[0], 0)
                self.assertEqual(self.con.execute('SELECT count(*) FROM artists').fetchone()[0], 0)

    def test_missing_provenance_and_duplicate_ids_are_rejected(self):
        for field in ('reason', 'source_urls', 'verified_on'):
            with self.subTest(missing=field):
                invalid = dict(self.item)
                del invalid[field]
                with self.assertRaises(ValueError):
                    self.apply([invalid])
        with self.assertRaises(ValueError):
            self.apply([self.item, self.item])
        self.assertEqual(self.con.execute('SELECT count(*) FROM releases').fetchone()[0], 0)

    def test_database_failure_rolls_back_all_announcement_writes(self):
        self.con.execute("CREATE TRIGGER reject_second BEFORE INSERT ON releases "
                         "WHEN NEW.id='official:second-entry' "
                         "BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.apply([self.item, dict(self.item, id='official:second-entry', artist='Other Group')])
        self.assertEqual(self.con.execute('SELECT count(*) FROM releases').fetchone()[0], 0)
        self.assertEqual(self.con.execute('SELECT count(*) FROM artists').fetchone()[0], 0)


class AnnouncementExportTests(unittest.TestCase):
    def test_export_only_restores_catalog_and_publishes_both_single_and_debut_ep(self):
        import build
        import catalog_state as state

        class FixedDate(datetime.date):
            @classmethod
            def today(cls):
                return cls(2026, 11, 6)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog, data = root / 'catalog', root / 'data'
            data.mkdir()
            with closing(state.open_database(':memory:')) as con:
                con.execute("INSERT INTO artists(name) VALUES('A2O SOUL')")
                con.execute("INSERT INTO releases(id,source,date,artist,title,rtype,rtype_src) "
                            "VALUES('am:october','apple','2026-10-13','A2O SOUL',"
                            "'SUPERSTAR - Single','Single','Single')")
                con.commit()
                state.save_snapshot(con, catalog)
            old_payload = {
                'artists': [{'name': 'A2O SOUL'}], 'members': [], 'mvs': [],
                'releases': [{'id': 'am:october', 'artist': 'A2O SOUL',
                              'title': 'SUPERSTAR - Single', 'date': '2026-10-13'}],
                'years': {}, 'olderCount': 0,
            }
            out_js, out_ics = data / 'data.js', data / 'zhiwei.ics'
            out_js.write_text('window.__KPOP_DATA__ = ' + json.dumps(old_payload) + ';',
                              encoding='utf-8')
            with patch.object(build, 'DB_PATH', str(root / 'restored.db')), \
                    patch.object(build, 'DATA_DIR', str(data)), \
                    patch.object(build, 'OUT_JS', str(out_js)), \
                    patch.object(build, 'ICS_FILE', str(out_ics)), \
                    patch.object(build, 'log'), \
                    patch.object(build.sys, 'argv', ['build.py', '--export-only']), \
                    patch.object(build.datetime, 'date', FixedDate), \
                    patch.object(state, 'CATALOG_DIR', catalog), \
                    patch.object(state, 'CORRECTIONS_PATH', root / 'none.json'):
                self.assertEqual(build.main(), 0)
            published = state.read_published(data)
            self.assertEqual(sorted((r['date'], r['rtype']) for r in published['releases']),
                             [('2026-10-13', 'Single'), ('2026-11-09', 'EP')])
            debut = next(r for r in published['releases'] if r['date'] == '2026-11-09')
            self.assertEqual(debut['id'], 'official:a2o-soul-superstar-debut-ep')
            self.assertEqual(debut['trackCount'], 5)
            self.assertEqual(debut['image'], '')
            self.assertEqual(debut.get('tracks', []), [])
            calendar = out_ics.read_text(encoding='utf-8')
            self.assertIn('DTSTART;VALUE=DATE:20261109', calendar)
            self.assertIn('DTSTART;VALUE=DATE:20261013', calendar)
            self.assertEqual(calendar.count('BEGIN:VEVENT'), 2)


if __name__ == '__main__':
    unittest.main()
