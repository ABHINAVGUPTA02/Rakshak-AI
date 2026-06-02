import io
import logging
from pathlib import Path

import pandas as pd
from fastapi import UploadFile
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.crime import CrimeRecord, Person, PersonRole
from app.schemas.crime import CrimeRecordCreate
from app.services.enrichment.geocoding import enrich_record_coordinates
from app.services.enrichment.graph_sync import sync_crime_to_graph
from app.services.ingestion.fir_parser import (
    extract_district,
    extract_incident_date,
    extract_police_station,
    infer_crime_type,
    parse_fir_from_text,
)
from app.services.ingestion.ocr import IMAGE_EXTENSIONS, extract_text_from_document

logger = logging.getLogger(__name__)

DOCUMENT_EXTENSIONS = {".pdf", *IMAGE_EXTENSIONS}


def parse_excel(content: bytes) -> list[dict]:
    df = pd.read_excel(io.BytesIO(content))
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    return df.to_dict(orient="records")


def ingest_crime_records(db: Session, records: list[CrimeRecordCreate]) -> list[CrimeRecord]:
    created: list[CrimeRecord] = []
    for record in records:
        lat, lon = enrich_record_coordinates(
            record.latitude,
            record.longitude,
            district=record.district,
            police_station=record.police_station,
            description=record.description,
        )
        crime = CrimeRecord(
            fir_number=record.fir_number,
            crime_type=record.crime_type,
            description=record.description,
            district=record.district,
            police_station=record.police_station,
            latitude=lat,
            longitude=lon,
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


def _sync_created_records(db: Session, created: list[CrimeRecord]) -> dict[str, bool]:
    status: dict[str, bool] = {}
    for crime in created:
        status[crime.fir_number] = sync_crime_to_graph(db, crime.id)
    return status


def _enrich_row_from_text(row: dict) -> dict:
    """Fill missing spreadsheet fields from description / combined row text."""
    description = str(row.get("description", "") or "")
    combined = " ".join(str(row.get(k, "") or "") for k in ("description", "police_station", "district", "crime_type"))
    if not combined.strip():
        return row

    district = str(row.get("district", "") or "").strip()
    if not district or district.lower() in {"unknown", "na", "n/a", ""}:
        inferred = extract_district(combined) or extract_district(description)
        if inferred:
            row["district"] = inferred

    ps = str(row.get("police_station", "") or "").strip()
    if not ps:
        inferred_ps = extract_police_station(combined)
        if inferred_ps:
            row["police_station"] = inferred_ps

    crime_type = str(row.get("crime_type", "") or "").strip()
    if not crime_type or crime_type.lower() in {"unknown", "na", "n/a", ""}:
        inferred_type = infer_crime_type(combined)
        if inferred_type != "Unknown":
            row["crime_type"] = inferred_type

    if not row.get("incident_date"):
        inferred_date = extract_incident_date(combined)
        if inferred_date:
            row["incident_date"] = inferred_date.isoformat()

    return row


def _ingest_spreadsheet_rows(db: Session, rows: list[dict]) -> tuple[list[CrimeRecord], int]:
    records: list[CrimeRecordCreate] = []
    skipped = 0
    for row in rows:
        row = _enrich_row_from_text(row)
        fir = str(row.get("fir_number", "")).strip()
        if not fir:
            skipped += 1
            continue
        if db.query(CrimeRecord).filter(CrimeRecord.fir_number == fir).first():
            skipped += 1
            continue

        incident_date = row.get("incident_date")
        if isinstance(incident_date, str) and incident_date:
            from datetime import datetime
            parsed_date = None
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                try:
                    parsed_date = datetime.strptime(incident_date[:10], fmt).date()
                    break
                except ValueError:
                    continue
            incident_date = parsed_date

        records.append(
            CrimeRecordCreate(
                fir_number=fir,
                crime_type=str(row.get("crime_type", "Unknown")),
                description=str(row.get("description", "")) or None,
                district=str(row.get("district", "Unknown")),
                police_station=str(row.get("police_station", "")) or None,
                latitude=float(row["latitude"]) if row.get("latitude") not in (None, "") else None,
                longitude=float(row["longitude"]) if row.get("longitude") not in (None, "") else None,
                incident_date=incident_date,
                status=str(row.get("status", "open")),
            )
        )
    created = ingest_crime_records(db, records) if records else []
    _sync_created_records(db, created)
    return created, skipped


def _ingest_document(db: Session, content: bytes, suffix: str, filename: str) -> dict:
    extraction = extract_text_from_document(content, suffix)
    warnings = list(extraction.warnings or [])

    if not extraction.text.strip():
        return {
            "type": "document",
            "records_ingested": 0,
            "extraction_method": extraction.method,
            "characters_extracted": 0,
            "text_preview": "",
            "warnings": warnings + ["No text could be extracted from the document."],
            "success": False,
        }

    parsed_record, parse_meta = parse_fir_from_text(extraction.text, source_filename=filename)
    if parse_meta.get("fir_number_generated"):
        warnings.append(
            f"FIR number not found in document — assigned temporary ID: {parsed_record.fir_number}"
        )

    existing = db.query(CrimeRecord).filter(CrimeRecord.fir_number == parsed_record.fir_number).first()
    if existing:
        return {
            "type": "document",
            "records_ingested": 0,
            "extraction_method": extraction.method,
            "characters_extracted": len(extraction.text),
            "text_preview": extraction.text[:500],
            "parsed_fields": parse_meta.get("parsed_fields"),
            "warnings": warnings + [f"FIR {parsed_record.fir_number} already exists — skipped duplicate."],
            "success": False,
        }

    try:
        created = ingest_crime_records(db, [parsed_record])
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Failed to save OCR-parsed FIR")
        return {
            "type": "document",
            "records_ingested": 0,
            "extraction_method": extraction.method,
            "characters_extracted": len(extraction.text),
            "text_preview": extraction.text[:500],
            "parsed_fields": parse_meta.get("parsed_fields"),
            "warnings": warnings + [f"Database save failed: {exc}"],
            "success": False,
        }

    graph_status = _sync_created_records(db, created)
    graph_synced = graph_status.get(created[0].fir_number, False) if created else False
    if not graph_synced:
        warnings.append("Saved to PostgreSQL but Neo4j graph sync failed — check Neo4j is running.")

    return {
        "type": "document",
        "records_ingested": len(created),
        "extraction_method": extraction.method,
        "characters_extracted": len(extraction.text),
        "text_preview": extraction.text[:500],
        "parsed_fields": parse_meta.get("parsed_fields"),
        "record": {
            "id": created[0].id,
            "fir_number": created[0].fir_number,
            "crime_type": created[0].crime_type,
            "district": created[0].district,
        } if created else None,
        "graph_synced": graph_synced,
        "warnings": warnings,
        "success": len(created) > 0,
    }


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

        created, skipped = _ingest_spreadsheet_rows(db, rows)
        return {
            "type": "spreadsheet",
            "records_ingested": len(created),
            "records_skipped": skipped,
        }

    if suffix in DOCUMENT_EXTENSIONS:
        return _ingest_document(db, content, suffix, filename)

    return {"type": "unsupported", "message": f"Unsupported file type: {suffix}", "records_ingested": 0}
