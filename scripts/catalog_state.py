"""Versioned public collector state. No credentials or account data belong here.

SQLite is the working copy; reviewed JSONL in Git is the durable source.
Missing/corrupt snapshots and unexplained losses fail closed before export.
"""
import argparse
from contextlib import closing
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CATALOG_DIR = ROOT / 'scripts' / 'catalog'
CORRECTIONS_PATH = ROOT / 'scripts' / 'catalog-corrections.json'
FIELDS = {
    'artists': 'name name_ko kind gender agency debut_year fandom am_id am_url am_updated ne_id coed_checked'.split(),
    'releases': 'id source date artist title rtype image url extra rtype_src'.split(),
    'tracks': 'id release_id artist name track_no disc duration_ms genre preview'.split(),
    'events': 'id date etype category title artist description source_url confirmed'.split(),
    'members': 'g n alt b src'.split(),
    'bili': 'bvid artist mid uname title play pubdate pic dead updated'.split(),
    'bili_mid': 'mid name official fans'.split(),
    'bili_seen': 'artist n at'.split(),
    'meta': 'k v'.split(),
}
KEYS = {t: [cols[0]] for t, cols in FIELDS.items()}
KEYS['members'] = ['g', 'n']
# Only content fields: status flags (dead/official/confirmed) must retain valid 0.
PRESERVE = {
    'artists': 'name_ko kind gender agency debut_year fandom am_id am_url ne_id'.split(),
    'releases': 'source date artist title image url rtype_src'.split(),
    'tracks': 'release_id artist name track_no disc duration_ms genre preview'.split(),
    'members': ['alt', 'b', 'src'],
    'events': 'date etype category title artist description source_url'.split(),
    'bili': 'artist mid uname title pubdate pic'.split(),
}


def key_of(table, row):
    return tuple(row[k] for k in KEYS[table])


def open_database(path):
    import build
    con = sqlite3.connect(path)
    con.executescript(build.SCHEMA)
    have = {r[1] for r in con.execute('PRAGMA table_info(artists)')}
    for name, declaration in [('ne_id', 'INTEGER'), ('coed_checked', 'INTEGER DEFAULT 0')]:
        if name not in have:
            con.execute(f'ALTER TABLE artists ADD COLUMN {name} {declaration}')
    con.execute('CREATE TABLE IF NOT EXISTS bili_seen (artist TEXT PRIMARY KEY, n INTEGER DEFAULT 0, at TEXT)')
    con.commit()
    return con


def database_rows(con):
    if con.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
        raise ValueError('SQLite integrity check failed')
    result = {}
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for table, columns in FIELDS.items():
        if table == 'bili_seen' and table not in tables:
            result[table] = []
            continue
        result[table] = [dict(zip(columns, row)) for row in con.execute(
            f"SELECT {','.join(columns)} FROM {table} ORDER BY {','.join(KEYS[table])}")]
    return result


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def save_snapshot(con, directory):
    rows = database_rows(con)
    if not rows['artists'] or not rows['releases']:
        raise ValueError('Refusing to save an empty public catalog')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {'format': 1, 'tables': {}}
    for table, records in rows.items():
        blob = ''.join(_encode(row) + '\n' for row in records).encode('utf-8')
        manifest['tables'][table] = {'rows': len(records), 'sha256': hashlib.sha256(blob).hexdigest()}
        tmp = directory / (table + '.jsonl.tmp')
        tmp.write_bytes(blob)
        os.replace(tmp, directory / (table + '.jsonl'))
    # Written last: an interrupted save is detected, never treated as complete.
    tmp = directory / 'manifest.json.tmp'
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    os.replace(tmp, directory / 'manifest.json')


def read_snapshot(directory):
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('format') != 1 or set(manifest.get('tables', {})) != set(FIELDS):
        raise ValueError('Unsupported/incomplete catalog manifest')
    result = {}
    for table, columns in FIELDS.items():
        # Git core.autocrlf changes checkout bytes on Windows. The digest is
        # over canonical LF JSONL, so content is protected across platforms.
        blob = (directory / (table + '.jsonl')).read_bytes().replace(b'\r\n', b'\n')
        entry = manifest['tables'][table]
        if hashlib.sha256(blob).hexdigest() != entry['sha256']:
            raise ValueError(f'Catalog checksum mismatch: {table}')
        rows = [json.loads(line) for line in blob.decode('utf-8').splitlines()]
        if len(rows) != entry['rows'] or any(set(row) != set(columns) for row in rows):
            raise ValueError(f'Invalid catalog rows: {table}')
        keys = [key_of(table, row) for row in rows]
        if len(set(keys)) != len(keys) or any(any(k is None or k == '' for k in key) for key in keys):
            raise ValueError(f'Missing/duplicate catalog keys: {table}')
        result[table] = rows
    if not result['artists'] or not result['releases']:
        raise ValueError('Empty catalog')
    return result


