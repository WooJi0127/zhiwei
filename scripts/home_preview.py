"""Render an initial schedule from the same published snapshot as the calendar."""
from datetime import date, datetime
from html import escape


PREVIEW_START = "<!-- home-preview:start -->"
PREVIEW_END = "<!-- home-preview:end -->"


def render_home_preview(html: str, published: dict) -> str:
    starts, ends = html.count(PREVIEW_START), html.count(PREVIEW_END)
    if not starts and not ends:
        return html
    if starts != 1 or ends != 1 or html.index(PREVIEW_START) > html.index(PREVIEW_END):
        raise ValueError("Invalid home preview markers")

    start = html.index(PREVIEW_START) + len(PREVIEW_START)
    end = html.index(PREVIEW_END)
    try:
        snapshot = datetime.fromisoformat(published["generated"]).date()
    except (KeyError, TypeError, ValueError):
        return html[:start] + "\n      " + html[end:]

    rows = set()
    for release in published.get("releases", []):
        raw_date = release.get("date")
        artist, title = release.get("artist"), release.get("title")
        if not all(isinstance(value, str) and value.strip() for value in (raw_date, artist, title)):
            continue
        try:
            released = date.fromisoformat(raw_date)
        except ValueError:
            continue
        # Match the live home schedule: snapshot day through day seven, inclusive.
        if released.isoformat() == raw_date and 0 <= (released - snapshot).days <= 7:
            rows.add((released, artist.strip(), title.strip()))

    day = snapshot.isoformat()
    section = [
        '<section class="hsec home-preview" aria-labelledby="homePreviewTitle">',
        '  <div class="hsec-h">',
        '    <h2 id="homePreviewTitle">未来 7 天回归</h2>',
        f'    <span class="hs">数据日期 <time datetime="{day}">{day}</time></span>',
        '  </div>',
    ]
    if rows:
        section.append('  <ul class="home-preview-list">')
        for released, artist, title in sorted(rows)[:12]:
            day = released.isoformat()
            section.append(
                f'    <li><time datetime="{day}">{day}</time> '
                f'<strong>{escape(artist)}</strong> · {escape(title)}</li>'
            )
        section.append('  </ul>')
    else:
        section.append('  <p class="hempty">这次数据更新暂未收录未来 7 天的发行。</p>')
    section.append('</section>')
    return html[:start] + "\n      " + "\n      ".join(section) + "\n      " + html[end:]
