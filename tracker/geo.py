"""Distance helpers using the offline ZIP database bundled with the `zipcodes` package."""
from __future__ import annotations

import math
from functools import lru_cache

import zipcodes


def haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@lru_cache(maxsize=None)
def zip_latlon(zip_code: str) -> tuple[float, float] | None:
    m = zipcodes.matching(zip_code[:5])
    if not m:
        return None
    return float(m[0]["lat"]), float(m[0]["long"])


# Spellings seen on auction sites that differ from the postal city name.
ALIASES = {"battleground": "battle ground", "st john": "saint john"}


def _norm_city(city: str) -> str:
    c = " ".join(city.lower().replace(".", "").replace("-", " ").split())
    return ALIASES.get(c, c)


@lru_cache(maxsize=None)
def _city_index(state: str) -> dict[str, tuple[float, float]]:
    """Average lat/lon of every ZIP for each city name in a state."""
    groups: dict[str, list[tuple[float, float]]] = {}
    for z in zipcodes.filter_by(state=state.upper()):
        if not z.get("lat"):
            continue
        pt = (float(z["lat"]), float(z["long"]))
        names = [z["city"], *z.get("acceptable_cities", [])]
        for name in names:
            groups.setdefault(_norm_city(name), []).append(pt)
    return {
        c: (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        for c, pts in groups.items()
    }


def city_latlon(city: str, state: str) -> tuple[float, float] | None:
    return _city_index(state).get(_norm_city(city))


def locate(*, zip_code: str | None, city: str, state: str) -> tuple[float, float] | None:
    return (zip_latlon(zip_code) if zip_code else None) or city_latlon(city, state)


def distance_from(home_zip: str, *, zip_code: str | None, city: str, state: str) -> float | None:
    home = zip_latlon(home_zip)
    if home is None:
        raise ValueError(f"Unknown home ZIP {home_zip}")
    pt = locate(zip_code=zip_code, city=city, state=state)
    if pt is None:
        return None
    return round(haversine_mi(*home, *pt), 1)


def places(state: str) -> list[dict]:
    """Every city and ZIP in a state with coordinates, for the site's location picker."""
    out = []
    cities: dict[str, list[tuple[float, float]]] = {}
    for z in zipcodes.filter_by(state=state.upper()):
        if not z.get("lat") or not z.get("active", True):
            continue
        lat, lon = round(float(z["lat"]), 4), round(float(z["long"]), 4)
        out.append({"n": f"{z['zip_code']} ({z['city'].title()})", "lat": lat, "lon": lon})
        cities.setdefault(z["city"].title(), []).append((lat, lon))
    for name, pts in cities.items():
        out.append({
            "n": f"{name}, {state.upper()}",
            "lat": round(sum(p[0] for p in pts) / len(pts), 4),
            "lon": round(sum(p[1] for p in pts) / len(pts), 4),
        })
    return sorted(out, key=lambda p: p["n"])
