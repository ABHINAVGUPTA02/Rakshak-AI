"""Ingest relational crime datasets (FIRs, persons, links, transactions, calls)."""

from __future__ import annotations

import io
import logging
import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from app.models.crime import CrimeRecord, Person, PersonRole
from app.models.entity import CrimeEntity, EntityKind
from app.models.operational import CallLog, PersonProfile, Transaction
from app.schemas.crime import CrimeRecordCreate
from app.services.enrichment.geocoding import enrich_record_coordinates
from app.services.ingestion.entity_extractor import extract_entities

logger = logging.getLogger(__name__)

# Match file stem to dataset role (order matters — most specific first)
ROLE_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("fir_person_links", ("fir_person_links", "fir_person_link", "fir_persons", "fir_links")),
    ("transactions", ("transactions", "transaction", "financial_transactions", "txns")),
    ("calls", ("calls", "call", "call_logs", "call_log", "cdr", "phone_calls")),
    ("persons", ("persons", "person", "people", "accused_victims")),
    ("firs", ("firs", "fir", "crime_records", "crimes", "fir_data")),
]


def classify_data_file(filename: str) -> str | None:
    # Nested paths like data/export/firs.csv → classify by file name only
    stem = Path(filename).name.rsplit(".", 1)[0].lower().replace("-", "_").replace(" ", "_")
    for role, patterns in ROLE_PATTERNS:
        if stem in patterns:
            return role
        for pattern in patterns:
            if stem.endswith(f"_{pattern}") or stem.startswith(f"{pattern}_"):
                return role
    return None


def _as_str_id(value) -> str:
    """Normalize spreadsheet ids (1, 1.0, '1') to a stable string key."""
    if value is None or value == "":
        return ""
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value).strip()
    if isinstance(value, int):
        return str(value)
    raw = str(value).strip()
    if raw.endswith(".0") and raw[:-2].isdigit():
        return raw[:-2]
    return raw


def _resolve_fir_number(data: dict, raw_row: dict) -> tuple[str, str | None]:
    """
    Return (fir_number_to_store, external_fir_id).
    Supports exports that use id/fir_id instead of fir_number.
    """
    fir = _as_str_id(data.get("fir_number"))
    external = _as_str_id(data.get("fir_id")) or _as_str_id(raw_row.get("id"))
    if not fir and external:
        fir = f"FIR/{external}"
    if fir and not external:
        external = fir
    return fir, external or None


def _lookup_fir(
    data: dict,
    raw_row: dict,
    external_fir_id_to_number: dict[str, str],
) -> str:
    ref = _as_str_id(data.get("fir_number")) or _as_str_id(data.get("fir_id")) or _as_str_id(
        raw_row.get("fir_id")
    )
    if not ref:
        return ""
    return external_fir_id_to_number.get(ref, ref)


def _load_table(content: bytes, filename: str) -> list[dict]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        df = pd.read_csv(io.BytesIO(content))
    else:
        df = pd.read_excel(io.BytesIO(content))
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    return df.to_dict(orient="records")


def _normalize_columns(row: dict) -> dict:
    aliases = {
        "fir_number": ("fir_number", "fir_no", "fir", "crime_no", "crime_number", "cr_no", "fir_id"),
        "crime_type": ("crime_type", "type", "offence", "offense"),
        "district": ("district", "dist"),
        "police_station": ("police_station", "ps", "station"),
        "description": ("description", "details", "fir_content", "narrative"),
        "status": ("status", "case_status"),
        "latitude": ("latitude", "lat"),
        "longitude": ("longitude", "lon", "lng"),
        "incident_date": ("incident_date", "date", "fir_date", "occurrence_date"),
        "person_id": ("person_id", "pid", "person_pk", "person_ref", "id"),
        "person_name": ("person_name", "name", "full_name"),
        "role": ("role", "person_role", "involvement"),
        "age": ("age",),
        "address": ("address", "addr"),
        "phone": ("phone", "mobile", "contact", "phone_number"),
        "email": ("email", "e_mail"),
        "amount": ("amount", "value", "txn_amount", "transaction_amount"),
        "from_account": ("from_account", "source_account", "sender", "from_ac"),
        "to_account": ("to_account", "destination_account", "receiver", "to_ac"),
        "upi_id": ("upi_id", "upi", "vpa"),
        "transaction_type": ("transaction_type", "txn_type", "type"),
        "transaction_date": ("transaction_date", "txn_date", "date"),
        "counterparty": ("counterparty", "beneficiary", "payee"),
        "caller_phone": ("caller_phone", "caller", "from_number", "a_party"),
        "callee_phone": ("callee_phone", "callee", "to_number", "b_party"),
        "call_date": ("call_date", "datetime", "timestamp", "start_time"),
        "duration_seconds": ("duration_seconds", "duration", "call_duration"),
        "cell_tower": ("cell_tower", "tower", "location"),
        "direction": ("direction", "call_direction"),
    }
    normalized: dict = {}
    for canonical, keys in aliases.items():
        for key in keys:
            if key in row and row[key] not in (None, ""):
                normalized[canonical] = row[key]
                break
    return normalized


