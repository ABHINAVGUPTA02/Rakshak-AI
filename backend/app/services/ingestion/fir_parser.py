"""Parse structured FIR fields from OCR or native document text."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.schemas.crime import CrimeRecordCreate, PersonCreate
from app.services.ingestion.text_normalizer import normalize_ocr_text
from app.services.intelligence.location_aliases import LOCATION_ALIASES, detect_locations_in_message

if TYPE_CHECKING:
    from app.models.crime import CrimeRecord

# Karnataka district names for fuzzy recovery from OCR body text
KARNATAKA_DISTRICTS = [
    "Bengaluru City", "Bengaluru Urban", "Bengaluru Rural", "Mysuru", "Mysore",
    "Tumakuru", "Tumkur", "Mangaluru", "Mangalore", "Hubballi", "Dharwad",
    "Belagavi", "Belgaum", "Kalaburagi", "Gulbarga", "Davanagere", "Ballari",
    "Bellary", "Shivamogga", "Shimoga", "Udupi", "Hassan", "Mandya", "Kolar",
    "Raichur", "Bidar", "Kodagu", "Coorg", "Chitradurga", "Vijayapura", "Bijapur",
    "Ramanagara", "Chikkaballapur", "Koppal", "Gadag", "Haveri", "Bagalkot",
    "Yadgir", "Chamarajanagar", "Chikkamagaluru", "Dakshina Kannada", "Uttara Kannada",
    "Karnataka",
]

CANONICAL_DISTRICT_LABEL: dict[str, str] = {
    "bengaluru": "Bengaluru City",
    "mysuru": "Mysuru",
    "mangaluru": "Mangaluru",
    "tumakuru": "Tumakuru",
    "hubballi": "Hubballi-Dharwad",
    "belagavi": "Belagavi",
    "kalaburagi": "Kalaburagi",
    "davanagere": "Davanagere",
    "ballari": "Ballari",
    "shivamogga": "Shivamogga",
    "udupi": "Udupi",
    "hassan": "Hassan",
    "mandya": "Mandya",
    "kolar": "Kolar",
    "raichur": "Raichur",
    "bidar": "Bidar",
    "kodagu": "Kodagu",
    "chitradurga": "Chitradurga",
    "vijayapura": "Vijayapura",
    "karnataka": "Karnataka",
}

# IPC / BNS / BNSS section → crime type
SECTION_CRIME_MAP: dict[str, str] = {
    "302": "Murder",
    "307": "Attempt to Murder",
    "304": "Culpable Homicide",
    "376": "Sexual Assault",
    "354": "Assault",
    "323": "Assault",
    "324": "Assault",
    "325": "Assault",
    "379": "Theft",
    "380": "Theft",
    "381": "Theft",
    "382": "Theft",
    "392": "Robbery",
    "393": "Robbery",
    "394": "Robbery",
    "395": "Robbery",
    "397": "Robbery",
    "420": "Cheating",
    "406": "Criminal Breach of Trust",
    "468": "Forgery",
    "471": "Forgery",
    "498A": "Domestic Violence",
    "506": "Criminal Intimidation",
    "509": "Harassment",
}

CRIME_KEYWORDS: dict[str, list[str]] = {
    "Theft": ["theft", "stolen", "stealing", "snatch", "pickpocket", "burglary", "chor", "ಕಳವು", "mobile stolen"],
    "Robbery": ["robbery", "dacoity", "armed robbery", "loot", "mugging"],
    "Assault": ["assault", "hurt", "grievous hurt", "attack", "beating", "physical assault"],
    "Murder": ["murder", "homicide", "killed", "culpable homicide"],
    "Cyber Fraud": ["cyber", "phishing", "upi fraud", "online fraud", "computer fraud", "it act"],
    "Cheating": ["cheating", "forgery", "fraud", "misappropriation", "criminal breach"],
    "Domestic Violence": ["domestic violence", "dowry", "cruelty", "498a"],
    "Drug Offence": ["ndps", "narcotic", "drug", "ganja", "heroin", "contraband"],
    "Sexual Assault": ["rape", "sexual assault", "molestation", "376"],
    "Chain Snatching": ["chain snatch", "chain snatching", "snatching"],
}


def _clean_field(value: str | None, max_len: int = 80) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip(" .,-\n\t|:")
    cleaned = re.sub(r"\s*(?:Act|Section|IPC|BNSS|BNS|\&).*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip(" .,-")
    if len(cleaned) < 2:
        return None
    return cleaned[:max_len]


def _title_field(value: str | None) -> str | None:
    if not value:
        return None
    parts = value.split()
    return " ".join("PS" if word.upper() == "PS" else word.capitalize() for word in parts)


def _normalize_district_label(district: str) -> str:
    cleaned = re.sub(r"\s+Dist(?:rict)?\.?$", "", district, flags=re.IGNORECASE).strip()
    return cleaned or district


def extract_fir_number(text: str) -> str | None:
    patterns = [
        r"(?:FIR|F\.I\.R)\s*(?:No|Number|#)?\s*[:\.]?\s*(FIR/\d{4}/\d+)",
        r"(?:FIR|F\.I\.R)\s*(?:No|Number|#)?\s*[:\.]?\s*(\d{1,5}/\d{4}(?:/\d+)?)",
        r"Crime\s*No\s*[:\.]?\s*(\d{1,5}/\d{4})",
        r"(?:CR|C\.R|GD)\s*(?:No|Number|#)?\s*[:\.]?\s*(\d{1,5}/\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            raw = re.sub(r"\s+", "", match.group(1).upper())
            if "CRIME" in pattern.upper() or raw.count("/") == 1:
                return f"CR/{raw}" if not raw.startswith("CR/") else raw
            if raw.startswith("FIR") and "/" not in raw:
                return raw.replace("FIR", "FIR/", 1)
            return raw[:64]
    return None


def extract_district(text: str) -> str | None:
    patterns = [
        r"District\s*[:\.]?\s*([A-Za-z][A-Za-z\s\.\-]{2,45}?)(?=\s*(?:Crime|FIR|Circle|PS|Police|State|Act|\||$))",
        r"([A-Za-z]+(?:uru|ore|ur[u]?|nagara|agiri|apura|balli|mogga|kannda))\s+(?:City|Dist(?:rict)?|Urban|Rural)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            val = _clean_field(match.group(1))
            if val and val.lower() not in {"unknown", "state", "karnataka state"}:
                return _title_field(val)

    lower = text.lower()
    for district in sorted(KARNATAKA_DISTRICTS, key=len, reverse=True):
        if district.lower() in lower:
            return district

    for canonical in detect_locations_in_message(text):
        if canonical in CANONICAL_DISTRICT_LABEL:
            return CANONICAL_DISTRICT_LABEL[canonical]

    return None


def extract_police_station(text: str) -> str | None:
    patterns = [
        r"Police\s*Station\s*[:\.]?\s*([A-Za-z][A-Za-z\s\.\-]{2,40}?)(?=\s*(?:Act|Section|District|Crime|FIR|Circle|$))",
        r"PS\s*[:\.]?\s*([A-Za-z][A-Za-z\s\.\-]{2,35}?)(?:\s*PS)?(?=\s*(?:Act|Section|District|Crime|FIR|Circle|$))",
        r"Circle\s*/?\s*Sub\s*Division\s*[:\.]?\s*([A-Za-z][A-Za-z\s\.\-]{2,40}?)(?=\s*(?:PS|Police|Act|District|Crime|$))",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            val = _clean_field(match.group(1))
            if val:
                if not val.upper().endswith(" PS"):
                    val = f"{val} PS" if "station" not in val.lower() else val
                return _title_field(val)
    return None


def extract_incident_date(text: str) -> date | None:
    patterns = [
        r"FIR\s*Date\s*[:\.]?\s*(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})",
        r"Date\s*of\s*(?:Occurrence|Incident|Offence|Reporting)\s*[:\.]?\s*(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})",
        r"Occurrence\s*Date\s*[:\.]?\s*(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})",
        r"(?:dated|on)\s+(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            parsed = _parse_date(match.group(1))
            if parsed:
                return parsed
    return None


def extract_act_sections(text: str) -> list[str]:
    sections: list[str] = []
    act_block = re.search(
        r"Act\s*(?:&|and)?\s*Section[s]?\s*[:\.]?\s*(.+?)(?=Complainant|Accused|Name of|Victim|$)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    haystack = act_block.group(1) if act_block else text
    for match in re.finditer(r"\b(\d{2,4}[A-Z]?)\s*(?:of\s*)?(?:IPC|BNSS|BNS|I\.P\.C)?", haystack, re.IGNORECASE):
        sections.append(match.group(1).upper())
    for match in re.finditer(r"(?:IPC|BNSS|BNS|I\.P\.C)\s*[:\-/]?\s*(\d{2,4}[A-Z]?)", haystack, re.IGNORECASE):
        sections.append(match.group(1).upper())
    return list(dict.fromkeys(sections))


def infer_crime_type(text: str) -> str:
    sections = extract_act_sections(text)
    for section in sections:
        base = re.sub(r"[A-Z]$", "", section)
        for key in (section, base):
            if key in SECTION_CRIME_MAP:
                return SECTION_CRIME_MAP[key]

    lower = text.lower()
    best_type = "Unknown"
    best_score = 0
    for crime_type, keywords in CRIME_KEYWORDS.items():
        score = sum(2 if kw in lower else 0 for kw in keywords)
        if score > best_score:
            best_score = score
            best_type = crime_type
    return best_type if best_score > 0 else "Unknown"


def extract_persons(text: str) -> list[PersonCreate]:
    """Extract complainants, accused, and victims from Karnataka FIR OCR text."""
    normalized = normalize_ocr_text(text)
    found: list[PersonCreate] = []

    def add_person(name: str, role: str) -> None:
        cleaned = _normalize_person_name(name)
        if not cleaned or _is_invalid_person_name(cleaned):
            return
        found.append(PersonCreate(name=cleaned, role=role))

    # Section 5 — Complainant / Informant
    complainant_patterns = [
        r"5\.?\s*Complainant\s*/?\s*Informant\s*:\s*([A-Za-z][A-Za-z\s\.]{2,70}?)\s*(?:\([a-z]\)|Email|Fax|Phone|Nationality|\(g\)|\(h\)|\(i\))",
        r"Complainant\s*/?\s*Informant\s*:\s*([A-Za-z][A-Za-z\s\.]{2,70}?)\s*(?:\([a-z]\)|Email|Fax|Phone|Nationality)",
    ]
    for pattern in complainant_patterns:
        match = re.search(pattern, normalized, re.IGNORECASE)
        if match:
            add_person(match.group(1), "victim")
            break

    # Section 6 — Accused table rows (Sl.No. N Accused Adult Male NAME(A1))
    for match in re.finditer(
        r"Sl\.No\.\s*\d+\s+Accused\s+(?:Adult|Minor)\s+(?:Male|Female)\s+([A-Z][A-Z0-9\s/]+?)\s*\(A\d+\)",
        normalized,
        re.IGNORECASE,
    ):
        add_person(match.group(1).split("/")[0].strip(), "accused")

    # Alternate accused pattern when spacing is still glued
    for match in re.finditer(
        r"Accused\s+(?:Adult|Minor)\s+(?:Male|Female)\s+([A-Z][A-Z0-9\s]+?)\(A\d+\)",
        normalized,
        re.IGNORECASE,
    ):
        add_person(match.group(1).strip(), "accused")

    # Section 7 — Victim table rows
    victim_block = re.search(
        r"7\.?\s*Details of Victims.*?8\.?\s*Particulars of Property",
        normalized,
        re.IGNORECASE | re.DOTALL,
    )
    victim_text = victim_block.group(0) if victim_block else normalized
    for match in re.finditer(
        r"Sl\.No\.\s*\d+\s+([A-Za-z][A-Za-z\s]+?)\s*(?:Male|Female)",
        victim_text,
        re.IGNORECASE,
    ):
        add_person(match.group(1), "victim")

    # Generic fallbacks for other FIR formats
    fallback_patterns = {
        "victim": [
            r"(?:Name of (?:the )?(?:Complainant|Victim|Informant))\s*[:\.]?\s*([A-Za-z][A-Za-z\s\.]{2,50}?)(?=\s*(?:Age|Address|Accused|Name|Son|D/o|S/o|$))",
            r"Complainant\s*[:\.]?\s*([A-Za-z][A-Za-z\s\.]{2,50}?)(?=\s*(?:Age|Address|Accused|Name|$))",
        ],
        "accused": [
            r"(?:Name of (?:the )?Accused|Accused/Suspect)\s*[:\.]?\s*([A-Za-z][A-Za-z\s\.]{2,50}?)(?=\s*(?:Age|Address|Complainant|Name|$))",
        ],
    }
    if not any(p.role == "accused" for p in found):
        for pattern in fallback_patterns["accused"]:
            match = re.search(pattern, normalized, re.IGNORECASE)
            if match:
                add_person(match.group(1), "accused")
                break

    return _dedupe_persons(found)


INVALID_PERSON_NAMES = {
    "unknown",
    "others",
    "other",
    "not known",
    "na",
    "nil",
    "none",
    "common man",
    "name and address not known",
    "name and address",
}


def _is_invalid_person_name(name: str) -> bool:
    lower = name.lower().strip()
    if len(lower) < 3:
        return True
    if lower in INVALID_PERSON_NAMES:
        return True
    return any(bad in lower for bad in ("not known", "address not known", "unknown,"))


def _normalize_person_name(raw: str) -> str | None:
    name = _clean_field(raw, max_len=80)
    if not name:
        return None
    # Remove accused markers like (A1)
    name = re.sub(r"\(A\d+\)", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s*/\s*.*$", "", name)  # drop father name after /
    # Split glued words: KumarDilip -> Kumar Dilip
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", name)
    name = re.sub(r"\s+", " ", name).strip(" .,-")
    if _is_invalid_person_name(name):
        return None
    return _title_field(name)


def _dedupe_persons(persons: list[PersonCreate]) -> list[PersonCreate]:
    """Deduplicate by normalized name; merge similar victim entries."""
    unique: list[PersonCreate] = []
    seen_keys: set[tuple[str, str]] = set()

    for person in persons:
        norm = re.sub(r"\s+", "", person.name.lower())
        key = (norm, person.role)
        if key in seen_keys:
            continue

        merged = False
        for idx, existing in enumerate(unique):
            if existing.role != person.role:
                continue
            ex_norm = re.sub(r"\s+", "", existing.name.lower())
            if norm in ex_norm or ex_norm in norm:
                if len(person.name) > len(existing.name):
                    unique[idx] = person
                merged = True
                break
        if merged:
            continue

        seen_keys.add(key)
        unique.append(person)
    return unique


def ensure_crime_persons(db: Session, crime: "CrimeRecord") -> "CrimeRecord":
    """Backfill persons from FIR description when missing (existing uploads)."""
    from app.models.crime import Person, PersonRole

    if crime.persons:
        return crime

    body = crime.description or ""
    body = re.sub(r"^\[Sections:[^\]]+\]\s*", "", body)
    extracted = extract_persons(body)
    if not extracted:
        return crime

    for person in extracted:
        crime.persons.append(
            Person(
                name=person.name,
                role=PersonRole(person.role),
                age=person.age,
                address=person.address,
            )
        )
    db.commit()
    db.refresh(crime)
    return crime


def _parse_date(raw: str) -> date | None:
    raw = raw.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _build_description(text: str, act_sections: list[str]) -> str:
    collapsed = re.sub(r"\s+", " ", text).strip()
    if act_sections:
        collapsed = f"[Sections: {', '.join(act_sections)}] {collapsed}"
    return collapsed[:4000] if collapsed else "Imported from document via OCR"


def _field_confidence(**fields: str | None) -> dict[str, str]:
    return {key: ("extracted" if val and str(val).lower() != "unknown" else "missing") for key, val in fields.items()}


def parse_fir_from_text(text: str, source_filename: str = "") -> tuple[CrimeRecordCreate, dict]:
    normalized = normalize_ocr_text(text)

    fir_number = extract_fir_number(normalized)
    generated = False
    if not fir_number:
        fir_number = f"FIR/OCR/{uuid.uuid4().hex[:8].upper()}"
        generated = True

    district = extract_district(normalized) or extract_district(text)
    police_station = extract_police_station(normalized) or extract_police_station(text)
    incident_date = extract_incident_date(normalized) or extract_incident_date(text)
    act_sections = extract_act_sections(normalized)
    crime_type = infer_crime_type(normalized)
    persons = extract_persons(normalized) or extract_persons(text)

    # Last-resort district from location alias scan on full body
    if not district:
        for canonical in detect_locations_in_message(normalized):
            district = CANONICAL_DISTRICT_LABEL.get(canonical)
            if district:
                break

    district = district or "Unknown"
    if district != "Unknown":
        district = _normalize_district_label(district)
    if crime_type == "Unknown" and act_sections:
        crime_type = infer_crime_type(f"Section {' '.join(act_sections)}")

    record = CrimeRecordCreate(
        fir_number=fir_number,
        crime_type=crime_type,
        description=_build_description(normalized, act_sections),
        district=district,
        police_station=police_station,
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
            "act_sections": act_sections,
            "persons_found": len(persons),
        },
        "field_confidence": _field_confidence(
            fir_number=None if generated else fir_number,
            district=record.district,
            police_station=record.police_station,
            crime_type=record.crime_type,
            incident_date=incident_date.isoformat() if incident_date else None,
        ),
    }
    return record, metadata
