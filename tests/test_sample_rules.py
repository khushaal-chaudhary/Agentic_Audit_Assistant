from decimal import Decimal
from pathlib import Path

from audit_core import analyze_dossier


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "Uebungsdaten_Muster_Verpackungen" / "Uebungsdaten Muster Verpackungen"


def test_sample_detects_expected_rule_families_with_grounded_amounts() -> None:
    report = analyze_dossier(SAMPLE)
    by_rule = {finding.rule_id: finding for finding in report.findings}

    assert set(by_rule) == {
        "VENDOR_CONTROL_CHAIN",
        "CAPITALISED_REPAIRS",
        "UNRECORDED_CUTOFF_LIABILITIES",
        "SPLIT_PAYMENTS_BELOW_THRESHOLD",
    }
    assert by_rule["VENDOR_CONTROL_CHAIN"].amount == Decimal("248000")
    assert by_rule["CAPITALISED_REPAIRS"].amount == Decimal("150800")
    assert by_rule["UNRECORDED_CUTOFF_LIABILITIES"].amount == Decimal("192000")
    assert by_rule["SPLIT_PAYMENTS_BELOW_THRESHOLD"].amount == Decimal("39040")
    assert all(finding.evidence for finding in report.findings)
    assert all(ref.sha256 for finding in report.findings for ref in finding.evidence)
    for finding in report.findings:
        assert finding.calculation is not None
        assert sum(
            (term.value for term in finding.calculation.terms),
            Decimal("0"),
        ) == finding.amount
        evidence = {
            reference.model_dump_json(exclude_none=True)
            for reference in finding.evidence
        }
        assert all(
            term.evidence.model_dump_json(exclude_none=True) in evidence
            for term in finding.calculation.terms
        )


def test_known_decoy_entities_are_not_published_as_findings() -> None:
    report = analyze_dossier(SAMPLE)
    published = " ".join(
        value
        for finding in report.findings
        for value in (finding.title, finding.summary, *finding.affected_entities)
    )

    for clean_entity in (
        "209110",
        "209111",
        "209112",
        "209113",
        "AR502040",
        "SG502041",
        "040000-000005",
        "040000-000197",
    ):
        assert clean_entity not in published
