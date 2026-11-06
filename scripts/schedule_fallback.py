"""Independent upcoming releases from KPOP OFFICIAL's public WordPress API.

The API is advertised in the HTML of https://kpopofficial.com/kpop-comebacks/.
Release fields are the labeled Album Details, never the article publication date.
Images there can be member photos or teaser posters, so we do not import them.
"""
import datetime
import re
from html.parser import HTMLParser
from urllib.parse import urlencode, urlparse

import sources

API = "https://kpopofficial.com/wp-json/wp/v2/"
MONTHS = ("january", "february", "march", "april", "may", "june",
          "july", "august", "september", "october", "november", "december")
PAGE_SIZE = 100
# Reviewed source spellings, matched to existing Apple artist identities:
# 1454642552 / 1625812861 / 1528632995 / 1256529606 respectively.
# Mark's source article links @onyourm__ark, the NCT MARK account; Mark Tuan
# is a different catalog identity. Never strip arbitrary artist qualifiers.
ARTIST_NAMES = {
    "TOMORROW X TOGETHER (TXT)": "TOMORROW X TOGETHER",
    "NAYEON (TWICE)": "Nayeon",
    "CHAERYEONG (ITZY)": "Chaeryeong",
    "Mark Lee": "Mark",
}
LABELS = {"Artist", "Release Date", "Album", "Language", "Languages",
          "Tracklist", "Track List", "Buy Album", "Official Source",
          "Music Video", "Streaming"}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.parts.append(" ".join(data.split()))


def _get(path, params, context):
    url = API + path + "?" + urlencode(params)
    try:
        data = sources.http_json(url)
    except Exception as exc:
        raise RuntimeError(f"KPOP OFFICIAL {context}: request failed: {exc}") from exc
    if data is None:
        raise RuntimeError(f"KPOP OFFICIAL {context}: request or JSON decoding failed ({url})")
    return data


def _parse(item, year, month):
    if not isinstance(item, dict) or type(item.get("id")) is not int or item["id"] <= 0:
        raise RuntimeError("KPOP OFFICIAL: album row has no valid id")
    ident = item["id"]
    link = item.get("link")
    if not isinstance(link, str) or urlparse(link).hostname != "kpopofficial.com":
        raise RuntimeError(f"KPOP OFFICIAL album {ident}: invalid source URL")
    content = item.get("content")
    if not isinstance(content, dict) or not isinstance(content.get("rendered"), str):
        raise RuntimeError(f"KPOP OFFICIAL album {ident}: missing rendered Album Details")
    parser = _Text()
    parser.feed(content["rendered"])
    parts = parser.parts
    # Exact field labels in the album's own details, before recommendations.
    try:
        start = parts.index("Artist", parts.index("Album Details"))
        stop = next(i for i in range(start, len(parts))
                    if parts[i] in {"Tracklist", "Track List", "Buy Album", "Official Source", "Music Video"})
    except (ValueError, StopIteration) as exc:
        raise RuntimeError(f"KPOP OFFICIAL album {ident}: missing Album Details labels") from exc
    fields = {}
    label = None
    for part in parts[start:stop]:
        if part in LABELS:
            if part in fields:
                raise RuntimeError(f"KPOP OFFICIAL album {ident}: duplicate {part} field")
            label = part
            fields[label] = []
        elif label:
            fields[label].append(part)
    fields = {key: " ".join(value).strip() for key, value in fields.items()}
    for key in ("Artist", "Release Date", "Album"):
        if not fields.get(key):
            raise RuntimeError(f"KPOP OFFICIAL album {ident}: missing {key}")

    date_match = re.fullmatch(r"([A-Za-z]+) (\d{1,2}), (\d{4})(?:\s*·.*)?", fields["Release Date"])
    if not date_match or date_match[1].lower() not in MONTHS:
        raise RuntimeError(f"KPOP OFFICIAL album {ident}: invalid Release Date {fields['Release Date']!r}")
    try:
        date = datetime.date(int(date_match[3]), MONTHS.index(date_match[1].lower()) + 1,
                             int(date_match[2]))
    except ValueError as exc:
        raise RuntimeError(f"KPOP OFFICIAL album {ident}: invalid Release Date") from exc
    if (date.year, date.month) != (year, month):
        print(f"    ! KPOP OFFICIAL album {ident}: date {date} outside requested month, skipped")
        return None

    # The published format and title are separated by a spaced dash. Never split
    # on a hyphen inside an actual title (e.g. NA-sty) or infer a missing title.
    album = re.split(r"\s+[–—-]\s+", fields["Album"], maxsplit=1)
    if len(album) != 2 or not album[0].strip() or not album[1].strip():
        raise RuntimeError(f"KPOP OFFICIAL album {ident}: missing explicit album title/format")
    raw_type, title = (value.strip() for value in album)
    # Scope evidence must come from metadata, not a guess about the artist.
    languages = " ".join(fields.get(key, "") for key in ("Language", "Languages"))
    if re.search(r"\b(?:Japanese|Chinese|Mandarin|Cantonese)\b|日本語|中文|日语|日文", raw_type + " " + languages, re.I):
        return None
    if re.search(r"\b(?:OST|soundtrack|remix|instrumental|concert|birthday)\b", raw_type, re.I):
        return None
    if re.search(r"\bsingle\b", raw_type, re.I):
        kind = "Single"
    elif re.search(r"\b(?:EP|mini album)\b", raw_type, re.I):
        kind = "EP"
    elif re.search(r"\b(?:full|studio) album\b", raw_type, re.I) or raw_type.lower() == "album":
        kind = "Album"
    else:
        kind = ""
    return {"date": date.isoformat(), "artist": ARTIST_NAMES.get(fields["Artist"], fields["Artist"]), "title": title,
            "type": kind, "image": "", "source_id": str(ident), "url": link}


