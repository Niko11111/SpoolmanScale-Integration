# Part 1: Inventory

**Contract version 1.** Describes firmware 0.8.2 and later, checked against
Spoolman 0.27.0; sections 6.4 and 6.5 joined with firmware 0.8.3. The
[common rules](../common.md) apply throughout. Questions and corrections: open
an issue in this repository.

SpoolmanScale is a filament scale with an NFC reader. In Spoolman mode it talks
to a server over the Spoolman REST API. This page lists exactly what it uses,
so another inventory system can serve the scale by speaking the same subset.
The user picks the Spoolman backend on the scale, enters your base URL and, if
your server needs one, a key.

The key words MUST, SHOULD and MAY are used as in RFC 2119. Sections marked
*informative* describe what the scale does; they are not requirements.

## 1. Minimum viable server

| Endpoint | Level | Section |
|---|---|---|
| `GET /api/v1/health` | MUST | 4.1 |
| `GET /api/v1/info` | MUST | 4.1 |
| `GET /api/v1/spool` (list) | MUST | 4.2 |
| `GET /api/v1/spool/{id}` | MUST | 4.3 |
| `PATCH /api/v1/spool/{id}` | MUST | 4.5 |
| `GET /api/v1/field/spool` | MUST (may return `[]`) | 4.6 |
| tag lookup: native tags **or** extra field `tag` | MUST, one of the two | 5 |
| `PUT /api/v1/spool/{id}/measure` | SHOULD | 6.1 |
| `limit`, `sort=id:desc`, `x-total-count` on the list | SHOULD | 6.2 |
| `GET /api/v1/location` | SHOULD | 6.3 |
| everything in 7 | MAY | 7 |

Native tags (5.1) are the recommended way. A server built on them needs no
extra fields for tag lookup.

## 2. Transport and authentication: this part

In addition to the [common rules](../common.md):

- The address field on the scale holds **79 characters**, scheme and prefix
  included.
- The scale offers all three forms of access for this part: `X-API-Key`,
  `Authorization: Bearer`, and HTTP Basic (user and password, for a Spoolman
  behind a proxy).
- With a wrong or missing key the server MUST answer `401` or `403` on every
  endpoint, the probes in 4.6 and 5.1 included. Only `/api/v1/health` MAY
  answer without a key.

## 3. General rules: this part

- **Types.** `archived` is a JSON boolean; weights are JSON numbers (integer or
  decimal).
- **Nulls in answers.** A field whose value is null MAY be omitted, except
  where section 4.4 says it MUST be present.
- **Nulls in PATCH bodies.** An explicit `null` clears the field. A key that is
  absent leaves the field unchanged.
- **Dates.** Return ISO 8601 in UTC with `Z`, e.g. `2026-10-01T12:34:56Z`.
  Fractional seconds are fine. Accept the same on input.
- **Status codes.** A GET succeeds only with `200`. Writes SHOULD answer `200`
  with the updated object; `201` is allowed on create. Several write paths on
  the scale accept exactly `200`, so do not answer `204`.
- **Error bodies** are ignored, except the `409` in 5.1. Any content type is
  fine.

## 4. Core

### 4.1 Health and info

`GET /api/v1/health` -> `200`, body ignored. Anything else shows the server as
unreachable.

`GET /api/v1/info` -> `200`

```json
{"version": "1.40.0"}
```

`version` is displayed only. You MAY add fields.

### 4.2 Spool list

`GET /api/v1/spool?allow_archived=false` returns active spools.
`GET /api/v1/spool?allow_archived=true` returns **all** spools, active and
archived.

- The answer MUST be one JSON array of spool objects (4.4) holding **every**
  matching spool when no `limit` is given. The scale does not page. A server
  that pages by default hides spools, and the scale then offers to link or
  create a spool that already exists.
- Order does not matter.

### 4.3 Single spool

`GET /api/v1/spool/{id}` -> `200` with one spool object, archived spools
included; `404` if the id does not exist.

### 4.4 The spool object

Fields the scale reads. Everything else is ignored.

