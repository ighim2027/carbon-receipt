"""
Great-circle distance between airports.

The airport table is small on purpose. Anything not in it: pass --flight-km
directly. A wrong coordinate is a silent error; a missing one is a loud one.
"""

import math

R_KM = 6371.0088  # IUGG mean Earth radius


class AirportError(ValueError):
    pass


# IATA -> (lat, lon). Hand-entered to ~2 decimal places, which is ~1 km.
# That is well below the precision of any emission factor here.
AIRPORTS = {
    "ATL": (33.64, -84.43), "AUS": (30.20, -97.67), "BOS": (42.36, -71.01),
    "BWI": (39.18, -76.67), "CLT": (35.21, -80.94), "CMH": (39.998, -82.89),
    "DCA": (38.85, -77.04), "DEN": (39.86, -104.67), "DFW": (32.90, -97.04),
    "DTW": (42.21, -83.35), "EWR": (40.69, -74.17), "FLL": (26.07, -80.15),
    "IAD": (38.94, -77.46), "IAH": (29.98, -95.34), "JFK": (40.64, -73.78),
    "LAS": (36.08, -115.15), "LAX": (33.94, -118.41), "LGA": (40.78, -73.87),
    "MCO": (28.43, -81.31), "MDW": (41.79, -87.75), "MIA": (25.79, -80.29),
    "MSP": (44.88, -93.22), "ORD": (41.98, -87.90), "PDX": (45.59, -122.60),
    "PHL": (39.87, -75.24), "PHX": (33.43, -112.01), "PIT": (40.49, -80.23),
    "SAN": (32.73, -117.19), "SEA": (47.45, -122.31), "SFO": (37.62, -122.38),
    "SLC": (40.79, -111.98), "STL": (38.75, -90.37), "TPA": (27.98, -82.53),
    # international
    "AMS": (52.31, 4.76), "CDG": (49.01, 2.55), "DXB": (25.25, 55.36),
    "FRA": (50.03, 8.56), "GRU": (-23.43, -46.47), "HKG": (22.31, 113.91),
    "HND": (35.55, 139.78), "ICN": (37.46, 126.44), "LHR": (51.47, -0.46),
    "MAD": (40.47, -3.57), "MEX": (19.44, -99.07), "NRT": (35.76, 140.39),
    "SIN": (1.36, 103.99), "SYD": (-33.95, 151.18), "YYZ": (43.68, -79.63),
    "ZRH": (47.46, 8.55),
}


def haversine(lat1, lon1, lat2, lon2):
    """Great-circle distance in km."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_KM * math.asin(math.sqrt(a))


def distance(origin, dest):
    """Great-circle km between two IATA codes."""
    o, d = origin.upper(), dest.upper()
    for code in (o, d):
        if code not in AIRPORTS:
            raise AirportError(
                f"{code} not in the bundled airport table "
                f"({len(AIRPORTS)} airports). Use --flight-km instead."
            )
    return haversine(*AIRPORTS[o], *AIRPORTS[d])
