"""Explicit, offline three-way recovery; never used by daily collectors.

Only merges supplied public databases. Conflicting content requires review;
absence is not permission to delete. Reviewed deletions live in corrections.
"""
import argparse
from contextlib import closing
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3

import catalog_state as state


def merge_record(table, base, local, cloud):
    merged = {}
    for field in local:
        old, left, right = base.get(field), local[field], cloud[field]
        if left == right:
            value = left
        elif left in (None, ''):
            value = right
        elif right in (None, ''):
            value = left
        elif left == old:
            value = right
        elif right == old:
            value = left
        elif table == 'releases' and field == 'rtype' and bool(local.get('rtype_src')) != bool(cloud.get('rtype_src')):
            value = left if local.get('rtype_src') else right
        elif field in ('am_updated', 'updated', 'at'):
            value = max(left, right)  # ISO collection timestamps, not content.
        else:
            raise ValueError(f'Unresolved conflict in {table}.{field}: {left!r} / {right!r}')
        merged[field] = value
    if table == 'artists' and merged.get('am_id') != cloud.get('am_id'):
        merged['am_updated'] = None  # Wrong identity's cache timestamp is invalid.
    return merged


def read_database(path):
    if path.suffix == '.gz':
        with closing(sqlite3.connect(':memory:')) as con:
            con.deserialize(gzip.decompress(path.read_bytes()))
            return state.database_rows(con)
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)) as con:
        return state.database_rows(con)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('base', 'local', 'cloud', 'output'):
        parser.add_argument('--'+arg, required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output must be a new database; originals are never overwritten')
    base, local, cloud = [read_database(p) for p in (args.base, args.local, args.cloud)]
    report = {'sources': {k: {'path': str(getattr(args,k)), 'sha256': hashlib.sha256(getattr(args,k).read_bytes()).hexdigest()}
                          for k in ('base','local','cloud')}, 'tables': {}}
    with closing(state.open_database(args.output)) as con:
        for table, columns in state.FIELDS.items():
            b, l, c = [{state.key_of(table,r):r for r in data[table]} for data in (base,local,cloud)]
            rows = []
            for key in sorted(l.keys() | c.keys()):
                if key in l and key in c:
                    row = merge_record(table,b.get(key,{}),l[key],c[key])
                else:
                    row = l.get(key) or c[key]
                rows.append(row)
            con.executemany(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                            [[r[k] for k in columns] for r in rows])
            report['tables'][table] = {'local':len(l),'cloud':len(c),'merged':len(rows),
                                       'local_only':len(l.keys()-c.keys()),'cloud_only':len(c.keys()-l.keys())}
        con.commit()
        state.apply_corrections(con, state.load_corrections())
        for table, rows in state.database_rows(con).items():
            report['tables'][table]['after_corrections'] = len(rows)
    args.output.with_suffix('.report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report['tables'],ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
