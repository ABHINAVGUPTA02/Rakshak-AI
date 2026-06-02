"""Karnataka location aliases for fuzzy geographic search."""

from __future__ import annotations

# Canonical key -> search terms (all lowercase)
LOCATION_ALIASES: dict[str, list[str]] = {
    "bengaluru": [
        "bengaluru", "bangalore", "bangaluru", "bengaluru city", "bengaluru urban",
        "blr", "bellanduru", "bellandur", "marathahalli", "koramangala", "indiranagar",
        "electronic city", "whitefield", "hebbal", "yelahanka",
    ],
    "mysuru": ["mysuru", "mysore", "nazarbad", "vijayanagar"],
    "mangaluru": ["mangaluru", "mangalore", "kadri"],
    "tumakuru": ["tumakuru", "tumkur", "tumakuru district"],
    "hubballi": ["hubballi", "hubli", "dharwad"],
    "belagavi": ["belagavi", "belgaum"],
    "kalaburagi": ["kalaburagi", "gulbarga"],
    "davanagere": ["davanagere", "davangere"],
    "ballari": ["ballari", "bellary"],
    "shivamogga": ["shivamogga", "shimoga"],
    "udupi": ["udupi", "udipi"],
    "hassan": ["hassan"],
    "mandya": ["mandya"],
    "kolar": ["kolar"],
    "raichur": ["raichur"],
    "bidar": ["bidar"],
    "kodagu": ["kodagu", "coorg", "madikeri"],
    "chitradurga": ["chitradurga"],
    "vijayapura": ["vijayapura", "bijapur"],
    "karnataka": ["karnataka", "ka state"],
}


def expand_location_terms(text: str) -> list[str]:
    """Return all alias terms that may match the user's location mention."""
    lower = text.lower()
    terms: set[str] = set()

    for _canonical, aliases in LOCATION_ALIASES.items():
        for alias in aliases:
            if alias in lower or _canonical in lower:
                terms.update(aliases)
                terms.add(_canonical)

    # Also pick standalone location-like tokens (4+ chars, not stop words)
    import re

    for token in re.findall(r"[a-z]{4,}", lower):
        for canonical, aliases in LOCATION_ALIASES.items():
            if token in aliases or token == canonical:
                terms.update(aliases)
                terms.add(canonical)

    return sorted(terms)


def detect_locations_in_message(message: str) -> list[str]:
    """Detect which canonical locations the user is asking about."""
    lower = message.lower()
    found: list[str] = []
    for canonical, aliases in LOCATION_ALIASES.items():
        if any(alias in lower for alias in aliases):
            found.append(canonical)
    return found
