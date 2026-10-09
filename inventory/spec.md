# Part 1: Inventory

**Contract version 1.** Describes firmware 0.8.2 and later, checked against
Spoolman 0.27.0. The [common rules](../common.md) apply throughout. Questions
and corrections: open an issue in this repository.

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

## 10. Versions and planned additions

Contract version 1. A change that breaks a server gets a new version and an
entry in the [changelog](../CHANGELOG.md); the scale keeps working against the
previous version for at least one firmware release.

**Planned, firmware 0.8.3 (in development, not released, no requirement level
yet).** The scale will create a spool from the data on a Bambu Lab tag or from
Spoolman's filament database when the tag is unknown. It then asks:

| Request | Purpose |
|---|---|
| `GET /api/v1/vendor?name=<exact>` | find the maker; `POST /api/v1/vendor` `{"name", "empty_spool_weight"}` creates it |
| `GET /api/v1/filament?<filter>` | find the filament by `article_number`, `external_id`, or vendor, material and colour |
| `POST /api/v1/filament` | create it: `name`, `vendor_id`, `material`, `density`, `diameter`, `color_hex`, and where known `weight`, `spool_weight`, `article_number`, `external_id`, `settings_extruder_temp`, `settings_bed_temp` |
| `GET /api/v1/external/filament/search?limit=N&query=<words>`, `GET /api/v1/external/material` | SpoolmanDB lookups for the product and the density |
| `POST /api/v1/spool` | as in 7.2 |

A server without the SpoolmanDB lookups answers `404` and the scale uses the
tag's own values. The exact filters and levels are fixed when 0.8.3 ships.