def fetch_month(year, month):
    """Return verified month rows or raise RuntimeError; never return partial pages.

    A successful empty taxonomy lookup means the future month is not published.
    WordPress's public response envelope retains total/page headers while using
    the project's standard HTTP JSON helper, including its retries and timeout.
    """
    datetime.date(year, month, 1)
    slug = f"{MONTHS[month - 1]}-{year}"
    terms = _get("album-month-year", {"slug": slug, "_fields": "id,name,slug"},
                 f"month {year:04d}-{month:02d} lookup")
    if not isinstance(terms, list):
        raise RuntimeError("KPOP OFFICIAL month lookup: invalid taxonomy response")
    if not terms:
        return []
    if (len(terms) != 1 or not isinstance(terms[0], dict)
            or terms[0].get("slug") != slug or type(terms[0].get("id")) is not int
            or terms[0]["id"] <= 0):
        raise RuntimeError("KPOP OFFICIAL month lookup: mismatched taxonomy")

    result, seen = [], set()
    page, total, pages = 1, None, None
    while True:
        data = _get("album", {"album-month-year": terms[0]["id"], "per_page": PAGE_SIZE,
                              "page": page, "orderby": "id", "order": "asc",
                              "_fields": "id,link,title,content.rendered", "_envelope": 1},
                    f"{slug} page {page}")
        if (not isinstance(data, dict) or data.get("status") != 200
                or not isinstance(data.get("body"), list)
                or not isinstance(data.get("headers"), dict)):
            raise RuntimeError(f"KPOP OFFICIAL {slug} page {page}: invalid response envelope")
        headers = {key.lower(): value for key, value in data["headers"].items()}
        try:
            current_total = int(headers["x-wp-total"])
            current_pages = int(headers["x-wp-totalpages"])
        except (KeyError, ValueError, TypeError) as exc:
            raise RuntimeError(f"KPOP OFFICIAL {slug} page {page}: missing pagination totals") from exc
        if (current_total < 0 or current_pages != (current_total + PAGE_SIZE - 1) // PAGE_SIZE
                or (total is not None and (total, pages) != (current_total, current_pages))):
            raise RuntimeError(f"KPOP OFFICIAL {slug} page {page}: inconsistent pagination totals")
        total, pages = current_total, current_pages
        expected = min(PAGE_SIZE, max(0, total - (page - 1) * PAGE_SIZE))
        if len(data["body"]) != expected:
            raise RuntimeError(f"KPOP OFFICIAL {slug} page {page}: row count differs from total")
        for item in data["body"]:
            row = _parse(item, year, month)
            if item["id"] in seen:
                raise RuntimeError(f"KPOP OFFICIAL {slug} page {page}: repeated album id {item['id']}")
            seen.add(item["id"])
            if row is not None:
                result.append(row)
        if page >= pages:
            break
        page += 1
    return result
