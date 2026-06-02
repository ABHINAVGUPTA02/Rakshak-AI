"""Search crime records for chat and investigative queries."""

from __future__ import annotations

import re

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.crime import CrimeRecord
from app.services.intelligence.location_aliases import expand_location_terms

STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "what", "who", "how", "when",
    "where", "tell", "me", "about", "show", "find", "give", "can", "you", "please",
    "any", "all", "this", "that", "these", "those", "and", "or", "for", "with",
    "crime", "crimes", "case", "cases", "incident", "incidents", "there", "have",
    "has", "had", "been", "being", "from", "into", "over", "under", "also",
}


def _keywords(message: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9/\-]{3,}", message.lower())
    return [t for t in tokens if t not in STOP_WORDS]


def search_crimes(db: Session, message: str, limit: int = 8) -> list[CrimeRecord]:
    message = message.strip()
    if not message:
        return get_recent_crimes(db, limit)

    fir_match = re.search(
        r"(FIR/OCR/[A-Z0-9]+|FIR/\d{4}/\d+|\d{1,5}/\d{4}(?:/\d+)?)",
        message,
        re.IGNORECASE,
    )
    if fir_match:
        by_fir = (
            db.query(CrimeRecord)
            .options(joinedload(CrimeRecord.persons))
            .filter(CrimeRecord.fir_number.ilike(f"%{fir_match.group(1)}%"))
            .limit(limit)
            .all()
        )
        if by_fir:
            return by_fir

    keywords = _keywords(message)
    location_terms = expand_location_terms(message)
    filters = []

    if keywords:
        for word in keywords[:8]:
            pattern = f"%{word}%"
            filters.extend(
                [
                    CrimeRecord.fir_number.ilike(pattern),
                    CrimeRecord.crime_type.ilike(pattern),
                    CrimeRecord.district.ilike(pattern),
                    CrimeRecord.police_station.ilike(pattern),
                    CrimeRecord.description.ilike(pattern),
                    CrimeRecord.status.ilike(pattern),
                ]
            )

    for term in location_terms[:12]:
        pattern = f"%{term}%"
        filters.extend(
            [
                CrimeRecord.district.ilike(pattern),
                CrimeRecord.police_station.ilike(pattern),
                CrimeRecord.description.ilike(pattern),
            ]
        )

    if filters:
        results = (
            db.query(CrimeRecord)
            .options(joinedload(CrimeRecord.persons))
            .filter(or_(*filters))
            .order_by(CrimeRecord.created_at.desc())
            .limit(limit)
            .all()
        )
        if results:
            return results

    return []


def get_recent_crimes(db: Session, limit: int = 5) -> list[CrimeRecord]:
    return db.query(CrimeRecord).order_by(CrimeRecord.created_at.desc()).limit(limit).all()


def format_crime_for_chat(crime: CrimeRecord) -> str:
    fir_label = crime.fir_number if crime.fir_number.upper().startswith("FIR") else f"FIR {crime.fir_number}"
    parts = [
        f"{fir_label} — {crime.crime_type} in {crime.district}",
    ]
    if crime.police_station:
        parts.append(f"PS: {crime.police_station}")
    if crime.incident_date:
        parts.append(f"Date: {crime.incident_date.isoformat()}")
    if crime.description:
        snippet = crime.description[:300].replace("\n", " ")
        parts.append(f"Details: {snippet}{'…' if len(crime.description) > 300 else ''}")
    if crime.persons:
        names = ", ".join(f"{p.name} ({p.role.value})" for p in crime.persons[:4])
        parts.append(f"Persons: {names}")
    return " | ".join(parts)
