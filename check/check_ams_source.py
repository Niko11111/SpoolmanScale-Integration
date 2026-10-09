#!/usr/bin/env python3
"""Runs the Part 2 checklist (ams-source/spec.md, section 10) against a server.

    python3 check/check_ams_source.py http://bridge.local:8001
    python3 check/check_ams_source.py http://bridge.local:8001 --write --printer 1 --spool 12 --spool-b 13

Read-only without --write. With --write it assigns spools A and B to two trays
(0/0 and 0/1 unless --tray and --tray-b say otherwise) and puts the trays back
the way it found them. Exit code 0 means every MUST passed; SHOULD findings
print as warnings. Python 3.9, standard library only.
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ams_source_rules as rules  # noqa: E402
from httpcheck import Client, Report, Response, auth_from  # noqa: E402

PREFIX = "/api/v1/ams-source"
UNKNOWN_SPOOL_ID = 999999999
UNKNOWN_PRINTER_OFFSET = 98      # above the highest printer id seen
DEFAULT_TIMEOUT_S = 10.0
DEFAULT_TRAY = "0/0"
DEFAULT_TRAY_B = "0/1"

Tray = Tuple[int, int]   # (ams_id, tray_id)


def parse_tray(text: str) -> Tray:
    ams, tray = text.split("/")
    return int(ams), int(tray)


class Run:
    def __init__(self, client: Client, report: Report, args: argparse.Namespace):
        self.c = client
        self.r = report
        self.args = args
        self.caps: set = set()
        self.printer: Optional[int] = None
        self.status: Any = None
        self.restore_plan: List[Tuple[Tray, Optional[int]]] = []

    def all(self) -> None:
        self.discovery()
        self.printers()
        self.unknown_printer()
        self.printer_status()
        self.assign_round()
        self.unknown_spool()
        self.auth()
        self.redirects()

    # -- reads ---------------------------------------------------------------

    def discovery(self) -> None:
        resp = self.c.get(PREFIX)
        found = [("must", str(resp))] if resp.status != 200 else rules.discovery_problems(resp.json)
        self.caps = rules.capabilities_of(resp.json)
        name = (resp.json or {}).get("server", {}).get("name", "?") if isinstance(resp.json, dict) else "?"
        self.r.findings(1, f"GET {PREFIX} -> 200, version 1, capabilities ({name}: {', '.join(sorted(self.caps)) or 'none'})", found)

    def printers(self) -> None:
        resp = self.c.get(PREFIX + "/printers")
        found = [("must", str(resp))] if resp.status != 200 else rules.printers_problems(resp.json)
        self.r.findings(2, f"GET {PREFIX}/printers -> array, ids from 1", found)
        ids = rules.printer_ids(resp.json)
        self.printer = self.args.printer or (ids[0] if ids else None)
        if self.printer is not None and self.printer not in ids:
            self.r.should("2b", f"--printer {self.printer} is not in the list", False, f"listed: {ids}")
        self.unknown_id = (max(ids) if ids else 1) + UNKNOWN_PRINTER_OFFSET

    def unknown_printer(self) -> None:
        resp = self.c.get(f"{PREFIX}/printers/{self.unknown_id}/status")
        self.r.must(3, f"GET {PREFIX}/printers/{self.unknown_id}/status (unknown) -> 404", resp.status == 404, str(resp))

    def _status(self) -> Response:
        return self.c.get(f"{PREFIX}/printers/{self.printer}/status")

    def printer_status(self) -> None:
        if self.printer is None:
            self.r.skip(4, "GET .../printers/{id}/status", "no printer listed")
            return
        resp = self._status()
        found = [("must", str(resp))] if resp.status != 200 else rules.status_problems(resp.json)
        self.status = resp.json if resp.status == 200 else None
        self.r.findings(4, f"GET {PREFIX}/printers/{self.printer}/status -> units, trays with spool_id, no 'active'", found)

    def auth(self) -> None:
        title = "a request without the key -> 401 or 403"
        if not self.c.auth:
            self.r.skip(10, title, "no key given (--key)")
            return
        resp = self.c.get(PREFIX + "/printers", with_auth=False)
        self.r.must(10, title, resp.status in (401, 403), str(resp))

    def redirects(self) -> None:
        hits = self.c.redirects_seen()
        self.r.must("c", "no request above was answered with a redirect (common rules)", not hits, "\n".join(hits))

    # -- writes --------------------------------------------------------------

    def _write_ok(self, number: Any, title: str, need_cap: str) -> bool:
        if not self.args.write:
            self.r.skip(number, title, "read-only run: add --write --printer P --spool A --spool-b B")
            return False
        if need_cap not in self.caps:
            self.r.skip(number, title, f"the source does not announce the capability '{need_cap}'")
            return False
        if self.printer is None or self.status is None:
            self.r.skip(number, title, "no printer status to work on")
            return False
        return True

    def _post(self, verb: str, body: dict) -> Response:
        return self.c.request("POST", f"{PREFIX}/printers/{self.printer}/{verb}", body)

    def _assign(self, spool: int, tray: Tray) -> Response:
        return self._post("assign", {"spool_id": spool, "ams_id": tray[0], "tray_id": tray[1]})

    def _unassign(self, tray: Tray) -> Response:
        return self._post("unassign", {"ams_id": tray[0], "tray_id": tray[1]})

    def assign_round(self) -> None:
        title = "assign A, replace with B, move B, unassign twice"
        if not self._write_ok(5, title, "assign"):
            return
        a, b = self.args.spool, self.args.spool_b
        if not (a and b):
            self.r.skip(5, title, "needs --spool A --spool-b B")
            return
        tray_a, tray_b = parse_tray(self.args.tray), parse_tray(self.args.tray_b)
        for tray in (tray_a, tray_b):
            present, spool = rules.tray_spool(self.status, *tray)
            if not present:
                self.r.must(5, f"tray {tray[0]}/{tray[1]} is not in the status", False, "pick another with --tray / --tray-b")
                return
            self.restore_plan.append((tray, spool))
        self._step5(a, tray_a)
        self._step6(a, b, tray_a)
        self._step7(b, tray_a, tray_b)
        self._step8(b, tray_b)

    def _step5(self, a: int, tray_a: Tray) -> None:
        resp = self._assign(a, tray_a)
        _, now = rules.tray_spool(self._status().json, *tray_a)
        self.r.must(5, f"assign spool {a} to {tray_a[0]}/{tray_a[1]} -> 200, status shows it there",
                    resp.status == 200 and now == a, f"{resp}; status spool_id = {now!r}")

    def _step6(self, a: int, b: int, tray_a: Tray) -> None:
        resp = self._assign(b, tray_a)
        status = self._status().json
        left = rules.spool_trays(status, a)
        _, now = rules.tray_spool(status, *tray_a)
        self.r.must(6, f"assign spool {b} to the same tray -> 200, spool {a} is in no tray",
                    resp.status == 200 and now == b and not left, f"{resp}; {a} still at {left}, tray holds {now!r}")

    def _step7(self, b: int, tray_a: Tray, tray_b: Tray) -> None:
        resp = self._assign(b, tray_b)
        status = self._status().json
        _, at_a = rules.tray_spool(status, *tray_a)
        where = rules.spool_trays(status, b)
        self.r.must(7, f"assign spool {b} to {tray_b[0]}/{tray_b[1]} -> 200, old tray empty, {b} only there",
                    resp.status == 200 and at_a is None and where == [tray_b],
                    f"{resp}; old tray holds {at_a!r}, {b} at {where}")

    def _step8(self, b: int, tray_b: Tray) -> None:
        if "unassign" not in self.caps:
            self.r.skip(8, "unassign twice", "the source does not announce 'unassign'")
            return
        first = self._unassign(tray_b)
        released = first.json.get("spool_id") if isinstance(first.json, dict) else "?"
        again = self._unassign(tray_b)
        released_again = again.json.get("spool_id") if isinstance(again.json, dict) else "?"
        self.r.must(8, f"unassign {tray_b[0]}/{tray_b[1]} -> 200 with spool_id {b}; again -> 200 with null",
                    first.status == 200 and released == b and again.status == 200 and released_again is None,
                    f"first: {first}; again: {again}")

    def unknown_spool(self) -> None:
        title = f"assign unknown spool {UNKNOWN_SPOOL_ID} -> 404"
        if not self._write_ok(9, title, "assign"):
            return
        tray = parse_tray(self.args.tray)
        resp = self._assign(UNKNOWN_SPOOL_ID, tray)
        self.r.must(9, title, resp.status == 404, str(resp))

    def restore(self) -> None:
        """Puts both trays back: the spool that was there, or empty."""
        for tray, spool in self.restore_plan:
            if spool is not None:
                resp = self._assign(spool, tray)
            elif "unassign" in self.caps:
                resp = self._unassign(tray)
            else:
                continue
            self.r.must("r", f"restore tray {tray[0]}/{tray[1]} ({'spool ' + str(spool) if spool else 'empty'}) -> 200",
                        resp.status == 200, str(resp))
        self.restore_plan = []


def parse_args(argv: Optional[List[str]]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("base", help="base URL, e.g. http://bridge.local:8001")
    p.add_argument("--key", help="sent as X-API-Key")
    p.add_argument("--write", action="store_true", help="run the assign round and the unknown-spool check")
    p.add_argument("--printer", type=int, help="printer id to use (default: the first listed)")
    p.add_argument("--spool", type=int, help="spool A, an id of the inventory behind the source")
    p.add_argument("--spool-b", type=int, help="spool B, a second one")
    p.add_argument("--tray", default=DEFAULT_TRAY, help="first tray as ams/tray, default 0/0")
    p.add_argument("--tray-b", default=DEFAULT_TRAY_B, help="second tray as ams/tray, default 0/1")
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
    print(f"SpoolmanScale AMS source check, Part 2 draft, against {client.base}")
    run = Run(client, report, args)
    try:
        run.all()
    finally:
        run.restore()
    print(report.summary())
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
