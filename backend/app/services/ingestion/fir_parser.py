"""Parse structured FIR fields from OCR or native document text."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime

from app.schemas.crime import CrimeRecordCreate, PersonCreate

FIR_NUMBER_PATTERNS = [
    r"(?:FIR|F\.I\.R)\s*(?:No|Number|#)?[\s.:/-]*(\d{1,5}/\d{4}(?:/\d+)?)",
    r"(?:FIR|F\.I\.R)\s*(?:No|Number|#)?[\s.:/-]*(FIR/\d{4}/\d+)",
    r"(?:CR|C\.R|GD)\s*(?:No|Number|#)?[\s.:/-]*(\d{1,5}/\d{4})",
    r"(?:FIR|F\.I\.R)\s*(?:No|Number|#)?[\s.:/-]*([A-Z]{1,6}/\d{4}/\d+)",
]

FIELD_PATTERNS = {
    "police_station": [
        r"Police\s*Station[\s:.-]+([A-Za-z0-9\s\.\-]+?)(?:\n|District|Date|,|$)",
        r"\bPS[\s:.-]+([A-Za-z0-9\s\.\-]+?)(?:\n|District|Date|,|$)",
    ],
    "district": [
        r"District[\s:.-]+([A-Za-z0-9\s\.\-]+?)(?:\n|State|Police|,|$)",
        r"जिल्ल[\s:.-]+([^\n]+)",
    ],
    "incident_date": [
        r"(?:Date\s*of\s*(?:Occurrence|Incident|Offence)|Occurrence\s*Date)[\s:.-]+(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})",
        r"(?:dated|on)[\s]+(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})",
    ],
    "complainant": [
        r"(?:Complainant|Victim|Informant)[\s:.-]+([A-Za-z][A-Za-z\s\.]{1,50}?)(?:\n|Accused|Age|Address|$)",
    ],
    "accused": [
        r"(?:Accused|Suspect|Offender)[\s:.-]+([A-Za-z][A-Za-z\s\.]{1,50}?)(?:\n|Complainant|Age|Address|IPC|$)",
    ],
}

CRIME_KEYWORDS: dict[str, list[str]] = {
    "Theft": ["theft", "stolen", "robbery", "snatch", "burglar", "chor", "ಕಳವು"],
    "Assault": ["assault", "hurt", "attack", "beating", "physical", "ಆಕ್ರಮಣ"],
    "Murder": ["murder", "homicide", "killed", "death", "ಕೊಲೆ"],
    "Cyber Fraud": ["cyber", "phishing", "upi", "online fraud", "computer", "ಫಿಶಿಂಗ್"],
    "Robbery": ["robbery", "dacoity", "armed", "loot"],
    "Cheating": ["cheating", "forgery", "fraud", "misappropriation"],
    "Domestic Violence": ["domestic violence", "dowry", "cruelty"],
    "Drug Offence": ["ndps", "narcotic", "drug", "ganja", "heroin"],
}


def _first_match(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            value = match.group(1).strip(" .,-\n\t")
            if value:
                return value
    return None


def _normalize_fir_number(raw: str) -> str:
    cleaned = raw.strip().upper()
    cleaned = re.sub(r"\s+", "", cleaned)
    cleaned = re.sub(r"[^A-Z0-9/\-]", "", cleaned)
    if cleaned.startswith("FIR") and not cleaned.startswith("FIR/"):
        cleaned = cleaned.replace("FIR", "FIR/", 1)
    return cleaned[:64] if cleaned else ""


def extract_fir_number(text: str) -> str | None:
    for pattern in FIR_NUMBER_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            normalized = _normalize_fir_number(match.group(1))
            if len(normalized) >= 4:
                return normalized
    return None


def infer_crime_type(text: str) -> str:
    lower = text.lower()
    ipc_match = re.search(r"\bIPC[\s/]*(\d+[A-Z]?)", text, re.IGNORECASE)
    if ipc_match:
        section = ipc_match.group(1)
        ipc_map = {
            "302": "Murder",
            "307": "Attempt to Murder",
            "376": "Sexual Assault",
            "420": "Cheating",
            "379": "Theft",
            "380": "Theft",
            "392": "Robbery",
            "395": "Robbery",
            "323": "Assault",
            "324": "Assault",
            "354": "Assault",
        }
        if section in ipc_map:
            return ipc_map[section]

    best_type = "Unknown"
    best_score = 0
    for crime_type, keywords in CRIME_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in lower)
        if score > best_score:
            best_score = score
            best_type = crime_type
    return best_type


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _build_description(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", text).strip()
    return collapsed[:2000] if collapsed else "Imported from document via OCR"


def parse_fir_from_text(text: str, source_filename: str = "") -> tuple[CrimeRecordCreate, dict]:
    fir_number = extract_fir_number(text)
    generated = False
    if not fir_number:
        suffix = uuid.uuid4().hex[:8].upper()
        fir_number = f"FIR/OCR/{suffix}"
        generated = True

    police_station = _first_match(text, FIELD_PATTERNS["police_station"])
    district = _first_match(text, FIELD_PATTERNS["district"]) or "Unknown"
    incident_date = _parse_date(_first_match(text, FIELD_PATTERNS["incident_date"]))
    crime_type = infer_crime_type(text)

    persons: list[PersonCreate] = []
    complainant = _first_match(text, FIELD_PATTERNS["complainant"])
    accused = _first_match(text, FIELD_PATTERNS["accused"])
    if complainant:
        persons.append(PersonCreate(name=complainant.title(), role="victim"))
    if accused:
        persons.append(PersonCreate(name=accused.title(), role="accused"))

    record = CrimeRecordCreate(
        fir_number=fir_number,
        crime_type=crime_type,
        description=_build_description(text),
        district=district.title() if district != "Unknown" else district,
        police_station=police_station.title() if police_station else None,
        incident_date=incident_date,
        status="open",
        persons=persons,
    )

    metadata = {
        "fir_number_generated": generated,
        "source_filename": source_filename,
        "parsed_fields": {
            "fir_number": fir_number,
            "crime_type": crime_type,
            "district": record.district,
            "police_station": record.police_station,
            "incident_date": incident_date.isoformat() if incident_date else None,
            "persons_found": len(persons),
        },
    }
    return record, metadata
