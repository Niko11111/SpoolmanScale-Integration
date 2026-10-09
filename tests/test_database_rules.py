"""Pins down the judgments in check/database_rules.py."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "check"))
import database_rules as rules  # noqa: E402

ENTRY = {"id": "polymaker_pla_luminousblue_1000_175", "manufacturer": "Polymaker", "material": "PLA",
         "name": "Panchroma Luminous Blue", "density": 1.24, "weight": 1000, "spool_weight": 140,
         "diameter": 1.75, "color_hex": "419EC2", "extruder_temp": 210, "bed_temp": 50}
INDEX = [{"name": "Polymaker", "count": 2,
          "materials": [{"name": "PLA", "count": 1}, {"name": "ABS", "count": 1}]},
         {"name": "Sunlu", "materials": [{"name": "PETG"}]}]


def without(obj, *keys):
    copy = dict(obj)
    for key in keys:
        copy.pop(key, None)
    return copy


def levels(found):
    return sorted(level for level, _ in found)


class EntryTests(unittest.TestCase):
    def test_the_full_entry_passes(self):
        self.assertEqual(rules.entry_problems(ENTRY), [])

    def test_the_four_texts_are_must(self):
        found = rules.entry_problems(without(ENTRY, "id", "manufacturer", "material", "name"))
        self.assertEqual(levels(found), ["must"] * 4)

    def test_an_empty_id_counts_as_missing(self):
        self.assertEqual(levels(rules.entry_problems(dict(ENTRY, id=" "))), ["must"])

    def test_long_texts_are_cut_on_the_scale(self):
        found = rules.entry_problems(dict(ENTRY, name="x" * 96, line="y" * 25))
        self.assertEqual(levels(found), ["should", "should"])

    def test_a_string_weight_and_a_hash_colour_are_should(self):
        found = rules.entry_problems(dict(ENTRY, weight="1000", color_hex="#419EC2"))
        self.assertEqual(levels(found), ["should", "should"])

    def test_see_through_colour_with_alpha_in_front_is_fine(self):
        self.assertEqual(rules.entry_problems(dict(ENTRY, color_hex="3CD8100C")), [])

    def test_no_colour_at_all_is_should(self):
        found = rules.entry_problems(without(ENTRY, "color_hex"))
        self.assertEqual(found, [("should", "no colour: the entry is not listed on the scale")])
        multi = dict(without(ENTRY, "color_hex"), color_hexes=["9CDBD9", "FFFFFF"], multi_color_direction="coaxial")
        self.assertEqual(rules.entry_problems(multi), [])

    def test_duplicate_ids_in_a_list_are_must(self):
        self.assertEqual(levels(rules.entries_problems([ENTRY, ENTRY])), ["must"])
        self.assertEqual(rules.entries_problems([ENTRY]), [])
        self.assertEqual(levels(rules.entries_problems({"items": []})), ["must"])


class LightFormTests(unittest.TestCase):
    def test_the_index_passes_and_names_its_first_pair(self):
        self.assertEqual(rules.index_problems(INDEX), [])
        self.assertEqual(rules.pick_pair(INDEX), ("Polymaker", "PLA"))

    def test_a_maker_without_materials_or_listed_twice_is_must(self):
        self.assertEqual(levels(rules.index_problems([{"name": "Polymaker", "materials": []}])), ["must"])
        twice = [INDEX[0], dict(INDEX[0], name="polymaker")]
        self.assertEqual(levels(rules.index_problems(twice)), ["must"])
        self.assertEqual(levels(rules.index_problems([])), ["must"])

    def test_a_count_that_is_no_integer_is_should(self):
        index = [{"name": "Polymaker", "count": "2", "materials": [{"name": "PLA", "count": 1.5}]}]
        self.assertEqual(levels(rules.index_problems(index)), ["should", "should"])

    def test_pick_pair_skips_a_material_with_count_zero(self):
        index = [{"name": "Polymaker", "materials": [{"name": "PLA", "count": 0}, {"name": "ABS", "count": 3}]}]
        self.assertEqual(rules.pick_pair(index), ("Polymaker", "ABS"))
        self.assertIsNone(rules.pick_pair([]))

    def test_the_filtered_list_may_hold_only_that_pair(self):
        self.assertEqual(rules.filtered_list_problems([ENTRY], "polymaker", "pla"), [])
        foreign = [ENTRY, dict(ENTRY, id="other", manufacturer="Sunlu")]
        self.assertEqual(levels(rules.filtered_list_problems(foreign, "Polymaker", "PLA")), ["must"])
        self.assertEqual(levels(rules.filtered_list_problems([], "Polymaker", "PLA")), ["must"])


class SpoolmanFormTests(unittest.TestCase):
    def test_a_page_within_the_limit_with_the_words_passes(self):
        self.assertEqual(rules.search_page_problems([ENTRY], "Polymaker PLA", 100), [])

    def test_a_hit_without_a_word_and_a_page_over_the_limit_are_must(self):
        self.assertEqual(levels(rules.search_page_problems([ENTRY], "Sunlu PLA", 100)), ["must"])
        page = [dict(ENTRY, id=str(i)) for i in range(3)]
        self.assertEqual(levels(rules.search_page_problems(page, "PLA", 2)), ["must"])

    def test_offset_gives_the_second_hit(self):
        a, b = dict(ENTRY, id="a"), dict(ENTRY, id="b")
        self.assertTrue(rules.offset_honoured([a, b], [b]))
        self.assertFalse(rules.offset_honoured([a, b], [a]))
        self.assertFalse(rules.offset_honoured([a, b], [a, b]))
        self.assertTrue(rules.offset_honoured([a], []))

    def test_the_material_list_needs_name_and_density(self):
        self.assertEqual(rules.material_list_problems([{"material": "PLA", "density": 1.24}]), [])
        self.assertEqual(levels(rules.material_list_problems([{"material": "PLA"}, {"density": 1.2}])),
                         ["must", "must"])


class CreateTests(unittest.TestCase):
    def test_a_create_answers_the_object_with_its_id_and_texts(self):
        sent = {"name": "Check Blue", "external_id": "x-1", "article_number": "SMS-1"}
        self.assertEqual(rules.created_problems(dict(sent, id=7), sent), [])
        self.assertEqual(levels(rules.created_problems(dict(sent, id=0), sent)), ["must"])
        self.assertEqual(levels(rules.created_problems(dict(sent, id=7, external_id=None), sent)), ["must"])
        self.assertEqual(levels(rules.created_problems("created", sent)), ["must"])

    def test_a_find_holds_the_id_or_nothing(self):
        self.assertEqual(rules.find_problems([{"id": 3}, {"id": 7}], 7), [])
        self.assertEqual(levels(rules.find_problems([{"id": 3}], 7)), ["must"])
        self.assertEqual(rules.find_problems([], None), [])
        self.assertEqual(levels(rules.find_problems([{"id": 3}], None)), ["must"])
        self.assertEqual(levels(rules.find_problems(None, 7)), ["must"])


if __name__ == "__main__":
    unittest.main()
