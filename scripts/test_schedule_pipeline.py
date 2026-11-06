"""A blocked primary calendar must not silently lose upcoming releases."""
from contextlib import closing, redirect_stdout, ExitStack
import datetime
import io
import json
import sqlite3
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import build


class NovemberDate(datetime.date):
    @classmethod
    def today(cls):
        return cls(2026, 11, 6)


def release(date='2026-11-09'):
    return dict(date=date, artist='A2O SOUL', title='SUPERSTAR', type='EP',
                image='', source_id='123', url='https://example.com/verified-release')


class SchedulePipelineTests(unittest.TestCase):
    def database(self):
        con = sqlite3.connect(':memory:')
        con.executescript(build.SCHEMA)
        con.execute("INSERT INTO artists(name) VALUES('A2O SOUL')")
        con.execute("INSERT INTO releases(id,source,artist,title,date,rtype) VALUES"
                    "('old-single','apple','A2O SOUL','SUPERSTAR - Single','2026-10-13','Single')")
        return con

    def collect(self, con, primary, fallback, months=(0,)):
        with patch.object(build.datetime, 'date', NovemberDate), \
                patch.object(build.sources, 'fetch_kpopping_month', side_effect=primary), \
                patch.object(build, 'schedule_fallback', types.SimpleNamespace(fetch_month=fallback), create=True), \
                patch.object(build.time, 'sleep'), patch.object(build, 'log'):
            return build.step_schedules(con, months)

    def test_blocked_primary_uses_fallback_and_keeps_prerelease(self):
        with closing(self.database()) as con:
            report = self.collect(con, [RuntimeError('HTTP 403')], lambda y, m: [release()])
            self.assertEqual(report[0]['status'], 'fallback')
            self.assertEqual(con.execute('SELECT date,rtype FROM releases ORDER BY date').fetchall(),
                             [('2026-10-13', 'Single'), ('2026-11-09', 'EP')])

    def test_repeated_fallback_updates_same_row_without_duplicate(self):
        with closing(self.database()) as con:
            for date in ('2026-11-09', '2026-11-10'):
                self.collect(con, [RuntimeError('blocked')], lambda y, m: [release(date)])
            self.assertEqual(con.execute('SELECT date FROM releases ORDER BY date').fetchall(),
                             [('2026-10-13',), ('2026-11-10',)])

    def test_healthy_primary_does_not_require_fallback(self):
        def unexpected(y, m):
            self.fail('Healthy primary must not depend on fallback availability')
        with closing(self.database()) as con:
            report = self.collect(con, [([release()], {}, set(), set())], unexpected)
            self.assertEqual(report[0]['status'], 'ok')
            self.assertEqual(con.execute('SELECT COUNT(*) FROM releases').fetchone()[0], 2)

    def test_both_sources_failed_is_not_a_successful_empty_month(self):
        def unavailable(y, m):
            raise RuntimeError('fallback unavailable')
        with closing(self.database()) as con:
            report = self.collect(con, [RuntimeError('HTTP 403')], unavailable)
            self.assertEqual(report[0]['status'], 'failed')
            self.assertIn('403', report[0]['error'])
            self.assertIn('fallback unavailable', report[0]['fallback_error'])
            self.assertEqual(con.execute('SELECT id FROM releases').fetchall(), [('old-single',)])

    def test_failed_month_does_not_skip_other_month(self):
        def unavailable(y, m):
            raise RuntimeError('unavailable')
        with closing(self.database()) as con:
            report = self.collect(con, [RuntimeError('HTTP 403'),
                                       ([release('2026-12-09')], {}, set(), set())],
                                  unavailable, months=(0, 1))
            self.assertEqual([r['status'] for r in report], ['failed', 'ok'])
            self.assertEqual(con.execute('SELECT date FROM releases ORDER BY date').fetchall(),
                             [('2026-10-13',), ('2026-12-09',)])

    def test_failed_coverage_returns_nonzero_with_actionable_annotation(self):
        output = io.StringIO()
        with patch.dict(build.os.environ, {'GITHUB_STEP_SUMMARY': ''}), redirect_stdout(output):
            status = build.report_schedule_health([
                {'month': '2026-11', 'status': 'failed', 'count': 0,
                 'error': 'HTTP 403', 'fallback_error': 'unavailable'}])
        self.assertNotEqual(status, 0)
        self.assertIn('::error', output.getvalue())
        self.assertIn('2026-11', output.getvalue())

    def test_working_fallback_is_successful_but_primary_outage_is_visible(self):
        output = io.StringIO()
        with patch.dict(build.os.environ, {'GITHUB_STEP_SUMMARY': ''}), redirect_stdout(output):
            status = build.report_schedule_health([
                {'month': '2026-11', 'status': 'fallback', 'count': 1, 'error': 'HTTP 403'}])
        self.assertEqual(status, 0)
        self.assertIn('::warning', output.getvalue())

    def test_fallback_does_not_duplicate_official_announcement(self):
        with closing(self.database()) as con:
            con.execute("INSERT INTO releases(id,source,artist,title,date,rtype) VALUES"
                        "('official:ep','official','A2O SOUL','SUPERSTAR','2026-11-09','EP')")
            self.collect(con, [RuntimeError('blocked')], lambda y, m: [release()])
            self.assertEqual(con.execute('SELECT id FROM releases ORDER BY id').fetchall(),
                             [('official:ep',), ('old-single',)])

    def test_fallback_deduplicates_release_under_another_artist_case(self):
        with closing(self.database()) as con:
            con.executemany('INSERT INTO artists(name) VALUES(?)',
                            [('NCT DREAM',), ('NCT Dream',)])
            con.execute("INSERT INTO releases(id,source,artist,title,date,rtype) VALUES"
                        "('kp:dream','kpopping','NCT Dream','DREAM AFTER DREAM','2026-11-09','Album')")
            announced = dict(release(), artist='NCT DREAM', title='DREAM AFTER DREAM',
                             type='Album', source_id='126977')
            report = self.collect(con, [RuntimeError('blocked')], lambda y, m: [announced])
            self.assertEqual(report[0]['status'], 'fallback')
            self.assertEqual(con.execute('SELECT id,artist FROM releases ORDER BY id').fetchall(),
                             [('kp:dream', 'NCT Dream'), ('old-single', 'A2O SOUL')])
            self.assertEqual(report[0]['count'], 0)

    def test_cli_retains_collected_work_but_fails_when_both_calendars_are_down(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            data = root / 'data'
            data.mkdir()
            (data / 'data.js').write_text('window.__KPOP_DATA__ = ' + json.dumps({
                'artists': [], 'releases': [], 'members': [], 'mvs': [], 'events': [],
                'years': {}, 'olderCount': 0}) + ';', encoding='utf-8')
            db = root / 'kpop.db'
            with closing(sqlite3.connect(db)) as con:
                con.executescript(build.SCHEMA)
                con.commit()
            for target, name, value in (
                    (build, 'DB_PATH', str(db)), (build, 'DATA_DIR', str(data)),
                    (build, 'OUT_JS', str(data / 'data.js')),
                    (build, 'ICS_FILE', str(data / 'zhiwei.ics')),
                    (build, 'LOG_PATH', str(root / 'update.log')),
                    (build.catalog_state, 'CATALOG_DIR', root / 'catalog'),
                    (build.catalog_state, 'CORRECTIONS_PATH', root / 'no-corrections.json'),
                    (build.sys, 'argv', ['build.py', '--schedules-only'])):
                stack.enter_context(patch.object(target, name, value))
            stack.enter_context(patch.object(build.sources, 'fetch_kpopping_month', side_effect=RuntimeError('403')))
            stack.enter_context(patch.object(build.schedule_fallback, 'fetch_month', side_effect=RuntimeError('unavailable')))
            stack.enter_context(patch.dict(build.os.environ, {'GITHUB_STEP_SUMMARY': ''}))
            stack.enter_context(redirect_stdout(io.StringIO()))
            status = build.main()
            self.assertEqual(status, 3)
            self.assertTrue((root / 'catalog' / 'manifest.json').is_file())
            with closing(sqlite3.connect(db)) as con:
                self.assertEqual(con.execute("SELECT date,rtype FROM releases WHERE artist='A2O SOUL'").fetchall(),
                                 [('2026-11-09', 'EP')])
            # An offline rebuild must replay the reviewed announcement without network.
            build.sys.argv = ['build.py', '--export-only']
            self.assertEqual(build.main(), 0)
            with closing(sqlite3.connect(db)) as con:
                self.assertEqual(con.execute("SELECT count(*) FROM releases WHERE artist='A2O SOUL'").fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