| Field | Level | Meaning |
|---|---|---|
| `id` | MUST | integer |
| `archived` | MUST | boolean |
| `extra` | MUST | object, `{}` when empty (section 7.1) |
| `tags` | MUST with native tags | array, `[]` when empty (section 5.1) |
| `remaining_weight` | SHOULD | net grams of filament on the spool now; omit or null if never weighed |
| `initial_weight` | SHOULD | net grams on a full spool |
| `spool_weight` | SHOULD | grams of the empty spool (tare) |
| `last_used`, `first_used`, `registered` | MAY | date; `first_used`/`registered` are printed on labels |
| `location` | MAY | string, 47 bytes or less; omit or null for none |
| `filament` | MUST | object, fields below |
| `filament.id` | MUST | integer |
| `filament.name` | SHOULD | string |
| `filament.material` | SHOULD | string, e.g. `PLA`, `PETG` |
| `filament.weight` | SHOULD | net grams on a full spool of this type |
| `filament.spool_weight` | MAY | tare, second choice |
| `filament.color_hex` | SHOULD | `RRGGBB` or `RRGGBBAA`, **no `#`** |
| `filament.article_number` | MAY | string |
| `filament.extra` | MAY | object |
| `filament.vendor` | MAY | object: `id` (integer), `name`, `empty_spool_weight` (tare, third choice) |

**Minimal spool object:**

```json
{
  "id": 12,
  "archived": false,
  "remaining_weight": 612,
  "initial_weight": 1000,
  "spool_weight": 196,
  "extra": {},
  "tags": [{"uid": "04A1B2C3D4E5F6"}],
  "filament": {"id": 3, "name": "Matte Black", "material": "PLA",
               "weight": 1000, "color_hex": "1A1A1A",
               "vendor": {"id": 1, "name": "Bambu Lab"}}
}
```

Rules behind the fields:

- **Weights.** `remaining_weight` MUST read back exactly as the scale last
  wrote it, until something else changes it. Do not derive it from consumption
  the scale does not know about.
- **Tare.** The scale uses `spool_weight`, else `filament.spool_weight`, else
  `filament.vendor.empty_spool_weight`. A value of 0 counts as unset; with none
  set, the tare is 0.
- **Full weight.** `initial_weight`, else `filament.weight`, else 1000 g.
- A vendor name starting with "Bambu" (any case) turns on the scale's matching
  against Bambu Lab's own tags.

### 4.5 Writing a spool

`PATCH /api/v1/spool/{id}` -> `200` with the updated spool. The scale sends
these bodies; accept any combination of their keys. Weights are sent as whole
grams.

```json
{"remaining_weight": 612}
{"remaining_weight": 612, "last_used": "2026-10-01"}
{"initial_weight": 1000, "remaining_weight": 1000}
{"spool_weight": 196}
{"remaining_weight": 0.0, "archived": true}
{"archived": false, "remaining_weight": 540}
{"location": "Shelf A"}
{"location": null}
{"extra": {"last_dried": "\"2026-10-01T12:34:56.000Z\""}}
```

- `last_used` can arrive as a date without a time (this will change to a full
  UTC time). Store it as midnight UTC.
- `remaining_weight` above `initial_weight`: treat the spool as full.
  A negative value is never sent.
- `extra` is **merged per key**. Keys not in the body stay as they are. The
  scale clears a value by sending `"\"\""`, never `null`.

### 4.6 Field list

`GET /api/v1/field/spool` MUST answer `200` with an array, `[]` if you have no
extra fields:

```json
[{"key": "last_dried", "name": "Last dried", "field_type": "text"}]
```

The scale asks for it during tag lookups and caches only a `200`. Without it,
a lookup that misses costs about four failed requests, a Bambu one about seven.

## 5. Finding a spool by its tag

The scale identifies a spool by the UID of its NFC chip. Bambu Lab spools also
carry a tray UUID in their tag data, shared by both chips of the spool.

UIDs as the scale sends them:

