"""
Loading and provenance for emission factors.

Design rule: no number enters a calculation without a source attached, and
the program knows which of its own numbers it cannot vouch for.
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FACTORS_PATH = os.path.join(HERE, "data", "factors.json")

LB_TO_KG = 0.45359237


class FactorError(ValueError):
    pass


def load(path=FACTORS_PATH):
    if not os.path.exists(path):
        raise FactorError(
            f"no factor file at {path}. Run: python fetch_factors.py"
        )
    with open(path) as f:
        return json.load(f)


class Warnings(list):
    """Collects every unverified factor actually used in this run."""

    def check(self, node, label):
        if isinstance(node, dict) and node.get("verified") is False:
            note = node.get("note", "no note")
            self.append(f"{label}: {note}")
        return node


def grid_kg_per_kwh(factors, region, warn, use_grid_loss=True):
    """
    kg CO2e per kWh. eGRID publishes lb/MWh *generated*; household bills are
    in kWh *delivered*. Dividing by (1 - loss) is the difference, and it is
    the correction v1 of this tool silently omitted.

    Accepts a subregion acronym (RFCW) or a state code (OH). Subregion wins.
    """
    grid = factors["grid"]
    region = region.upper()

    if region in grid["subregions"]:
        entry = grid["subregions"][region]
        lb = entry["co2e_lb_per_mwh"]
        loss = entry["grid_loss_pct"] / 100.0
        kind, name = "subregion", entry["name"]
    elif region in grid["states"]:
        lb = grid["states"][region]["co2e_lb_per_mwh"]
        loss = grid["default_grid_loss_pct"] / 100.0
        kind, name = "state", region
        warn.append(
            f"grid {region}: using STATE average. A state can span several "
            f"eGRID subregions; the subregion figure is the better one if you "
            f"know it."
        )
    else:
        raise FactorError(
            f"unknown region {region!r}.\n"
            f"  subregions: {', '.join(sorted(grid['subregions']))}\n"
            f"  states:     {', '.join(sorted(grid['states']))}"
        )

    kg_per_kwh = lb * LB_TO_KG / 1000.0
    if use_grid_loss:
        kg_per_kwh /= 1.0 - loss

    return kg_per_kwh, {"kind": kind, "name": name, "lb_per_mwh": lb,
                        "grid_loss_pct": loss * 100}


def flight_factor(factors, distance_km, cabin, warn):
    """Pick the haul band, apply the cabin multiplier, flag what's shaky."""
    fl = factors["flight"]
    bands = fl["haul_bands"]

    for band_name in ("domestic", "short_haul", "long_haul"):
        band = bands[band_name]
        if band["max_km"] is None or distance_km <= band["max_km"]:
            break

    econ = band["economy"]
    warn.check(econ, f"flight/{band_name}")

    mult_node = fl["cabin_multipliers"].get(cabin)
    if mult_node is None:
        raise FactorError(
            f"unknown cabin {cabin!r}; try {', '.join(fl['cabin_multipliers'])}"
        )
    warn.check(mult_node, f"flight/cabin/{cabin}")

    return econ["value"] * mult_node["value"], band_name


def gcd_uplift(factors, warn):
    node = factors["flight"]["gcd_uplift"]
    warn.check(node, "flight/gcd_uplift")
    return node["value"]
