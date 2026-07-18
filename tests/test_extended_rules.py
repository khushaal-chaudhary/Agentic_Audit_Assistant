from __future__ import annotations

from decimal import Decimal
from hashlib import sha256
from pathlib import Path

from audit_core.engine import AuditEngine, _declared_gl_row_count
from audit_core.models import EvidenceRef, IngestionCoverage, IngestionRole
from audit_core.parsers import extract_jet_threshold
from tests.factories import ScenarioFactory


def _page(path: Path, root: Path, excerpt: str) -> EvidenceRef:
    path.write_text(excerpt, encoding="utf-8")
    return EvidenceRef(
        document=path.relative_to(root).as_posix(),
        locator_type="page",
        page=1,
        passage="lines:1-3",
        excerpt=excerpt,
        sha256=sha256(path.read_bytes()).hexdigest(),
    )


def _completeness_engine(
    tmp_path: Path,
    export_count: str,
    confirmation_count: str,
    physical_count: int,
) -> AuditEngine:
    export_ref = _page(
        tmp_path / "export.pdf",
        tmp_path,
        f"Sachkonten/Sachkontobuchungen.txt\n{export_count}\n0,00 EUR",
    )
    confirmation_ref = _page(
        tmp_path / "confirmation.pdf",
        tmp_path,
        f"The file Sachkontobuchungen.txt contains all {confirmation_count} ledger rows.",
    )
    ledger = tmp_path / "ledger.txt"
    ledger.write_text("", encoding="utf-8")
    engine = AuditEngine.__new__(AuditEngine)
    engine.root = tmp_path
    engine.gl_path = ledger
    engine.gl_row_count = physical_count
    engine.discovery = IngestionCoverage(
        roles=[
            IngestionRole(
                role="export_manifest",
                status="resolved",
                document="export.pdf",
                reason="test",
            ),
            IngestionRole(
                role="it_completeness_confirmation",
                status="resolved",
                document="confirmation.pdf",
                reason="test",
            ),
        ],
        source_passages=[export_ref, confirmation_ref],
    )
    return engine


def test_completeness_reconciliation_publishes_exact_source_mismatch(
    tmp_path: Path,
) -> None:
    engine = _completeness_engine(tmp_path, "1.083.723", "1.083.713", 1_083_723)

    findings = engine.detect_export_completeness_mismatch()

    assert len(findings) == 1
    assert findings[0].rule_id == "EXPORT_COMPLETENESS_RECONCILIATION"
    assert {reference.locator_type for reference in findings[0].evidence} == {
        "page",
        "query",
    }
    assert "1083723" in findings[0].summary
    assert "1083713" in findings[0].summary


def test_completeness_reconciliation_clean_twin_stays_clean(tmp_path: Path) -> None:
    engine = _completeness_engine(tmp_path, "1,083,723", "1.083.723", 1_083_723)

    assert engine.detect_export_completeness_mismatch() == []


def test_declared_count_rejects_unrelated_numeric_passage(tmp_path: Path) -> None:
    reference = _page(
        tmp_path / "unrelated.pdf",
        tmp_path,
        "Financial report dated 31.12.2025 with revenue of 1,083,723 EUR.",
    )

    assert _declared_gl_row_count([reference]) is None


def _approval_engine(
    factory: ScenarioFactory,
    *,
    creator: str = "USER-1",
    approver: str = "USER-1",
    status: str = "Approved (creator=approver)",
    absolute_amount: str = "120000",
    threshold_text: str = "Clearly trivial threshold: 50,000 EUR",
) -> AuditEngine:
    positive = factory.row(
        "ledger.txt",
        SACHKONTONUMMER="600000",
        BUCHUNGSNUMMER="J-1",
        BUCHUNGSDATUM="2031-12-31",
        BUCHUNGSBETRAG="60000",
        BUCHUNGSTEXT="Manual adjustment",
        ERFASSUNGSNUMMER="CAP-1",
        BENUTZERKENNUNG=creator,
        ERFASSUNGSDATUM="2032-01-02",
        ERFASSUNGSZEIT="09:00:00",
        BUCHUNGSTYP="Created Journals",
    )
    negative = factory.row(
        "ledger.txt",
        SACHKONTONUMMER="290000",
        BUCHUNGSNUMMER="J-1",
        BUCHUNGSDATUM="2031-12-31",
        BUCHUNGSBETRAG="-60000",
        BUCHUNGSTEXT="Manual adjustment",
        ERFASSUNGSNUMMER="CAP-1",
        BENUTZERKENNUNG=creator,
        ERFASSUNGSDATUM="2032-01-02",
        ERFASSUNGSZEIT="09:00:00",
        BUCHUNGSTYP="Created Journals",
    )
    approval = factory.row(
        "approval.csv",
        ERFASSUNGSNUMMER="CAP-1",
        JOURNALNAME="GL-1",
        ANZAHL_ZEILEN="2",
        SUMME_ABS_EUR=absolute_amount,
        ERSTELLER=creator,
        ERFASST_AM="2032-01-02",
        ERFASST_UM="09:00:00",
        FREIGEBER=approver,
        FREIGABESTATUS=status,
    )
    planning = factory.passage("planning.docx", threshold_text)
    engine = factory.engine(gl=[positive, negative], planning=[planning])
    engine.journal_approvals = [approval]
    engine.gl_by_capture = {"CAP-1": [positive, negative]}
    return engine


def test_material_self_approved_manual_journal_publishes_with_exact_terms(
    tmp_path: Path,
) -> None:
    engine = _approval_engine(ScenarioFactory(tmp_path))

    findings, suppressed = engine.detect_manual_journal_approval_violations()

    assert suppressed == 0
    assert len(findings) == 1
    finding = findings[0]
    assert finding.rule_id == "MANUAL_JOURNAL_APPROVAL_VIOLATION"
    assert finding.amount == Decimal("60000")
    assert finding.calculation is not None
    assert [term.value for term in finding.calculation.terms] == [Decimal("60000")]
    assert finding.calculation.terms[0].evidence in finding.evidence


def test_independently_approved_manual_journal_is_clean(tmp_path: Path) -> None:
    engine = _approval_engine(
        ScenarioFactory(tmp_path),
        approver="USER-2",
        status="Approved",
    )

    findings, suppressed = engine.detect_manual_journal_approval_violations()

    assert findings == []
    assert suppressed == 0


def test_below_threshold_approval_exception_is_suppressed(tmp_path: Path) -> None:
    engine = _approval_engine(
        ScenarioFactory(tmp_path),
        absolute_amount="40000",
    )

    findings, suppressed = engine.detect_manual_journal_approval_violations()

    assert findings == []
    assert suppressed == 1


def test_unreconciled_approval_log_is_suppressed(tmp_path: Path) -> None:
    engine = _approval_engine(
        ScenarioFactory(tmp_path),
        absolute_amount="125000",
    )

    findings, suppressed = engine.detect_manual_journal_approval_violations()

    assert findings == []
    assert suppressed == 1


def test_jet_threshold_supports_german_and_english_formats(tmp_path: Path) -> None:
    factory = ScenarioFactory(tmp_path)
    german = factory.passage(
        "german.docx",
        "Nichtaufgriffsgrenze JET: 50.000 EUR",
    )
    english = factory.passage(
        "english.docx",
        "Clearly trivial threshold: 50,000 EUR",
    )

    assert extract_jet_threshold([german])[0] == Decimal("50000")
    assert extract_jet_threshold([english])[0] == Decimal("50000")
