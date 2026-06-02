from sqlalchemy.orm import Session

from app.models.crime import CrimeRecord, Person, PersonRole


def summarize_case(db: Session, crime_id: int) -> dict | None:
    from sqlalchemy.orm import joinedload

    crime = (
        db.query(CrimeRecord)
        .options(joinedload(CrimeRecord.persons), joinedload(CrimeRecord.entities))
        .filter(CrimeRecord.id == crime_id)
        .first()
    )
    if not crime:
        return None

    from app.services.ingestion.fir_parser import ensure_crime_entities, ensure_crime_persons

    if not crime.persons or not crime.entities:
        ensure_crime_persons(db, crime)
        ensure_crime_entities(db, crime)
        crime = (
            db.query(CrimeRecord)
            .options(joinedload(CrimeRecord.persons), joinedload(CrimeRecord.entities))
            .filter(CrimeRecord.id == crime_id)
            .first()
        )
        if not crime:
            return None

    accused = [p.name for p in crime.persons if p.role == PersonRole.ACCUSED]
    victims = [p.name for p in crime.persons if p.role == PersonRole.VICTIM]

    summary_parts = [
        f"FIR {crime.fir_number} — {crime.crime_type} in {crime.district}.",
    ]
    if crime.police_station:
        summary_parts.append(f"Registered at {crime.police_station} police station.")
    if crime.incident_date:
        summary_parts.append(f"Incident date: {crime.incident_date.isoformat()}.")
    if crime.description:
        summary_parts.append(crime.description)
    if accused:
        summary_parts.append(f"Accused: {', '.join(accused)}.")
    if victims:
        summary_parts.append(f"Victims: {', '.join(victims)}.")

    repeat_offenders = []
    for name in accused:
        count = (
            db.query(CrimeRecord)
            .join(Person)
            .filter(Person.name == name, Person.role == PersonRole.ACCUSED)
            .distinct()
            .count()
        )
        if count > 1:
            repeat_offenders.append({"name": name, "case_count": count})

    return {
        "crime_id": crime.id,
        "fir_number": crime.fir_number,
        "summary": " ".join(summary_parts),
        "accused": accused,
        "victims": victims,
        "entities": [
            {"kind": e.kind.value, "value": e.value, "label": e.label}
            for e in crime.entities
        ],
        "repeat_offenders": repeat_offenders,
        "status": crime.status,
    }


def find_similar_cases(db: Session, crime_id: int, limit: int = 5) -> list[dict]:
    crime = db.query(CrimeRecord).filter(CrimeRecord.id == crime_id).first()
    if not crime:
        return []

    similar = (
        db.query(CrimeRecord)
        .filter(CrimeRecord.id != crime.id, CrimeRecord.crime_type == crime.crime_type)
        .limit(limit)
        .all()
    )
    return [
        {
            "id": c.id,
            "fir_number": c.fir_number,
            "crime_type": c.crime_type,
            "district": c.district,
            "similarity_reason": f"Same crime type ({c.crime_type})",
        }
        for c in similar
    ]