| Kind | Example |
|---|---|
| 4-byte chip | `A1:B2:C3:D4` |
| 7-byte chip | `04:A1:B2:C3:D4:E5:F6` |
| Bambu tray UUID | 32 hex digits, no separators |

The server MUST normalise before storing and comparing: remove every character
that is not a hex digit, then uppercase. The scale compares the same way, so any
spelling you return works. 64 characters are enough for every UID.

### 5.1 Native tags (recommended)

**Probe.** `GET /api/v1/tag/reader` MUST answer `200` (any body, e.g. `[]`) if
you implement this section and `404` if you do not. The scale caches `200` and
`404` per server; any other answer is asked again on the next lookup.

**Scan.** `POST /api/v1/tag/scan`

```json
{"uid": "04:A1:B2:C3:D4:E5:F6", "reader_id": "spoolmanscale-3FA2C1",
 "name": "scale", "format": "ntag"}
```

Only `uid` is required; the rest identifies the scale and MAY be ignored.
Answer `200` in every case, never `404`:

```json
{"matched_spool_id": 12, "spool": { ... full spool object ... }}
```

```json
{"matched_spool_id": null}
```

- The match includes archived spools. The scale shows the spool as archived,
  and the user can bring it back from there.
- Embedding `spool` SHOULD be done; without it the scale needs one more
  `GET /api/v1/spool/{id}`.
- A scan MUST NOT change stored data. Logging it is fine.

**Search.** `GET /api/v1/spool?allow_archived=false&tag=<uid>` -> array with the
one active spool holding the tag, or `[]`. The UID is URL-encoded
(`04%3AA1%3A...`).

**Link.** `POST /api/v1/spool/{id}/tag`

```json
{"uid": "04:A1:B2:C3:D4:E5:F6", "format": "ntag"}
```

- `2xx` when linked, also when the tag was already on this spool.
- `409` when another spool holds it, with that spool's id at top level:
  ```json
  {"message": "Tag 04A1B2C3D4E5F6 is already linked to spool 7.", "spool_id": 7}
  ```
  The scale then asks the user whether to move the tag.
- `format` is informational: `ntag` for most tags, `bambu` for both the chip
  UID and the tray UUID of a Bambu spool. Accept unknown values.
- A spool can hold several tags.

**Unlink.** `DELETE /api/v1/spool/{id}/tag/{uid}` -> `2xx`. When the tag was
not on this spool, `404` is fine. The UID in the path may be spelled
differently from the one stored.

**Spool objects** MUST list their tags in `tags`, e.g.
`[{"uid": "04A1B2C3D4E5F6", "format": "ntag"}]`. When a spool is found but the
tag on the reader is missing from `tags`, the scale links it again on every
placement.

### 5.2 Tag in an extra field (fallback)

If `/tag/reader` answers `404`, the scale stores the UID in the text extra field
`tag` as plain uppercase hex (`"\"04A1B2C3D4E5F6\""`), one per spool, and
searches with `GET /api/v1/spool?allow_archived=false&extra.tag=04A1B2C3D4E5F6`
(the raw value, not JSON-quoted). A substring or exact match are both fine; the
scale checks every hit itself. If the parameter is ignored and the whole list
comes back, it still works, only slower. This needs the extra fields of
section 7.1.

## 6. Recommended

### 6.1 Measure

`PUT /api/v1/spool/{id}/measure`

```json
{"weight": 1196}
```

`weight` is the gross weight on the scale in grams: spool plus filament. The
server subtracts the tare (4.4), stores the net weight as `remaining_weight`,
sets `last_used`, and answers `200` with the spool.

- The server MUST subtract exactly the tare it reports for the spool, or the
  scale and the server show different weights.
- A spool whose gross weight exceeds initial weight plus tare: treat the net
  weight as the new `initial_weight`.
- Not implemented: answer `404` or `405`. The scale then sends the net weight as
  a PATCH (4.5). Any other error means the weight was not saved and the user
  sees an error.
- The scale also uses the PATCH when the tare came from the vendor.

### 6.2 List stamp

`GET /api/v1/spool?allow_archived=false&limit=1&sort=id:desc`

