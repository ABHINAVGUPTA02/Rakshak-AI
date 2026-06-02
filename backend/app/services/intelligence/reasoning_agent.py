"""Reasoning agent — intent detection, retrieval, and narrative synthesis."""

from __future__ import annotations

import re
from collections import Counter
from enum import Enum

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.crime import CrimeRecord, Person
from app.schemas.chat import ChatResponse, EvidenceItem
from app.services.intelligence.context_builder import get_crime_stats, get_hotspots
from app.services.intelligence.crime_search import format_crime_for_chat, get_recent_crimes, search_crimes
from app.services.intelligence.location_aliases import detect_locations_in_message, expand_location_terms


class QueryIntent(str, Enum):
    LOCATION = "location"
    PERSON = "person"
    FIR = "fir"
    ANALYTICS = "analytics"
    HOTSPOT = "hotspot"
    NETWORK = "network"
    RECENT = "recent"
    GENERAL = "general"


def detect_intent(message: str) -> QueryIntent:
    lower = message.lower()
    if re.search(r"\b(FIR|fir/|\d{1,5}/\d{4})", message):
        return QueryIntent.FIR
    if detect_locations_in_message(message):
        return QueryIntent.LOCATION
    if re.search(r"\b(how many|total|count|statistics|overview|summary)\b", lower):
        return QueryIntent.ANALYTICS
    if re.search(r"\b(hotspot|hot spot|geospatial)\b", lower):
        return QueryIntent.HOTSPOT
    if re.search(r"\b(network|associate|connection|link|gang|repeat offender)\b", lower):
        return QueryIntent.NETWORK
    if re.search(r"\b(recent|latest|new|uploaded)\b", lower):
        return QueryIntent.RECENT
    if re.search(r"\b(victim|accused|complainant|witness|who is|person named)\b", lower):
        return QueryIntent.PERSON
    return QueryIntent.GENERAL


def retrieve_records(db: Session, message: str, intent: QueryIntent, limit: int = 10) -> list[CrimeRecord]:
    """Multi-strategy retrieval with location alias expansion."""
    seen: set[int] = set()
    results: list[CrimeRecord] = []

    def add(records: list[CrimeRecord]) -> None:
        for r in records:
            if r.id not in seen:
                seen.add(r.id)
                results.append(r)

    # Standard keyword + FIR search
    add(search_crimes(db, message, limit=limit))

    # Location alias expansion
    if intent in (QueryIntent.LOCATION, QueryIntent.GENERAL):
        location_terms = expand_location_terms(message)
        if location_terms:
            filters = []
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
                loc_results = (
                    db.query(CrimeRecord)
                    .options(joinedload(CrimeRecord.persons))
                    .filter(or_(*filters))
                    .order_by(CrimeRecord.created_at.desc())
                    .limit(limit)
                    .all()
                )
                add(loc_results)

    # Person name search
    if intent == QueryIntent.PERSON or re.search(r"\b[A-Z][a-z]+\b", message):
        tokens = re.findall(r"[A-Za-z]{3,}", message)
        stop = {"tell", "about", "the", "who", "what", "crime", "crimes", "case", "cases"}
        name_tokens = [t for t in tokens if t.lower() not in stop]
        if name_tokens:
            filters = [Person.name.ilike(f"%{t}%") for t in name_tokens[:4]]
            person_results = (
                db.query(CrimeRecord)
                .options(joinedload(CrimeRecord.persons))
                .join(Person)
                .filter(or_(*filters))
                .order_by(CrimeRecord.created_at.desc())
                .limit(limit)
                .all()
            )
            add(person_results)

    return results[:limit]


