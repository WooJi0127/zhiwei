"""Apple artist lookups must not reassign an existing collection's owner."""
import sqlite3
import unittest
from unittest.mock import patch

import build


class AppleCollectionIdentityTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(':memory:')
        self.addCleanup(self.con.close)
        self.con.executescript(build.SCHEMA)

    def album(self, collection_id=1773213946, title='Mantra - Single'):
        return {
            'wrapperType': 'collection', 'collectionId': collection_id,
            'collectionName': title, 'releaseDate': '2024-10-11T00:00:00Z',
            'primaryGenreName': 'K-Pop', 'copyright': 'Verified label',
            'trackCount': 1, 'artworkUrl100': 'updated-cover',
            'collectionViewUrl': 'https://music.apple.com/kr/album/' + str(collection_id),
        }

    def refresh(self, responses, force=True):
        with patch.object(build.sources, 'itunes_lookup_albums',
                          side_effect=lambda aid: responses.get(aid, [])), \
                patch.object(build.sources, 'itunes_lookup_songs', return_value=[]), \
                patch.object(build.sources, 'itunes_search_artist', return_value=None), \
                patch.object(build.time, 'sleep'), patch.object(build, 'log'):
            return build.step_apple_music(self.con, force=force)

    def test_alias_refresh_keeps_existing_owner_in_either_refresh_order(self):
        self.con.executemany('INSERT INTO artists(name,am_id) VALUES(?,?)',
                             [('JENNIE', 913944), ('Jennie', 913944)])
        self.con.execute("INSERT INTO releases(id,artist,title,date) "
                         "VALUES('am:1773213946','JENNIE','Mantra - Single','2024-10-11')")
        for order in (('JENNIE', 'Jennie'), ('Jennie', 'JENNIE')):
            with self.subTest(order=order):
                self.con.execute("UPDATE releases SET artist='JENNIE'")
                for name in order:
                    self.con.execute("UPDATE artists SET am_updated='9999-01-01 00:00:00'")
                    self.con.execute('UPDATE artists SET am_updated=NULL WHERE name=?', (name,))
                    self.refresh({913944: [self.album()]}, force=False)
                    self.assertEqual(self.con.execute('SELECT artist FROM releases').fetchone()[0], 'JENNIE')

    def test_collaborator_lookup_cannot_reassign_an_existing_collection(self):
        self.con.executemany('INSERT INTO artists(name,am_id) VALUES(?,?)',
                             [('Coogie', 448249729), ('pH-1', 1173422048)])
        self.con.execute("INSERT INTO releases(id,artist,title,date) "
                         "VALUES('am:1532682066','pH-1','Life Goes On (feat. pH-1) - Single','2020-09-19')")
        album = self.album(1532682066, 'Life Goes On (feat. pH-1) - Single')
        album['releaseDate'] = '2020-09-19T00:00:00Z'
        self.refresh({448249729: [album], 1173422048: []})
        self.assertEqual(self.con.execute('SELECT artist FROM releases').fetchone()[0], 'pH-1')

    def test_existing_collection_still_refreshes_its_metadata(self):
        self.con.execute("INSERT INTO artists(name,am_id) VALUES('Jennie',913944)")
        self.con.execute("INSERT INTO releases(id,artist,title,date,image) "
                         "VALUES('am:1773213946','JENNIE','Old title','2024-10-10','old-cover')")
        self.refresh({913944: [self.album()]})
        self.assertEqual(self.con.execute(
            'SELECT artist,title,date,image FROM releases').fetchone(),
            ('JENNIE', 'Mantra - Single', '2024-10-11', 'updated-cover'))

    def test_missing_owner_is_filled_from_the_current_lookup(self):
        self.con.execute("INSERT INTO artists(name,am_id) VALUES('JENNIE',913944)")
        for owner in (None, ''):
            with self.subTest(owner=owner):
                self.con.execute('DELETE FROM releases')
                self.con.execute("INSERT INTO releases(id,artist,title,date) VALUES(?,?,?,?)",
                                 ('am:1773213946', owner, 'Mantra - Single', '2024-10-11'))
                self.refresh({913944: [self.album()]})
                self.assertEqual(self.con.execute('SELECT artist FROM releases').fetchone()[0], 'JENNIE')

    def test_new_collection_is_still_added_with_its_lookup_artist(self):
        self.con.execute("INSERT INTO artists(name,am_id) VALUES('JENNIE',913944)")
        self.refresh({913944: [self.album()]})
        self.assertEqual(self.con.execute('SELECT id,artist FROM releases').fetchall(),
                         [('am:1773213946', 'JENNIE')])


if __name__ == '__main__':
    unittest.main()
