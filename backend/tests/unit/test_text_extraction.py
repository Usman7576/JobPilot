from __future__ import annotations

import pytest

from app.domain.text_extraction import (
    ExtractionError,
    extract_text,
    normalize_text,
    pdf_page_count,
    sniff_kind,
)
from tests.fixtures import RESUME_LINES, make_docx, make_pdf


def test_sniff_by_content_not_name() -> None:
    assert sniff_kind(make_pdf()) == "pdf"
    assert sniff_kind(make_docx()) == "docx"
    assert sniff_kind(b"PK\x03\x04 not really a zip") is None
    assert sniff_kind(b"<html>resume</html>") is None


def test_pdf_text_extraction() -> None:
    result = extract_text(make_pdf(), "pdf", max_pages=10)
    assert result.pages == 1
    assert "Ada Lovelace" in result.text
    assert "Cut PostgreSQL query latency by 40%" in result.text


def test_docx_text_extraction() -> None:
    result = extract_text(make_docx(), "docx", max_pages=10)
    assert "Analytical Engines Ltd" in result.text
    assert result.text.count("Ada Lovelace") == 1


def test_too_many_pages() -> None:
    pdf = make_pdf([RESUME_LINES] * 3)
    assert pdf_page_count(pdf) == 3
    with pytest.raises(ExtractionError) as exc:
        extract_text(pdf, "pdf", max_pages=2)
    assert exc.value.code == "too_many_pages"


def test_scanned_or_empty_pdf_reports_no_text() -> None:
    with pytest.raises(ExtractionError) as exc:
        extract_text(make_pdf([["Hi"]]), "pdf", max_pages=10)
    assert exc.value.code == "no_text"


def test_normalize_drops_repeated_headers_and_page_numbers() -> None:
    pages = [
        "Ada Lovelace - Resume\nPython engineer\nPage 1 of 2",
        "Ada Lovelace - Resume\nBuilt APIs with Fast-\nAPI\n2",
    ]
    text = normalize_text(pages)
    assert "Ada Lovelace - Resume" not in text
    assert "Page 1" not in text
    assert "FastAPI" in text  # hyphenated line break re-joined
