"""Extract phones, emails, vehicles, accounts, and property from FIR / crime text."""

from __future__ import annotations

import re

from app.schemas.entity import EntityCreate

# Indian mobile: 10 digits starting 6-9
PHONE_PATTERN = re.compile(
    r"(?:Phone\s*No\.?|Mobile|Contact|Tel)\s*[:\.]?\s*([6-9]\d{9})\b",
    re.IGNORECASE,
)
PHONE_FALLBACK = re.compile(r"\b([6-9]\d{9})\b")

EMAIL_PATTERN = re.compile(r"\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b")

# Karnataka vehicle registration (e.g. KA 01 AB 1234, KA01AB1234)
VEHICLE_PATTERN = re.compile(
    r"\b(KA\s*\d{1,2}\s*[A-Z]{1,3}\s*\d{3,4})\b",
    re.IGNORECASE,
)

UPI_PATTERN = re.compile(
    r"\b([a-zA-Z0-9._-]+@[a-zA-Z]{2,15})\b",  # overlap with email — filter @paytm etc.
)
UPI_VPA_PATTERN = re.compile(r"\b([6-9]\d{9}@[a-zA-Z]+)\b", re.IGNORECASE)

ACCOUNT_PATTERN = re.compile(
    r"(?:A/?c(?:count)?|Account)\s*(?:No\.?|Number)?\s*[:\.]?\s*(\d{8,18})",
    re.IGNORECASE,
)

IFSC_PATTERN = re.compile(r"\b([A-Z]{4}0[A-Z0-9]{6})\b")

PROPERTY_VALUE_PATTERN = re.compile(
    r"Total\s+Value\s+of\s+the\s+property\s+Stolen\s*/?\s*Involved\s*[:\.]?\s*(?:Rs\.?|INR)?\s*([\d,]+)",
    re.IGNORECASE,
)

PROPERTY_ITEM_PATTERN = re.compile(
    r"(?:Item\s+description|Property\s+Type|Main\s+Description)\s*[:\.]?\s*([^|]+?)(?=Sub\s+Description|Quantity|Total\s+Value|Sl\.No|$)",
    re.IGNORECASE,
)

PASSPORT_PATTERN = re.compile(
    r"Passport\s*No\.?\s*#?\s*([A-Z0-9]{6,12})",
    re.IGNORECASE,
)


def _normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits if len(digits) == 10 else raw.strip()


def _normalize_vehicle(raw: str) -> str:
    return re.sub(r"\s+", "", raw.upper())


