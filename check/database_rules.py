"""Pure judgments on a filament database and the create path (Part 1, 6.4 and 6.5).

Plain functions over parsed JSON: no network, no clock, no printing.
database_checks.py does the talking and asks these, tests/test_database_rules.py
pins them down. Section numbers refer to inventory/spec.md.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from inventory_rules import is_hex_color, is_int, is_number

# ("must" | "should", message)
Finding = Tuple[str, str]

# What the scale keeps of an entry, in bytes (section 6.4).
MAX_ID_BYTES = 79
MAX_MAKER_BYTES = 31
MAX_MATERIAL_BYTES = 16
MAX_NAME_BYTES = 95
MAX_LINE_BYTES = 24
SEARCH_PAGE_MAX = 100        # the scale never asks for more per page
DIAMETER_MM = 1.75           # the only diameter the scale lists


def _text(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _too_long(value: Any, limit: int) -> bool:
    return isinstance(value, str) and len(value.encode("utf-8")) > limit


def _same(a: Any, b: Any) -> bool:
    return isinstance(a, str) and isinstance(b, str) and a.strip().lower() == b.strip().lower()


def entry_problems(entry: Any) -> List[Finding]:
    """Section 6.4, the entry: four MUST texts, the rest typed when present."""
    if not isinstance(entry, dict):
        return [("must", "entry is not a JSON object")]
    found: List[Finding] = []
    found += _entry_text_findings(entry)
    found += _entry_number_findings(entry)
    found += _entry_colour_findings(entry)
    return found


def _entry_text_findings(entry: Dict[str, Any]) -> List[Finding]:
    found: List[Finding] = []
    limits = (("id", MAX_ID_BYTES), ("manufacturer", MAX_MAKER_BYTES),
              ("material", MAX_MATERIAL_BYTES), ("name", MAX_NAME_BYTES))
    for key, limit in limits:
        if not _text(entry.get(key)):
            found.append(("must", f"{key} is missing or not a non-empty string"))
        elif _too_long(entry.get(key), limit):
            found.append(("should", f"{key} longer than {limit} bytes is cut on the scale"))
    line = entry.get("line")
    if line is not None and not isinstance(line, str):
        found.append(("should", "line is not a string"))
    elif _too_long(line, MAX_LINE_BYTES):
        found.append(("should", f"line longer than {MAX_LINE_BYTES} bytes is cut on the scale"))
    return found


def _entry_number_findings(entry: Dict[str, Any]) -> List[Finding]:
    found: List[Finding] = []
    for key in ("diameter", "density", "weight", "spool_weight"):
        value = entry.get(key)
        if value is not None and not is_number(value):
            found.append(("should", f"{key} is not a JSON number (reads as 0 on the scale)"))
    for key in ("extruder_temp", "bed_temp"):
        value = entry.get(key)
        if value is not None and not is_int(value):
            found.append(("should", f"{key} is not an integer"))
    return found


def _entry_colour_findings(entry: Dict[str, Any]) -> List[Finding]:
    found: List[Finding] = []
    color = entry.get("color_hex")
    if color is not None and not is_hex_color(color):
        found.append(("should", f"color_hex {color!r} is not RRGGBB or AARRGGBB without '#'"))
    multi = entry.get("color_hexes")
    if multi is not None and (not isinstance(multi, list) or not all(is_hex_color(c) for c in multi)):
        found.append(("should", "color_hexes is not an array of RRGGBB"))
    if color is None and not multi:
        found.append(("should", "no colour: the entry is not listed on the scale"))
    return found


def entries_problems(doc: Any) -> List[Finding]:
    """An array of entries with unique ids, each well formed."""
    if not isinstance(doc, list):
        return [("must", "answer is not a JSON array")]
    found: List[Finding] = []
    ids = [e.get("id") for e in doc if isinstance(e, dict)]
    if len(set(ids)) != len(ids):
        found.append(("must", "entry ids are not unique"))
    for entry in doc:
        label = f"entry {entry.get('id') if isinstance(entry, dict) else '?'}: "
        found += [(level, label + msg) for level, msg in entry_problems(entry)]
    return found


def filtered_list_problems(doc: Any, manufacturer: str, material: str) -> List[Finding]:
    """Section 6.4, light form: the list holds that maker and material only."""
    found = entries_problems(doc)
    if not isinstance(doc, list):
        return found
    foreign = [e.get("id") for e in doc if isinstance(e, dict)
               and not (_same(e.get("manufacturer"), manufacturer) and _same(e.get("material"), material))]
    if foreign:
        found.append(("must", f"entries of another maker or material in the list: {foreign[:5]}"))
    if not doc:
        found.append(("must", "the list is empty although the index counts entries"))
    return found


def index_problems(doc: Any) -> List[Finding]:
    """Section 6.4, light form: makers with their materials, names unique."""
    if not isinstance(doc, list):
        return [("must", "answer is not a JSON array")]
    found: List[Finding] = []
    seen: List[str] = []
    for maker in doc:
        if not isinstance(maker, dict) or not _text(maker.get("name")):
            found.append(("must", "a maker has no name"))
            continue
        name = maker["name"].strip().lower()
        if name in seen:
            found.append(("must", f"maker {maker['name']!r} listed twice"))
        seen.append(name)
        found += _maker_findings(maker)
    if not doc:
        found.append(("must", "the index is empty"))
    return found


def _maker_findings(maker: Dict[str, Any]) -> List[Finding]:
    label = f"maker {maker['name']}: "
    found: List[Finding] = []
    materials = maker.get("materials")
    if not isinstance(materials, list) or not materials:
        return [("must", label + "materials is missing or empty")]
    for item in materials:
        if not isinstance(item, dict) or not _text(item.get("name")):
            found.append(("must", label + "a material has no name"))
        elif item.get("count") is not None and not is_int(item.get("count")):
            found.append(("should", label + f"count of {item['name']} is not an integer"))
    if maker.get("count") is not None and not is_int(maker.get("count")):
        found.append(("should", label + "count is not an integer"))
    return found


def pick_pair(index: Any) -> Optional[Tuple[str, str]]:
    """A maker and material to ask the list for: the first pair with entries."""
    for maker in index if isinstance(index, list) else []:
        if not isinstance(maker, dict) or not _text(maker.get("name")):
            continue
        for item in maker.get("materials") or []:
            if not isinstance(item, dict) or not _text(item.get("name")):
                continue
            count = item.get("count")
            if count is None or (is_int(count) and count > 0):
                return maker["name"], item["name"]
    return None


def search_page_problems(doc: Any, words: str, limit: int) -> List[Finding]:
    """Section 6.4, Spoolman form: at most limit hits, each carrying every word."""
    found = entries_problems(doc)
    if not isinstance(doc, list):
        return found
    if len(doc) > limit:
        found.append(("must", f"limit={limit} answered with {len(doc)} entries"))
    wanted = [w.lower() for w in words.split() if w]
    for entry in doc:
        if not isinstance(entry, dict):
            continue
        haystack = " ".join(str(entry.get(k) or "") for k in ("manufacturer", "name", "material")).lower()
        missing = [w for w in wanted if w not in haystack]
        if missing:
            found.append(("must", f"entry {entry.get('id')}: hit without the words {missing}"))
    return found


def offset_honoured(page_of_two: Any, page_at_one: Any) -> bool:
    """limit=2 gives [a, b]; limit=1&offset=1 must give [b]."""
    if not (isinstance(page_of_two, list) and isinstance(page_at_one, list)):
        return False
    if len(page_of_two) < 2:
        return True   # fewer than two hits: nothing to skip
    if len(page_at_one) != 1:
        return False
    return (page_at_one[0] or {}).get("id") == (page_of_two[1] or {}).get("id")


def material_list_problems(doc: Any) -> List[Finding]:
    """Section 6.4: every material has a name and a density."""
    if not isinstance(doc, list):
        return [("must", "answer is not a JSON array")]
    found: List[Finding] = []
    for item in doc:
        if not isinstance(item, dict) or not _text(item.get("material")):
            found.append(("must", "a material has no name"))
        elif not is_number(item.get("density")):
            found.append(("must", f"material {item['material']}: density is not a JSON number"))
    return found


def created_problems(answer: Any, sent: Dict[str, Any]) -> List[Finding]:
    """Section 6.5: a create answers the object with an integer id and the texts as sent."""
    if not isinstance(answer, dict):
        return [("must", "answer is not a JSON object")]
    found: List[Finding] = []
    if not is_int(answer.get("id")) or answer["id"] <= 0:
        found.append(("must", "id is missing or not a positive integer"))
    for key in ("name", "external_id", "article_number"):
        if key in sent and answer.get(key) != sent[key]:
            found.append(("must", f"{key} came back as {answer.get(key)!r}, sent {sent[key]!r}"))
    return found


def find_problems(hits: Any, wanted_id: Optional[int]) -> List[Finding]:
    """Section 6.5: a find answers an array; it holds the id, or nothing for an unknown value."""
    if not isinstance(hits, list):
        return [("must", "answer is not a JSON array (an empty find answers [])")]
    ids = [h.get("id") for h in hits if isinstance(h, dict)]
    if wanted_id is None and ids:
        return [("must", f"an unknown value matched {ids[:5]}")]
    if wanted_id is not None and wanted_id not in ids:
        return [("must", f"id {wanted_id} not among the hits {ids[:5]}")]
    return []
