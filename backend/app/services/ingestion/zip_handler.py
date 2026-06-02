"""Safe extraction and batch ingestion of ZIP archives containing FIR files."""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

from app.services.ingestion.ocr import IMAGE_EXTENSIONS

logger = logging.getLogger(__name__)

SPREADSHEET_EXTENSIONS = {".xlsx", ".xls", ".csv"}
DOCUMENT_EXTENSIONS = {".pdf", *IMAGE_EXTENSIONS}
INGESTABLE_EXTENSIONS = SPREADSHEET_EXTENSIONS | DOCUMENT_EXTENSIONS

MAX_FILES_IN_ARCHIVE = 50
MAX_MEMBER_BYTES = 25 * 1024 * 1024  # 25 MB per file
MAX_TOTAL_UNCOMPRESSED = 150 * 1024 * 1024  # 150 MB total


def _is_safe_member(name: str) -> bool:
    path = Path(name)
    if path.is_absolute() or ".." in path.parts:
        return False
    return True


def _member_basename(name: str) -> str:
    return Path(name).name


def iter_archive_files(content: bytes) -> tuple[list[tuple[str, bytes]], list[str]]:
    """
    Extract supported files from a ZIP archive in memory.
    Returns ([(filename, content), ...], warnings).
    """
    warnings: list[str] = []
    extracted: list[tuple[str, bytes]] = []
    total_size = 0

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = [info for info in archive.infolist() if not info.is_dir()]
            if len(members) > MAX_FILES_IN_ARCHIVE:
                warnings.append(
                    f"Archive has {len(members)} files; only the first {MAX_FILES_IN_ARCHIVE} supported files are processed."
                )
                members = members[: MAX_FILES_IN_ARCHIVE * 2]

            for info in members:
                if len(extracted) >= MAX_FILES_IN_ARCHIVE:
                    break

                if not _is_safe_member(info.filename):
                    warnings.append(f"Skipped unsafe path: {info.filename}")
                    continue

                basename = _member_basename(info.filename)
                if not basename or basename.startswith("."):
                    continue

                suffix = Path(basename).suffix.lower()
                if suffix not in INGESTABLE_EXTENSIONS:
                    continue

                if info.file_size > MAX_MEMBER_BYTES:
                    warnings.append(f"Skipped {basename}: file exceeds size limit ({MAX_MEMBER_BYTES // (1024 * 1024)} MB).")
                    continue

                total_size += info.file_size
                if total_size > MAX_TOTAL_UNCOMPRESSED:
                    warnings.append("Archive uncompressed size limit reached; remaining files skipped.")
                    break

                try:
                    data = archive.read(info)
                except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
                    warnings.append(f"Could not read {basename}: {exc}")
                    continue

                if len(data) > MAX_MEMBER_BYTES:
                    warnings.append(f"Skipped {basename}: exceeds size limit after extraction.")
                    continue

                extracted.append((basename, data))

    except zipfile.BadZipFile:
        warnings.append("Invalid or corrupted ZIP archive.")
        return [], warnings

    if not extracted and not warnings:
        warnings.append(
            "No supported files in archive. Include PDFs, images, or datasets: "
            "firs, persons, fir_person_links, transactions, calls (CSV/Excel)."
        )

    return extracted, warnings
