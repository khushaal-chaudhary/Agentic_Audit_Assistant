from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import pytest

from audit_core import analyze_dossier
from audit_core.graph import build_evidence_graph
from audit_core.qa import _ModelClaim, _resolve_claims, answer_question
from services.api.jobs import JobStore


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "Uebungsdaten_Muster_Verpackungen" / "Uebungsdaten Muster Verpackungen"


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