- Header `x-total-count`: number of active spools, ignoring `limit`.
- Body: one spool, the one with the highest id.

Before showing a spool list the scale asks this, with 2 s to connect and 2 s
for the first bytes. If count and highest id did not change, it reuses its
cached list. Honour `limit` even without the header. A slow answer makes the
link and copy screens report the server as down.

`GET /api/v1/spool?allow_archived=false&limit=1` (no sort) is also sent, from
the connection screen, for the count alone.

### 6.3 Locations

`GET /api/v1/location` -> array of strings, e.g. `["Shelf A", "Dry box"]`. The
scale sets a location by picking from this list.

### 6.4 Filament database

*Firmware 0.8.3 and later.*

A spool without a maker's chip gets its filament from the server's filament
database: the user picks maker, material, product line and colour on the
scale, the scale fills a new filament from the entry and books the spool under
it (6.5). The same database completes what a Bambu Lab tag does not say. A
server SHOULD offer one. Without it the "New from database" tile does not
appear, and a Bambu Lab tag is created from the tag's own values.

The scale needs three things from a database: an index of makers and their
materials, every entry of one maker and material, and the entries that could
match a tag. Two forms deliver them. A server offers one of them. Spoolman
0.27 offers the first; a server with a catalogue of its own finds the second
cheaper, since it needs no copy of the whole database and no word search.

| The scale needs | Spoolman form | Light form |
|---|---|---|
| index of makers and materials | `GET /api/v1/external/filament`, the whole database, read once a week; the scale keeps makers and materials | `GET /api/v1/external/manufacturer?diameter=1.75`, one small answer |
| entries of one maker and material | `GET /api/v1/external/filament/search?query=<maker material>&limit=100&offset=N`, pages | `GET /api/v1/external/filament?manufacturer=<name>&material=<name>&diameter=1.75` |
| entries for a tag | the search, with product line or colour name as words | the same filtered list; the scale compares locally |
| density of a material | `GET /api/v1/external/material` | `GET /api/v1/external/material`, optional |

**Discovery.** Once per address, and again after a change of address or
backend:

1. `GET /api/v1/external/manufacturer` -> `200`: light form.
2. else `GET /api/v1/external/filament/search?limit=1&query=PLA` -> `200`:
   Spoolman form.
3. else no database. A server without one MUST answer `404` (or `405`) on
   both. Any other failure is treated as temporary and asked again later.

**Spoolman form**, as Spoolman 0.27.0 serves it:

- `GET /api/v1/external/filament` -> array of every entry. It MAY be large
  (SpoolmanDB: 8120 entries, 3 MB); chunked transfer is fine. The scale reads
  it in one pass and keeps only `manufacturer`, `material`, `name` and
  `diameter`.
- `GET /api/v1/external/filament/search?query=<words>&limit=N&offset=M` ->
  array of entries. Every word of `query` MUST match in `manufacturer`, `name`
  or `material`, case-insensitive (all words, in any field); `limit` up to 100
  and `offset` MUST be honoured. The scale asks 100 at a time, at most 20
  pages, and filters the hits to the exact maker and material itself.
- `GET /api/v1/external/material` -> array of
  `{"material": "PLA", "density": 1.24, "extruder_temp": 210, "bed_temp": 50}`.
  The scale asks it for a density when no entry of the material has one.

**Light form:**

- `GET /api/v1/external/manufacturer` -> array, one object per maker:

  ```json
  [{"name": "Polymaker", "count": 444,
    "materials": [{"name": "PLA", "count": 224}, {"name": "ABS", "count": 31}]}]
  ```

  `name` MUST be unique and spelled as the entries spell `manufacturer`;
  `materials[].name` as the entries spell `material`. `count` SHOULD be the
  number of entries the list below returns. With `diameter=1.75` a server
  SHOULD leave out the other diameters; one that ignores the parameter still
  works, the scale filters.
