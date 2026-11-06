"""Regression cases reduced from KPOP OFFICIAL's public WordPress response.

Captured 2026-11-06: /wp-json/wp/v2/album/127592 and
/wp-json/wp/v2/album?album-month-year=3831&_envelope=1.
Only the network boundary is mocked; the HTML and pagination parser run normally.
"""
import copy
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import schedule_fallback


NOTICE = {
    "id": 127592,
    "date": "2026-11-05T11:28:17",  # Article date, never a release date.
    "link": "https://kpopofficial.com/album/a2o-soul-album-superstar/",
    "title": {"rendered": "A2O SOUL Debut EP &#8211; SUPERSTAR (2026)"},
    "content": {"rendered": '''
        <h2>Album Details</h2><div class="gspb_container">
        <div><div class="gspb_text">Artist</div></div>
        <div><span class="gspb_meta_value">A2O SOUL</span></div>
        <div><div class="gspb_text">Release Date</div></div>
        <div><span class="gspb_meta_value">November 9, 2026 · Monday · 6 PM KST</span></div>
        <div><div class="gspb_text">Album</div></div>
        <div><span class="gspb_meta_value">Debut EP – SUPERSTAR</span></div>
        <div>Tracklist</div><div>Title – “Superstar”, “Dancing in the Dark”</div>
        </div><h2>Music Video</h2><iframe></iframe>'''},
}


def envelope(rows, total=None, pages=1):
    return {"body": rows, "status": 200,
            "headers": {"X-WP-Total": len(rows) if total is None else total,
                        "X-WP-TotalPages": pages}}


def response(rows):
    return [[{"id": 3831, "name": "NOVEMBER 2026", "slug": "november-2026"}],
            envelope(rows)]


