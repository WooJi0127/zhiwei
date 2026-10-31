"""Offline regression cases for durable catalog state and publication gates."""
from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build

try:
    import catalog_state as state
except ImportError:
    state = None


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(state, 'Durable catalog persistence is missing')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'kpop.db'
        self.con = state.open_database(self.db)
        self.addCleanup(self.con.close)
        self.con.execute("INSERT INTO artists(name,agency) VALUES('Group','Verified agency')")
        self.con.execute("INSERT INTO releases(id,artist,title,date,image,extra) VALUES('r1','Group','Record','2026-10-01','cover','{\"trackCount\":2}')")
        self.con.execute("INSERT INTO tracks(id,release_id,name) VALUES('t1','r1','Track')")
        self.con.execute("INSERT INTO members(g,n,b,src) VALUES('Group','Member','2000-01-02','verified URL')")
        self.con.execute("INSERT INTO bili(bvid,artist,play,dead) VALUES('BV1','Group',10,0)")
        self.con.commit()
        self.catalog = self.root / 'catalog'
        state.save_snapshot(self.con, self.catalog)
        self.before = state.read_snapshot(self.catalog)

    def payload(self):
        return {'artists':[{'name':'Group'}], 'members':[{'g':'Group','n':'Member','b':'2000-01-02'}],
                'mvs':[{'v':'BV1'}], 'releases':[{'id':'r1','artist':'Group','title':'Record','date':'2026-10-01','tracks':[{'n':'Track'}]}],
                'years':{}, 'olderCount':0}

    def test_restores_every_table_without_cache_and_preserves_cloud_only_rows(self):
        self.con.execute("INSERT INTO releases(id,artist,title,date) VALUES('cloud-new','Group','New','2026-11-03')")
        self.con.commit()
        state.save_snapshot(self.con, self.catalog)
        target = self.root / 'fresh.db'
        state.restore_snapshot(self.catalog, target)
        with closing(sqlite3.connect(target)) as con:
            self.assertEqual(state.database_rows(con), state.read_snapshot(self.catalog))
            self.assertEqual(con.execute('SELECT count(*) FROM releases').fetchone()[0], 2)

    def test_snapshot_bytes_are_stable(self):
        before = {p.name:p.read_bytes() for p in self.catalog.iterdir()}
        state.save_snapshot(self.con, self.catalog)
        self.assertEqual(before, {p.name:p.read_bytes() for p in self.catalog.iterdir()})

    def test_windows_checkout_line_endings_preserve_snapshot_identity(self):
        for path in self.catalog.glob('*.jsonl'):
            path.write_bytes(path.read_bytes().replace(b'\n', b'\r\n'))
        self.assertEqual(state.read_snapshot(self.catalog), self.before)

    def test_corrupt_snapshot_cannot_overwrite_existing_database(self):
        (self.catalog / 'members.jsonl').write_text('', encoding='utf-8')
        original = self.db.read_bytes()
        with self.assertRaises(ValueError):
            state.restore_snapshot(self.catalog, self.db, replace=True)
        self.assertEqual(self.db.read_bytes(), original)

    def test_missing_snapshot_never_falls_back_to_empty_database(self):
        with self.assertRaises((ValueError, FileNotFoundError)):
            state.restore_snapshot(self.root / 'missing', self.root / 'new.db')
        self.assertFalse((self.root / 'new.db').exists())

    def test_local_edits_require_explicit_replace_and_get_backup(self):
        self.con.execute("UPDATE artists SET agency='Unsaved local correction'")
        self.con.commit()
        self.con.close()
        with self.assertRaises(ValueError):
            state.restore_snapshot(self.catalog, self.db)
        backup = state.restore_snapshot(self.catalog, self.db, replace=True)
        self.assertTrue(backup.is_file())
        with closing(sqlite3.connect(backup)) as old:
            self.assertEqual(old.execute('SELECT agency FROM artists').fetchone()[0], 'Unsaved local correction')

    def test_empty_response_preserves_existing_fields_and_extra(self):
        self.con.execute("UPDATE artists SET agency=''")
        self.con.execute("UPDATE releases SET image='', extra='{\"trackCount\":0}'")
        state.preserve_known_fields(self.con, self.before)
        self.assertEqual(self.con.execute('SELECT agency FROM artists').fetchone()[0], 'Verified agency')
        image, extra = self.con.execute('SELECT image,extra FROM releases').fetchone()
        self.assertEqual(image, 'cover')
        self.assertEqual(json.loads(extra)['trackCount'], 2)

    def test_loss_of_members_or_tracks_blocks_publication(self):
        for table in ('members','tracks'):
            with self.subTest(table=table):
                self.con.execute('SAVEPOINT regression')
                self.con.execute('DELETE FROM ' + table)
                with self.assertRaisesRegex(ValueError, table):
                    state.validate_database(self.con, self.before, [])
                self.con.execute('ROLLBACK TO regression')
                self.con.execute('RELEASE regression')

    def test_new_rows_do_not_mask_loss_of_existing_ids(self):
        self.con.execute("DELETE FROM members")
        self.con.execute("INSERT INTO members(g,n,b) VALUES('Group','Other','2001-01-02')")
        with self.assertRaisesRegex(ValueError, 'members'):
            state.validate_database(self.con, self.before, [])

    def test_explicit_correction_reapplied_and_deletion_is_explained(self):
        corrections = [
            {'table':'artists','key':{'name':'Group'},'set':{'am_id':123},'reason':'Verified artist identity','source':'https://music.apple.com/artist/123'},
            {'table':'releases','key':{'id':'r1'},'delete':True,'reason':'Wrong artist','source':'verified audit'},
        ]
        state.apply_corrections(self.con, corrections)
        self.assertEqual(self.con.execute('SELECT am_id FROM artists').fetchone()[0], 123)
        self.assertEqual(self.con.execute('SELECT count(*) FROM tracks').fetchone()[0], 0)
        state.validate_database(self.con, self.before, corrections)
        state.apply_corrections(self.con, corrections)  # idempotent

    def test_correction_without_evidence_is_rejected(self):
        with self.assertRaises(ValueError):
            state.apply_corrections(self.con, [{'table':'releases','key':{'id':'r1'},'delete':True}])

    def test_identity_correction_expires_only_the_wrong_artists_fetch_cache(self):
        self.con.execute("UPDATE artists SET am_id=999,am_updated='2026-10-31 09:00:00'")
        correction = [{'table':'artists','key':{'name':'Group'},'set':{'am_id':123},'reason':'Identity checked','source':'verified URL'}]
        state.apply_corrections(self.con, correction)
        self.assertIsNone(self.con.execute('SELECT am_updated FROM artists').fetchone()[0])
        self.con.execute("UPDATE artists SET am_updated='2026-10-31 10:00:00'")
        state.apply_corrections(self.con, correction)
        self.assertEqual(self.con.execute('SELECT am_updated FROM artists').fetchone()[0], '2026-10-31 10:00:00')

    def test_export_failure_leaves_previous_files_unchanged(self):
        data = self.root / 'data'
        data.mkdir()
        prior = 'window.__KPOP_DATA__ = ' + json.dumps(self.payload()) + ';\n'
        (data / 'data.js').write_text(prior, encoding='utf-8')
        self.con.execute('DELETE FROM members')
        with patch.object(build, 'DATA_DIR', str(data)), patch.object(build, 'OUT_JS', str(data/'data.js')), patch.object(state, 'CATALOG_DIR', self.catalog), patch.object(state, 'CORRECTIONS_PATH', self.root/'none.json'):
            with self.assertRaises(ValueError):
                build.export_data(self.con)
        self.assertEqual((data / 'data.js').read_text(encoding='utf-8'), prior)

    def test_missing_year_slice_blocks_export(self):
        data = self.root/'data'
        data.mkdir()
        payload = self.payload()
        payload['years'] = {'2020':1}
        payload['olderCount'] = 1
        (data/'data.js').write_text('window.__KPOP_DATA__ = '+json.dumps(payload)+';', encoding='utf-8')
        with self.assertRaises((ValueError, FileNotFoundError)):
            state.read_published(data)

    def test_dedup_keeps_the_more_complete_track_list(self):
        self.con.execute("UPDATE releases SET source='apple' WHERE id='r1'")
        self.con.execute("INSERT INTO releases(id,artist,title,date,source) VALUES('r2','Group','Record','2026-10-01','netease')")
        self.con.executemany('INSERT INTO tracks(id,release_id,name) VALUES(?,?,?)', [('t2','r2','Track'),('t3','r2','Second track')])
        self.con.commit()
        data = self.root/'data'
        data.mkdir()
        (data/'data.js').write_text('window.__KPOP_DATA__ = '+json.dumps(self.payload())+';', encoding='utf-8')
        with patch.object(build,'DATA_DIR',str(data)), patch.object(build,'OUT_JS',str(data/'data.js')), patch.object(state,'CATALOG_DIR',self.catalog), patch.object(state,'CORRECTIONS_PATH',self.root/'none.json'):
            result = build.export_data(self.con)
        self.assertEqual(result['releases'][0]['id'], 'r2')
        self.assertEqual(len(result['releases'][0]['tracks']), 2)

    def test_confirmed_dead_mv_allowed_but_disappearing_live_mv_blocked(self):
        before = self.payload()
        after = self.payload()
        after['mvs'] = []
        with self.assertRaisesRegex(ValueError, 'MV'):
            state.validate_export(self.con, before, after, [])
        self.con.execute("UPDATE bili SET dead=1 WHERE bvid='BV1'")
        state.validate_export(self.con, before, after, [])

    def test_dedup_change_allowed_but_track_loss_blocked(self):
        before, after = self.payload(), self.payload()
        after['releases'][0]['id'] = 'apple-r1'
        after['releases'][0]['title'] = 'Record - Single'
        after['releases'][0]['date'] = '2026-10-02'
        state.validate_export(self.con, before, after, [])
        after['releases'][0]['tracks'] = []
        with self.assertRaisesRegex(ValueError, 'tracks'):
            state.validate_export(self.con, before, after, [])

    def test_expired_history_is_allowed(self):
        before, after = self.payload(), self.payload()
        before['releases'][0]['date'] = '2000-01-01'
        after['releases'] = []
        state.validate_export(self.con, before, after, [])

    def test_only_public_catalog_tables_are_serialized(self):
        self.con.execute('CREATE TABLE users(secret TEXT)')
        self.con.execute("INSERT INTO users VALUES('private')")
        state.save_snapshot(self.con, self.catalog)
        self.assertNotIn('private', ''.join(p.read_text(encoding='utf-8') for p in self.catalog.iterdir()))


if __name__ == '__main__':
    unittest.main()
