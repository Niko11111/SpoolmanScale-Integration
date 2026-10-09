"""Pins down the judgments in check/ams_source_rules.py."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "check"))
import ams_source_rules as rules  # noqa: E402

DISCOVERY = {"version": 1, "server": {"name": "Bridge", "version": "1.0"},
             "capabilities": ["assign", "unassign"], "inventory": {"url": "http://inv:7912"}}

STATUS = {
    "name": "X1C", "connected": True, "ams_exists": True, "tray_now": 1,
    "ams": [{"id": 0, "module_type": "n3f", "humidity": 23, "temp": 27.4,
             "tray": [{"id": 0, "tray_type": "PLA", "tray_color": "1A1A1AFF", "exists": True,
                       "spool_id": 12, "remain_g": 612},
                      {"id": 1, "tray_type": "", "tray_color": "00000000", "exists": False,
                       "spool_id": None, "remain_g": None}]}],
    "vt_tray": [{"id": 254, "tray_type": "PETG", "tray_color": "FF6A00FF", "spool_id": 31, "remain_g": 840}],
}


def levels(found):
    return [level for level, _ in found]


class DiscoveryTests(unittest.TestCase):
    def test_the_example_passes(self):
        self.assertEqual(rules.discovery_problems(DISCOVERY), [])
        self.assertEqual(rules.capabilities_of(DISCOVERY), {"assign", "unassign"})

    def test_wrong_version_and_bad_capabilities_are_must(self):
        self.assertEqual(levels(rules.discovery_problems(dict(DISCOVERY, version=2))), ["must"])
        self.assertEqual(levels(rules.discovery_problems(dict(DISCOVERY, version="1"))), ["must"])
        self.assertEqual(levels(rules.discovery_problems(dict(DISCOVERY, capabilities="assign"))), ["must"])

    def test_missing_server_name_is_should(self):
        doc = dict(DISCOVERY)
        del doc["server"]
        self.assertEqual(levels(rules.discovery_problems(doc)), ["should"])
        self.assertEqual(rules.capabilities_of([]), set())


class PrinterTests(unittest.TestCase):
    def test_ids_from_one_and_unique(self):
        self.assertEqual(rules.printers_problems([{"id": 1, "name": "A", "connected": True}]), [])
        self.assertEqual(levels(rules.printers_problems([{"id": 0, "name": "A"}])), ["must"])
        self.assertEqual(levels(rules.printers_problems([{"id": 1, "name": "A"}, {"id": 1, "name": "B"}])), ["must"])
        self.assertEqual(rules.printer_ids([{"id": 3}, {"id": "x"}, 5]), [3])

    def test_name_is_should(self):
        self.assertEqual(levels(rules.printers_problems([{"id": 2}])), ["should"])


class StatusTests(unittest.TestCase):
    def test_the_example_passes(self):
        self.assertEqual(rules.status_problems(STATUS), [])

    def test_active_anywhere_is_must(self):
        doc = {"ams_exists": True, "ams": [{"id": 0, "tray": [{"id": 0, "spool_id": None, "active": True}]}]}
        found = rules.status_problems(doc)
        self.assertEqual(levels(found), ["must"])
        self.assertIn("ams[0].tray[0].active", found[0][1])

    def test_missing_spool_id_is_must_null_is_fine(self):
        doc = {"ams_exists": True, "ams": [{"id": 0, "tray": [{"id": 0}]}]}
        self.assertEqual(levels(rules.status_problems(doc)), ["must"])
        doc = {"ams_exists": True, "ams": [{"id": 0, "tray": [{"id": 0, "spool_id": None}]}]}
        self.assertEqual(rules.status_problems(doc), [])

    def test_humidity_index_and_hash_colour_are_should(self):
        doc = {"ams_exists": True, "ams": [{"id": 0, "humidity": 150,
                                             "tray": [{"id": 0, "spool_id": None, "tray_color": "#1A1A1A"}]}]}
        self.assertEqual(levels(rules.status_problems(doc)), ["should", "should"])

    def test_shape_errors_are_must(self):
        self.assertEqual(levels(rules.status_problems([])), ["must"])
        self.assertEqual(levels(rules.status_problems({"ams_exists": True, "ams": {}})), ["must"])


class LookupTests(unittest.TestCase):
    def test_tray_spool_in_units_and_external_holder(self):
        self.assertEqual(rules.tray_spool(STATUS, 0, 0), (True, 12))
        self.assertEqual(rules.tray_spool(STATUS, 0, 1), (True, None))
        self.assertEqual(rules.tray_spool(STATUS, 255, 254), (True, 31))
        self.assertEqual(rules.tray_spool(STATUS, 1, 0), (False, None))

    def test_spool_trays_lists_every_claim(self):
        self.assertEqual(rules.spool_trays(STATUS, 12), [(0, 0)])
        self.assertEqual(rules.spool_trays(STATUS, 99), [])
        doubled = dict(STATUS, vt_tray=[dict(STATUS["vt_tray"][0], spool_id=12)])
        self.assertEqual(rules.spool_trays(doubled, 12), [(0, 0), (255, 254)])


if __name__ == "__main__":
    unittest.main()
