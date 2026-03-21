"""
Geocoding and travel time estimation using postcodes.io.

Converts UK postcodes to lat/lng, calculates straight-line distance via
haversine, and estimates travel time assuming London traffic speeds.
"""
from __future__ import annotations

import math
from functools import lru_cache
from typing import Optional, Tuple

import requests

_POSTCODES_IO_BASE = "https://api.postcodes.io/postcodes"
_AVG_SPEED_KMH = 25.0  # London average with traffic
_BUFFER_MINUTES = 15    # parking + setup time


@lru_cache(maxsize=128)
def get_lat_lng(postcode: str) -> Optional[Tuple[float, float]]:
    """Fetch lat/lng for a UK postcode via postcodes.io. Returns None on failure."""
    try:
        cleaned = postcode.strip().replace(" ", "")
        resp = requests.get(f"{_POSTCODES_IO_BASE}/{cleaned}", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == 200:
                result = data["result"]
                return (result["latitude"], result["longitude"])
    except requests.RequestException:
        pass
    return None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line distance between two lat/lng points in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def estimate_travel_minutes(distance_km: float) -> int:
    """Estimate total travel time in minutes including buffer for parking/setup."""
    travel = (distance_km / _AVG_SPEED_KMH) * 60
    return int(math.ceil(travel + _BUFFER_MINUTES))


def travel_time_between_postcodes(from_postcode: str, to_postcode: str) -> Optional[int]:
    """Return estimated travel time in minutes between two postcodes, or None if geocoding fails."""
    origin = get_lat_lng(from_postcode)
    dest = get_lat_lng(to_postcode)
    if origin is None or dest is None:
        return None
    dist = haversine_km(origin[0], origin[1], dest[0], dest[1])
    return estimate_travel_minutes(dist)
