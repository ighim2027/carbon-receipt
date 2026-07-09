#!/usr/bin/env python3
"""
carbon-receipt: estimate personal CO2e from a few basic inputs.

Every factor is loaded from data/factors.json with a citation attached.
Factors the project could not verify against a primary source are marked,
and the program tells you when it used one.

    python carbon_receipt.py --miles 8000 --kwh 10500 --grid RFCW
    python carbon_receipt.py --kwh 10500 --grid OH --flight CMH-LHR
    python carbon_receipt.py --miles 8000 --grid CAMX --json
"""

import argparse
import json
import sys

import airports
import factors as F

RESET = "\033[0m"
DIM = "\033[2m"
YELLOW = "\033[33m"


def compute(fx, warn, miles=0.0, kwh=0.0, therms=0.0, grid="US",
            flights=(), cabin="economy", grid_loss=True):
    """Return (line_items, detail). All values kg CO2e."""
    items, detail = {}, {}

    if miles:
        f = fx["driving"]["car_mile"]
        warn.check(f, "driving/car_mile")
        items["driving"] = miles * f["value"]
        detail["driving"] = {"miles": miles, "kg_per_mile": f["value"]}

    if kwh:
        kg_kwh, meta = F.grid_kg_per_kwh(fx, grid, warn, grid_loss)
        items["electricity"] = kwh * kg_kwh
        detail["electricity"] = dict(meta, kwh=kwh, kg_per_kwh=round(kg_kwh, 5),
                                     grid_loss_applied=grid_loss)

    if therms:
        f = fx["natural_gas"]["therm"]
        warn.check(f, "natural_gas/therm")
        items["natural gas"] = therms * f["value"]
        detail["natural gas"] = {"therms": therms, "kg_per_therm": f["value"]}

    if flights:
        uplift = F.gcd_uplift(fx, warn)
        total, legs = 0.0, []
        for leg in flights:
            gcd = leg["km"]
            flown = gcd * (1 + uplift)
            ef, band = F.flight_factor(fx, flown, cabin, warn)
            kg = flown * ef
            total += kg
            legs.append({"route": leg["label"], "gcd_km": round(gcd, 1),
                         "flown_km": round(flown, 1), "band": band,
                         "cabin": cabin, "kg_per_pkm": ef, "kg": round(kg, 1)})
        items["flights"] = total
        detail["flights"] = {"uplift": uplift, "legs": legs}

    return items, detail


US_AVG_T = 14.5  # t CO2e/yr, energy-related, order-of-magnitude only


def render(items, detail, warn, color=True):
    w = 46
    y = YELLOW if color else ""
    d = DIM if color else ""
    r = RESET if color else ""
    out = []
    total = sum(items.values())

    out.append("=" * w)
    out.append("CARBON RECEIPT".center(w))
    out.append("=" * w)

    for name, kg in items.items():
        out.append(f"{name:<28}{kg:>12,.0f} kg")
        if name == "electricity":
            m = detail["electricity"]
            out.append(f"{d}  {m['name']} ({m['kind']}), "
                       f"{m['kg_per_kwh']} kg/kWh delivered{r}")
        if name == "flights":
            for leg in detail["flights"]["legs"]:
                out.append(f"{d}  {leg['route']}  {leg['flown_km']:,.0f} km "
                           f"{leg['band']}  {leg['kg']:,.0f} kg{r}")

    out.append("-" * w)
    out.append(f"{'TOTAL':<28}{total:>12,.0f} kg")
    out.append(f"{'':<28}{total / 1000:>12,.2f} t")
    out.append("=" * w)

    if total > 0:
        out.append(f"\nUS average is roughly {US_AVG_T} t/yr. "
                   f"You're at {100 * (total / 1000) / US_AVG_T:.0f}%.")

    out.append("\nDirect energy use only. Food, goods and services are excluded")
    out.append("and are typically a third to half of a household footprint.")
    out.append("This total is a floor, not an estimate.")

    if warn:
        out.append(f"\n{y}UNVERIFIED FACTORS USED ({len(warn)}):{r}")
        for m in warn:
            out.append(f"{y}  ! {m}{r}")

    return "\n".join(out)


def parse_flights(specs, km_specs):
    legs = []
    for s in specs or []:
        if "-" not in s:
            raise SystemExit(f"--flight expects ORIG-DEST, got {s!r}")
        o, dst = s.split("-", 1)
        legs.append({"label": f"{o.upper()}-{dst.upper()}",
                     "km": airports.distance(o, dst)})
    for k in km_specs or []:
        legs.append({"label": f"{float(k):,.0f} km leg", "km": float(k)})
    return legs


def main():
    p = argparse.ArgumentParser(description="Estimate CO2e from basic inputs.")
    p.add_argument("--miles", type=float, default=0)
    p.add_argument("--kwh", type=float, default=0)
    p.add_argument("--therms", type=float, default=0)
    p.add_argument("--grid", default="US",
                   help="eGRID subregion (RFCW) or state (OH). Subregion preferred.")
    p.add_argument("--no-grid-loss", action="store_true",
                   help="report per MWh generated instead of delivered")
    p.add_argument("--flight", action="append", metavar="ORIG-DEST",
                   help="one-way leg by IATA code; repeat for more")
    p.add_argument("--flight-km", action="append", metavar="KM",
                   help="one-way leg by distance; repeat for more")
    p.add_argument("--cabin", default="economy")
    p.add_argument("--zip", help="not supported; explains why")
    p.add_argument("--json", action="store_true")
    p.add_argument("--list-regions", action="store_true")
    p.add_argument("--no-color", action="store_true")
    args = p.parse_args()

    fx = F.load()

    if args.list_regions:
        g = fx["grid"]
        for a, e in sorted(g["subregions"].items()):
            print(f"  {a:<6}{e['co2e_lb_per_mwh']:>8.1f} lb/MWh  {e['name']}")
        return

    if args.zip:
        raise SystemExit(
            "--zip is not supported, and I would rather say so than guess.\n\n"
            "EPA publishes emission rates by eGRID subregion, not by ZIP. Mapping\n"
            "a ZIP to a subregion requires intersecting ZCTA polygons with the\n"
            "subregion boundary shapefile -- a spatial join EPA does not publish\n"
            "as a dataset. No open crosswalk was found while building this tool.\n\n"
            "Use --grid with a subregion (look yours up in EPA's Power Profiler),\n"
            "or --grid with your state code for a coarser but fully sourced number.\n"
            "See README, 'The ZIP TODO I did not finish'."
        )

    warn = F.Warnings()
    legs = parse_flights(args.flight, args.flight_km)

    items, detail = compute(
        fx, warn, miles=args.miles, kwh=args.kwh, therms=args.therms,
        grid=args.grid, flights=legs, cabin=args.cabin,
        grid_loss=not args.no_grid_loss,
    )

    if not items:
        raise SystemExit("Nothing to compute. Try --miles / --kwh / --flight.")

    if args.json:
        json.dump({
            "total_kg": round(sum(items.values()), 2),
            "total_t": round(sum(items.values()) / 1000, 4),
            "items_kg": {k: round(v, 2) for k, v in items.items()},
            "detail": detail,
            "unverified_factors_used": list(warn),
            "factor_sources": {
                "grid": fx["grid"]["source"],
                "driving": fx["driving"]["car_mile"]["source"],
                "flight": fx["flight"]["source"],
            },
            "scope_note": "Direct energy use only; excludes food, goods, services.",
        }, sys.stdout, indent=2)
        print()
    else:
        print(render(items, detail, warn, color=not args.no_color))


if __name__ == "__main__":
    main()
