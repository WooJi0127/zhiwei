"""Version browser assets and describe the site release before sync copies it."""
from datetime import datetime
import hashlib
from pathlib import Path
import re

from catalog_state import read_published
from home_preview import render_home_preview


def lf_bytes(path):
    """Match the server's CR removal for files with LF or CRLF line endings."""
    content = path.read_bytes().replace(b'\r\n', b'\n')
    if b'\r' in content:
        raise ValueError(f'Unsupported line endings: {path}')
    return content


def stamp_assets(root):
    root = Path(root)
    core, data = root / 'core', root / 'data'
    page = core / 'index.html'
    manifest = core / 'release-manifest.tsv'
    original = lf_bytes(page).decode('utf-8')
    text = original

    assets = {'app.css': core / 'app.css', 'app.js': core / 'app.js'}
    main_data = data / 'data.js'
    # sync.py calls this before refreshing core/data, so only root/data is authoritative.
    published = read_published(data) if main_data.is_file() else None
    if published is not None:
        assets['data/data.js'] = main_data

    digests = {name: hashlib.sha256(lf_bytes(path)).hexdigest() for name, path in assets.items()}
    for name, digest in digests.items():
        text, count = re.subn(
            r'((?:href|src)=")' + re.escape(name) + r'(?:\?[^"<>]*)?"',
            lambda match: match.group(1) + name + '?v=' + digest[:16] + '"',
            text,
        )
        if count != 1:
            raise ValueError('Expected one asset reference: ' + name)

    manifest_text = None
    if published is not None:
        generated = published.get('generated')
        if not isinstance(generated, str) or not re.fullmatch(
            r'[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}', generated
        ):
            raise ValueError('Invalid published data timestamp')
        datetime.fromisoformat(generated)
        text = render_home_preview(text, published)
        files = {'zhiwei.ics': data / 'zhiwei.ics'}
        for year in published['years']:
            if not re.fullmatch(r'[0-9]{4}', year):
                raise ValueError('Invalid archive year: ' + year)
            files[f'data/data-{year}.js'] = data / f'data-{year}.js'
        for name in ('backup.js', 'robots.txt', 'sitemap.xml'):
            if (core / name).is_file():
                files[name] = core / name
        digests.update({name: hashlib.sha256(lf_bytes(path)).hexdigest() for name, path in files.items()})
        icon = core / 'site-icon.png'
        if icon.is_file():
            digests[icon.name] = hashlib.sha256(icon.read_bytes()).hexdigest()
        digests['index.html'] = hashlib.sha256(text.encode('utf-8')).hexdigest()
        rows = [f'zhiwei-release-v1\t{generated}']
        rows.extend(f'{digest}\t{name}' for name, digest in sorted(digests.items()))
        manifest_text = '\n'.join(rows) + '\n'

    if text != original:
        page.write_text(text, encoding='utf-8', newline='\n')
    if manifest_text is not None:
        manifest.write_text(manifest_text, encoding='utf-8', newline='\n')
    else:
        # Asset-only builds are still supported, but cannot advertise a data release.
        manifest.unlink(missing_ok=True)


if __name__ == '__main__':
    stamp_assets(Path(__file__).resolve().parents[1])
