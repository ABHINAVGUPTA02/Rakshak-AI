"""Build live intelligence context from PostgreSQL for the chat assistant."""

from __future__ import annotations

from collections import Counter

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.crime import CrimeRecord, Person
from app.services.enrichment.geocoding import resolve_coordinates
from app.services.intelligence.crime_search import format_crime_for_chat, get_recent_crimes, search_crimes


def get_crime_stats(db: Session) -> dict:
    total = db.query(func.count(CrimeRecord.id)).scalar() or 0
    by_type_rows = db.query(CrimeRecord.crime_type, func.count()).group_by(CrimeRecord.crime_type).all()
    by_district_rows = db.query(CrimeRecord.district, func.count()).group_by(CrimeRecord.district).all()
    open_cases = db.query(func.count(CrimeRecord.id)).filter(CrimeRecord.status == "open").scalar() or 0
    return {
        "total_crimes": total,
        "by_type": {row[0]: row[1] for row in by_type_rows},
        "by_district": {row[0]: row[1] for row in by_district_rows},
        "open_cases": open_cases,
    }


def get_hotspots(db: Session) -> list[dict]:
    """Aggregate crime hotspots using explicit coords or geocoded location fallback."""
    crimes = db.query(CrimeRecord).all()
    buckets: dict[str, dict] = {}

    for crime in crimes:
        district = (crime.district or "Unknown").strip()
        if district.lower() in {"unknown", "na", "n/a", ""}:
            district = "Unknown"

        lat, lon, source = resolve_coordinates(
            crime.latitude,
            crime.longitude,
            district=crime.district,
            police_station=crime.police_station,
            description=crime.description,
        )
        if lat is None or lon is None:
            continue

        bucket = buckets.setdefault(
            district,
            {
                "district": district,
                "explicit_lats": [],
                "explicit_lons": [],
                "geocoded_lats": [],
                "geocoded_lons": [],
                "crime_count": 0,
            },
        )
        bucket["crime_count"] += 1
        if source == "explicit":
            bucket["explicit_lats"].append(lat)
            bucket["explicit_lons"].append(lon)
        else:
            bucket["geocoded_lats"].append(lat)
            bucket["geocoded_lons"].append(lon)

    hotspots: list[dict] = []
    for bucket in buckets.values():
        if bucket["explicit_lats"]:
            latitude = sum(bucket["explicit_lats"]) / len(bucket["explicit_lats"])
            longitude = sum(bucket["explicit_lons"]) / len(bucket["explicit_lons"])
        else:
            latitude = sum(bucket["geocoded_lats"]) / len(bucket["geocoded_lats"])
            longitude = sum(bucket["geocoded_lons"]) / len(bucket["geocoded_lons"])

        hotspots.append(
            {
                "district": bucket["district"],
                "latitude": latitude,
                "longitude": longitude,
                "crime_count": bucket["crime_count"],
            }
        )

    return sorted(hotspots, key=lambda h: h["crime_count"], reverse=True)


def _search_persons(db: Session, message: str, limit: int = 5) -> list[CrimeRecord]:
    import re

    tokens = re.findall(r"[A-Za-z]{3,}", message)
    if not tokens:
        return []
    filters = [Person.name.ilike(f"%{t}%") for t in tokens[:4]]
    return (
        db.query(CrimeRecord)
        .options(joinedload(CrimeRecord.persons))
        .join(Person)
        .filter(or_(*filters))
        .order_by(CrimeRecord.created_at.desc())
        .limit(limit)
        .all()
    )


def build_intelligence_context(db: Session, message: str) -> dict:
    stats = get_crime_stats(db)
    matched = search_crimes(db, message, limit=8)
    person_matches = _search_persons(db, message, limit=5)
    recent = get_recent_crimes(db, limit=5)
    hotspots = get_hotspots(db)

    # Merge unique records: search results + person matches + recent as background
    seen_ids: set[int] = set()
    all_records: list[CrimeRecord] = []
    for group in (matched, person_matches, recent):
        for crime in group:
            if crime.id not in seen_ids:
                seen_ids.add(crime.id)
                all_records.append(crime)

    primary = matched or person_matches or recent

    return {
        "stats": stats,
        "hotspots": hotspots,
        "matched_records": matched,
        "person_matches": person_matches,
        "recent_records": recent,
        "primary_records": primary,
        "all_records": all_records,
    }


def context_to_text(ctx: dict) -> str:
    stats = ctx["stats"]
    lines = [
        "=== LIVE CRIME INTELLIGENCE CONTEXT ===",
        f"Total records: {stats['total_crimes']} ({stats['open_cases']} open)",
    ]

    if stats["by_type"]:
        types = ", ".join(f"{k}: {v}" for k, v in Counter(stats["by_type"]).most_common(8))
        lines.append(f"By type: {types}")

    if stats["by_district"]:
        districts = ", ".join(f"{k}: {v}" for k, v in Counter(stats["by_district"]).most_common(8))
        lines.append(f"By district: {districts}")

    if ctx["hotspots"]:
        top = sorted(ctx["hotspots"], key=lambda h: h["crime_count"], reverse=True)[:5]
        geo = ", ".join(f"{h['district']} ({h['crime_count']})" for h in top)
        lines.append(f"Geospatial hotspots: {geo}")

    if ctx["matched_records"]:
        lines.append("\n--- Records matching this query ---")
        for crime in ctx["matched_records"]:
            lines.append(_record_detail(crime))

    if ctx["person_matches"]:
        matched_ids = {c.id for c in ctx["matched_records"]}
        extra_person = [c for c in ctx["person_matches"] if c.id not in matched_ids]
        if extra_person:
            lines.append("\n--- Records linked to named persons ---")
            for crime in extra_person:
                lines.append(_record_detail(crime))

    if ctx["recent_records"]:
        lines.append("\n--- Most recent records ---")
        for crime in ctx["recent_records"]:
            lines.append(_record_detail(crime))

    if stats["total_crimes"] == 0:
        lines.append("\nNo crime records in database. User should upload FIRs via Crime Records.")

    return "\n".join(lines)


def _record_detail(crime: CrimeRecord) -> str:
    detail = format_crime_for_chat(crime)
    if crime.description and len(crime.description) > 300:
        detail += f" | Full excerpt: {crime.description[:800].replace(chr(10), ' ')}…"
    return f"• {detail}"
