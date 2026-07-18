from __future__ import annotations

import shutil
import zipfile
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from audit_core import analyze_dossier
from audit_core.graph import build_evidence_graph
from audit_core.models import DossierReport, EvidenceRef, Finding, ProcedureResult
from audit_core.qa import _ModelClaim, _resolve_claims, answer_question
from services.api import main as api_main
from services.api.jobs import JobStore


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "Uebungsdaten_Muster_Verpackungen" / "Uebungsdaten Muster Verpackungen"


def minimal_report() -> DossierReport:
    return DossierReport(
        dossier_name="Synthetic review dossier",
        files_scanned=1,
        tests_run=1,
        findings=[
            Finding(
                id="finding-1",
                rule_id="SYNTHETIC_RULE",
                category="control",
                severity="medium",
                confidence=Decimal("0.95"),
                title="Synthetic sourced exception",
                summary="A synthetic exception used only to test the review workflow.",
                amount=Decimal("100"),
                currency="EUR",
                affected_entities=["ENTITY-1"],
                evidence=[
                    EvidenceRef(
                        document="evidence.csv",
                        locator_type="row",
                        row=1,
                        excerpt="amount=100",
                        sha256="a" * 64,
                    )
                ],
                next_step="Inspect the source row.",
            )
        ],
        procedures=[ProcedureResult(rule_id="SYNTHETIC_RULE", status="completed")],
    )


def test_missing_input_marks_procedure_not_testable(tmp_path: Path) -> None:
    dossier = tmp_path / "dossier"
    shutil.copytree(SAMPLE, dossier)
    next((dossier / "Begleitdokumente").glob("*Pruefungsplanung*.docx")).unlink()

    report = analyze_dossier(dossier)
    split = next(
        procedure
        for procedure in report.procedures
        if procedure.rule_id == "SPLIT_PAYMENTS_BELOW_THRESHOLD"
    )

    assert split.status == "not_testable"
    assert all(
        finding.rule_id != "SPLIT_PAYMENTS_BELOW_THRESHOLD" for finding in report.findings
    )


def test_local_job_store_rejects_zip_path_traversal(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs")
    job = store.create("unsafe")
    archive = store.incoming_dir(job.id) / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../outside.txt", "must not escape")

    with pytest.raises(ValueError, match="Unsafe archive path"):
        store.prepare_source(job.id)

    assert not (tmp_path / "outside.txt").exists()


@pytest.mark.parametrize("origin", ["http://localhost:3000", "http://127.0.0.1:3000"])
@pytest.mark.parametrize("method", ["GET", "PUT"])
def test_local_api_cors_allows_demo_origins_and_methods(
    origin: str,
    method: str,
) -> None:
    response = TestClient(api_main.app).options(
        "/api/rules",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_review_dispositions_validate_and_survive_store_reload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = JobStore(tmp_path / "jobs")
    job = store.create("review")
    store.save_report(job.id, minimal_report())
    monkeypatch.setattr(api_main, "JOBS", store)
    client = TestClient(api_main.app)
    endpoint = f"/api/dossiers/{job.id}/reviews/finding-1"

    rejected = client.put(
        endpoint,
        json={"status": "dismissed", "note": "no"},
    )
    saved = client.put(
        endpoint,
        json={
            "status": "dismissed",
            "note": "Explained clean item after source inspection.",
            "reviewer": "Test auditor",
        },
    )
    unknown = client.put(
        f"/api/dossiers/{job.id}/reviews/missing-finding",
        json={"status": "confirmed"},
    )
    reviews = client.get(f"/api/dossiers/{job.id}/reviews")

    assert rejected.status_code == 422
    assert saved.status_code == 200
    assert saved.json()["finding_id"] == "finding-1"
    assert saved.json()["status"] == "dismissed"
    assert unknown.status_code == 404
    assert reviews.json() == [saved.json()]
    reloaded = JobStore(tmp_path / "jobs").reviews(job.id)
    assert reloaded[0].note == "Explained clean item after source inspection."


def test_deterministic_question_answer_keeps_source_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    report = analyze_dossier(SAMPLE)

    answer = answer_question(report, "Which repair costs were capitalised?")

    assert answer.status == "answered"
    assert answer.claims
    assert all(claim.finding_ids for claim in answer.claims)
    assert all(claim.evidence for claim in answer.claims)
    assert all(reference.sha256 for claim in answer.claims for reference in claim.evidence)


def test_graph_projection_links_findings_and_calculations_to_locators() -> None:
    graph = build_evidence_graph(analyze_dossier(SAMPLE))
    supported = {edge.source for edge in graph.edges if edge.relation == "SUPPORTED_BY"}
    derived = {edge.source for edge in graph.edges if edge.relation == "DERIVED_FROM"}

    assert all(node.id in supported for node in graph.nodes if node.type == "finding")
    assert all(node.id in derived for node in graph.nodes if node.type == "calculation")


def test_model_claims_hide_raw_ids_and_reject_unsupported_numbers() -> None:
    report = analyze_dossier(SAMPLE)
    finding = report.findings[0]
    accepted = _resolve_claims(
        report,
        [
            _ModelClaim(
                statement=f"Finding {finding.id} is supported by the dossier.",
                finding_ids=[finding.id],
            )
        ],
    )
    rejected = _resolve_claims(
        report,
        [_ModelClaim(statement="The unsupported exposure is 999999999.", finding_ids=[finding.id])],
    )

    assert accepted and finding.id not in accepted[0].statement
    assert rejected == []
