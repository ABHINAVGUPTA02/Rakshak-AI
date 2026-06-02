"""Hybrid geocoding — use explicit coordinates or resolve from location text."""

from __future__ import annotations

import re

from app.services.intelligence.location_aliases import LOCATION_ALIASES, detect_locations_in_message

# Approximate district / city centroids in Karnataka (lat, lon)
DISTRICT_CENTROIDS: dict[str, tuple[float, float]] = {
    "bengaluru": (12.9716, 77.5946),
    "mysuru": (12.2958, 76.6394),
    "mangaluru": (12.9141, 74.8560),
    "tumakuru": (13.3409, 77.1010),
    "hubballi": (15.3647, 75.1240),
    "belagavi": (15.8497, 74.4977),
    "kalaburagi": (17.3297, 76.8343),
    "davanagere": (14.4644, 75.9218),
    "ballari": (15.1394, 76.9214),
    "shivamogga": (13.9299, 75.5681),
    "udupi": (13.3409, 74.7421),
    "hassan": (13.0068, 76.0996),
    "mandya": (12.5212, 76.8951),
    "kolar": (13.1360, 78.1290),
    "raichur": (16.2076, 77.3463),
    "bidar": (17.9104, 77.5199),
    "kodagu": (12.4244, 75.7382),
    "chitradurga": (14.2226, 76.3980),
    "vijayapura": (16.8302, 75.7100),
    "karnataka": (12.9716, 77.5946),
}

# Finer points for police stations / localities (lat, lon)
LOCALITY_COORDS: dict[str, tuple[float, float]] = {
    "bellanduru": (12.9260, 77.6761),
    "bellandur": (12.9260, 77.6761),
    "marathahalli": (12.9591, 77.6974),
    "whitefield": (12.9698, 77.7500),
    "koramangala": (12.9279, 77.6271),
    "indiranagar": (12.9784, 77.6408),
    "electronic city": (12.8399, 77.6770),
    "hebbal": (13.0358, 77.5970),
    "yelahanka": (13.1007, 77.5963),
    "tumakuru town": (13.3409, 77.1010),
    "tumakuru cen": (13.3409, 77.1010),
    "bhoganahalli": (12.9120, 77.7100),
    "varthuru": (12.9390, 77.7480),
    "kodihalli": (12.9680, 77.6520),
    "k r extention": (13.3409, 77.1010),
    "kadri": (12.8870, 74.8560),
    "nazarbad": (12.3050, 76.6550),
    "dharwad": (15.4589, 75.0078),
}

KARNATAKA_LAT_RANGE = (11.5, 18.8)
KARNATAKA_LON_RANGE = (74.0, 78.5)


def _normalize_key(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _valid_explicit_coords(latitude: float | None, longitude: float | None) -> bool:
    if latitude is None or longitude is None:
        return False
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError):
        return False
    if lat == 0.0 and lon == 0.0:
        return False
    return (
        KARNATAKA_LAT_RANGE[0] <= lat <= KARNATAKA_LAT_RANGE[1]
        and KARNATAKA_LON_RANGE[0] <= lon <= KARNATAKA_LON_RANGE[1]
    )


def _match_locality(text: str) -> tuple[float, float] | None:
    lower = _normalize_key(text)
    for key in sorted(LOCALITY_COORDS, key=len, reverse=True):
        if key in lower:
            return LOCALITY_COORDS[key]
    return None


def _match_district_centroid(*texts: str | None) -> tuple[float, float] | None:
    combined = " ".join(t for t in texts if t).lower()
    if not combined.strip():
        return None

    # Direct district label match (longest first)
    district_labels = {
        "bengaluru city": "bengaluru",
        "bengaluru urban": "bengaluru",
        "bengaluru rural": "bengaluru",
        "tumakuru dist": "tumakuru",
        "tumkur": "tumakuru",
        "mysore": "mysuru",
        "mangalore": "mangaluru",
        "hubli": "hubballi",
        "belgaum": "belagavi",
        "gulbarga": "kalaburagi",
        "shimoga": "shivamogga",
        "coorg": "kodagu",
        "bijapur": "vijayapura",
    }
    for label, canonical in sorted(district_labels.items(), key=lambda x: len(x[0]), reverse=True):
        if label in combined:
            return DISTRICT_CENTROIDS.get(canonical)

    for canonical in detect_locations_in_message(combined):
        if canonical in DISTRICT_CENTROIDS:
            return DISTRICT_CENTROIDS[canonical]

    for canonical, aliases in LOCATION_ALIASES.items():
        for alias in sorted(aliases, key=len, reverse=True):
            if alias in combined:
                return DISTRICT_CENTROIDS.get(canonical)

    return None


def resolve_coordinates(
    latitude: float | None,
    longitude: float | None,
    district: str | None = None,
    police_station: str | None = None,
    description: str | None = None,
) -> tuple[float | None, float | None, str]:
    """
    Return (latitude, longitude, source).
    source is 'explicit' when coords came from the data source, else 'geocoded', else 'missing'.
    """
    if _valid_explicit_coords(latitude, longitude):
        return float(latitude), float(longitude), "explicit"

    # Prefer finer locality (police station / address cues) before district centroid
    for text in (police_station, description, district):
        if not text:
            continue
        locality = _match_locality(text)
        if locality:
            return locality[0], locality[1], "geocoded"

    centroid = _match_district_centroid(district, police_station, description)
    if centroid:
        return centroid[0], centroid[1], "geocoded"

    return None, None, "missing"


def enrich_record_coordinates(
    latitude: float | None,
    longitude: float | None,
    district: str | None = None,
    police_station: str | None = None,
    description: str | None = None,
) -> tuple[float | None, float | None]:
    """Apply hybrid geocoding for persistence during ingestion."""
    lat, lon, _ = resolve_coordinates(latitude, longitude, district, police_station, description)
    return lat, lon