- `GET /api/v1/external/filament?manufacturer=<name>&material=<name>` -> array
  of every entry of that maker and material, complete, in one answer. The
  server MUST filter by both, exact and case-insensitive, and SHOULD honour
  `diameter`. One maker's material rarely has more than a few hundred entries.
- `GET /api/v1/external/material` MAY exist. Without it, an entry without a
  density takes the density of another entry of the same material in the list;
  without any, the scale does not create the filament (the inventory requires
  a density, 6.5).

**The entry**, in both forms, with the levels the scale needs:

| Field | Level | Content |
|---|---|---|
| `id` | MUST | string, unique and stable, up to 79 bytes; the scale stores it as the filament's `external_id` (6.5) |
| `manufacturer` | MUST | the maker, spelled as the index spells it, up to 31 bytes |
| `material` | MUST | `PLA`, `PETG`, as the index spells it, up to 16 bytes |
| `name` | MUST | product line and colour, without maker and material: `Panchroma Luminous Blue`, `Tough+ Cyan`; up to 95 bytes |
| `color_hex` | SHOULD | `RRGGBB`, or `AARRGGBB` for a see-through colour, no `#`. An entry without a colour is not listed |
| `diameter` | SHOULD | mm; absent reads as 1.75. The scale lists 1.75 mm only |
| `density` | SHOULD | g/cm³ |
| `weight` | SHOULD | net grams on a full spool. One entry per weight a product is sold in; the scale asks which |
| `spool_weight` | SHOULD | the empty spool in grams; absent or 0 means unknown, and the spool counts as full when weighed (4.4) |
| `extruder_temp`, `bed_temp` | SHOULD | °C, integers |
| `color_hexes`, `multi_color_direction` | MAY | two or more `RRGGBB` for a gradient or dual colour spool; `coaxial` is side by side, `longitudinal` along the filament |
| `line` | MAY | the product line on its own: `Matte`, `PolyTerra`, up to 24 bytes. With two or more lines in a list the scale asks for the line first and shows a name without its leading line |
| anything else | ignored | `translucent`, `glow`, `finish`, `pattern`, `spool_type` cost bandwidth only |

The scale keeps at least 400 makers, 640 pairs of maker and material and 600
entries per list; beyond that it cuts in the order received, so order a list
by name. Text is cut at the byte counts above, on character boundaries. The
database's spelling is kept on the server; trademark signs and a "(Formerly
...)" note are hidden on the screen only.

A reference of the light form:
[`examples/light_form_proxy.py`](../examples/light_form_proxy.py) serves it
from a list of entries in front of any inventory server, and passes the
checker.

### 6.5 Creating a filament and its spool

*Firmware 0.8.3 and later.*

When the scale creates a spool, from a Bambu Lab tag or from the database
(6.4), it finds or creates the maker and the filament first, then books the
spool and links the tag (5). A server SHOULD offer this. Without it the user
confirms the new spool and then sees the server refuse it.

In order, each `200` (or `201` on a create) with the object, `id` included:

| Step | Request |
|---|---|
| find the maker | `GET /api/v1/vendor?name="<exact>"` -> array. The scale compares `name` itself, case-insensitive, so a partial match is harmless |
| create the maker | `POST /api/v1/vendor` `{"name": "Polymaker", "empty_spool_weight": 140}` (the weight only when known) |
| find the filament, first hit wins, lowest `id` | `GET /api/v1/filament?article_number="<exact>"` for a tag with one, among the hits the maker's; `GET /api/v1/filament?external_id="<id>"` for a database entry; else `GET /api/v1/filament?vendor.name="<exact>"&material="<exact>"`, with `&color_hex=RRGGBB&color_similarity_threshold=0` for a single colour, and the scale compares name and colours itself |
| create the filament | `POST /api/v1/filament` with `name`, `vendor_id`, `material`, `density`, `diameter`, and `color_hex` or `multi_color_hexes` (comma list) with `multi_color_direction`; where known `weight`, `spool_weight`, `article_number`, `external_id`, `settings_extruder_temp`, `settings_bed_temp` |
| create the spool | `POST /api/v1/spool` as in 7.2, with `filament_id` |

