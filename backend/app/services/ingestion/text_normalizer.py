"""Normalize OCR / PDF text before FIR field extraction."""

from __future__ import annotations

import re

# Labels commonly glued to preceding text in Karnataka FIR OCR output
FIELD_LABELS = [
    "FIRST INFORMATION REPORT",
    "KARNATAKA STATE POLICE",
    "District",
    "Crime No",
    "FIR No",
    "FIR Number",
    "FIR Date",
    "Date of Occurrence",
    "Date of Incident",
    "Circle/Sub Division",
    "Circle",
    "Sub Division",
    "Police Station",
    "PS",
    "Act & Section",
    "Act and Section",
    "Section",
    "Complainant",
    "Name of Complainant",
    "Name of the Complainant",
    "Accused",
    "Name of Accused",
    "Victim",
    "Informant",
    "Under Section",
]

# Fix known OCR word glues
GLUE_FIXES = [
    (r"CityCrime", "City Crime"),
    (r"Dist(?:rict)?Crime", "Dist Crime"),
    (r"DivisPS", "Divis PS"),
    (r"Divis\s*PS", "Divis PS"),
    (r"StatePolice", "State Police"),
    (r"PoliceBefore", "Police Before"),
    (r"Sanhita\)(\d)", r"Sanhita) \1"),
    (r"(\d)\.(District)", r"\1. \2"),
    (r"(\w)(District\s*:)", r"\1 \2"),
    (r"(\w)(Crime\s*No\s*:)", r"\1 \2"),
    (r"(\w)(FIR\s*Date\s*:)", r"\1 \2"),
    (r"(\w)(PS\s*:)", r"\1 \2"),
    (r"Accused(Adult|Minor)(Male|Female)", r"Accused \1 \2"),
    (r"Sl\.No\.(\d+)([A-Za-z])", r"Sl.No.\1 \2"),
    (r"(Male|Female)([A-Z#])", r"\1 \2"),
    (r"Fax([a-zA-Z0-9._%+-]+@)", r"Fax \1"),
]


def normalize_ocr_text(text: str) -> str:
    if not text:
        return ""

    # Standardize unicode dashes and colons
    text = text.replace("\u2013", "-").replace("\u2014", "-").replace("：", ":")
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    for pattern, replacement in GLUE_FIXES:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # Insert space before field labels when glued to prior characters
    for label in sorted(FIELD_LABELS, key=len, reverse=True):
        text = re.sub(
            rf"(?<=[A-Za-z0-9\)])({re.escape(label)})",
            r" \1",
            text,
            flags=re.IGNORECASE,
        )

    # Ensure colon-separated fields have spacing
    text = re.sub(r"\s*:\s*", " : ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
