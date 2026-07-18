from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter

from audit_core import analyze_dossier
from audit_core.discovery import discover_dossier, pdf_role_matches
from audit_core.models import EvidenceRef
from audit_core.parsers import read_pdf_passages
from services.api import main as api_main
from services.api.jobs import JobStore


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "Uebungsdaten_Muster_Verpackungen" / "Uebungsdaten Muster Verpackungen"
PDF_DIR = SAMPLE / "Begleitdokumente"
STATEMENTS = PDF_DIR / "JA-Entwurf_2025_Auszug_Bilanz_GuV.pdf"


def test_sample_pdfs_are_classified_from_native_page_text() -> None:
    coverage = discover_dossier(SAMPLE)
    pdfs = {item.document: item for item in coverage.documents if item.format == "pdf"}

    assert len(pdfs) == 3
    assert {role for item in pdfs.values() for role in item.role_matches} == {
        "export_manifest",
        "financial_statements",
        "it_completeness_confirmation",
    }
    assert all(item.status == "recognized" for item in pdfs.values())
    assert all(item.extraction_status == "native" for item in pdfs.values())
    assert all(item.page_count == item.extracted_pages == 1 for item in pdfs.values())
    assert all(item.passage_count > 0 for item in pdfs.values())
    assert coverage.source_passages
    assert all(reference.locator_type == "page" for reference in coverage.source_passages)
    assert all(reference.page and reference.passage for reference in coverage.source_passages)
    assert all(reference.sha256 for reference in coverage.source_passages)


def test_mixed_pdf_is_partial_and_keeps_native_page_passages(tmp_path: Path) -> None:
    target = tmp_path / "mixed.pdf"
    writer = PdfWriter()
    writer.add_page(PdfReader(STATEMENTS).pages[0])
    writer.add_blank_page(width=612, height=792)
    with target.open("wb") as destination:
        writer.write(destination)

    extraction = read_pdf_passages(target, tmp_path)
    coverage = discover_dossier(tmp_path)
    document = next(item for item in coverage.documents if item.document == "mixed.pdf")

    assert extraction.status == "partial"
    assert extraction.page_count == 2
    assert extraction.extracted_pages == 1
    assert extraction.passages
    assert {passage.page for passage in extraction.passages} == {1}
    assert document.extraction_status == "partial"
    assert document.role_matches == ["financial_statements"]


def test_image_only_pdf_is_explicitly_unreadable_without_ocr(tmp_path: Path) -> None:
    target = tmp_path / "scan.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with target.open("wb") as destination:
        writer.write(destination)

    coverage = discover_dossier(tmp_path)
    document = next(item for item in coverage.documents if item.document == "scan.pdf")

    assert document.status == "unsupported"
    assert document.extraction_status == "unreadable"
    assert document.page_count == 1
    assert document.extracted_pages == 0
    assert document.passage_count == 0
    assert "OCR is disabled" in document.reason
    assert coverage.source_passages == []


def test_unrelated_passage_is_not_misclassified_as_financial_pdf() -> None:
    passage = EvidenceRef(
        document="clean.pdf",
        locator_type="page",
        page=1,
        passage="lines:1-2",
        excerpt="Employee handbook\nOffice opening hours and holiday calendar",
        sha256="0" * 64,
    )

    assert pdf_role_matches([passage]) == []


def test_document_api_exposes_pdf_extraction_coverage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = JobStore(tmp_path / "jobs")
    job = store.create("pdf-coverage")
    store.save_source_root(job.id, SAMPLE)
    store.save_report(job.id, analyze_dossier(SAMPLE))
    monkeypatch.setattr(api_main, "JOBS", store)

    response = TestClient(api_main.app).get(f"/api/dossiers/{job.id}/documents")

    assert response.status_code == 200
    pdfs = [item for item in response.json() if item["extension"] == "pdf"]
    assert len(pdfs) == 3
    assert all(item["extraction_status"] == "native" for item in pdfs)
    assert all(item["page_count"] == item["extracted_pages"] == 1 for item in pdfs)
    assert all(item["passage_count"] > 0 for item in pdfs)
    assert {item["role"] for item in pdfs} == {
        "export_manifest",
        "financial_statements",
        "it_completeness_confirmation",
    }
