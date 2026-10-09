"""Pure judgments on what an AMS source answered (Part 2).

Plain functions over parsed JSON, no network, no printing. Section numbers
refer to ams-source/spec.md. check_ams_source.py does the talking.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from inventory_rules import is_hex_color, is_int, is_number

Finding = Tuple[str, str]

KNOWN_VERSION = 1
HUMIDITY_MAX_PERCENT = 100
# The one word a status must not carry: it means "assigned" on some servers
# and "feeding now" on the printer (section 5).
FORBIDDEN_KEY = "active"


def discovery_problems(doc: Any) -> List[Finding]:
    """Section 2: version, capabilities, server, optional inventory."""
    if not isinstance(doc, dict):
        return [("must", "discovery answer is not a JSON object")]
    found: List[Finding] = []
    version = doc.get("version")
    if not is_int(version):
        found.append(("must", "version is not an integer"))
    elif version != KNOWN_VERSION:
        found.append(("must", f"version {version}: this checker knows version {KNOWN_VERSION}"))
    caps = doc.get("capabilities")
    if not isinstance(caps, list) or not all(isinstance(c, str) for c in caps):
        found.append(("must", "capabilities is not an array of strings"))
    server = doc.get("server")
    if not isinstance(server, dict) or not isinstance(server.get("name"), str):
        found.append(("should", "server.name missing: the scale shows '?' for the source"))
    inventory = doc.get("inventory")
    if inventory is not None and not isinstance((inventory or {}).get("url"), str):
        found.append(("should", "inventory.url is not a string"))
    return found


def capabilities_of(doc: Any) -> set:
    caps = doc.get("capabilities") if isinstance(doc, dict) else None
    return {c for c in caps if isinstance(c, str)} if isinstance(caps, list) else set()


def printers_problems(doc: Any) -> List[Finding]:
    """Section 4: an array of printers with integer ids from 1."""
    if not isinstance(doc, list):
        return [("must", "printer list is not a JSON array")]
    found: List[Finding] = []
    ids = []
    for printer in doc:
        if not isinstance(printer, dict) or not is_int(printer.get("id")) or printer["id"] < 1:
            found.append(("must", "a printer has no integer id from 1"))
            continue
        ids.append(printer["id"])
        if not isinstance(printer.get("name"), str):
            found.append(("should", f"printer {printer['id']} has no name"))
        if "connected" in printer and not isinstance(printer["connected"], bool):
            found.append(("should", f"printer {printer['id']}: connected is not a boolean"))
    if len(set(ids)) != len(ids):
        found.append(("must", "printer ids are not unique"))
    return found


def printer_ids(doc: Any) -> List[int]:
    if not isinstance(doc, list):
        return []
    return [p["id"] for p in doc if isinstance(p, dict) and is_int(p.get("id"))]


def _forbidden_keys(node: Any, path: str = "") -> List[str]:
    """Every place a forbidden key appears, as a path for the report."""
    hits: List[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else key
            if key == FORBIDDEN_KEY:
                hits.append(here)
            hits += _forbidden_keys(value, here)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            hits += _forbidden_keys(item, f"{path}[{i}]")
    return hits


def _tray_findings(tray: Any, where: str) -> List[Finding]:
    if not isinstance(tray, dict):
        return [("must", f"{where}: tray is not an object")]
    found: List[Finding] = []
    if not is_int(tray.get("id")):
        found.append(("must", f"{where}: tray id is not an integer"))
    if "spool_id" not in tray:
        found.append(("must", f"{where}: spool_id missing (null when the tray has no spool)"))
    elif tray["spool_id"] is not None and not is_int(tray["spool_id"]):
        found.append(("must", f"{where}: spool_id is not an integer or null"))
    color = tray.get("tray_color")
    if color not in (None, "") and not is_hex_color(color):
        found.append(("should", f"{where}: tray_color {color!r} is not RRGGBB or RRGGBBAA without '#'"))
    if "exists" in tray and not isinstance(tray["exists"], bool):
        found.append(("should", f"{where}: exists is not a boolean"))
    grams = tray.get("remain_g")
    if grams is not None and not is_number(grams):
        found.append(("should", f"{where}: remain_g is not a number or null"))
    return found


def _unit_findings(unit: Any, index: int) -> List[Finding]:
    where = f"ams[{index}]"
    if not isinstance(unit, dict):
        return [("must", f"{where}: unit is not an object")]
    found: List[Finding] = []
    if not is_int(unit.get("id")):
        found.append(("must", f"{where}: id is not an integer"))
    trays = unit.get("tray")
    if not isinstance(trays, list):
        found.append(("must", f"{where}: tray is not an array"))
        trays = []
    humidity = unit.get("humidity")
    if humidity is not None and not (is_number(humidity) and 0 <= humidity <= HUMIDITY_MAX_PERCENT):
        found.append(("should", f"{where}: humidity {humidity!r} is not a percentage or null"))
    temp = unit.get("temp")
    if temp is not None and not is_number(temp):
        found.append(("should", f"{where}: temp is not a number or null"))
    for t, tray in enumerate(trays):
        found += _tray_findings(tray, f"{where}.tray[{t}]")
    return found


def status_problems(doc: Any) -> List[Finding]:
    """Section 5: the shape of one printer's status."""
    if not isinstance(doc, dict):
        return [("must", "status is not a JSON object")]
    found: List[Finding] = []
    if not isinstance(doc.get("ams_exists"), bool):
        found.append(("must", "ams_exists is not a boolean"))
    units = doc.get("ams")
    if not isinstance(units, list):
        found.append(("must", "ams is not an array ([] without AMS)"))
        units = []
    for i, unit in enumerate(units):
        found += _unit_findings(unit, i)
    vt = doc.get("vt_tray")
    if vt is not None and not isinstance(vt, list):
        found.append(("should", "vt_tray is not an array"))
    for i, tray in enumerate(vt if isinstance(vt, list) else []):
        found += _tray_findings(tray, f"vt_tray[{i}]")
    if "tray_now" in doc and not is_int(doc["tray_now"]):
        found.append(("should", "tray_now is not an integer"))
    for hit in _forbidden_keys(doc):
        found.append(("must", f"field '{FORBIDDEN_KEY}' at {hit}: never send it, the scale derives feeding and assignment itself"))
    return found


def _trays(doc: Dict[str, Any]):
    """(ams_id, tray) for every tray in units and the external holder (ams_id 255)."""
    for unit in doc.get("ams") or []:
        if isinstance(unit, dict):
            for tray in unit.get("tray") or []:
                yield unit.get("id"), tray
    for tray in doc.get("vt_tray") or []:
        yield 255, tray


def tray_spool(doc: Any, ams_id: int, tray_id: int) -> Tuple[bool, Optional[int]]:
    """(tray found, spool_id in it) for one tray of a status answer."""
    if not isinstance(doc, dict):
        return False, None
    for unit_id, tray in _trays(doc):
        if isinstance(tray, dict) and unit_id == ams_id and tray.get("id") == tray_id:
            return True, tray.get("spool_id")
    return False, None


def spool_trays(doc: Any, spool_id: int) -> List[Tuple[int, int]]:
    """Every tray that claims the spool; more than one breaks section 6."""
    if not isinstance(doc, dict):
        return []
    return [(unit_id, tray.get("id")) for unit_id, tray in _trays(doc)
            if isinstance(tray, dict) and tray.get("spool_id") == spool_id]
