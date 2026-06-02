from collections import Counter

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.crime import CrimeRecord
from app.schemas.chat import ChatResponse, EvidenceItem
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
    rows = (
        db.query(
            CrimeRecord.district,
            func.avg(CrimeRecord.latitude),
            func.avg(CrimeRecord.longitude),
            func.count(CrimeRecord.id),
        )
        .filter(CrimeRecord.latitude.isnot(None), CrimeRecord.longitude.isnot(None))
        .group_by(CrimeRecord.district)
        .all()
    )
    return [
        {
            "district": row[0],
            "latitude": float(row[1]),
            "longitude": float(row[2]),
            "crime_count": row[3],
        }
        for row in rows
    ]


def answer_query(db: Session, message: str, language: str = "en") -> ChatResponse:
    stats = get_crime_stats(db)
    message_lower = message.lower()
    evidence: list[EvidenceItem] = []

    # Search live DB records first (includes OCR-uploaded FIRs)
    search_triggers = [
        "fir", "case", "record", "upload", "recent", "latest", "complainant",
        "accused", "victim", "describe", "detail", "summary", "search", "find",
    ]
    matched = search_crimes(db, message)
    if matched and (
        any(t in message_lower for t in search_triggers)
        or len(_message_keywords(message)) >= 2
    ):
        lines = [f"- {format_crime_for_chat(crime)}" for crime in matched]
        reply = f"Found {len(matched)} matching record(s) in the database:\n" + "\n".join(lines)
        evidence = [
            EvidenceItem(source="PostgreSQL", detail=f"{crime.fir_number} — {crime.crime_type}")
            for crime in matched
        ]
        return ChatResponse(
            reply=reply,
            evidence=evidence,
            suggested_queries=[
                "Show recent FIR uploads",
                "What are the most common crime types?",
                "Show crime hotspots by district",
            ],
        )

    if any(word in message_lower for word in ["recent", "latest", "uploaded", "new"]):
        recent = get_recent_crimes(db)
        if not recent:
            reply = "No crime records in the database yet. Upload FIRs via Crime Records."
        else:
            lines = [f"- {format_crime_for_chat(crime)}" for crime in recent]
            reply = f"Most recent {len(recent)} record(s):\n" + "\n".join(lines)
            evidence = [
                EvidenceItem(source="PostgreSQL", detail=f"{crime.fir_number} — {crime.crime_type}")
                for crime in recent
            ]
        return ChatResponse(
            reply=reply,
            evidence=evidence,
            suggested_queries=["Search by FIR number", "Show crime hotspots by district"],
        )

    if any(word in message_lower for word in ["hotspot", "map", "district", "location"]):
        hotspots = get_hotspots(db)
        if not hotspots:
            reply = "No geospatial crime data available yet. Ingest records with latitude and longitude."
        else:
            top = sorted(hotspots, key=lambda h: h["crime_count"], reverse=True)[:3]
            lines = [f"- {h['district']}: {h['crime_count']} incidents" for h in top]
            reply = "Top crime hotspots by district:\n" + "\n".join(lines)
            evidence = [EvidenceItem(source="PostgreSQL", detail=f"{h['district']} — {h['crime_count']} crimes") for h in top]

    elif any(word in message_lower for word in ["network", "associate", "link", "connection"]):
        reply = (
            "Criminal network analysis uses the Neo4j knowledge graph. "
            f"Currently tracking {stats['total_crimes']} crime records across "
            f"{len(stats['by_district'])} districts. Open the Network Graph view for visualization."
        )
        evidence = [EvidenceItem(source="Knowledge Graph", detail="Person–Crime–Location relationships")]

    elif any(word in message_lower for word in ["type", "category", "theft", "assault", "robbery"]):
        if not stats["by_type"]:
            reply = "No crime type data available yet."
        else:
            top_types = Counter(stats["by_type"]).most_common(5)
            lines = [f"- {t}: {c}" for t, c in top_types]
            reply = "Crime breakdown by type:\n" + "\n".join(lines)
            evidence = [EvidenceItem(source="PostgreSQL", detail=f"{t}: {c} cases") for t, c in top_types]

    elif language == "kn":
        reply = (
            f"ರಕ್ಷಕ AI: Currently {stats['total_crimes']} ಅಪರಾಧ ದಾಖಲೆಗಳಿವೆ. "
            "English or Kannada ನಲ್ಲಿ hotspot, network, ಅಥವಾ crime type ಬಗ್ಗೆ ಕೇಳಿ."
        )
    else:
        reply = (
            f"Rakshak AI Intelligence Assistant. I have access to {stats['total_crimes']} crime records "
            f"({stats['open_cases']} open cases). Ask about specific FIRs, recent uploads, hotspots, "
            "crime types, or networks."
        )

    if settings.openai_api_key:
        reply += "\n\n[LLM integration ready — configure OPENAI_API_KEY to enable advanced reasoning.]"

    return ChatResponse(
        reply=reply,
        evidence=evidence,
        suggested_queries=[
            "Show recent FIR uploads",
            "Show crime hotspots by district",
            "What are the most common crime types?",
        ],
    )


def _message_keywords(message: str) -> list[str]:
    import re

    stop = {"a", "an", "the", "is", "are", "what", "who", "how", "when", "where", "tell", "me", "about"}
    tokens = re.findall(r"[A-Za-z0-9/\-]{3,}", message.lower())
    return [t for t in tokens if t not in stop]
