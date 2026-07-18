from __future__ import annotations

import json
import shutil
import zipfile
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from audit_core import analyze_dossier
from audit_core.graph import _locator_id, build_evidence_graph
from audit_core.models import (
    CalculationTerm,
    CalculationTrace,
    DossierReport,
    EvidenceRef,
    Finding,
    ProcedureResult,
)
from audit_core.qa import _ModelClaim, _resolve_claims, answer_question
from services.api import main as api_main
from services.api.jobs import JobStore


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "Uebungsdaten_Muster_Verpackungen" / "Uebungsdaten Muster Verpackungen"


def minimal_report() -> DossierReport:
    amount_evidence = EvidenceRef(
        document="evidence.csv",
        locator_type="row",
        row=1,
        excerpt="amount=100",
        sha256="a" * 64,
    )
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
                evidence=[amount_evidence],
                calculation=CalculationTrace(
                    currency="EUR",
                    terms=[
                        CalculationTerm(
                            label="synthetic row 1",
                            value=Decimal("100"),
                            evidence=amount_evidence,
                        )
                    ],
                ),
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


def test_legacy_amount_report_requires_rerun(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = JobStore(tmp_path / "jobs")
    job = store.create("legacy")
    payload = minimal_report().model_dump(mode="json")
    del payload["findings"][0]["calculation"]
    (store.job_dir(job.id) / "report.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    store.update(job.id, report_ready=True)
    monkeypatch.setattr(api_main, "JOBS", store)

    response = TestClient(api_main.app).get(f"/api/dossiers/{job.id}/report")

    assert response.status_code == 409
    assert "rerun" in response.json()["detail"].casefold()


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

    assert graph.schema_version == "1.1"
    assert all(node.id in supported for node in graph.nodes if node.type == "finding")
    assert all(node.id in derived for node in graph.nodes if node.type == "calculation")


def test_graph_calculations_derive_only_from_exact_terms() -> None:
    report = analyze_dossier(SAMPLE)
    graph = build_evidence_graph(report)
    derived_by_calculation = {
        f"calculation:{finding.id}": {
            edge.target
            for edge in graph.edges
            if edge.source == f"calculation:{finding.id}"
            and edge.relation == "DERIVED_FROM"
        }
        for finding in report.findings
    }

    for finding in report.findings:
        assert finding.calculation is not None
        assert derived_by_calculation[f"calculation:{finding.id}"] == {
            _locator_id(term.evidence) for term in finding.calculation.terms
        }
    assert any(
        len(derived_by_calculation[f"calculation:{finding.id}"])
        < len(finding.evidence)
        for finding in report.findings
    )


def test_amount_findings_fail_closed_without_complete_lineage() -> None:
    report = minimal_report()
    valid = report.findings[0]
    other_evidence = valid.evidence[0].model_copy(update={"row": 2})

    with pytest.raises(ValidationError, match="exact calculation trace"):
        Finding(**valid.model_dump(exclude={"calculation"}))
    with pytest.raises(ValidationError, match="terms total"):
        Finding(
            **valid.model_dump(exclude={"calculation"}),
            calculation=valid.calculation.model_copy(
                update={
                    "terms": [
                        valid.calculation.terms[0].model_copy(
                            update={"value": Decimal("99")}
                        )
                    ]
                }
            ),
        )
    with pytest.raises(ValidationError, match="absent from finding evidence"):
        Finding(
            **valid.model_dump(exclude={"calculation"}),
            calculation=valid.calculation.model_copy(
                update={
                    "terms": [
                        valid.calculation.terms[0].model_copy(
                            update={"evidence": other_evidence}
                        )
                    ]
                }
            ),
        )
    with pytest.raises(ValidationError, match="currencies must match"):
        Finding(
            **valid.model_dump(exclude={"calculation"}),
            calculation=valid.calculation.model_copy(update={"currency": "USD"}),
        )
    with pytest.raises(ValidationError, match="cannot repeat"):
        Finding(
            **valid.model_dump(exclude={"amount", "calculation"}),
            amount=Decimal("200"),
            calculation=valid.calculation.model_copy(
                update={"terms": [valid.calculation.terms[0]] * 2}
            ),
        )


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
