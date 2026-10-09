#!/usr/bin/env python3
"""A reference server for the light form of the filament database (Part 1, 6.4).

Sits in front of an inventory server and answers the two light-form routes
itself, from a list of entries; everything else is passed through unchanged:

    python3 examples/light_form_proxy.py http://127.0.0.1:7930 --port 7931
    python3 examples/light_form_proxy.py http://127.0.0.1:7930 --port 7931 --db entries.json

Without --db the entries are read once from the upstream's
GET /api/v1/external/filament (Spoolman's whole database). The search route
answers 404, so the scale and the checker see a pure light-form server:

    GET /api/v1/external/manufacturer[?diameter=1.75]
    GET /api/v1/external/filament?manufacturer=<name>&material=<name>[&diameter=1.75]

Python 3.9, standard library only. A reference, not a product: one thread,
no cache beyond the list, no HTTPS.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlsplit

INDEX_PATH = "/api/v1/external/manufacturer"
LIST_PATH = "/api/v1/external/filament"
SEARCH_PATH = "/api/v1/external/filament/search"
DIAMETER_TOLERANCE_MM = 0.02
READ_TIMEOUT_S = 60


def same(a: Any, b: Any) -> bool:
    return isinstance(a, str) and isinstance(b, str) and a.strip().lower() == b.strip().lower()


def diameter_fits(entry: Dict[str, Any], wanted: Optional[float]) -> bool:
    """An entry without a diameter counts as 1.75 mm (section 6.4)."""
    if wanted is None:
        return True
    value = entry.get("diameter", 1.75)
    return isinstance(value, (int, float)) and abs(value - wanted) <= DIAMETER_TOLERANCE_MM


def build_index(entries: List[Dict[str, Any]], diameter: Optional[float]) -> List[Dict[str, Any]]:
    """Makers with their materials and counts, in the order first seen."""
    makers: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        if not diameter_fits(entry, diameter):
            continue
        maker, material = entry.get("manufacturer"), entry.get("material")
        if not isinstance(maker, str) or not isinstance(material, str):
            continue
        bucket = makers.setdefault(maker.lower(), {"name": maker, "count": 0, "materials": {}})
        bucket["count"] += 1
        slot = bucket["materials"].setdefault(material.lower(), {"name": material, "count": 0})
        slot["count"] += 1
    return [dict(m, materials=list(m["materials"].values())) for m in makers.values()]


def filtered(entries: List[Dict[str, Any]], maker: str, material: str,
             diameter: Optional[float]) -> List[Dict[str, Any]]:
    return [e for e in entries if same(e.get("manufacturer"), maker) and same(e.get("material"), material)
            and diameter_fits(e, diameter)]


def load_entries(upstream: str, db_path: Optional[str]) -> List[Dict[str, Any]]:
    if db_path:
        with open(db_path, encoding="utf-8") as handle:
            return json.load(handle)
    with urllib.request.urlopen(upstream + LIST_PATH, timeout=READ_TIMEOUT_S) as resp:
        return json.load(resp)


class Handler(BaseHTTPRequestHandler):
    upstream = ""
    entries: List[Dict[str, Any]] = []

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s %s\n" % (self.command, fmt % args))

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        diameter = float(query["diameter"]) if query.get("diameter") else None
        if url.path == INDEX_PATH:
            self._send_json(200, build_index(self.entries, diameter))
        elif url.path == LIST_PATH and "manufacturer" in query:
            self._send_json(200, filtered(self.entries, query["manufacturer"], query.get("material", ""), diameter))
        elif url.path in (SEARCH_PATH, LIST_PATH):
            self._send_json(404, {"message": "not offered: this server speaks the light form"})
        else:
            self._forward()

    def do_POST(self) -> None:
        self._forward()

    def do_PATCH(self) -> None:
        self._forward()

    def do_PUT(self) -> None:
        self._forward()

    def do_DELETE(self) -> None:
        self._forward()

    def _forward(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        req = urllib.request.Request(self.upstream + self.path, data=body, method=self.command)
        for key, value in self.headers.items():
            if key.lower() not in ("host", "content-length"):
                req.add_header(key, value)
        try:
            with urllib.request.urlopen(req, timeout=READ_TIMEOUT_S) as resp:
                self._relay(resp.status, dict(resp.headers), resp.read())
        except urllib.error.HTTPError as err:
            self._relay(err.code, dict(err.headers), err.read())
        except (urllib.error.URLError, OSError) as err:
            self._send_json(502, {"message": f"upstream failed: {err}"})

    def _relay(self, status: int, headers: Dict[str, str], body: bytes) -> None:
        self.send_response(status)
        for key, value in headers.items():
            if key.lower() in ("content-type", "x-total-count"):
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("upstream", help="the inventory server, e.g. http://127.0.0.1:7930")
    p.add_argument("--port", type=int, default=7931)
    p.add_argument("--db", help="a JSON array of entries instead of the upstream's whole list")
    args = p.parse_args(argv)
    Handler.upstream = args.upstream.rstrip("/")
    Handler.entries = load_entries(Handler.upstream, args.db)
    print(f"light form proxy on http://127.0.0.1:{args.port}, {len(Handler.entries)} entries, "
          f"upstream {Handler.upstream}", flush=True)
    HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
