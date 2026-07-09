# carbon-receipt

Estimates annual CO2e from driving, electricity, natural gas, and flights. Prints it as a receipt.

No runtime dependencies. Python 3.8+.

```bash
python carbon_receipt.py --miles 8000 --kwh 10500 --grid RFCW --flight CMH-LHR --flight LHR-CMH
python carbon_receipt.py --miles 8000 --grid CAMX --json
python carbon_receipt.py --list-regions
```

## Why this exists

Most carbon calculators are a black box. This one keeps every number in `data/factors.json` with a citation, a data year, and a `verified` flag. Where the project could not confirm a number against a primary source, the program says so at the bottom of the receipt:

```
UNVERIFIED FACTORS USED (2):
  ! flight/short_haul: NOT read from the DEFRA table. Inferred from a secondary
    source stating economy spans 0.13-0.20 kg/pkm. Treat as a placeholder.
  ! flight/cabin/business: CONFLICTING SOURCES. One gives business ~2.9x economy;
    another quotes long-haul business 0.41077 kg/pkm, which is 3.51x the verified
    0.11704 economy figure. Unresolved -- do not rely on cabin class.
```

That warning block is the feature. A calculator that reports two significant figures with no indication of which digits are real is worse than no calculator.

---

## What changed from v1, and why v1 was wrong

v1 hardcoded five grid factors and one driving factor. All six were wrong. Checked against **eGRID2023 Rev 2** and EPA's **Greenhouse Gas Equivalencies** references:

| Factor | v1 | Correct | Error |
|---|---|---|---|
| `car_mile` (kg CO2e/mi) | 0.335 | 0.392 | **−15%** |
| Washington grid (kg/kWh) | 0.098 | 0.126 | **−22%** |
| California grid | 0.211 | 0.187 | +13% |
| Texas grid | 0.401 | 0.365 | +10% |
| Ohio grid | 0.531 | 0.506 | +5% |
| US average grid | 0.371 | 0.365 | +2% |

v1 also made two structural errors:

**It labeled state values as "eGRID subregion intensities."** They are different things. eGRID publishes by subregion (RFCW, CAMX, NWPP); a state can span several. v2 accepts either, prefers subregions, and warns when you fall back to a state.

**It ignored grid loss.** eGRID rates are per MWh *generated*. Your electric bill is in kWh *delivered*. About 4.2% of generation never arrives. Consumption accounting must divide by `(1 − loss)`, which v1 didn't, understating electricity by ~4%.

On the same inputs, v1 reported **8.26 t** and v2 reports **7.69 t**. Neither number moved because the world changed. v1 was just wrong.

---

## The four TODOs

### 1. Fetch factors from EPA instead of hardcoding — done, with a caveat

`fetch_factors.py` downloads EPA's eGRID summary tables, parses the subregion and state tables, diffs against the bundled `data/factors.json`, and writes.

```bash
python fetch_factors.py --verify        # diff only, exit 1 if drift
python fetch_factors.py                 # refresh
```

**The download path has never been executed against the live endpoint.** The sandbox this was written in blocks egress to `epa.gov` (`x-deny-reason: host_not_allowed`). Run it yourself before trusting it. The *parser* is tested: `tests/egrid_excerpt.txt` holds real text from EPA's PDF, and `test_roundtrip_against_real_pdf_text` asserts the parser independently reproduces every hand-entered value — name, rate, and grid-loss percent. Two independent transcriptions of the same table agree, which is the check that would have caught v1's errors.

### 2. Full eGRID subregion list, keyed by ZIP — **half done. Read this part.**

The subregion list is complete: all 27 subregions plus the national row, with per-subregion grid loss, straight from EPA.

**The ZIP lookup does not exist, and I am not going to fake it.**

EPA publishes emission rates by subregion. It does *not* publish a ZIP-to-subregion crosswalk. Building one means intersecting ~33,000 Census ZCTA polygons against the eGRID subregion boundary shapefile — a spatial join, with real edge cases (ZIPs straddling two subregions, territories). Searching turned up no open crosswalk; the tools that offer ZIP lookup are commercial services that did the spatial join themselves and charge for it.

So `--zip` exits with an explanation instead of a number:

