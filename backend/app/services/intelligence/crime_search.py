"""Search crime records for chat and investigative queries."""

from __future__ import annotations

import re

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.crime import CrimeRecord

STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "what", "who", "how", "when",
    "where", "tell", "me", "about", "show", "find", "give", "latest", "recent",
    "uploaded", "fir", "case", "crime", "record", "records", "details", "summary",
}


def _keywords(message: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9/\-]{3,}", message.lower())
    return [t for t in tokens if t not in STOP_WORDS]


def search_crimes(db: Session, message: str, limit: int = 5) -> list[CrimeRecord]:
    message = message.strip()
    if not message:
        return []

    fir_match = re.search(
        r"(?:FIR[/\s-]*)?(\d{1,5}/\d{4}(?:/\d+)?|FIR/\d{4}/\d+|FIR/OCR/[A-Z0-9]+)",
        message,
        re.IGNORECASE,
    )
    if fir_match:
        by_fir = (
            db.query(CrimeRecord)
            .filter(CrimeRecord.fir_number.ilike(f"%{fir_match.group(1)}%"))
            .limit(limit)
            .all()
        )
        if by_fir:
            return by_fir

    keywords = _keywords(message)
    if not keywords:
        return get_recent_crimes(db, limit)

    filters = []
    for word in keywords[:6]:
        pattern = f"%{word}%"
        filters.extend(
            [
                CrimeRecord.fir_number.ilike(pattern),
                CrimeRecord.crime_type.ilike(pattern),
                CrimeRecord.district.ilike(pattern),
                CrimeRecord.police_station.ilike(pattern),
                CrimeRecord.description.ilike(pattern),
            ]
        )

    return (
        db.query(CrimeRecord)
        .filter(or_(*filters))
        .order_by(CrimeRecord.created_at.desc())
        .limit(limit)
        .all()
    )


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
