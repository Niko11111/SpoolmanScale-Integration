"""Pins down the judgments in check/inventory_rules.py."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "check"))
import inventory_rules as rules  # noqa: E402

MINIMAL = {
    "id": 12, "archived": False, "remaining_weight": 612, "initial_weight": 1000,
    "spool_weight": 196, "extra": {}, "tags": [{"uid": "04A1B2C3D4E5F6"}],
    "filament": {"id": 3, "name": "Matte Black", "material": "PLA", "weight": 1000,
                 "color_hex": "1A1A1A", "vendor": {"id": 1, "name": "Bambu Lab"}},
}


def without(spool, *keys):
    copy = dict(spool)
    for key in keys:
        copy.pop(key, None)
    return copy


class UidTests(unittest.TestCase):
    def test_every_spelling_normalises_to_the_same_hex(self):
        for spelling in ("04:A1:B2:C3:D4:E5:F6", "04a1b2c3d4e5f6", "04-a1-B2-c3-d4-e5-f6"):
            self.assertEqual(rules.normalise_uid(spelling), "04A1B2C3D4E5F6")

    def test_tags_hold_compares_normalised(self):
        self.assertTrue(rules.tags_hold(MINIMAL, "04:a1:b2:c3:d4:e5:f6"))
        self.assertFalse(rules.tags_hold(MINIMAL, "04:00:00:00:00:00:00"))
        self.assertFalse(rules.tags_hold(without(MINIMAL, "tags"), "04A1B2C3D4E5F6"))


class WeightTests(unittest.TestCase):
    def test_tare_prefers_spool_then_filament_then_vendor(self):
        spool = {"spool_weight": 196, "filament": {"spool_weight": 250,
                                                    "vendor": {"empty_spool_weight": 300}}}
        self.assertEqual(rules.tare_of(spool), 196)
        self.assertEqual(rules.tare_of(without(spool, "spool_weight")), 250)
        self.assertEqual(rules.tare_of({"filament": {"vendor": {"empty_spool_weight": 300}}}), 300)
        self.assertEqual(rules.tare_of({"filament": {}}), 0)

    def test_zero_tare_counts_as_unset(self):
        self.assertEqual(rules.tare_of({"spool_weight": 0, "filament": {"spool_weight": 250}}), 250)

    def test_full_weight_falls_back_to_filament_then_1000(self):
        self.assertEqual(rules.full_weight_of(MINIMAL), 1000)
        self.assertEqual(rules.full_weight_of({"filament": {"weight": 750}}), 750)
        self.assertEqual(rules.full_weight_of({"filament": {}}), 1000)

    def test_measure_subtracts_the_reported_tare(self):
        net, initial = rules.net_after_measure(1196, MINIMAL)
        self.assertEqual((net, initial), (1000, 1000))
        net, initial = rules.net_after_measure(1400, MINIMAL)
        self.assertEqual((net, initial), (1204, 1204))

    def test_weights_match_within_half_a_gram(self):
        self.assertTrue(rules.weights_match(500, 500.4))
        self.assertFalse(rules.weights_match(500, 501))
        self.assertFalse(rules.weights_match("500", 500))


class SpoolObjectTests(unittest.TestCase):
    def test_the_minimal_object_passes(self):
        self.assertEqual(rules.spool_object_problems(MINIMAL, native_tags=True), [])

    def test_missing_must_fields_are_must_findings(self):
        found = rules.spool_object_problems(without(MINIMAL, "extra", "archived", "tags"), True)
        self.assertEqual(sorted(level for level, _ in found), ["must", "must", "must"])
        found = rules.spool_object_problems(without(MINIMAL, "tags"), native_tags=False)
        self.assertEqual(found, [])

    def test_a_string_weight_is_a_must_finding(self):
        found = rules.spool_object_problems(dict(MINIMAL, remaining_weight="612"), True)
        self.assertEqual(found, [("must", "remaining_weight is not a JSON number (reads as 0 on the scale)")])

    def test_a_hash_in_the_colour_is_a_should_finding(self):
        spool = dict(MINIMAL, filament=dict(MINIMAL["filament"], color_hex="#1A1A1A"))
        found = rules.spool_object_problems(spool, True)
        self.assertEqual([level for level, _ in found], ["should"])

    def test_dates_and_location_are_should_findings(self):
        spool = dict(MINIMAL, last_used="2026-10-01T12:34:56+02:00", location="x" * 48)
        found = rules.spool_object_problems(spool, True)
        self.assertEqual([level for level, _ in found], ["should", "should"])
        self.assertEqual(rules.spool_object_problems(dict(MINIMAL, last_used="2026-10-01T12:34:56.123Z"), True), [])

    def test_not_an_object_at_all(self):
        self.assertEqual(rules.spool_object_problems([1, 2], True), [("must", "spool is not a JSON object")])


class ListTests(unittest.TestCase):
    def test_archived_spools_in_the_active_list_fail(self):
        spools = [dict(MINIMAL), dict(MINIMAL, id=13, archived=True)]
        self.assertEqual(rules.list_problems(spools, allow_archived=False),
                         [("must", "allow_archived=false returned archived spools [13]")])
        self.assertEqual(rules.list_problems(spools, allow_archived=True), [])

    def test_duplicate_ids_and_non_arrays_fail(self):
        self.assertEqual(rules.list_problems([dict(MINIMAL), dict(MINIMAL)], True),
                         [("must", "spool ids are not unique")])
        self.assertEqual(rules.list_problems({"items": []}, True), [("must", "answer is not a JSON array")])


class TagAndStampTests(unittest.TestCase):
    def test_scan_answers(self):
        self.assertIsNone(rules.scan_problem({"matched_spool_id": 12}, 12))
        self.assertIsNone(rules.scan_problem({"matched_spool_id": None}, None))
        self.assertIn("expected 12", rules.scan_problem({"matched_spool_id": 7}, 12))
        self.assertIn("no matched_spool_id", rules.scan_problem({"spool": {}}, 12))

    def test_stamp_wants_one_spool_the_highest_id_and_the_count(self):
        self.assertEqual(rules.stamp_problems([MINIMAL], 1, 1, 12), [])
        found = rules.stamp_problems([MINIMAL], None, 1, 13)
        self.assertEqual([m for _, m in found],
                         ["sort=id:desc did not return the highest id 13", "x-total-count header missing"])
        self.assertEqual(rules.stamp_problems([MINIMAL, MINIMAL], 2, 2, 12)[0][1],
                         "limit=1 did not return exactly one spool")


if __name__ == "__main__":
    unittest.main()