def synthesize_reply(
    message: str,
    intent: QueryIntent,
    records: list[CrimeRecord],
    db: Session,
    language: str = "en",
) -> tuple[str, list[EvidenceItem]]:
    stats = get_crime_stats(db)
    evidence = [
        EvidenceItem(source="PostgreSQL", detail=f"{r.fir_number} — {r.crime_type}, {r.district}")
        for r in records[:8]
    ]

    if stats["total_crimes"] == 0:
        msg = (
            "No crime records in the database yet. Upload FIRs via the Crime Records page."
            if language != "kn"
            else "ಡೇಟಾಬೇಸ್‌ನಲ್ಲಿ ದಾಖಲೆಗಳಿಲ್ಲ. Crime Records ನಿಂದ FIR ಅಪ್‌ಲೋಡ್ ಮಾಡಿ."
        )
        return msg, evidence

    locations = detect_locations_in_message(message)
    reasoning_lines: list[str] = []

    # --- Reasoning header ---
    if intent == QueryIntent.LOCATION and locations:
        loc_label = ", ".join(loc.title() for loc in locations)
        search_terms = expand_location_terms(message)[:5]
        reasoning_lines.append(
            f"Searching for crimes linked to {loc_label} "
            f"(including aliases: {', '.join(search_terms)})."
        )
    elif intent == QueryIntent.ANALYTICS:
        reasoning_lines.append(f"Analyzing all {stats['total_crimes']} records in the database.")
    elif intent == QueryIntent.FIR:
        reasoning_lines.append("Looking up the specified FIR number.")
    else:
        reasoning_lines.append("Searching records by keywords, location, and FIR text.")

    # --- Location-specific answer ---
    if intent == QueryIntent.LOCATION:
        if records:
            by_type = Counter(r.crime_type for r in records)
            districts = Counter(r.district for r in records)
            stations = [r.police_station for r in records if r.police_station]

            body = [
                f"Found {len(records)} crime record(s) related to your query.",
                f"Crime types: {', '.join(f'{t} ({c})' for t, c in by_type.most_common())}.",
            ]
            if districts:
                body.append(f"Districts in records: {', '.join(f'{d} ({c})' for d, c in districts.most_common())}.")
            if stations:
                body.append(f"Police stations: {', '.join(sorted(set(stations)))}.")

            body.append("\nCases:")
            for r in records[:6]:
                body.append(f"  • {format_crime_for_chat(r)}")
                if r.description and len(r.description) > 200:
                    excerpt = _extract_location_snippet(r.description, locations or expand_location_terms(message))
                    if excerpt:
                        body.append(f"    → {excerpt}")

            return "\n".join(reasoning_lines) + "\n\n" + "\n".join(body), evidence

        # No records but we know the location — helpful empty state
        loc_label = locations[0].title() if locations else "that area"
        return (
            "\n".join(reasoning_lines)
            + f"\n\nNo FIR records explicitly tagged to {loc_label} were found. "
            f"The database currently has {stats['total_crimes']} record(s) total. "
            "Upload Bangalore/Bengaluru FIRs or try searching by FIR number or police station name."
        ), evidence

    # --- Analytics ---
    if intent == QueryIntent.ANALYTICS:
        lines = [
            f"Database: {stats['total_crimes']} records ({stats['open_cases']} open).",
        ]
        if stats["by_type"]:
            lines.append("By type: " + ", ".join(f"{t}: {c}" for t, c in Counter(stats["by_type"]).most_common()))
        if stats["by_district"]:
            lines.append("By district: " + ", ".join(f"{d}: {c}" for d, c in Counter(stats["by_district"]).most_common()))
        if records:
            lines.append(f"\nRecords relevant to your query ({len(records)}):")
            lines.extend(f"  • {format_crime_for_chat(r)}" for r in records[:5])
        return "\n".join(reasoning_lines) + "\n\n" + "\n".join(lines), evidence

    # --- FIR / matched records ---
    if records:
        header = f"Found {len(records)} relevant record(s)."
        cases = "\n".join(f"  • {format_crime_for_chat(r)}" for r in records[:6])
        if len(records) == 1 and records[0].description:
            excerpt = records[0].description[:700].replace("\n", " ")
            cases += f"\n\n  Full excerpt: {excerpt}{'…' if len(records[0].description) > 700 else ''}"
        return "\n".join(reasoning_lines) + "\n\n" + header + "\n" + cases, evidence

    # --- Fallback with recent data ---
    recent = get_recent_crimes(db, 5)
    reply = (
        "\n".join(reasoning_lines)
        + f"\n\nNo direct matches for your query. Current database ({stats['total_crimes']} records):\n"
    )
    if stats["by_type"]:
        reply += "Types: " + ", ".join(f"{t} ({c})" for t, c in Counter(stats["by_type"]).most_common(5)) + "\n"
    if recent:
        reply += "\nRecent records:\n" + "\n".join(f"  • {format_crime_for_chat(r)}" for r in recent)
    reply += "\n\nTry: a city name (Bangalore, Mysuru), FIR number, crime type, or person name."
    return reply, evidence


def _extract_location_snippet(description: str, terms: list[str]) -> str:
    lower = description.lower()
    for term in terms:
        idx = lower.find(term.lower())
        if idx >= 0:
            start = max(0, idx - 40)
            end = min(len(description), idx + 120)
            return description[start:end].replace("\n", " ").strip() + "…"
    return description[:150].replace("\n", " ") + "…"


def run_reasoning_agent(db: Session, message: str, language: str = "en") -> ChatResponse:
    intent = detect_intent(message)
    records = retrieve_records(db, message, intent)
    reply, evidence = synthesize_reply(message, intent, records, db, language)
    return ChatResponse(
        reply=reply,
        evidence=evidence,
        suggested_queries=_suggestions(records, intent),
    )


def _suggestions(records: list[CrimeRecord], intent: QueryIntent) -> list[str]:
    if not records:
        return ["Tell me about crimes in Bengaluru", "How many records are in the database?"]
    fir = records[0].fir_number
    if intent == QueryIntent.LOCATION:
        return [f"Summarize {fir}", "What crime types are most common?", "Show recent uploads"]
    return [f"Tell me about {fir}", "Crimes in Bengaluru", "How many open cases?"]