```
$ python carbon_receipt.py --zip 43054
--zip is not supported, and I would rather say so than guess.
```

Guessing here would have been easy and invisible. Mapping ZIP → state → state average would run without error and be silently wrong for every state spanning multiple subregions — which is most of them. Ohio alone spans RFCW and RFCM.

Finishing this properly needs `geopandas`, the ZCTA TIGER/Line shapefile, and EPA's subregion shapefile. That's a real afternoon, not a lookup table.

### 3. Distance-based flight model — done, and it is the weakest part

`--flight ORD-LHR` computes great-circle distance via haversine over a 49-airport table, applies a routing uplift, classifies into a DEFRA haul band, and multiplies by a per-passenger-km factor. `--flight-km 3000` skips the airport table.

Haversine is checked against six published great-circle distances (JFK–LHR, LHR–SYD, SFO–SIN, ...) and agrees within 0.3%. The residual is spherical-vs-ellipsoidal geometry, which is expected and correct.

The **geometry is solid; the emission factors are not.**

- **Long-haul economy, 0.11704 kg CO2e/pkm (with radiative forcing): verified.** DEFRA 2025, corroborated by two independent secondary sources.
- **Short-haul economy, 0.13: a placeholder.** Not read from DEFRA's table. Flagged at runtime.
- **Domestic, 0.22928: unconfirmed vintage.** From a mirror, not the source.
- **Cabin multipliers: contradictory.** One source says business ≈ 2.9× economy. Another quotes DEFRA 2025 long-haul business at 0.41077 kg/pkm, which is 3.51× the verified economy figure. Both cannot be right. Unresolved, and flagged.
- **The 9% great-circle uplift: unconfirmed.** DEFRA applies an uplift for indirect routing and holding; 9% is my recollection, not something I read in the methodology paper.

Two further caveats. DEFRA's haul bands are defined *for flights to and from the UK*; applying them to a US domestic itinerary is an approximation DEFRA does not endorse. And the **2024** DEFRA release was built on 2021 load factors, when planes flew half-empty under COVID — it overstates per-passenger emissions by 16–42%. This tool uses the **2025** release. If you copy flight factors from anywhere, check the vintage.

### 4. `--json` output — done

```bash
python carbon_receipt.py --miles 8000 --grid RFCW --flight LAX-JFK --json
```

Emits totals, per-item breakdown, the resolved grid region and its `kg/kWh`, per-leg flight detail, `factor_sources` with URLs and data years, and `unverified_factors_used`. The provenance travels with the number.

---

## Scope

Direct energy use only. Food, goods, and services are excluded and are typically a third to half of a household footprint. **The total is a floor, not an estimate.** The natural gas factor is CO2-only and ignores upstream methane leakage, which is material.

## Tests

```bash
python -m unittest discover -s tests -t . -v
```

32 tests. The ones that matter:

- `test_roundtrip_against_real_pdf_text` — parser reproduces the hand-entered table
- `test_grid_loss_raises_intensity` — delivered kWh always dirtier than generated
- `test_long_haul_economy_is_verified_so_no_warning` — the flag is selective, not blanket
- `test_unverified_factors_carry_a_note` — walks the whole factor tree; nothing can be marked unverified without explaining why
- `test_zip_refuses_and_explains` — the refusal is a tested behavior

## Sources

- EPA, [eGRID2023 Rev 2 Summary Tables](https://www.epa.gov/system/files/documents/2025-06/summary_tables_rev2.pdf) — grid rates, grid loss
- EPA, [GHG Equivalencies: Calculations and References](https://www.epa.gov/energy/greenhouse-gas-equivalencies-calculator-calculations-and-references) — driving, natural gas
- UK DESNZ, [GHG conversion factors 2025](https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting) — flights

## TODO (v3)

- [ ] ZCTA → subregion spatial join, so `--zip` can exist
- [ ] Read short-haul, domestic, and cabin factors from the DEFRA spreadsheet directly; retire every `verified: false`
- [ ] Confirm the GCD uplift against DEFRA's methodology paper
- [ ] Natural gas: add CH4/N2O combustion and upstream leakage
- [ ] Household size — per-capita vs per-household is currently ambiguous
