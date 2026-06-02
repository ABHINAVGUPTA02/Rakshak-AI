import io
from pathlib import Path

import pandas as pd
from fastapi import UploadFile
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.models.crime import CrimeRecord, Person, PersonRole
from app.schemas.crime import CrimeRecordCreate
from app.services.enrichment.graph_sync import sync_crime_to_graph


def parse_excel(content: bytes) -> list[dict]:
    df = pd.read_excel(io.BytesIO(content))
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    return df.to_dict(orient="records")


def parse_pdf_text(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def ingest_crime_records(db: Session, records: list[CrimeRecordCreate]) -> list[CrimeRecord]:
    created: list[CrimeRecord] = []
    for record in records:
        crime = CrimeRecord(
            fir_number=record.fir_number,
            crime_type=record.crime_type,
            description=record.description,
            district=record.district,
            police_station=record.police_station,
            latitude=record.latitude,
            longitude=record.longitude,
            incident_date=record.incident_date,
            status=record.status,
        )
        for person in record.persons:
            crime.persons.append(
                Person(
                    name=person.name,
                    role=PersonRole(person.role),
                    age=person.age,
                    address=person.address,
                )
            )
        db.add(crime)
        created.append(crime)
    db.commit()
    for crime in created:
        db.refresh(crime)
    return created


async def ingest_upload(db: Session, file: UploadFile) -> dict:
    content = await file.read()
    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()

    if suffix in {".xlsx", ".xls", ".csv"}:
        if suffix == ".csv":
            df = pd.read_csv(io.BytesIO(content))
            df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
            rows = df.to_dict(orient="records")
        else:
            rows = parse_excel(content)

        records: list[CrimeRecordCreate] = []
        for row in rows:
            fir = str(row.get("fir_number", "")).strip()
            if not fir:
                continue
            if db.query(CrimeRecord).filter(CrimeRecord.fir_number == fir).first():
                continue
            records.append(
                CrimeRecordCreate(
                    fir_number=fir,
                    crime_type=str(row.get("crime_type", "unknown")),
                    description=str(row.get("description", "")) or None,
                    district=str(row.get("district", "unknown")),
                    police_station=str(row.get("police_station", "")) or None,
                    latitude=float(row["latitude"]) if row.get("latitude") not in (None, "") else None,
                    longitude=float(row["longitude"]) if row.get("longitude") not in (None, "") else None,
                    status=str(row.get("status", "open")),
                )
            )
        created = ingest_crime_records(db, records)
        for crime in created:
            try:
                sync_crime_to_graph(db, crime.id)
            except Exception:
                pass
        return {"type": "spreadsheet", "records_ingested": len(created)}

    if suffix == ".pdf":
        text = parse_pdf_text(content)
        return {"type": "pdf", "characters_extracted": len(text), "preview": text[:500]}

    return {"type": "unsupported", "message": f"Unsupported file type: {suffix}"}
