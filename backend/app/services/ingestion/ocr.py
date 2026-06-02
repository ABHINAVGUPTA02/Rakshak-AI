"""OCR and text extraction for PDFs, images, and scanned documents."""

from __future__ import annotations

import io
import logging
import shutil
from dataclasses import dataclass

from PIL import Image, ImageEnhance, ImageFilter
from pypdf import PdfReader

from app.config import settings

logger = logging.getLogger(__name__)

MIN_NATIVE_TEXT_CHARS = 80
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp", ".bmp"}


@dataclass
class ExtractionResult:
    text: str
    method: str  # native_text | ocr | hybrid
    page_count: int = 1
    warnings: list[str] | None = None


def _tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def _preprocess_image(image: Image.Image) -> Image.Image:
    gray = image.convert("L")
    enhanced = ImageEnhance.Contrast(gray).enhance(1.8)
    return enhanced.filter(ImageFilter.SHARPEN)


def ocr_image(image: Image.Image, languages: str | None = None) -> str:
    import pytesseract

    lang = languages or settings.ocr_languages
    processed = _preprocess_image(image)
    return pytesseract.image_to_string(processed, lang=lang)


def extract_text_from_image(content: bytes, languages: str | None = None) -> ExtractionResult:
    warnings: list[str] = []
    if not _tesseract_available():
        return ExtractionResult(
            text="",
            method="ocr",
            warnings=["Tesseract OCR is not installed. Run: brew install tesseract tesseract-lang"],
        )

    image = Image.open(io.BytesIO(content))
    text = ocr_image(image, languages)
    if not text.strip():
        warnings.append("OCR returned empty text — image may be low quality or unreadable.")
    return ExtractionResult(text=text.strip(), method="ocr", page_count=1, warnings=warnings)


def _extract_pdf_native(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


def _extract_pdf_via_pymupdf(content: bytes) -> tuple[str, list[Image.Image]]:
    import fitz

    doc = fitz.open(stream=content, filetype="pdf")
    native_parts: list[str] = []
    page_images: list[Image.Image] = []

    for page in doc:
        page_text = page.get_text().strip()
        native_parts.append(page_text)
        if len(page_text) < MIN_NATIVE_TEXT_CHARS:
            pix = page.get_pixmap(dpi=settings.ocr_dpi)
            page_images.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))

    doc.close()
    return "\n".join(native_parts).strip(), page_images


def extract_text_from_pdf(content: bytes, languages: str | None = None) -> ExtractionResult:
    warnings: list[str] = []
    native_text = _extract_pdf_native(content)
    page_count = len(PdfReader(io.BytesIO(content)).pages)

    if len(native_text) >= MIN_NATIVE_TEXT_CHARS:
        return ExtractionResult(text=native_text, method="native_text", page_count=page_count)

    if not _tesseract_available():
        if native_text:
            return ExtractionResult(
                text=native_text,
                method="native_text",
                page_count=page_count,
                warnings=[
                    "Scanned PDF detected but Tesseract is not installed.",
                    "Install: brew install tesseract tesseract-lang",
                ],
            )
        return ExtractionResult(
            text="",
            method="native_text",
            page_count=page_count,
            warnings=["No extractable text and Tesseract OCR is not installed."],
        )

    try:
        combined_native, page_images = _extract_pdf_via_pymupdf(content)
    except Exception as exc:
        logger.warning("PyMuPDF extraction failed: %s", exc)
        combined_native = native_text
        page_images = []

    ocr_parts: list[str] = []
    for idx, image in enumerate(page_images):
        try:
            ocr_parts.append(ocr_image(image, languages))
        except Exception as exc:
            warnings.append(f"OCR failed on page {idx + 1}: {exc}")

    ocr_text = "\n".join(part.strip() for part in ocr_parts if part.strip())
    merged = "\n".join(part for part in [combined_native, ocr_text, native_text] if part).strip()

    if merged and ocr_text:
        method = "hybrid" if combined_native or native_text else "ocr"
    elif merged:
        method = "native_text"
    else:
        method = "ocr"
        warnings.append("Could not extract readable text from PDF.")

    return ExtractionResult(text=merged, method=method, page_count=page_count, warnings=warnings)


def extract_text_from_document(content: bytes, suffix: str) -> ExtractionResult:
    from app.services.ingestion.text_normalizer import normalize_ocr_text

    suffix = suffix.lower()
    if suffix == ".pdf":
        result = extract_text_from_pdf(content)
    elif suffix in IMAGE_EXTENSIONS:
        result = extract_text_from_image(content)
    else:
        raise ValueError(f"Unsupported document type for OCR: {suffix}")

    if result.text.strip():
        result.text = normalize_ocr_text(result.text)
    return result
