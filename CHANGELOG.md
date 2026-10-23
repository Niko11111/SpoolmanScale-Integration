# Changelog

One entry per part and version. The date is the day the text was published
here. A version changes only when an existing server would break; new
optional fields, endpoints and capabilities are listed under the version they
joined.

## Part 1: Inventory

### Version 1 (2026-10-08)

- First published version. Describes firmware 0.8.2 and later, checked
  against Spoolman 0.27.0.
- 2026-10-09, firmware 0.8.3: section 6.4, the filament database in two
  forms (Spoolman's whole list and search, or the light form with
  `GET /api/v1/external/manufacturer` and a filtered
  `GET /api/v1/external/filament`), and section 6.5, creating a maker, a
  filament and a spool. Both optional for a server, so the version stays 1.
  Checklist items 15 to 17.
- 2026-10-23, firmware 0.8.3: section 7.1, the companion field beside native
  tags (off, `tag` or `nfc_id`) replaces the switch that wrote `tag` for
  OpenSpoolman, and unlinking one tag takes its UID out of every tag field
  that names it. Nothing new is required of a server, so the version stays 1.

## Part 2: AMS source

### Draft (2026-10-09)

- First draft, not binding: it describes a firmware feature that is not
  released yet and may change without a version bump until it ships.
- 2026-10-23: section 9, a spool taken out of a tray loses the location that
  still names the unit when no new one is chosen.