- `density` and `diameter` are always sent: Spoolman requires them. Without a
  density from tag, database or material list the scale does not create the
  filament.
- A server MUST store `article_number` and `external_id` as given and filter
  by them exactly: that is how the scale avoids a second filament for the same
  product. A find answers `200` with `[]` when nothing matches, never `404`.
- The quotes in `?name="..."` ask Spoolman for an exact match. A server that
  does not know the quoting matches the bare text; the scale compares anyway.
- `GET /api/v1/vendor` without a filter is also read, to list the makers the
  inventory already has first. Without it only that order is lost.

## 7. Optional

### 7.1 Extra fields

- Values are **JSON-encoded strings**: the text `abc` travels as `"\"abc\""`.
  This is a Spoolman convention, kept for compatibility.
- Keys are lowercase `[a-z0-9_]`.
- A server either answers **`400`** to a PATCH with an unknown key and
  implements `POST /api/v1/field/spool/{key}`, or accepts any key and lists the
  keys it holds in `GET /api/v1/field/spool`.
- Create: `POST /api/v1/field/spool/{key}` and
  `POST /api/v1/field/filament/{key}` with
  `{"name": "Drying", "field_type": "text", "default_value": "\"\""}` ->
  `200` or `201`.

Fields the scale uses:

| Key | On | Content | When |
|---|---|---|---|
| `last_dried` | spool | ISO 8601 UTC | user logs a drying |
| `tag` | spool | plain hex UID or tray UUID | 5.2, or as a copy of the tray UUID for OpenSpoolman (switch) |
| `nfc_id`, `card_uids` | spool | hex UID, or comma list | only if the user picked them as tag field |
| `rfid_tag` | spool | comma list of hex chip UIDs | Happy Hare MMU gates (switch) |
| `drying` | filament | text such as `55 °C, 8 h` | from Bambu tags |

The scale creates its spool fields before the first write when the field list
does not have them. The filament field `drying` it creates after a `400` and
retries once. The scale also reads other text fields of a spool (up to 16) as
possible tag UIDs.

### 7.2 More writes

| Feature on the scale | Request | Answer |
|---|---|---|
| copy a spool | `POST /api/v1/spool` `{"filament_id": 3, "initial_weight": 1000, "spool_weight": 196, "remaining_weight": 850}` | `200` or `201` with the full spool, `id` included |
| tare on the filament | `PATCH /api/v1/filament/{id}` `{"spool_weight": 196}` | `200` |
| tare on the vendor | `PATCH /api/v1/vendor/{id}` `{"empty_spool_weight": 196}` | `200` |
| drying advice | `PATCH /api/v1/filament/{id}` `{"extra": {"drying": "\"55 °C, 8 h\""}}` | `200` |

Without them, answer `404`. The user sees the copy or the tare fail; the
drying advice is written in the background and only logged.

### 7.3 Spool page link

The scale links to `<base>/spool/show/{id}`, also in the QR code on printed
labels. Serve that page or a redirect to your own spool page; a redirect is
fine here, outside `/api/v1`. A per-server pattern is planned.

## 8. Scale behaviour (informative)

**Timeouts.** Connect about 5 s, then the time below without data:

| Request | Time |
|---|---|
| health, info | 3 s |
| list during a tag lookup | 20 s, two attempts |
| list for link / copy / archive screens | 8 s / 10 s / 8 s |
| single spool, scan, location list | 8 s |
| PATCH, measure, tag link | 5 s |
| stamp | 2 s connect, 2 s |

**Retries.** Writes are not retried, except linking a tag right after writing
it (once). Reads of the lookup list get two attempts.

**Load.**

- Every 30 s: `GET /api/v1/health`.
- Per tag placed on the reader: `POST /tag/scan`, then `?tag=` and
  `?extra.<field>=` if needed. The full list only if all of them miss and the
  scale has no recent proof that the tag is unknown.
- After a spool is found, possibly: a tag link, a copy of the tray UUID into
  `extra.tag`, `rfid_tag`, the filament's `drying`. Each only when missing.
