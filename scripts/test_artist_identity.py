"""Exact artist identities and old release IDs survive publication deduplication."""
import copy
import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build
import catalog_state as state


class ArtistIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.con = state.open_database(self.root / 'test.db')
        self.addCleanup(self.con.close)
        self.date = datetime.date.today().isoformat()
        self.artists = ['NCT DREAM', 'NCT Dream', 'LISA', 'Lisa', 'ROSÉ', 'Rosé']
        self.con.executemany('INSERT INTO artists(name) VALUES(?)', [(n,) for n in self.artists])
        self.before = {'artists': [{'name': n} for n in self.artists], 'releases': [],
                       'members': [], 'mvs': [], 'years': {}, 'olderCount': 0}
        self.data = self.root / 'data'
        self.data.mkdir()

    def release(self, rid, artist, title='Record', date=None, tracks=0, source='apple'):
        date = date or self.date
        self.con.execute('INSERT INTO releases(id,artist,title,date,source) VALUES(?,?,?,?,?)',
                         (rid, artist, title, date, source))
        for i in range(tracks):
            self.con.execute('INSERT INTO tracks(id,release_id,name,track_no) VALUES(?,?,?,?)',
                             (rid + ':' + str(i), rid, 'Track ' + str(i), i + 1))
        self.con.commit()
        rel = {'id': rid, 'artist': artist, 'title': title, 'date': date}
        if tracks:
            rel['tracks'] = [{'n': 'Track ' + str(i)} for i in range(tracks)]
        self.before['releases'].append(rel)
        return rel

    def export(self):
        (self.data / 'data.js').write_text('window.__KPOP_DATA__ = ' + json.dumps(self.before) + ';', encoding='utf-8')
        with patch.object(build, 'DATA_DIR', str(self.data)), patch.object(build, 'OUT_JS', str(self.data / 'data.js')), \
             patch.object(state, 'CATALOG_DIR', self.root / 'missing-catalog'), \
             patch.object(state, 'CORRECTIONS_PATH', self.root / 'missing-corrections.json'):
            build.export_data(self.con)
        return state.read_published(self.data)

    def test_case_variants_merge_without_losing_raw_records_or_old_ids(self):
        for i, (upper, mixed) in enumerate(zip(self.artists[::2], self.artists[1::2])):
            self.release('old' + str(i), upper, tracks=1, source='kpopping')
            self.release('full' + str(i), mixed, tracks=2)
        raw = state.database_rows(self.con)
        after = self.export()
        self.assertEqual(len(after['releases']), 3)
        self.assertEqual(after['releaseAliases'], {'old0': 'full0', 'old1': 'full1', 'old2': 'full2'})
        self.assertTrue(all(len(r['tracks']) == 2 for r in after['releases']))
        self.assertEqual(state.database_rows(self.con), raw)

    def test_explicit_aliases_merge_but_different_dates_and_distinct_names_do_not(self):
        pairs = [('TXT', 'TOMORROW X TOGETHER'), ('(G)I-DLE', 'i-dle')]
        for i, (a, b) in enumerate(pairs):
            self.release('alias' + str(i), a, title='Alias ' + str(i))
            self.release('canonical' + str(i), b, title='Alias ' + str(i), tracks=1)
        for i, artist in enumerate(['Rose', 'Rosé', 'NCT 127', 'NCT DREAM', 'Mark', 'Mark Tuan']):
            self.release('distinct' + str(i), artist, title='Distinct')
        self.release('later', 'NCT Dream', title='Distinct',
                     date=(datetime.date.today() + datetime.timedelta(days=10)).isoformat())
        after = self.export()
        self.assertEqual(len(after['releases']), 9)
        self.assertEqual(after['releaseAliases'], {'alias0': 'canonical0', 'alias1': 'canonical1'})

    def test_global_aliases_cover_archives_and_survive_winner_changes(self):
        day = (datetime.date.today() - datetime.timedelta(days=800)).isoformat()
        self.release('old', 'NCT DREAM', date=day, tracks=1)
        self.release('winner', 'NCT Dream', date=day, tracks=2)
        first = self.export()
        self.assertEqual(first['releaseAliases']['old'], 'winner')
        self.before = first
        self.con.execute('INSERT INTO tracks(id,release_id,name) VALUES(?,?,?)', ('old:new1', 'old', 'New 1'))
        self.con.execute('INSERT INTO tracks(id,release_id,name) VALUES(?,?,?)', ('old:new2', 'old', 'New 2'))
        self.con.commit()
        # A previously published alias is retained even if its raw source later vanished.
        self.before['releaseAliases']['older-link'] = 'winner'
        # Write a flat fixture baseline; export will generate a real archive manifest.
        self.before['years'], self.before['olderCount'] = {}, 0
        second = self.export()
        self.assertEqual(second['releaseAliases'], {'winner': 'old', 'older-link': 'old'})
        self.assertEqual(second['releases'][0]['id'], 'old')
        self.assertEqual(second['olderCount'], 1)

    def test_publication_requires_compatible_alias_for_removed_id(self):
        old = self.release('old', 'NCT DREAM', tracks=1)
        after = copy.deepcopy(self.before)
        after['releases'][0].update(id='new', artist='NCT Dream')
        with self.assertRaisesRegex(ValueError, 'release missing|alias'):
            state.validate_export(self.con, self.before, after, [])
        after['releaseAliases'] = {'old': 'new'}
        state.validate_export(self.con, self.before, after, [])
        for changes in [{'artist': 'NCT 127'}, {'title': 'Unrelated'}, {'tracks': []},
                        {'date': (datetime.date.today() + datetime.timedelta(days=10)).isoformat()}]:
            invalid = copy.deepcopy(after)
            invalid['releases'][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                state.validate_export(self.con, self.before, invalid, [])

    def test_publication_cannot_drop_existing_alias_or_allow_dangling_alias(self):
        self.release('record', 'NCT DREAM')
        self.before['releaseAliases'] = {'old-link': 'record'}
        after = copy.deepcopy(self.before)
        after['releaseAliases'] = {}
        with self.assertRaisesRegex(ValueError, 'alias'):
            state.validate_export(self.con, self.before, after, [])
        after['releaseAliases'] = {'old-link': 'missing'}
        with self.assertRaisesRegex(ValueError, 'alias'):
            state.validate_export(self.con, self.before, after, [])

    def test_existing_alias_follows_verified_date_change_of_same_source_id(self):
        self.release('record', 'NCT DREAM')
        self.before['releaseAliases'] = {'old-link': 'record'}
        after = copy.deepcopy(self.before)
        after['releases'][0]['date'] = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()
        state.validate_export(self.con, self.before, after, [])


if __name__ == '__main__':
    unittest.main()
