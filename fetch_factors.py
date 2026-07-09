#!/usr/bin/env python3
"""
Refresh the grid section of data/factors.json from EPA's published eGRID
summary tables.

    python fetch_factors.py            # fetch, diff, write
    python fetch_factors.py --verify   # fetch, diff, DON'T write
    python fetch_factors.py --from-text extracted.txt   # parse a local file

Requires `pypdf` for the download path (pip install pypdf). The parser
itself is stdlib and is what the tests exercise.

STATUS: the download path has NOT been executed against the live endpoint
from the environment this was written in (egress to epa.gov was blocked).
The parser has been tested against the real PDF text. Treat the network
code as unverified until you run it. See README.
"""

import argparse
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
FACTORS = os.path.join(HERE, "data", "factors.json")

EGRID_URL = ("https://www.epa.gov/system/files/documents/2025-06/"
             "summary_tables_rev2.pdf")

# Subregion rows look like:
#   RFCW RFC West 911.4 0.071 0.010 916.1 0.4 0.4 0.412 1,757.4 ... 4.2%
# We want: acronym, name, the 4th number (CO2e total output), and the
# trailing loss %. Numbers may carry thousands separators.
NUM = r"[\d,]+\.\d+"
SUBREGION_RE = re.compile(
    rf"^([A-Z]{{4}})\s+(.+?)\s+"
    rf"({NUM})\s+({NUM})\s+({NUM})\s+({NUM})\s+"      # CO2 CH4 N2O CO2e
    rf"(?:{NUM}|\d+\.\d+)\s+.*?"                       # skip NOx.. onward
    rf"(\d+\.\d+)%\s*$"                                # grid gross loss
)

# State rows: "OH 1,063.8 0.068 0.010 1,068.3 0.3 0.3 0.610"
STATE_RE = re.compile(
    rf"^([A-Z]{{2}})\s+({NUM})\s+({NUM})\s+({NUM})\s+({NUM})\s+"
)


def _f(s):
    return float(s.replace(",", ""))


def parse(text):
    """Return (subregions, states) from eGRID summary-table text."""
    subregions, states = {}, {}

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        m = SUBREGION_RE.match(line)
        if m:
            acr, name, _co2, _ch4, _n2o, co2e, loss = m.groups()
            subregions[acr] = {
                "name": name.strip(),
                "co2e_lb_per_mwh": _f(co2e),
                "grid_loss_pct": float(loss),
            }
            continue

        m = STATE_RE.match(line)
        if m:
            st, _co2, _ch4, _n2o, co2e = m.groups()
            # Guard: subregion acronyms are 4 chars, states 2, so no clash.
            states.setdefault(st, {"co2e_lb_per_mwh": _f(co2e)})

    if not subregions:
        raise SystemExit("parsed 0 subregions -- EPA changed the table layout")
    return subregions, states


def download(url=EGRID_URL):
    try:
        from pypdf import PdfReader
    except ImportError:
        raise SystemExit("pip install pypdf")
    import io

    req = urllib.request.Request(url, headers={"User-Agent": "carbon-receipt"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    reader = PdfReader(io.BytesIO(raw))
    return "\n".join(p.extract_text() or "" for p in reader.pages)


def diff(old, new, label):
    changes = []
    for k, v in new.items():
        o = old.get(k)
        if o is None:
            changes.append(f"  + {label} {k}: new, {v['co2e_lb_per_mwh']}")
        elif abs(o["co2e_lb_per_mwh"] - v["co2e_lb_per_mwh"]) > 1e-9:
            a, b = o["co2e_lb_per_mwh"], v["co2e_lb_per_mwh"]
            changes.append(f"  ~ {label} {k}: {a} -> {b} ({100*(b-a)/a:+.1f}%)")
    for k in old:
        if k not in new:
            changes.append(f"  - {label} {k}: gone from source")
    return changes


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--verify", action="store_true", help="diff only, no write")
    p.add_argument("--from-text", help="parse a local text file instead")
    args = p.parse_args()

    text = open(args.from_text).read() if args.from_text else download()
    subregions, states = parse(text)
    print(f"parsed {len(subregions)} subregions, {len(states)} states")

    fx = json.load(open(FACTORS))
    changes = (diff(fx["grid"]["subregions"], subregions, "sub")
               + diff(fx["grid"]["states"], states, "st"))

    if not changes:
        print("no change; bundled factors match the source")
    else:
        print(f"{len(changes)} change(s):")
        print("\n".join(changes))

    if args.verify:
        sys.exit(1 if changes else 0)

    fx["grid"]["subregions"] = subregions
    fx["grid"]["states"] = states
    json.dump(fx, open(FACTORS, "w"), indent=2)
    print(f"wrote {FACTORS}")


if __name__ == "__main__":
    main()