def _dedupe_entities(entities: list[EntityCreate]) -> list[EntityCreate]:
    seen: set[tuple[str, str]] = set()
    unique: list[EntityCreate] = []
    for ent in entities:
        key = (ent.kind.lower(), ent.value.lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(ent)
    return unique


def extract_phones(text: str, role_hint: str | None = None) -> list[EntityCreate]:
    found: list[EntityCreate] = []
    seen: set[str] = set()

    for match in PHONE_PATTERN.finditer(text):
        phone = _normalize_phone(match.group(1))
        if phone in seen or len(phone) != 10:
            continue
        seen.add(phone)
        found.append(EntityCreate(kind="phone", value=phone, label="Phone from FIR", role=role_hint))

    if not found:
        for match in PHONE_FALLBACK.finditer(text):
            phone = _normalize_phone(match.group(1))
            if phone in seen:
                continue
            # Skip numbers that look like dates or FIR fragments
            if phone.startswith(("202", "201", "199")):
                continue
            seen.add(phone)
            found.append(EntityCreate(kind="phone", value=phone, label="Phone from FIR", role=role_hint))

    return found


def extract_emails(text: str, role_hint: str | None = None) -> list[EntityCreate]:
    found: list[EntityCreate] = []
    for match in EMAIL_PATTERN.finditer(text):
        email = match.group(1).lower()
        email = re.sub(r"^(?:fax|email)", "", email)
        if "@" not in email or len(email) < 6:
            continue
        found.append(EntityCreate(kind="email", value=email, label="Email from FIR", role=role_hint))
    return found


def extract_vehicles(text: str) -> list[EntityCreate]:
    found: list[EntityCreate] = []
    seen: set[str] = set()
    for match in VEHICLE_PATTERN.finditer(text):
        plate = _normalize_vehicle(match.group(1))
        if plate in seen:
            continue
        seen.add(plate)
        found.append(EntityCreate(kind="vehicle", value=plate, label="Vehicle registration"))
    # Keyword-based vehicle mentions without plate
    if re.search(r"\b(?:two\s*wheeler|motor\s*cycle|bike|car|auto|vehicle|scooter)\b", text, re.I):
        if not found:
            found.append(
                EntityCreate(kind="vehicle", value="VEHICLE_MENTIONED", label="Vehicle mentioned in FIR")
            )
    return found


def extract_accounts_and_financial(text: str) -> list[EntityCreate]:
    found: list[EntityCreate] = []
    seen: set[str] = set()

    for match in UPI_VPA_PATTERN.finditer(text):
        vpa = match.group(1).lower()
        if vpa not in seen:
            seen.add(vpa)
            found.append(EntityCreate(kind="account", value=vpa, label="UPI VPA"))

    for match in ACCOUNT_PATTERN.finditer(text):
        acct = match.group(1)
        if acct not in seen:
            seen.add(acct)
            found.append(EntityCreate(kind="account", value=acct, label="Bank account number"))

    for match in IFSC_PATTERN.finditer(text):
        ifsc = match.group(1).upper()
        if ifsc not in seen:
            seen.add(ifsc)
            found.append(EntityCreate(kind="account", value=ifsc, label="IFSC code"))

    value_match = PROPERTY_VALUE_PATTERN.search(text)
    if value_match:
        amount = re.sub(r"[^\d]", "", value_match.group(1))
        if amount and amount not in seen:
            seen.add(amount)
            found.append(
                EntityCreate(
                    kind="account",
                    value=f"INR_{amount}",
                    label=f"Stolen/involved property value: Rs. {value_match.group(1)}",
                )
            )

    if re.search(r"\b(?:UPI|NEFT|RTGS|IMPS|cyber|online\s+transfer|phishing)\b", text, re.I):
        key = "CYBER_FINANCIAL"
        if key not in seen:
            found.append(EntityCreate(kind="account", value=key, label="Financial/cyber crime indicator"))

    return found


def extract_property(text: str) -> list[EntityCreate]:
    found: list[EntityCreate] = []
    block = re.search(
        r"8\.?\s*Particulars of Property stolen.*?(?:9\.|Inquest Report|$)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    haystack = block.group(0) if block else text

    for match in PROPERTY_ITEM_PATTERN.finditer(haystack):
        desc = re.sub(r"\s+", " ", match.group(1)).strip(" :,-")[:200]
        if len(desc) >= 3 and desc.lower() not in {"na", "nil", "unknown"}:
            found.append(EntityCreate(kind="property", value=desc[:120], label="Stolen property item"))

    if re.search(r"\b(?:mobile|laptop|cash|jewel|gold|chain|phone)\b", haystack, re.I) and not found:
        for kw in ("mobile", "cash", "laptop", "jewellery", "chain", "phone"):
            if re.search(rf"\b{kw}\b", haystack, re.I):
                found.append(EntityCreate(kind="property", value=kw.upper(), label=f"Stolen: {kw}"))
                break

    return found


def extract_documents(text: str, role_hint: str | None = None) -> list[EntityCreate]:
    found: list[EntityCreate] = []
    for match in PASSPORT_PATTERN.finditer(text):
        doc_id = match.group(1).upper()
        found.append(
            EntityCreate(kind="document", value=doc_id, label="Passport number", role=role_hint)
        )
    return found


def extract_entities(text: str) -> list[EntityCreate]:
    """Extract all entity types from normalized FIR text."""
    if not text.strip():
        return []

    complainant_block = ""
    cm = re.search(
        r"5\.?\s*Complainant\s*/?\s*Informant.*?(?:6\.|Details of known)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if cm:
        complainant_block = cm.group(0)

    entities: list[EntityCreate] = []
    entities.extend(extract_phones(complainant_block or text, role_hint="victim"))
    entities.extend(extract_emails(complainant_block or text, role_hint="victim"))
    entities.extend(extract_documents(complainant_block or text, role_hint="victim"))
    entities.extend(extract_phones(text))  # any other phones in full doc
    entities.extend(extract_emails(text))
    entities.extend(extract_vehicles(text))
    entities.extend(extract_accounts_and_financial(text))
    entities.extend(extract_property(text))

    return _dedupe_entities(entities)
