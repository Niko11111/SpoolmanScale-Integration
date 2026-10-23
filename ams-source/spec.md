# Part 2: AMS source

**Status: draft.** This part describes a firmware feature that is not released
yet. Until the firmware that carries it ships, the draft can change without a
version bump; from then on the rules in [common.md](../common.md#parts-and-versions)
apply. The [common rules](../common.md) apply throughout. Questions and
corrections: open an issue in this repository.

Spoolman keeps filament, not printers. An **AMS source** is a server that
knows the printers and their AMS units: which tray holds which spool, what the
printer is doing, how humid the unit is. With one configured beside the
inventory, the scale shows the AMS view in Spoolman mode and lets the user
assign the spool on the scale to a tray. The source is the authority for the
assignment; the scale never writes it into the inventory itself.

The key words MUST, SHOULD and MAY are used as in RFC 2119. Sections marked
*informative* describe what the scale does; they are not requirements.

## 1. Overview

All paths start with `/api/v1/ams-source`. Answers carry no envelope such as
`{success, data}`: the HTTP status says whether it worked.

| Endpoint | Level | Section |
|---|---|---|
| `GET /api/v1/ams-source` | MUST | 2 |
| `GET .../printers` | MUST | 4 |
| `GET .../printers/{id}/status` | MUST | 5 |
| `POST .../printers/{id}/assign` | MUST with capability `assign` | 6 |
| `POST .../printers/{id}/unassign` | MUST with capability `unassign` | 7 |

The status answer has the shape Bambu Lab printers report over MQTT, which
servers with an AMS view already hand out. This version is deliberately that
dialect; a unit of another make MAY be reported in the same shape with its
own `module_type`.

- The address field on the scale holds **95 characters**, scheme and prefix
  included.
- The scale sends its key for this part as `X-API-Key` only.
- Spool ids are the ids of the inventory the scale uses (Part 1). The source
  MUST book against the same inventory, see section 2.

## 2. Discovery

`GET /api/v1/ams-source` -> `200`

```json
{
  "version": 1,
  "server": {"name": "OpenSpoolMan", "version": "2.1.0"},
  "capabilities": ["assign", "unassign", "sets_printer_filament"],
  "inventory": {"url": "http://spoolman.local:7912"}
}
```

| Field | Level | Meaning |
|---|---|---|
| `version` | MUST | the version of this part the server speaks, integer |
| `server.name`, `server.version` | SHOULD | shown to the user on the scale's backend page; name cut to 31 bytes, version to 15 |
| `capabilities` | MUST | array of strings, see below; `[]` for a source that only reads |
| `inventory.url` | MAY | base URL of the inventory the source books against, so the scale can warn when it is not the one it talks to |

| Capability | Meaning |
|---|---|
| `assign` | `POST .../assign` works. Without it the scale shows the AMS but offers no assignment. |
| `unassign` | `POST .../unassign` works. Without it the AMS detail card has no "take out" button. |
| `sets_printer_filament` | Assigning also sends the spool's material and colour to the printer. Informative for the user. |

Unknown capabilities MUST be ignored by the scale. A source that does not
answer this route is still read (the status route is all the view needs) but
is treated as read-only: nothing that writes is offered.

## 3. Ids

- **Printer ids** are integers from 1. They MUST stay the same across restarts
  of the server, because the scale remembers the printer the user picked. A
  server that knows printers by serial or entity id keeps its own table from
  that key to the number.
- **`ams_id`**, as the printer reports it:
  - `0` to `3`: a regular AMS, AMS 2 Pro or AMS Lite, four trays `0` to `3`.
  - `128` and up: an AMS HT, one tray, `tray_id` `0`.
  - `255`: the external holder (`vt_tray`). Its `tray_id` is whatever the
    printer reports, `254` on every model checked so far.
- **`tray_now`** is the printer's own number for the tray it feeds from:
  `ams_id * 4 + tray_id` for a regular AMS, the `ams_id` itself for an
  AMS HT, `254` for the external holder, `255` for nothing loaded.

## 4. Printers

`GET /api/v1/ams-source/printers` -> `200`

```json
[{"id": 1, "name": "X1C Workshop", "connected": true}]
```

- Every printer the server knows, connected or not. The scale reads up to 8.
- `name` is shown on the scale, cut to 23 bytes.

## 5. Status

`GET /api/v1/ams-source/printers/{id}/status` -> `200`, unknown id -> `404`.

```json
{
  "name": "X1C Workshop",
  "connected": true,
  "ams_exists": true,
  "tray_now": 1,
  "gcode_state": "RUNNING",
  "mc_percent": 42,
  "ams": [
    {
      "id": 0,
      "module_type": "n3f",
      "is_ams_ht": false,
      "humidity": 23,
      "temp": 27.4,
      "dry_status": 0,
      "dry_time": 0,
      "dry_target_temp": null,
      "tray": [
        {"id": 0, "tray_type": "PLA", "tray_sub_brands": "PLA Matte",
         "tray_color": "1A1A1AFF", "remain": 61, "exists": true,
         "spool_id": 12, "remain_g": 612},
        {"id": 1, "tray_type": "", "tray_sub_brands": "",
         "tray_color": "00000000", "remain": -1, "exists": false,
         "spool_id": null, "remain_g": null}
      ]
    }
  ],
  "vt_tray": [
    {"id": 254, "tray_type": "PETG", "tray_sub_brands": "",
     "tray_color": "FF6A00FF", "remain": -1, "exists": true,
     "spool_id": 31, "remain_g": 840}
  ]
}
```

**Printer fields**

| Field | Level | Meaning |
|---|---|---|
| `name` | SHOULD | as in section 4 |
| `connected` | SHOULD | the server's link to the printer is up. Absent means unknown. |
| `ams_exists` | MUST | at least one AMS unit is attached |
| `tray_now` | SHOULD | section 3; absent reads as `255` |
| `gcode_state` | MAY | the printer's state word, e.g. `IDLE`, `RUNNING`, `PAUSE`, `FINISH`, `FAILED`; cut to 15 bytes |
| `mc_percent` | MAY | job progress 0 to 100 |
| `ams` | MUST | array of units, `[]` without AMS. The scale reads up to 4. |
| `vt_tray` | SHOULD | array of external holder trays. The scale reads up to 2. |

**Unit fields** (`ams[]`)

| Field | Level | Meaning |
|---|---|---|
| `id` | MUST | `ams_id`, section 3 |
| `tray` | MUST | array of trays, up to 4 |
| `module_type` | SHOULD | the printer's module code: `ams`, `n3f` (AMS 2 Pro), `n3s` (AMS HT), `ams_lite`; empty if unknown |
| `is_ams_ht` | MAY | the scale also infers it from `id` >= 128 or `module_type` `n3s` |
| `humidity` | SHOULD | relative humidity in **percent**, or `null`. Never Bambu's 1-to-5 humidity index: it runs the other way round (high means dry). `null` on an AMS Lite, which has no sensor. |
| `temp` | SHOULD | °C as a number, or `null`; `null` on an AMS Lite |
| `dry_status` | MAY | the printer's drying state; 1 to 4 mean a cycle is running |
| `dry_time` | MAY | minutes left in a drying cycle, `0` when none |
| `dry_target_temp` | MAY | °C of the running cycle |

**Tray fields** (`ams[].tray[]` and `vt_tray[]`)

| Field | Level | Meaning |
|---|---|---|
| `id` | MUST | `tray_id`, section 3 |
| `exists` | SHOULD | a spool is physically in the tray. Bambu reports it in `tray_exist_bits`. Absent: a tray with a `tray_type` counts as filled. |
| `tray_type` | SHOULD | material as the printer knows it, e.g. `PLA` |
| `tray_sub_brands` | MAY | product name, e.g. `PLA Matte`; shown instead of the material, cut to 19 bytes |
| `tray_color` | SHOULD | `RRGGBB` or `RRGGBBAA`, no `#`. `00000000` with a `tray_type` means a clear filament, without one it means no colour. Empty is fine for no colour. |
| `remain` | MAY | percent left as the printer estimates it, `-1` for unknown |
| `spool_id` | MUST | the spool assigned to this tray, or `null` |
| `remain_g` | SHOULD | net grams left on that spool, from the inventory, or `null` |

Rules:

- **Do not send `active`.** Servers use the word for different things
  ("assigned" or "feeding now"). The scale derives the feeding tray from
  `tray_now` and the assignment from `spool_id`.
- **`spool_id` is the server's assignment**, not a guess from the tray's
  colour or material. It MUST reflect an `assign` or `unassign` on the next
  status request.
- Fields the scale does not read (`tray_uuid`, `k`, nozzle temperatures, a
  top-level `version` or `id`, ...) MAY be sent and are ignored.

## 6. Assign

`POST /api/v1/ams-source/printers/{id}/assign`

```json
{"spool_id": 12, "ams_id": 0, "tray_id": 1}
```

-> `200`

```json
{"printer_id": 1, "ams_id": 0, "tray_id": 1, "spool_id": 12}
```

- **One spool per tray.** A spool assigned to this tray before MUST be
  released.
- **One tray per spool.** If spool 12 was assigned to another tray, that
  assignment MUST end.
- Assigning the spool that is already there is a success.
- The tray MAY be empty. The user often assigns before loading.
- With `sets_printer_filament` (section 2) the server also sends material
  and colour to the printer.

## 7. Unassign

`POST /api/v1/ams-source/printers/{id}/unassign`

```json
{"ams_id": 0, "tray_id": 1}
```

-> `200`

```json
{"printer_id": 1, "ams_id": 0, "tray_id": 1, "spool_id": 12}
```

- `spool_id` is the spool that was released, `null` if the tray had none. An
  empty tray is not an error.

## 8. Errors

Every answer other than `200` SHOULD carry a short English sentence for the
log:

```json
{"error": "Printer 3 not found"}
```

| Status | When | The scale says |
|---|---|---|
| `400` | body missing a field, or a field of the wrong type | assignment failed |
| `401` / `403` | key wrong or missing | key rejected |
| `403` | the server is in a read-only mode and refuses writes | the server refuses the assignment |
| `404` | unknown printer, unknown spool, or a tray the printer does not have | printer, spool or bay unknown |
| `502` | the inventory behind the server did not answer | the inventory is not answering the server |
| `503` | the server has no link to the printer and cannot assign now | printer offline |

The scale shows its own translated sentence per code and never the `error`
text.

## 9. Scale behaviour (informative)

| Request | When | Timeout |
|---|---|---|
| discovery | once per address, before the first printer list | 5 s |
| printers, status | once after boot (about 20 s), then every 5 min, to know whether to offer the AMS view | 5 s |
| printers, status | when the user opens the AMS view or the tray picker | 8 s |
| assign, unassign | when the user picks a tray, or taps "take out" on a tray's card | 8 s |

- No polling while the AMS view is idle on screen.
- Writes are not retried.
- The scale reads with a filter: fields it does not know cost bandwidth, not
  memory.
- After an assignment the scale MAY also set the spool's `location` in the
  inventory to the unit's name ("X1C AMS 1"), when the user switched that on.
  That is a Part 1 write, not a request to the source.
- After taking a spool out, the scale offers the location list. Closed without
  a choice, it clears a location that still names the unit
  (`{"location": null}`, Part 1); a location the user named stays.

## 10. Checklist

`check/check_ams_source.py` in this repository runs this list against a server.

1. `GET /api/v1/ams-source` -> `200`, `version` is `1`, `capabilities` is an
   array of strings
2. `GET .../printers` -> array, ids from 1; same ids after a server restart
3. `GET .../printers/99/status` -> `404`
4. `GET .../printers/1/status` -> `ams` array, `humidity` in percent or
   `null`, every tray has `spool_id`, no `active` field anywhere
5. assign spool A to tray 0/0 -> `200`; status shows `spool_id` A at 0/0
6. assign spool B to tray 0/0 -> `200`; A is no longer in any tray
7. assign spool B to tray 0/1 -> `200`; 0/0 is empty, B is at 0/1 only
8. unassign 0/1 -> `200` with `spool_id` B; unassign 0/1 again -> `200` with
   `null`
9. assign with an unknown spool id -> `404`
10. with a key configured: any request without it -> `401` or `403`

## 11. Planned, not part of version 1

These may come as capabilities, so a version 1 server keeps working:

- `GET .../spools/{id}/slot`: which tray holds a spool, without reading every
  printer's status.
- `ETag` on status, answered with `304` while nothing changed.
- A flag on `assign` to leave the printer's filament setting untouched.
- The last job's consumption per spool, once the server books usage.