def _parse_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def _parse_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        cleaned = re.sub(r"[^\d.\-]", "", str(value))
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def _parse_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    raw = str(value).strip()[:19]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_datetime(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    raw = str(value).strip()[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    parsed = _parse_date(value)
    return datetime.combine(parsed, datetime.min.time()) if parsed else None


def _normalize_phone(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if len(digits) >= 10:
        return digits[-10:]
    return None


def _map_role(raw: str | None) -> str:
    if not raw:
        return "witness"
    lower = str(raw).lower()
    if "accus" in lower or "suspect" in lower or "offender" in lower:
        return "accused"
    if "victim" in lower or "complainant" in lower or "informant" in lower:
        return "victim"
    if "witness" in lower:
        return "witness"
    return lower if lower in {"accused", "victim", "witness"} else "witness"


def ingest_structured_bundle(db: Session, files_by_role: dict[str, list[tuple[str, bytes]]]) -> dict:
    """
    Ingest a multi-table export in dependency order:
    firs → persons → fir_person_links → transactions → calls
    """
    warnings: list[str] = []
    stats = {
        "firs": 0,
        "persons": 0,
        "links": 0,
        "transactions": 0,
        "calls": 0,
        "skipped": 0,
    }
    fir_id_by_number: dict[str, int] = {}
    external_fir_id_to_number: dict[str, str] = {}
    profile_by_key: dict[str, PersonProfile] = {}

    def _rows_for(role: str) -> list[tuple[dict, dict]]:
        """Return (raw_row, normalized_row) pairs."""
        rows: list[tuple[dict, dict]] = []
        for filename, content in files_by_role.get(role, []):
            try:
                for raw in _load_table(content, filename):
                    rows.append((raw, _normalize_columns(raw)))
            except Exception as exc:
                warnings.append(f"Failed to read {filename}: {exc}")
        return rows

    firs_rows = _rows_for("firs")
    if files_by_role.get("firs") and not firs_rows:
        warnings.append("Could not read any rows from firs file(s).")

    # 1) FIRs
    for raw_row, data in firs_rows:
        fir, external_id = _resolve_fir_number(data, raw_row)
        if not fir:
            stats["skipped"] += 1
            continue
        if external_id:
            external_fir_id_to_number[external_id] = fir
        external_fir_id_to_number[fir] = fir

        if fir in fir_id_by_number or db.query(CrimeRecord).filter(CrimeRecord.fir_number == fir).first():
            existing = db.query(CrimeRecord).filter(CrimeRecord.fir_number == fir).first()
            if existing:
                fir_id_by_number[fir] = existing.id
            stats["skipped"] += 1
            continue

        lat, lon = enrich_record_coordinates(
            _parse_float(data.get("latitude")),
            _parse_float(data.get("longitude")),
            district=str(data.get("district", "Unknown")),
            police_station=data.get("police_station"),
            description=data.get("description"),
        )
        record = CrimeRecordCreate(
            fir_number=fir,
            crime_type=str(data.get("crime_type", "Unknown")),
            description=str(data.get("description", "")) or None,
            district=str(data.get("district", "Unknown")),
            police_station=str(data.get("police_station")) or None,
            latitude=lat,
            longitude=lon,
            incident_date=_parse_date(data.get("incident_date")),
            status=str(data.get("status", "open")),
            entities=extract_entities(str(data.get("description", "") or "")),
        )
        from app.services.ingestion.service import ingest_crime_records

        created = ingest_crime_records(db, [record])
        if created:
            fir_id_by_number[fir] = created[0].id
            stats["firs"] += 1

    # Refresh map for any pre-existing FIRs
    for crime in db.query(CrimeRecord).all():
        fir_id_by_number[crime.fir_number] = crime.id

    if files_by_role.get("firs") and stats["firs"] == 0 and len(firs_rows) > 0:
        warnings.append(
            f"No FIRs imported from {len(firs_rows)} row(s). "
            "Add a fir_number column or numeric id/fir_id per FIR."
        )

    # 2) Person profiles
    for raw_row, data in _rows_for("persons"):
        name = str(data.get("person_name") or data.get("name") or raw_row.get("name") or "").strip()
        if not name:
            stats["skipped"] += 1
            continue
        ext_id = _as_str_id(data.get("person_id")) or _as_str_id(raw_row.get("id")) or None
        if ext_id and ext_id in profile_by_key:
            stats["skipped"] += 1
            continue
        existing = None
        if ext_id:
            existing = db.query(PersonProfile).filter(PersonProfile.external_id == ext_id).first()
        if existing:
            profile_by_key[ext_id] = existing
            profile_by_key[name.lower()] = existing
            continue

        profile = PersonProfile(
            external_id=ext_id,
            name=name,
            age=_parse_int(data.get("age")),
            address=str(data.get("address", "")) or None,
            phone=_normalize_phone(data.get("phone")),
            email=str(data.get("email", "")).lower() or None,
        )
        db.add(profile)
        db.flush()
        if ext_id:
            profile_by_key[ext_id] = profile
        profile_by_key[name.lower()] = profile
        stats["persons"] += 1
    db.commit()

    # 3) FIR ↔ person links
    links_rows = _rows_for("fir_person_links")
    for raw_row, data in links_rows:
        fir = _lookup_fir(data, raw_row, external_fir_id_to_number)
        if not fir or fir not in fir_id_by_number:
            stats["skipped"] += 1
            continue
        crime_id = fir_id_by_number[fir]
        name = str(data.get("person_name") or raw_row.get("name") or "").strip()
        ext_id = _as_str_id(data.get("person_id")) or _as_str_id(raw_row.get("person_id")) or _as_str_id(
            raw_row.get("id")
        )
        profile = profile_by_key.get(ext_id) or (profile_by_key.get(name.lower()) if name else None)
        if profile and not name:
            name = profile.name
        if not name:
            stats["skipped"] += 1
            continue

        role = _map_role(data.get("role"))
        exists = (
            db.query(Person)
            .filter(Person.crime_record_id == crime_id, Person.name == name, Person.role == PersonRole(role))
            .first()
        )
        if exists:
            stats["skipped"] += 1
            continue

        person = Person(
            name=name,
            role=PersonRole(role),
            age=profile.age if profile else None,
            address=profile.address if profile else None,
            crime_record_id=crime_id,
        )
        db.add(person)
        if profile and profile.phone:
            crime = db.query(CrimeRecord).filter(CrimeRecord.id == crime_id).first()
            if crime and not any(e.kind == EntityKind.PHONE and e.value == profile.phone for e in crime.entities):
                crime.entities.append(
                    CrimeEntity(
                        kind=EntityKind.PHONE,
                        value=profile.phone,
                        label="Phone from person registry",
                        role=role,
                    )
                )
        stats["links"] += 1
    db.commit()

    if files_by_role.get("fir_person_links") and stats["links"] == 0 and len(links_rows) > 0:
        warnings.append(
            f"No person links imported ({len(links_rows)} rows). "
            "Check fir_id/fir_number matches the firs table id values."
        )

    # 4) Transactions
    for raw_row, data in _rows_for("transactions"):
        fir = _lookup_fir(data, raw_row, external_fir_id_to_number)
        if not fir or fir not in fir_id_by_number:
            stats["skipped"] += 1
            continue
        crime_id = fir_id_by_number[fir]
        txn = Transaction(
            crime_record_id=crime_id,
            fir_number=fir,
            amount=_parse_float(data.get("amount")),
            from_account=str(data.get("from_account", "")) or None,
            to_account=str(data.get("to_account", "")) or None,
            upi_id=str(data.get("upi_id", "")) or None,
            transaction_type=str(data.get("transaction_type", "")) or None,
            transaction_date=_parse_date(data.get("transaction_date")),
            counterparty=str(data.get("counterparty", "")) or None,
            description=str(data.get("description", "")) or None,
        )
        db.add(txn)
        stats["transactions"] += 1
    db.commit()

    # 5) Call logs
    for raw_row, data in _rows_for("calls"):
        fir = _lookup_fir(data, raw_row, external_fir_id_to_number)
        crime_id = fir_id_by_number.get(fir) if fir else None
        caller = _normalize_phone(data.get("caller_phone"))
        callee = _normalize_phone(data.get("callee_phone"))
        if not caller and not callee:
            stats["skipped"] += 1
            continue

        call = CallLog(
            crime_record_id=crime_id,
            fir_number=fir or None,
            caller_phone=caller,
            callee_phone=callee,
            call_date=_parse_datetime(data.get("call_date")),
            duration_seconds=_parse_int(data.get("duration_seconds")),
            cell_tower=str(data.get("cell_tower", "")) or None,
            person_name=str(data.get("person_name", "")) or None,
            direction=str(data.get("direction", "")) or None,
        )
        db.add(call)

        if crime_id:
            crime = db.query(CrimeRecord).filter(CrimeRecord.id == crime_id).first()
            if crime:
                for phone, label in ((caller, "Caller"), (callee, "Callee")):
                    if phone and not any(e.kind == EntityKind.PHONE and e.value == phone for e in crime.entities):
                        crime.entities.append(
                            CrimeEntity(kind=EntityKind.PHONE, value=phone, label=f"{label} from call log")
                        )
        stats["calls"] += 1
    db.commit()

    total_records = stats["firs"] + stats["links"] + stats["transactions"] + stats["calls"]
    return {
        "type": "structured_bundle",
        "success": total_records > 0,
        "records_ingested": total_records,
        "records_skipped": stats["skipped"],
        "stats": stats,
        "warnings": warnings,
    }
