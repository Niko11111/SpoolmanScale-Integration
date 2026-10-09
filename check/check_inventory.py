#!/usr/bin/env python3
"""Runs the Part 1 checklist (inventory/spec.md, section 9) against a server.

    python3 check/check_inventory.py http://host:7912
    python3 check/check_inventory.py https://inv.example --key K --write --spool 12 --spool-b 13

Read-only without --write. With --write it changes spool A (and B for the tag
conflict) and puts remaining weight, initial weight, location and tags back the
way it found them; last_used moves to now. It also creates a maker, a filament
and a spool the way the scale does (section 6.5) and deletes them again. Exit
code 0 means every MUST passed; SHOULD findings print as warnings. Python 3.9,
standard library only, so it runs on the machine the server runs on.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import inventory_rules as rules  # noqa: E402
from database_checks import DatabaseRun  # noqa: E402
from httpcheck import Client, Report, auth_from  # noqa: E402

# A UID no chip carries, in the spelling the scale sends (section 5).
TEST_UID = "04:CC:CC:CC:CC:CC:01"
TEST_UNKNOWN_UID = "04:CC:CC:CC:CC:CC:02"
PATCH_TEST_WEIGHT_G = 500
MEASURE_TEST_NET_G = 600
UNKNOWN_ID_OFFSET = 100000       # above the highest id seen: an id that does not exist
DEFAULT_TIMEOUT_S = 10.0

LIST_ACTIVE = "/api/v1/spool?allow_archived=false"
LIST_ALL = "/api/v1/spool?allow_archived=true"
LIST_STAMP = "/api/v1/spool?allow_archived=false&limit=1&sort=id:desc"


class Run:
    """The checklist, in its order, against one server."""

    def __init__(self, client: Client, report: Report, args: argparse.Namespace):
        self.c = client
        self.r = report
        self.args = args
        self.spools: List[Dict[str, Any]] = []
        self.native = False
        self.probe_status = 0
        self.saved: Dict[str, Any] = {}

    def all(self) -> None:
        self.probe()
        self.health_and_info()
        self.lists()
        self.single_spool()
        self.patch_writes()
        self.field_list()
        self.probe_report()
        self.tags()
        self.auth()
        self.measure()
        self.stamp()
        self.locations()
        DatabaseRun(self.c, self.r, self.args).all()
        self.redirects()

    # -- reads ---------------------------------------------------------------

    def probe(self) -> None:
        self.probe_status = self.c.get("/api/v1/tag/reader").status
        self.native = self.probe_status == 200

    def health_and_info(self) -> None:
        resp = self.c.get("/api/v1/health")
        self.r.must(1, "GET /api/v1/health -> 200", resp.status == 200, str(resp))
        resp = self.c.get("/api/v1/info")
        version = resp.json.get("version") if isinstance(resp.json, dict) else None
        ok = resp.status == 200 and isinstance(version, str)
        self.r.must("1b", f"GET /api/v1/info -> 200 with version ({version or '?'})", ok, str(resp))

    def lists(self) -> None:
        active = self.c.get(LIST_ACTIVE)
        found = self._list_findings(active, allow_archived=False)
        self.r.findings(2, f"GET {LIST_ACTIVE} -> every active spool, well formed", found)
        if isinstance(active.json, list):
            self.spools = [s for s in active.json if isinstance(s, dict)]
        every = self.c.get(LIST_ALL)
        found = self._list_findings(every, allow_archived=True)
        if not found and isinstance(every.json, list) and len(every.json) < len(self.spools):
            found.append(("must", "allow_archived=true returned fewer spools than the active list"))
        self.r.findings(3, f"GET {LIST_ALL} -> the archived ones too", found)

    def _list_findings(self, resp: Response, allow_archived: bool) -> List[rules.Finding]:
        if resp.status != 200:
            return [("must", str(resp))]
        found = rules.list_problems(resp.json, allow_archived)
        for spool in resp.json if isinstance(resp.json, list) else []:
            label = f"spool {spool.get('id') if isinstance(spool, dict) else '?'}: "
            found += [(level, label + msg) for level, msg in rules.spool_object_problems(spool, self.native)]
        return found

    def _ids(self) -> List[int]:
        return [s["id"] for s in self.spools if rules.is_int(s.get("id"))]

    def single_spool(self) -> None:
        ids = self._ids()
        if not ids:
            self.r.skip(4, "GET /api/v1/spool/{id}", "no active spool to ask for")
            return
        resp = self.c.get(f"/api/v1/spool/{ids[0]}")
        ok = resp.status == 200 and isinstance(resp.json, dict) and resp.json.get("id") == ids[0]
        self.r.must(4, f"GET /api/v1/spool/{ids[0]} -> 200 with that spool", ok, str(resp))
        unknown = max(ids) + UNKNOWN_ID_OFFSET
        resp = self.c.get(f"/api/v1/spool/{unknown}")
        self.r.must("4b", f"GET /api/v1/spool/{unknown} (unknown id) -> 404", resp.status == 404, str(resp))

    def field_list(self) -> None:
        resp = self.c.get("/api/v1/field/spool")
        ok = resp.status == 200 and isinstance(resp.json, list)
        self.r.must(7, "GET /api/v1/field/spool -> 200 and an array", ok, str(resp))

    def probe_report(self) -> None:
        what = "native tags (5.1)" if self.native else "extra field tag (5.2)"
        self.r.must(8, f"GET /api/v1/tag/reader -> {self.probe_status}: {what}",
                    self.probe_status in (200, 404), "answer 200 or 404, nothing else")

    def auth(self) -> None:
        title = "a request without the key -> 401 or 403"
        if not self.c.auth:
            self.r.skip(10, title, "no key given (--key, --bearer or --basic)")
            return
        resp = self.c.get(LIST_ACTIVE + "&limit=1", with_auth=False)
        self.r.must(10, title, resp.status in (401, 403), str(resp))

    def redirects(self) -> None:
        hits = self.c.redirects_seen()
        self.r.must(11, "no request above was answered with a redirect", not hits, "\n".join(hits))

    def stamp(self) -> None:
        resp = self.c.get(LIST_STAMP)
        if resp.status != 200:
            self.r.should(13, f"GET {LIST_STAMP} -> 200", False, str(resp))
            return
        header = resp.headers.get("x-total-count")
        count = int(header) if header and header.isdigit() else None
        ids = self._ids()
        found = rules.stamp_problems(resp.json, count, len(self.spools), max(ids) if ids else None)
        self.r.findings(13, f"GET {LIST_STAMP} -> one spool, the highest id, x-total-count", found)

    def locations(self) -> None:
        resp = self.c.get("/api/v1/location")
        ok = resp.status == 200 and isinstance(resp.json, list) and all(isinstance(x, str) for x in resp.json)
        self.r.should(14, "GET /api/v1/location -> array of strings", ok, str(resp))

    # -- writes --------------------------------------------------------------

    def _write_target(self, number: Any, title: str) -> Optional[int]:
        """The spool the write checks may touch, or None after printing why not."""
        if not self.args.write:
            self.r.skip(number, title, "read-only run: add --write --spool ID")
            return None
        if not self.args.spool:
            self.r.skip(number, title, "--write needs --spool ID")
            return None
        return self.args.spool

    def patch_writes(self) -> None:
        spool_id = self._write_target(5, "PATCH /api/v1/spool/{id} remaining_weight")
        if spool_id is None:
            self.r.skip(6, "PATCH /api/v1/spool/{id} location null", "see 5")
            return
        before = self.c.get(f"/api/v1/spool/{spool_id}")
        if before.status != 200 or not isinstance(before.json, dict):
            self.r.must(5, f"GET /api/v1/spool/{spool_id} before writing", False, str(before))
            return
        self.saved = {"id": spool_id, "spool": before.json}
        self._patch_weight(spool_id)
        self._patch_location(spool_id)

    def _patch_weight(self, spool_id: int) -> None:
        path = f"/api/v1/spool/{spool_id}"
        resp = self.c.request("PATCH", path, {"remaining_weight": PATCH_TEST_WEIGHT_G})
        after = self.c.get(path).json if resp.status == 200 else None
        got = after.get("remaining_weight") if isinstance(after, dict) else None
        self.r.must(5, f"PATCH {path} remaining_weight {PATCH_TEST_WEIGHT_G} -> 200, GET reads it back",
                    rules.weights_match(got, PATCH_TEST_WEIGHT_G), f"{resp}; GET remaining_weight = {got!r}")

    def _patch_location(self, spool_id: int) -> None:
        path = f"/api/v1/spool/{spool_id}"
        resp = self.c.request("PATCH", path, {"location": None})
        after = self.c.get(path).json if resp.status == 200 else None
        location = after.get("location") if isinstance(after, dict) else "?"
        ok = resp.status == 200 and isinstance(after, dict) and location in (None, "")
        self.r.must(6, f"PATCH {path} location null -> 200, location gone", ok,
                    f"{resp}; GET location = {location!r}")

    def measure(self) -> None:
        title = "PUT /api/v1/spool/{id}/measure"
        if not self.saved:
            self.r.skip(12, title, "needs --write --spool ID")
            return
        spool_id, spool = self.saved["id"], self.saved["spool"]
        tare = rules.tare_of(spool)
        gross = tare + MEASURE_TEST_NET_G
        path = f"/api/v1/spool/{spool_id}/measure"
        resp = self.c.request("PUT", path, {"weight": gross})
        if resp.status in (404, 405):
            self.r.should(12, f"{title}: not implemented ({resp.status}), the scale falls back to PATCH", True)
            return
        after = self.c.get(f"/api/v1/spool/{spool_id}").json if resp.status == 200 else None
        got = after.get("remaining_weight") if isinstance(after, dict) else None
        self.r.should(12, f"PUT {path} weight {gross:g} (tare {tare:g}) -> 200, remaining {MEASURE_TEST_NET_G}",
                      rules.weights_match(got, MEASURE_TEST_NET_G), f"{resp}; GET remaining_weight = {got!r}")

    def tags(self) -> None:
        title = "native tags: link, scan, conflict, unknown uid, unlink"
        if not self.native:
            self.r.skip(9, title, "no native tags on this server; the scale uses an extra field (5.2)")
            return
        if not (self.args.write and self.args.spool and self.args.spool_b):
            self.r.skip(9, title, "needs --write --spool A --spool-b B")
            return
        a, b = self.args.spool, self.args.spool_b
        try:
            self._tag_round(a, b)
        finally:
            for spool_id in (a, b):
                self.c.request("DELETE", f"/api/v1/spool/{spool_id}/tag/{TEST_UID}")

    def _scan(self, uid: str) -> Response:
        body = {"uid": uid, "reader_id": "spoolmanscale-check", "name": "check", "format": "ntag"}
        return self.c.request("POST", "/api/v1/tag/scan", body)

    def _tag_round(self, a: int, b: int) -> None:
        link = self.c.request("POST", f"/api/v1/spool/{a}/tag", {"uid": TEST_UID, "format": "ntag"})
        self.r.must(9, f"POST /api/v1/spool/{a}/tag {TEST_UID} -> 2xx", 200 <= link.status < 300, str(link))
        spool = self.c.get(f"/api/v1/spool/{a}").json
        holds = isinstance(spool, dict) and rules.tags_hold(spool, TEST_UID)
        tags = spool.get("tags") if isinstance(spool, dict) else None
        self.r.must("9b", f"GET /api/v1/spool/{a} lists the tag in tags", holds, json.dumps(tags))
        scan = self._scan(TEST_UID.lower().replace(":", ""))
        problem = rules.scan_problem(scan.json, a)
        self.r.must("9c", f"POST /api/v1/tag/scan lowercase, no colons -> 200, matched_spool_id {a}",
                    scan.status == 200 and problem is None, problem or str(scan))
        embedded = isinstance(scan.json, dict) and isinstance(scan.json.get("spool"), dict)
        self.r.should("9d", "the scan answer embeds the spool", embedded, "without it the scale needs one more GET")
        clash = self.c.request("POST", f"/api/v1/spool/{b}/tag", {"uid": TEST_UID, "format": "ntag"})
        names_a = isinstance(clash.json, dict) and clash.json.get("spool_id") == a
        self.r.must("9e", f"POST /api/v1/spool/{b}/tag same uid -> 409 with spool_id {a}",
                    clash.status == 409 and names_a, str(clash))
        unknown = self._scan(TEST_UNKNOWN_UID)
        problem = rules.scan_problem(unknown.json, None)
        self.r.must("9f", "scan of an unknown uid -> 200 with matched_spool_id null",
                    unknown.status == 200 and problem is None, problem or str(unknown))
        gone = self.c.request("DELETE", f"/api/v1/spool/{a}/tag/{TEST_UID}")
        self.r.must("9g", f"DELETE /api/v1/spool/{a}/tag/{TEST_UID} -> 2xx", 200 <= gone.status < 300, str(gone))

    def restore(self) -> None:
        """Puts spool A back: weights and location as read before the writes."""
        if not self.saved:
            return
        spool_id, before = self.saved["id"], self.saved["spool"]
        body: Dict[str, Any] = {"location": before.get("location")}
        for key in ("remaining_weight", "initial_weight"):
            if rules.is_number(before.get(key)):
                body[key] = before[key]
        resp = self.c.request("PATCH", f"/api/v1/spool/{spool_id}", body)
        self.r.must("r", f"restore spool {spool_id} ({', '.join(body)}) -> 200", resp.status == 200, str(resp))
        self.saved = {}


def parse_args(argv: Optional[List[str]]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("base", help="base URL, e.g. http://inventory.local:7912")
    auth = p.add_mutually_exclusive_group()
    auth.add_argument("--key", help="sent as X-API-Key")
    auth.add_argument("--bearer", help="sent as Authorization: Bearer")
    auth.add_argument("--basic", metavar="USER:PASSWORD", help="sent as HTTP Basic")
    p.add_argument("--write", action="store_true", help="run the write checks on --spool (and --spool-b)")
    p.add_argument("--spool", type=int, help="spool id the write checks may touch; values are restored")
    p.add_argument("--spool-b", type=int, help="second spool, for the tag conflict check")
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S, help="seconds per request")
    p.add_argument("--insecure", action="store_true", help="do not verify the TLS certificate")
    p.add_argument("-v", "--verbose", action="store_true", help="print the answers of passing checks too")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    if not args.base.startswith(("http://", "https://")):
        print("the base URL must start with http:// or https://", file=sys.stderr)
        return 2
    client = Client(args.base, auth_from(args), args.timeout, args.insecure)
    report = Report(args.verbose)
    print(f"SpoolmanScale inventory check, Part 1 version 1, against {client.base}")
    run = Run(client, report, args)
    try:
        run.all()
    finally:
        run.restore()
    print(report.summary())
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
