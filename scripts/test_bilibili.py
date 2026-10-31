"""Offline collection regressions: network uncertainty must never become bad data."""
import sqlite3
import unittest
from unittest.mock import patch

import bilibili


class BilibiliCollectionTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.executescript(bilibili.DDL)
        self.addCleanup(self.db.close)
        bilibili._MIDCACHE.clear()
        self.addCleanup(bilibili._MIDCACHE.clear)
        for name, replacement in [('log', lambda *_: None), ('SLEEP', 0)]:
            mock = patch.object(bilibili, name, replacement)
            mock.start()
            self.addCleanup(mock.stop)

    def test_only_explicit_not_found_marks_video_dead(self):
        responses = [None, {}, {'code': -352}, {'code': -412}, {'code': -509},
                     {'code': -500}, {'code': -101}, {'code': 0}, {'code': -404}]
        for i in range(len(responses)):
            self.db.execute('INSERT INTO bili(bvid,dead) VALUES (?,0)', (f'video-{i}',))
        with patch.object(bilibili, 'api', side_effect=responses):
            bilibili.check_dead(self.db)
        self.assertEqual(self.db.execute('SELECT bvid FROM bili WHERE dead=1').fetchall(),
                         [('video-8',)])

    def test_failed_card_request_is_retried_and_never_cached_as_nonofficial(self):
        good = {'code': 0, 'data': {'card': {'name': 'Verified Label',
                'official_verify': {'type': 1, 'desc': 'Official music label'}}}}
        with patch.object(bilibili, 'api', side_effect=[{'code': -352}, good]) as api:
            self.assertFalse(bilibili.is_official(self.db, '123')[0])
            self.assertIsNone(self.db.execute('SELECT mid FROM bili_mid').fetchone())
            self.assertTrue(bilibili.is_official(self.db, '123')[0])
            self.assertEqual(api.call_count, 2)

    def test_legacy_empty_negative_cache_does_not_block_reverification(self):
        self.db.execute("INSERT INTO bili_mid VALUES ('123','',0,0)")
        good = {'code': 0, 'data': {'card': {'name': 'Verified Label',
                'official_verify': {'type': 1}}}}
        with patch.object(bilibili, 'api', return_value=good) as api:
            self.assertTrue(bilibili.is_official(self.db, '123')[0])
            api.assert_called_once()
        self.assertEqual(self.db.execute('SELECT official FROM bili_mid').fetchone(), (1,))

    def test_failed_profile_requests_keep_the_request_interval(self):
        with patch.object(bilibili, 'api', return_value={'code': -352}), \
             patch.object(bilibili, 'SLEEP', 2), \
             patch.object(bilibili.time, 'sleep') as sleep:
            for _ in range(3):
                bilibili.is_official(self.db, '123')
        self.assertEqual([call.args for call in sleep.call_args_list], [(1.0,)] * 3)

    def test_known_nonofficial_response_still_uses_cache(self):
        plain = {'code': 0, 'data': {'card': {'name': 'Fan Account',
                 'official_verify': {'type': -1}}}}
        with patch.object(bilibili, 'api', return_value=plain) as api:
            self.assertFalse(bilibili.is_official(self.db, '123')[0])
            bilibili._MIDCACHE.clear()
            self.assertFalse(bilibili.is_official(self.db, '123')[0])
            api.assert_called_once()

    def test_incomplete_successful_profile_stays_unknown(self):
        for response in [None, {'code': 0, 'data': {}},
                         {'code': 0, 'data': {'card': {'name': 'Unknown Status'}}},
                         {'code': 0, 'data': {'card': {'official_verify': {'type': 1}}}}]:
            with self.subTest(response=response), patch.object(bilibili, 'api', return_value=response):
                self.assertFalse(bilibili.is_official(self.db, '123')[0])
                self.assertIsNone(self.db.execute('SELECT mid FROM bili_mid').fetchone())


if __name__ == '__main__':
    unittest.main()