def restore_snapshot(directory, target, replace=False):
    rows = read_snapshot(directory)  # Validate before touching the working DB.
    target = Path(target)
    backup = None
    if target.exists():
        with closing(sqlite3.connect(target.as_uri() + '?mode=ro', uri=True)) as old:
            same = database_rows(old) == rows
        if same:
            return None
        if not replace:
            raise ValueError('Local database differs: save reviewed changes, or restore --replace to back it up first')
        backup_dir = target.parent / '.build-logs' / 'catalog-backups'
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / (dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.db')
        with closing(sqlite3.connect(target.as_uri() + '?mode=ro', uri=True)) as old, closing(sqlite3.connect(backup)) as dest:
            old.backup(dest)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, filename = tempfile.mkstemp(prefix='catalog-', suffix='.db', dir=target.parent)
    os.close(fd)
    try:
        con = open_database(filename)
        try:
            for table, records in rows.items():
                columns = FIELDS[table]
                con.executemany(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                                [[row[c] for c in columns] for row in records])
            con.commit()
            if database_rows(con) != rows:
                raise ValueError('Restored database differs from snapshot')
        finally:
            con.close()
        os.replace(filename, target)
    finally:
        if os.path.exists(filename):
            os.unlink(filename)
    return backup


def load_corrections():
    if not CORRECTIONS_PATH.exists():
        return []
    return json.loads(CORRECTIONS_PATH.read_text(encoding='utf-8'))


def _check_corrections(corrections):
    for item in corrections:
        table = item.get('table')
        if table not in FIELDS or set(item.get('key', {})) != set(KEYS[table]):
            raise ValueError('Invalid correction table/key')
        if not item.get('reason') or not item.get('source'):
            raise ValueError('Corrections require reason and source evidence')
        fields = item.get('set', {})
        if bool(fields) == bool(item.get('delete')) or not set(fields) <= set(FIELDS[table]) - set(KEYS[table]):
            raise ValueError('Invalid correction operation')


def apply_corrections(con, corrections):
    _check_corrections(corrections)
    with con:
        for item in corrections:
            table = item['table']
            where = ' AND '.join(k + '=?' for k in KEYS[table])
            values = [item['key'][k] for k in KEYS[table]]
            if item.get('delete'):
                if table == 'releases':
                    con.execute('DELETE FROM tracks WHERE release_id=?', values)
                con.execute(f'DELETE FROM {table} WHERE {where}', values)
            else:
                fields = dict(item['set'])
                if table == 'artists' and 'am_id' in fields:
                    previous = con.execute(f'SELECT am_id FROM artists WHERE {where}', values).fetchone()
                    if previous and previous[0] != fields['am_id']:
                        fields['am_updated'] = None
                con.execute(f"UPDATE {table} SET {','.join(k+'=?' for k in fields)} WHERE {where}",
                            list(fields.values()) + values)


def preserve_known_fields(con, before):
    current = database_rows(con)
    for table, columns in PRESERVE.items():
        previous = {key_of(table, r): r for r in before[table]}
        for row in current[table]:
            old = previous.get(key_of(table, row))
            if not old:
                continue
            changes = {c: old[c] for c in columns if row[c] in (None, '', 0) and old[c] not in (None, '', 0)}
            if table == 'releases':
                old_extra = json.loads(old['extra'] or '{}')
                extra = json.loads(row['extra'] or '{}')
                merged = dict(extra)
                for k, value in old_extra.items():
                    if merged.get(k) in (None, '', 0) and value not in (None, '', 0):
                        merged[k] = value
                if merged != extra:
                    changes['extra'] = _encode(merged)
            if changes:
                where = ' AND '.join(k + '=?' for k in KEYS[table])
                con.execute(f"UPDATE {table} SET {','.join(k+'=?' for k in changes)} WHERE {where}",
                            list(changes.values()) + list(key_of(table, row)))
    con.commit()


def _allowed_deletions(before, corrections):
    import build
    _check_corrections(corrections)
    allowed = {table: set() for table in FIELDS}
    for item in corrections:
        if item.get('delete'):
            allowed[item['table']].add(key_of(item['table'], item['key']))
    # Explicit site scope rules, shared with build.step_purge_scope.
    for row in before['releases']:
        if not build.is_wanted(row['title']):
            allowed['releases'].add((row['id'],))
    for row in before['tracks']:
        if (row['release_id'],) in allowed['releases']:
            allowed['tracks'].add((row['id'],))
    return allowed


def validate_database(con, before, corrections):
    after = database_rows(con)
    allowed = _allowed_deletions(before, corrections)
    errors = []
    for table in ('artists', 'releases', 'tracks', 'members', 'events', 'bili'):
        missing = ({key_of(table, r) for r in before[table]} -
                   {key_of(table, r) for r in after[table]} - allowed[table])
        if missing:
            errors.append(f'{table}: lost {len(missing)} existing records; examples {sorted(missing)[:5]}')
    if errors:
        raise ValueError('Publication blocked: ' + '; '.join(errors))


def _read_js(path, prefix):
    text = path.read_text(encoding='utf-8').strip()
    if not text.startswith(prefix) or not text.endswith(';'):
        raise ValueError(f'Invalid data wrapper: {path.name}')
    return json.loads(text[len(prefix):-1].strip())


def read_published(directory):
    directory = Path(directory)
    payload = _read_js(directory / 'data.js', 'window.__KPOP_DATA__ = ')
    payload['releases'] = list(payload['releases'])
    count = 0
    for year, expected in payload['years'].items():
        if len(year) != 4 or not year.isdigit():
            raise ValueError('Invalid archive year')
        chunk = _read_js(directory / f'data-{year}.js', f'window.__KPOP_CHUNK_{year}__ = ')
        if chunk['y'] != year or len(chunk['releases']) != expected:
            raise ValueError(f'Incomplete year slice: {year}')
        payload['releases'].extend(chunk['releases'])
        count += expected
    if count != payload['olderCount']:
        raise ValueError('Incomplete archive manifest')
    ids = [r['id'] for r in payload['releases']]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate published release IDs')
    return payload


def validate_export(con, before, after, corrections):
    import build
    current = database_rows(con)
    allowed = _allowed_deletions(current, corrections)
    # Public baseline can contain IDs no longer present in raw DB (manual deletion).
    removed_releases = allowed['releases']
    floor = (dt.date.today() - dt.timedelta(days=build.HISTORY_DAYS)).isoformat()
    releases = {r['id']: r for r in after['releases']}
    errors = []
    for old in before['releases']:
        if old['date'] < floor or (old['id'],) in removed_releases or not build.is_wanted(old['title']):
            continue
        replacement = releases.get(old['id'])
        if replacement is None:
            # A source switch is allowed only for the same album under existing dedup rules.
            candidates = [r for r in after['releases'] if r['artist'] == old['artist']
                          and build.normalize_release_title(r['title']) == build.normalize_release_title(old['title'])
                          and abs((dt.date.fromisoformat(r['date']) - dt.date.fromisoformat(old['date'])).days) <= build.DATE_TOL_DAYS]
            replacement = next(iter(candidates), None)
        if replacement is None:
            errors.append('release missing: ' + old['id'])
        elif len(replacement.get('tracks', [])) < len(old.get('tracks', [])):
            errors.append('tracks reduced: ' + old['id'])
    for label, fields in [('artists', ('name',)), ('members', ('g', 'n'))]:
        new_keys = {tuple(r[k] for k in fields) for r in after[label]}
        for row in before[label]:
            key = tuple(row[k] for k in fields)
            if key not in new_keys and key not in allowed[label]:
                errors.append(f'{label} missing: {key}')
    live = {r['v'] for r in after['mvs']}
    dead = {r['bvid'] for r in current['bili'] if r['dead'] == 1}
    for row in before['mvs']:
        if row['v'] not in live and row['v'] not in dead and (row['v'],) not in allowed['bili']:
            errors.append('MV missing without confirmed removal: ' + row['v'])
    if errors:
        raise ValueError(f'Publication blocked ({len(errors)} losses): ' + '; '.join(errors[:12]))


def prepare_export(con):
    corrections = load_corrections()
    if CATALOG_DIR.exists():
        before = read_snapshot(CATALOG_DIR)
        preserve_known_fields(con, before)
        apply_corrections(con, corrections)
        validate_database(con, before, corrections)
    else:
        apply_corrections(con, corrections)
    return corrections


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('restore', 'check'))
    parser.add_argument('--db', type=Path, default=ROOT/'kpop.db')
    parser.add_argument('--replace', action='store_true', help='Back up a different working DB before replacing it')
    args = parser.parse_args()
    if args.action == 'restore':
        backup = restore_snapshot(CATALOG_DIR, args.db.resolve(), args.replace)
        print('Restored verified catalog.' + (f' Backup: {backup}' if backup else ''))
    else:
        with closing(sqlite3.connect(args.db.resolve().as_uri() + '?mode=ro', uri=True)) as con:
            before = read_snapshot(CATALOG_DIR)
            validate_database(con, before, load_corrections())
            print('Catalog validated: ' + str({k: len(v) for k, v in database_rows(con).items()}))


if __name__ == '__main__':
    main()