class ScheduleFallbackTests(unittest.TestCase):
    def test_reviewed_source_aliases_share_existing_artists_without_fuzzy_matching(self):
        for source_name, canonical in [
                ('TOMORROW X TOGETHER (TXT)', 'TOMORROW X TOGETHER'),
                ('NAYEON (TWICE)', 'Nayeon'), ('CHAERYEONG (ITZY)', 'Chaeryeong'),
                ('Mark Lee', 'Mark'), ('Mark Tuan', 'Mark Tuan'),
                ('Unknown (New Group)', 'Unknown (New Group)')]:
            with self.subTest(source_name=source_name):
                row = copy.deepcopy(NOTICE)
                row['content']['rendered'] = row['content']['rendered'].replace('A2O SOUL', source_name)
                with patch('schedule_fallback.sources.http_json', side_effect=response([row])):
                    self.assertEqual(schedule_fallback.fetch_month(2026, 11)[0]['artist'], canonical)

    def test_ep_uses_labeled_release_date_and_keeps_provenance(self):
        with patch("schedule_fallback.sources.http_json", side_effect=response([NOTICE])):
            rows = schedule_fallback.fetch_month(2026, 11)
        self.assertEqual(rows, [{"date": "2026-11-09", "artist": "A2O SOUL",
                                "title": "SUPERSTAR", "type": "EP", "image": "",
                                "source_id": "127592", "url": NOTICE["link"]}])

    def test_same_title_october_single_is_a_different_release(self):
        single = copy.deepcopy(NOTICE)
        single["id"] = 126618
        single["link"] = "https://kpopofficial.com/album/a2o-soul-superstar/"
        single["content"]["rendered"] = single["content"]["rendered"].replace(
            "November 9, 2026", "October 13, 2026").replace(
            "Debut EP –", "Debut Album Pre-Release Single –")
        with patch("schedule_fallback.sources.http_json", side_effect=[
                [{"id": 3830, "slug": "october-2026"}], envelope([single])]):
            row = schedule_fallback.fetch_month(2026, 10)[0]
        self.assertEqual((row["date"], row["type"], row["title"]),
                         ("2026-10-13", "Single", "SUPERSTAR"))

    def test_missing_date_cannot_fall_back_to_post_date(self):
        item = copy.deepcopy(NOTICE)
        item["content"]["rendered"] = item["content"]["rendered"].replace(
            "November 9, 2026 · Monday · 6 PM KST", "TBA")
        with patch("schedule_fallback.sources.http_json", side_effect=response([item])):
            with self.assertRaisesRegex(RuntimeError, "127592.*[Dd]ate"):
                schedule_fallback.fetch_month(2026, 11)

    def test_unknown_format_is_not_guessed_from_title(self):
        item = copy.deepcopy(NOTICE)
        item["content"]["rendered"] = item["content"]["rendered"].replace(
            "Debut EP –", "Solo Debut Album –")
        with patch("schedule_fallback.sources.http_json", side_effect=response([item])):
            self.assertEqual(schedule_fallback.fetch_month(2026, 11)[0]["type"], "")

    def test_explicit_japanese_release_is_excluded(self):
        item = copy.deepcopy(NOTICE)
        item["content"]["rendered"] = item["content"]["rendered"].replace(
            "Debut EP –", "1st Japanese EP –")
        with patch("schedule_fallback.sources.http_json", side_effect=response([item])):
            self.assertEqual(schedule_fallback.fetch_month(2026, 11), [])

    def test_explicit_language_field_is_excluded(self):
        item = copy.deepcopy(NOTICE)
        item["content"]["rendered"] = item["content"]["rendered"].replace(
            "<div>Tracklist</div>", "<div>Language</div><span>Chinese</span><div>Tracklist</div>")
        with patch("schedule_fallback.sources.http_json", side_effect=response([item])):
            self.assertEqual(schedule_fallback.fetch_month(2026, 11), [])

    def test_other_month_is_not_imported(self):
        item = copy.deepcopy(NOTICE)
        item["content"]["rendered"] = item["content"]["rendered"].replace(
            "November 9, 2026", "December 9, 2026")
        with patch("schedule_fallback.sources.http_json", side_effect=response([item])):
            self.assertEqual(schedule_fallback.fetch_month(2026, 11), [])

    def test_all_pages_are_returned_beyond_one_hundred(self):
        items = []
        for i in range(105):
            item = copy.deepcopy(NOTICE)
            item["id"] = 200000 + i
            item["link"] = "https://kpopofficial.com/album/example-" + str(i) + "/"
            items.append(item)

        def api(url):
            if "/album-month-year?" in url:
                return [{"id": 3831, "slug": "november-2026"}]
            query = parse_qs(urlparse(url).query)
            page = int(query["page"][0])
            limit = int(query["per_page"][0])
            return envelope(items[(page - 1) * limit:page * limit], 105, (105 + limit - 1) // limit)

        with patch("schedule_fallback.sources.http_json", side_effect=api):
            rows = schedule_fallback.fetch_month(2026, 11)
        self.assertEqual(len(rows), 105)
        self.assertEqual(rows[-1]["source_id"], "200104")

    def test_later_network_failure_never_returns_partial_success(self):
        items = [dict(NOTICE, id=200000 + i) for i in range(100)]
        with patch("schedule_fallback.sources.http_json", side_effect=[
                [{"id": 3831, "slug": "november-2026"}], envelope(items, 101, 2), None]):
            with self.assertRaisesRegex(RuntimeError, "page 2"):
                schedule_fallback.fetch_month(2026, 11)

    def test_short_page_is_detected_using_announced_total(self):
        with patch("schedule_fallback.sources.http_json", side_effect=[
                [{"id": 3831, "slug": "november-2026"}], envelope([NOTICE], 2, 1)]):
            with self.assertRaisesRegex(RuntimeError, "count|length|total"):
                schedule_fallback.fetch_month(2026, 11)

    def test_missing_month_is_empty_but_failed_lookup_is_error(self):
        with patch("schedule_fallback.sources.http_json", return_value=[]):
            self.assertEqual(schedule_fallback.fetch_month(2026, 12), [])
        with patch("schedule_fallback.sources.http_json", return_value=None):
            with self.assertRaises(RuntimeError):
                schedule_fallback.fetch_month(2026, 12)

    def test_malformed_taxonomy_and_page_are_errors(self):
        for invalid in ({"code": "forbidden"}, [{"id": 3831, "slug": "october-2026"}]):
            with self.subTest(invalid=invalid), patch(
                    "schedule_fallback.sources.http_json", return_value=invalid):
                with self.assertRaises(RuntimeError):
                    schedule_fallback.fetch_month(2026, 11)
        with patch("schedule_fallback.sources.http_json", side_effect=[
                [{"id": 3831, "slug": "november-2026"}], {"body": [], "status": 403}]):
            with self.assertRaises(RuntimeError):
                schedule_fallback.fetch_month(2026, 11)


if __name__ == "__main__":
    unittest.main()
