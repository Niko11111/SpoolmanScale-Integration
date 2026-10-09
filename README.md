# SpoolmanScale Integration

How to serve a [SpoolmanScale](https://github.com/Niko11111/SpoolmanScale)
from your own software: a filament inventory, a printer bridge, or both. The
scale talks HTTP to the servers the user enters. This repository says exactly
what it sends and what it expects back, so no driver for your system has to
live in the firmware.

## Which part do you need?

| You build | Read | Status |
|---|---|---|
| a filament inventory | [common rules](common.md), then [Part 1: Inventory](inventory/spec.md) | version 1, firmware 0.8.2 and later |
| a bridge that knows the printer and its AMS | Part 2: AMS source | in preparation, published with the firmware release that uses it |
| both in one server | both parts | |

The parts are versioned separately, see [Parts and versions](common.md#parts-and-versions).
Every change is listed in [CHANGELOG.md](CHANGELOG.md).

## Check your server

`check/check_inventory.py` runs the checklist at the end of Part 1 against a
server. Python 3.9 or later, nothing to install.

```bash
# read-only: everything the scale reads
python3 check/check_inventory.py http://inventory.local:7912

# with the writes, on two spools you can spare; weight, location and tags
# are put back afterwards, last_used moves to now
python3 check/check_inventory.py http://inventory.local:7912 --write --spool 12 --spool-b 13

# with a key, or --bearer TOKEN, or --basic USER:PASSWORD
python3 check/check_inventory.py https://inv.example --key YOUR_KEY
```

Exit code 0 means every MUST passed. SHOULD findings print as warnings.

## Questions and changes

Open an issue in this repository. A change to a part goes through this
repository and its changelog, and the scale keeps working against the previous
version for at least one firmware release.

## License

The specification texts (every `.md` file outside `check/`, `tests/` and
`scripts/`) are licensed under [CC BY 4.0](LICENSE-CC-BY-4.0.txt): copy them
into your own documentation, keep the attribution. The scripts and tests are
under the [MIT License](LICENSE).

## Related

- Firmware: https://github.com/Niko11111/SpoolmanScale
- User manual: https://niko11111.github.io/SpoolmanScale-Docs
- Spoolman: https://github.com/Donkie/Spoolman