- While an unknown tag lies on the reader: one or two small searches every 4 s,
  backing off to 60 s while the server does not answer.
- Once after linking: the same scan again after 3.5 s.
- No background polling of the list.

**Caching.** The scale keeps the active list for up to 30 min while the stamp
(6.2) agrees, 2 min without one, and only up to 1000 spools; above that nothing
is cached and every list is downloaded. The cache fills screens; before
anything is written to a spool the scale reads that spool again.

**Size.** About 650 bytes per spool with a full Spoolman object. The scale
filters while reading, so extra fields it does not need cost bandwidth, not
memory.

**Database (6.4).** The form is probed when the picker is first opened or a
tag needs the database, and remembered until the address or backend changes.
The index stays in RAM for a day; in the Spoolman form it is also kept in
flash for a week, bound to the address, so the whole list is read once a week
at most. The light form's index is read on each day's first opening. A list of
entries is loaded when its maker and material are picked and dropped when the
picker closes. Reads give the server 15 s per chunk; the whole list on a slow
link takes as long as it takes. Makers the inventory already has
(`GET /api/v1/vendor`) are listed first; that is asked on every index load.

## 9. Checklist

`check/check_inventory.py` in this repository runs this list against a server
(see the [README](../README.md)).

MUST:

1. `GET /api/v1/health` -> `200`
2. `GET /api/v1/spool?allow_archived=false` -> every active spool, each with
   `id`, `archived`, `extra`, `filament.id`
3. `GET /api/v1/spool?allow_archived=true` -> also the archived ones
4. `GET /api/v1/spool/{id}` -> `200`; unknown id -> `404`
5. `PATCH /api/v1/spool/{id}` `{"remaining_weight": 500}` -> `200`, then a GET
   shows 500
6. `PATCH /api/v1/spool/{id}` `{"location": null}` -> `200`, location gone
7. `GET /api/v1/field/spool` -> `200` and an array
8. `GET /api/v1/tag/reader` -> `200` or `404`
9. with native tags: link `04:A1:B2:C3:D4:E5:F6` to a spool -> `2xx`; scan
   `04a1b2c3d4e5f6` -> `200` with that spool; link it to another spool -> `409`
   with `spool_id`; scan an unknown uid -> `200` with `matched_spool_id: null`
10. with a key configured: any request without it -> `401` or `403`
11. nothing under `/api/v1/` answers with a redirect

SHOULD:

12. `PUT /api/v1/spool/{id}/measure` `{"weight": 1196}` -> `200`, remaining is
    1196 minus the reported tare; or `404`/`405`
13. `GET /api/v1/spool?allow_archived=false&limit=1&sort=id:desc` -> one spool
    and `x-total-count`
14. `GET /api/v1/location` -> array of strings
15. filament database (6.4): `GET /api/v1/external/manufacturer` -> `200`
    with a well formed index, and `GET /api/v1/external/filament?manufacturer=
    <name>&material=<name>` -> entries of exactly that maker and material;
    or the search probe -> `200`, a page of at most 100 entries that all carry
    the words, and the whole list; or `404` on both. Every entry well formed
16. `GET /api/v1/external/material` -> array with `material` and `density`,
    or `404`
17. with `--write` (6.5): `POST /api/v1/vendor` -> `id`;
    `GET /api/v1/vendor?name="<exact>"` finds it; `POST /api/v1/filament` with
    `external_id` and `article_number` -> `id`; `GET /api/v1/filament?
    external_id="..."` and `?article_number="..."` find it, an unknown value
    gives `[]`; `POST /api/v1/spool` -> `id`; then the three are deleted
    again. Without `DELETE` routes the checker names what it left behind

## 10. Versions and planned additions

Contract version 1. A change that breaks a server gets a new version and an
entry in the [changelog](../CHANGELOG.md); the scale keeps working against the
previous version for at least one firmware release.

Sections 6.4 and 6.5 joined with firmware 0.8.3. Everything in them is optional
for a server, so the version stayed 1: a server written for the first
publication keeps working, only without the new spools.
