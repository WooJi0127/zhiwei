"""Birthday names are opt-in and scoped to an explicitly identified member."""
from datetime import date
import unittest

import member_names


class MemberNamesTest(unittest.TestCase):
    def test_known_member_with_birthday(self):
        self.assertEqual(
            member_names.member_name_zh("TWICE", "Jeongyeon", "1996-11-01"),
            "俞定延",
        )

    def test_exact_group_and_stage_name_suffice_when_birth_is_absent(self):
        self.assertEqual(member_names.member_name_zh("BTS", "Jimin"), "朴智旻")

    def test_conflicting_or_partial_birth_is_not_accepted(self):
        for birth in ("1996-10-01", "1996-11", "11-01", 1996):
            with self.subTest(birth=birth):
                self.assertEqual(member_names.member_name_zh("TWICE", "Jeongyeon", birth), "")

    def test_same_name_in_different_group_is_not_translated(self):
        self.assertEqual(member_names.member_name_zh("AOA", "Jimin", "1991-01-08"), "")
        self.assertEqual(member_names.member_name_zh("Unknown", "Jimin", "1995-10-13"), "")

    def test_unknown_and_fuzzy_names_return_empty(self):
        for group, name in (("BTS fan club", "Jimin"), ("BTS", "Park Jimin"),
                            ("BTS", "Jimi"), ("EXO-new", "Baekhyun"),
                            ("", "Jimin"), (None, None)):
            with self.subTest(group=group, name=name):
                self.assertEqual(member_names.member_name_zh(group, name), "")

    def test_only_case_and_outer_whitespace_are_normalized(self):
        self.assertEqual(member_names.member_name_zh(" bts ", " JIMIN "), "朴智旻")
        self.assertEqual(member_names.member_name_zh("B TS", "Jimin"), "")

    def test_unicode_spelling_is_canonical_but_not_fuzzy(self):
        self.assertEqual(member_names.member_name_zh("BLACKPINK", "Rose\u0301"), "朴彩英")
        self.assertEqual(member_names.member_name_zh("BLACKPINK", "Rose"), "")
        self.assertEqual(member_names.member_name_zh("EXO", "DO"), "")

    def test_explicit_subunit_membership_does_not_include_other_members(self):
        self.assertEqual(member_names.member_name_zh("EXO-CBX", "Baekhyun"), "伯贤")
        self.assertEqual(member_names.member_name_zh("EXO-CBX", "Kai"), "")

    def test_verified_person_has_the_same_name_in_every_explicit_group(self):
        fixtures = (
            ("The8", "1997-11-07", "徐明浩", ("SEVENTEEN", "SVT PERFORMANCE Team", "V8")),
            ("Karina", "2000-04-11", "柳智敏", ("aespa", "GOT the beat")),
            ("Nayeon", "1995-09-22", "林娜琏", ("TWICE", "Nayeon")),
            ("Sakura", "1998-03-19", "宫胁咲良", ("LE SSERAFIM", "IZ*ONE")),
        )
        for name, birth, zh, groups in fixtures:
            for group in groups:
                with self.subTest(group=group, name=name):
                    self.assertEqual(member_names.member_name_zh(group, name, birth), zh)

    def test_aliases_do_not_spread_to_other_members_or_changed_birthdays(self):
        for group, name, birth in (
            ("V8", "Hoshi", "1996-06-15"),
            ("SVT VOCAL Team", "The8", "1997-11-07"),
            ("GOT the beat", "Giselle", "2000-10-30"),
            ("Nayeon", "Mina", "1997-03-24"),
            ("IZ*ONE", "Huh Yunjin", "2001-10-08"),
            ("V8", "The8", "1997-11-08"),
            ("Nayeon", "Nayeon", "2000-09-22"),
        ):
            with self.subTest(group=group, name=name, birth=birth):
                self.assertEqual(member_names.member_name_zh(group, name, birth), "")

    def test_duplicate_identity_fails_at_registration_instead_of_overwriting(self):
        record = member_names.MEMBER_NAMES[0]
        with self.assertRaises(ValueError):
            member_names._build_index((record, record))

    def test_all_names_have_traceable_sources(self):
        self.assertTrue(member_names.MEMBER_NAMES)
        for record in member_names.MEMBER_NAMES:
            with self.subTest(name=record.name):
                self.assertTrue(record.zh)
                self.assertTrue(record.source_ids)
                self.assertEqual(date.fromisoformat(record.birth).isoformat(), record.birth)
                for source_id in record.source_ids:
                    source = member_names.SOURCES[source_id]
                    self.assertTrue(source["url"].startswith("https://"))
                    self.assertTrue(source["title"])

    def test_upstream_birthday_correction_falls_back_without_rewriting_input(self):
        # A future source correction must not block export or be silently overwritten.
        # Use a stable fixture, not today's live catalog as an immutable assertion.
        upstream = {"g": "TWICE", "n": "Jeongyeon", "b": "1996-11-02", "src": "kpopping"}
        before = upstream.copy()
        self.assertEqual(
            member_names.member_name_zh(upstream["g"], upstream["n"], upstream["b"]), ""
        )
        self.assertEqual(upstream, before)
        self.assertEqual(
            member_names.member_name_zh("TWICE", "Jeongyeon", "1996-11-01"), "俞定延"
        )


if __name__ == "__main__":
    unittest.main()
