"""Checklist items 15 to 17 of Part 1: the filament database and the create path.

Called by check_inventory.py with its client and report. Item 15 finds out
which form the server offers (6.4) and checks its shape; 16 the material
list; 17, with --write, creates a maker, a filament and a spool the way the
scale does (6.5), finds them again and deletes them.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import database_rules as rules
from httpcheck import Client, Report, Response

INDEX_PATH = "/api/v1/external/manufacturer"
LIST_PATH = "/api/v1/external/filament"
SEARCH_PATH = "/api/v1/external/filament/search"
MATERIAL_PATH = "/api/v1/external/material"
PROBE_WORDS = "PLA"
PAGE = rules.SEARCH_PAGE_MAX

CHECK_VENDOR_NAME = "SpoolmanScale check"
CHECK_FILAMENT = {"name": "Check Blue", "material": "PLA", "density": 1.24,
                  "diameter": rules.DIAMETER_MM, "color_hex": "0055AA",
                  "weight": 1000, "spool_weight": 140,
                  "settings_extruder_temp": 210, "settings_bed_temp": 55}
CHECK_SPOOL = {"initial_weight": 1000, "spool_weight": 140, "remaining_weight": 1000}
UNKNOWN_EXTERNAL_ID = "spoolmanscale-check-nothing"


def exact(key: str, value: str) -> str:
    """Spoolman's exact-match filter: the value in quotes (section 6.5)."""
    return f"{key}={quote(chr(34) + value + chr(34))}"


