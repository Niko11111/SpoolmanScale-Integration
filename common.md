# Common rules

Rules every part of this specification shares. A part's own document adds
what applies to it alone.

The key words MUST, SHOULD and MAY are used as in RFC 2119. Sections marked
*informative* describe what the scale does; they are not requirements.

## Parts and versions

| Part | Covers | Version | Firmware |
|---|---|---|---|
| 1, [Inventory](inventory/spec.md) | spools, filaments, tags, weights: a subset of the Spoolman 0.27 REST API | 1 | 0.8.2 and later |
| 2, AMS source | printers, their AMS units and trays, assigning a spool to a tray | in preparation | not released |

- Each part has its own version, an integer. A change that breaks an existing
  server gets a new version and an entry in [CHANGELOG.md](CHANGELOG.md), and
  the scale keeps working against the previous version for at least one
  firmware release. New optional fields, endpoints and capabilities do not
  change the version.
- Part 1 follows Spoolman, so a change there can bring a change here. Part 2
  is SpoolmanScale's own API and changes only through this repository.
- The scale holds one address per part. Both MAY point to the same server.
- This specification describes released firmware only. What a coming release
  adds is listed as *planned*, without a requirement level, until it ships.

## Transport

- **Base URL.** The user enters `http://host[:port][/prefix]` or
  `https://...`. The scale appends every path in this specification to it:
  base `https://inv.example/sub` gives `https://inv.example/sub/api/v1/health`.
  Each part states how long its address may be.
- **HTTPS** needs a certificate from a public CA, or the user turns
  verification off on the scale for a self-signed one.
- **Redirects are not followed.** Serve `/api/v1/...` directly: no redirect
  for a trailing slash, from http to https, or to a login page. A redirect
  reads as an error on the scale.
- The scale sends no `Origin`, no cookies and no CSRF token. The API MUST NOT
  require them.
- The scale asks for `Accept-Encoding: identity`: do not compress. Chunked
  transfer encoding and HTTP keep-alive are fine.

## Authentication

Spoolman itself has none. Other servers usually have, so the user can set up
access per address on the scale's web page. Nothing is sent until a secret is
stored, so a plain Spoolman stays as it is.

- The scale sends the secret on every request to that address, in one of
  three forms: `X-API-Key: <key>`, `Authorization: Bearer <token>`, or HTTP
  Basic with user and password. Each part says which forms the scale offers.
- The secret travels in a header, never in the URL, and is bound to the
  address it was entered for: a changed address gets no secret until the user
  enters one for it.
- With a wrong or missing secret the server MUST answer `401` or `403`. The
  scale shows that as a rejected key, not as an unreachable server. A server
  without authentication MUST ignore the header.
- The scale keeps the secret in its flash and never writes it to a log; it
  shows only whether one is set.
- A secret is a static credential. The scale cannot run a login flow, refresh
  a token, or follow a redirect to a login page: issue a long-lived key or
  token for it. Up to 511 characters are kept, which fits a JWT.
- *Recommended for a server reachable from the internet:* require a secret,
  serve HTTPS only and refuse plain HTTP rather than redirecting it, and let
  the user issue a key that is scoped to the one account and can be revoked
  on its own. The scale needs read access plus the writes its part lists. A
  read-only key makes every write fail with `401`/`403`, which the user sees
  as a rejected key.

## Data

- **Bodies** are JSON in UTF-8. Requests with a body carry
  `Content-Type: application/json`.
- **Types.** Ids are JSON integers, flags are JSON booleans, weights are JSON
  numbers (integer or decimal). A string where a number is expected reads as
  0 on the scale.
- **Nulls in answers.** A field whose value is null MAY be omitted, unless a
  part says it MUST be present.
- **Dates** are ISO 8601 in UTC with `Z`, e.g. `2026-10-01T12:34:56Z`.
  Fractional seconds are fine.
- **Unknown fields and query parameters** MUST be ignored, by the server and
  by the scale. Adding a field to an answer never breaks the scale: it reads
  with a filter, so fields it does not know cost bandwidth, not memory.
- **Text** the scale shows is cut to a fixed number of bytes per field, stated
  in the part. Cuts fall on UTF-8 character boundaries.

## Discovery

The scale learns what a server can do by asking, not from a version number.

- Part 1: `GET /api/v1/info` for the server's version, then probes
  (`GET /api/v1/tag/reader`, `GET /api/v1/field/spool`) whose `200` or `404`
  is cached per server. A server that speaks the Spoolman API announces
  nothing.
- Part 2: a route of its own under the part's prefix, answering version and
  capabilities. Defined in Part 2.

## Errors

- `401` and `403` mean a rejected secret, on every part (see Authentication).
- Everything else is defined per part. Part 1 follows Spoolman's status
  codes, Part 2 has a table of its own.
- An error body is a courtesy for the log. The scale tells the user what
  happened in their language; it never shows the server's text.
