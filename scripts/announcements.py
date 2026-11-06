"""Replay reviewed official announcements before collector/export corrections.

IDs describe the release, never its scheduled date: a postponement updates the
same row. The JSON ledger is versioned with the source, so rebuilding SQLite
does not lose confirmed announcements absent from third-party calendars.

This is an additive ledger. Withdrawals use catalog-corrections.json after
replay; removing a JSON entry alone does not delete a historical catalog row.
"""
import datetime
import json
from pathlib import Path
import re
from urllib.parse import urlsplit


ANNOUNCEMENTS_PATH = Path(__file__).with_name('verified-announcements.json')
SUBTYPES = (None, 'Single', 'EP', 'Album')


def _iso_date(value, field):
    try:
        if not isinstance(value, str) or datetime.date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError(f'Announcement {field} must be a valid YYYY-MM-DD date') from None


def _validate(items):
    """Validate the entire ledger before its first database mutation."""
    if not isinstance(items, list):
        raise ValueError('Verified announcements must be a JSON list')
    ids = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('Each verified announcement must be an object')
        rid = item.get('id')
        if not isinstance(rid, str) or not re.fullmatch(r'official:[a-z0-9]+(?:[-_:][a-z0-9]+)*', rid):
            raise ValueError('Announcement id must use the official: namespace')
        if rid in ids:
            raise ValueError(f'Duplicate announcement id: {rid}')
        ids.add(rid)
        for field in ('artist', 'title', 'reason'):
            value = item.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'Announcement {field} must be nonempty text')
        _iso_date(item.get('date'), 'date')
        _iso_date(item.get('verified_on'), 'verified_on')
        if item.get('subtype') not in SUBTYPES:
            raise ValueError('Announcement subtype must be Single, EP, Album, or null')
        urls = item.get('source_urls')
        if not isinstance(urls, list) or not urls:
            raise ValueError('Announcement source_urls must contain HTTPS evidence')
        for url in urls:
            try:
                if not isinstance(url, str) or any(ch.isspace() for ch in url):
                    raise ValueError
                parsed = urlsplit(url)
                if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
                    raise ValueError
                parsed.port  # Reject malformed ports as well as malformed hosts.
            except ValueError:
                raise ValueError('Announcement source_urls must contain valid HTTPS URLs') from None
        if 'track_count' in item and (type(item['track_count']) is not int or item['track_count'] <= 0):
            raise ValueError('Announcement track_count must be a positive integer when known')


def apply_verified_announcements(con, path=None):
    """Atomically upsert reviewed entries; return the number replayed.

Only explicitly known fields are filled. Existing artwork, tracks, artist
details, and unrelated extra metadata survive each replay unchanged.
"""
    ledger = ANNOUNCEMENTS_PATH if path is None else Path(path)
    items = json.loads(ledger.read_text(encoding='utf-8'))
    _validate(items)
    with con:
        for item in items:
            previous = con.execute('SELECT extra FROM releases WHERE id=?', (item['id'],)).fetchone()
            extra = json.loads(previous[0]) if previous and previous[0] else {}
            if not isinstance(extra, dict):
                raise ValueError(f'Existing announcement extra must be an object: {item["id"]}')
            extra['verified_announcement'] = item
            if 'track_count' in item:
                extra['trackCount'] = item['track_count']
            con.execute('INSERT OR IGNORE INTO artists(name) VALUES(?)', (item['artist'],))
            con.execute('''
                INSERT INTO releases(id,source,date,artist,title,rtype,image,url,extra,rtype_src)
                VALUES(?, 'official', ?, ?, ?, ?, '', ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    source=excluded.source, date=excluded.date,
                    artist=excluded.artist, title=excluded.title,
                    rtype=COALESCE(excluded.rtype,releases.rtype),
                    rtype_src=COALESCE(excluded.rtype_src,releases.rtype_src),
                    url=CASE WHEN COALESCE(releases.url,'')=''
                             THEN excluded.url ELSE releases.url END,
                    extra=excluded.extra
            ''', (item['id'], item['date'], item['artist'], item['title'],
                  item.get('subtype'), item['source_urls'][0],
                  json.dumps(extra, ensure_ascii=False, sort_keys=True, separators=(',', ':')),
                  item.get('subtype')))
    return len(items)