class DatabaseRun:
    def __init__(self, client: Client, report: Report, args: Any):
        self.c = client
        self.r = report
        self.args = args
        self.created: Dict[str, int] = {}   # what 17 made, in the order to delete it

    def all(self) -> None:
        self.database()
        self.materials()
        self.creation()

    # -- 15, the database ------------------------------------------------------

    def database(self) -> None:
        index = self.c.get(INDEX_PATH)
        if index.status == 200:
            self._light_form(index)
            return
        probe = self.c.get(f"{SEARCH_PATH}?limit=1&query={PROBE_WORDS}")
        if probe.status == 200:
            self._spoolman_form()
            return
        absent = index.status in (404, 405) and probe.status in (404, 405)
        self.r.should(15, "filament database: none (404 on both forms), the scale creates from tags only"
                      if absent else f"filament database: index -> {index.status}, search -> {probe.status}",
                      False, "" if absent else "a server without a database answers 404 on both routes")

    def _light_form(self, index: Response) -> None:
        found = rules.index_problems(index.json)
        self.r.findings(15, f"GET {INDEX_PATH} -> 200, the index (light form)", found)
        pair = rules.pick_pair(index.json)
        if not pair:
            self.r.skip("15b", f"GET {LIST_PATH}?manufacturer=&material=", "no maker with a material in the index")
            return
        maker, material = pair
        path = f"{LIST_PATH}?manufacturer={quote(maker)}&material={quote(material)}&diameter={rules.DIAMETER_MM}"
        resp = self.c.get(path)
        found = rules.filtered_list_problems(resp.json, maker, material) if resp.status == 200 else [("must", str(resp))]
        self.r.findings("15b", f"GET {LIST_PATH}?manufacturer={maker}&material={material} -> that pair's entries",
                        found)

    def _spoolman_form(self) -> None:
        page = self.c.get(f"{SEARCH_PATH}?limit={PAGE}&query={PROBE_WORDS}")
        found = rules.search_page_problems(page.json, PROBE_WORDS, PAGE) if page.status == 200 else [("must", str(page))]
        self.r.findings(15, f"GET {SEARCH_PATH}?limit={PAGE}&query={PROBE_WORDS} -> a page (Spoolman form)", found)
        sample = next((e for e in page.json or [] if isinstance(e, dict)), None) if page.status == 200 else None
        if sample:
            self._search_words(sample)
            self._search_offset()
        whole = self.c.get(LIST_PATH)
        found = rules.entries_problems(whole.json) if whole.status == 200 else [("must", str(whole))]
        if sample and not found and sample.get("id") not in {e.get("id") for e in whole.json}:
            found.append(("must", f"the whole list lacks entry {sample.get('id')} the search found"))
        size = f"{len(whole.body) / 1e6:.1f} MB, {len(whole.json) if isinstance(whole.json, list) else '?'} entries"
        self.r.findings("15d", f"GET {LIST_PATH} -> the whole database, well formed ({size})", found)

    def _search_words(self, sample: Dict[str, Any]) -> None:
        words = f"{sample.get('manufacturer', '')} {sample.get('material', '')}".strip()
        resp = self.c.get(f"{SEARCH_PATH}?limit={PAGE}&query={quote(words)}")
        found = rules.search_page_problems(resp.json, words, PAGE) if resp.status == 200 else [("must", str(resp))]
        self.r.findings("15b", f"GET {SEARCH_PATH}?query={words} -> every hit carries both words", found)

    def _search_offset(self) -> None:
        two = self.c.get(f"{SEARCH_PATH}?limit=2&query={PROBE_WORDS}")
        one = self.c.get(f"{SEARCH_PATH}?limit=1&offset=1&query={PROBE_WORDS}")
        ok = two.status == 200 and one.status == 200 and rules.offset_honoured(two.json, one.json)
        self.r.must("15c", f"GET {SEARCH_PATH}?limit=1&offset=1 -> the second hit of limit=2", ok,
                    f"limit=2: {two}; offset=1: {one}")

    # -- 16, the material list -------------------------------------------------

    def materials(self) -> None:
        resp = self.c.get(MATERIAL_PATH)
        if resp.status in (404, 405):
            self.r.should(16, f"GET {MATERIAL_PATH} -> {resp.status}: no material list, densities come from entries", True)
            return
        found = rules.material_list_problems(resp.json) if resp.status == 200 else [("must", str(resp))]
        self.r.findings(16, f"GET {MATERIAL_PATH} -> array with material and density", found)

    # -- 17, creating ----------------------------------------------------------

    def creation(self) -> None:
        title = "create a maker, a filament and a spool, find them, delete them (6.5)"
        if not self.args.write:
            self.r.skip(17, title, "read-only run: add --write")
            return
        try:
            self._create_round()
        finally:
            self._delete_created()

    def _create_round(self) -> None:
        stamp = str(int(time.time()))
        vendor_id = self._post("17a", "/api/v1/vendor", {"name": CHECK_VENDOR_NAME, "empty_spool_weight": 140}, "vendor")
        if not vendor_id:
            return
        self._find("17b", f"/api/v1/vendor?{exact('name', CHECK_VENDOR_NAME)}", vendor_id)
        filament = dict(CHECK_FILAMENT, vendor_id=vendor_id, external_id=f"spoolmanscale-check-{stamp}",
                        article_number=f"SMS-{stamp}")
        filament_id = self._post("17c", "/api/v1/filament", filament, "filament")
        if not filament_id:
            return
        self._find("17d", f"/api/v1/filament?{exact('external_id', filament['external_id'])}", filament_id)
        self._find("17e", f"/api/v1/filament?{exact('article_number', filament['article_number'])}", filament_id)
        self._find("17f", f"/api/v1/filament?{exact('external_id', UNKNOWN_EXTERNAL_ID)}", None)
        self._post("17g", "/api/v1/spool", dict(CHECK_SPOOL, filament_id=filament_id), "spool")

    def _post(self, number: str, path: str, body: Dict[str, Any], what: str) -> Optional[int]:
        resp = self.c.request("POST", path, body)
        if number == "17a" and resp.status in (404, 405):
            self.r.should(number, f"POST {path} -> {resp.status}: creating is not offered, the scale cannot make new spools",
                          False)
            return None
        found = rules.created_problems(resp.json, body) if resp.status in (200, 201) else [("must", str(resp))]
        self.r.findings(number, f"POST {path} -> 200 or 201 with the {what}, id included", found)
        if found or not isinstance(resp.json, dict):
            return None
        self.created[what] = resp.json["id"]
        return resp.json["id"]

    def _find(self, number: str, path: str, wanted: Optional[int]) -> None:
        resp = self.c.get(path)
        found = rules.find_problems(resp.json, wanted) if resp.status == 200 else [("must", str(resp))]
        what = f"finds id {wanted}" if wanted else "answers [] for an unknown value"
        self.r.findings(number, f"GET {path} -> 200, {what}", found)

    def _delete_created(self) -> None:
        left: List[str] = []
        for what in ("spool", "filament", "vendor"):
            if what not in self.created:
                continue
            resp = self.c.request("DELETE", f"/api/v1/{what}/{self.created[what]}")
            if not 200 <= resp.status < 300:
                left.append(f"{what} {self.created[what]} ({resp})")
        if self.created:
            self.r.must("17h", "DELETE the spool, the filament and the maker again -> 2xx", not left,
                        "left behind, delete by hand: " + "; ".join(left))
        self.created = {}
