from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from audit_core.engine import AuditEngine
from audit_core.rules import IMPLEMENTED_RULES, RULE_CATALOG
from tests.factories import ScenarioFactory


def vendor_scenario(tmp_path: Path) -> AuditEngine:
    factory = ScenarioFactory(tmp_path)
    changes = [
        factory.row(
            "changes.csv",
            FELD="Neuanlage",
            ART="Kreditor",
            KONTO="VENDOR-X",
            NAME="Synthetic Supplier",
            GEAENDERT_VON="USER-X",
            GENEHMIGT_VON="USER-X",
            DATUM="01.02.2031",
        )
    ]
    permissions = [
        factory.row(
            "permissions.csv",
            Benutzer="USER-X",
            Buchen="yes",
            Zahlungslauf="yes",
            **{"Stammdaten/Kreditor anlegen": "yes"},
        )
    ]
    invoices = [
        factory.row(
            "vendor.txt",
            LIEFERANTENKONTONUMMER="VENDOR-X",
            BUCHUNGSNUMMER=f"INV-{index}",
            BUCHUNGSDATUM=f"0{index + 1}.02.2031",
            BUCHUNGSTEXT="Rechnung",
            BUCHUNGSBETRAG="-2000",
        )
        for index in range(3)
    ]
    payments = [
        factory.row(
            "vendor.txt",
            LIEFERANTENKONTONUMMER="VENDOR-X",
            BUCHUNGSNUMMER=f"PAY-{index}",
            BUCHUNGSDATUM="10.02.2031",
            BUCHUNGSTEXT="Zahlung Rechnung",
            BUCHUNGSBETRAG="2000",
        )
        for index in range(3)
    ]
    gl = [
        factory.row(
            "gl.txt",
            SACHKONTONUMMER="600100",
            BUCHUNGSNUMMER=f"INV-{index}",
            BUCHUNGSBETRAG="2000",
            BENUTZERKENNUNG="USER-X",
            BUCHUNGSDATUM=f"0{index + 1}.02.2031",
            BUCHUNGSTEXT="Service",
        )
        for index in range(3)
    ]
    return factory.engine(
        gl=gl,
        vendor_postings=invoices + payments,
        changes=changes,
        permissions=permissions,
    )


def rebuild(engine: AuditEngine) -> None:
    engine._build_indexes()


def test_vendor_control_minimal_positive_is_grounded(tmp_path: Path) -> None:
    engine = vendor_scenario(tmp_path)

    findings, _ = engine.detect_vendor_control_failures()

    assert len(findings) == 1
    assert findings[0].amount == Decimal("6000")
    assert findings[0].affected_entities[:2] == ["VENDOR-X", "Synthetic Supplier"]
    assert all(reference.sha256 for reference in findings[0].evidence)


@pytest.mark.parametrize(
    "mutation",
    [
        "independent_approval",
        "missing_permission",
        "two_invoices",
        "two_payments",
        "different_poster",
        "late_invoice",
        "non_round_expense",
        "matching_receipt",
    ],
)
def test_vendor_control_clean_twins_are_suppressed(
    tmp_path: Path, mutation: str
) -> None:
    engine = vendor_scenario(tmp_path)
    if mutation == "independent_approval":
        engine.changes[0].data["GENEHMIGT_VON"] = "USER-Y"
    elif mutation == "missing_permission":
        engine.permissions[0].data["Zahlungslauf"] = ""
    elif mutation == "two_invoices":
        engine.vendor_postings = [
            row
            for row in engine.vendor_postings
            if row.data.get("BUCHUNGSNUMMER") != "INV-2"
        ]
    elif mutation == "two_payments":
        engine.vendor_postings = [
            row
            for row in engine.vendor_postings
            if row.data.get("BUCHUNGSNUMMER") != "PAY-2"
        ]
    elif mutation == "different_poster":
        engine.gl[0].data["BENUTZERKENNUNG"] = "USER-Y"
    elif mutation == "late_invoice":
        for row in engine.vendor_postings:
            if row.data.get("BUCHUNGSNUMMER", "").startswith("INV-"):
                row.data["BUCHUNGSDATUM"] = "05.03.2031"
    elif mutation == "non_round_expense":
        engine.gl[0].data["BUCHUNGSBETRAG"] = "1500"
    elif mutation == "matching_receipt":
        factory = ScenarioFactory(engine.root)
        engine.receipts = [
            factory.row("receipts.csv", KREDITOR="VENDOR-X", BETRAG_EUR="2000")
        ]
    rebuild(engine)

    findings, suppressed = engine.detect_vendor_control_failures()

    assert findings == []
    assert suppressed == 1


def capitalised_repairs_scenario(tmp_path: Path) -> AuditEngine:
    factory = ScenarioFactory(tmp_path)
    assets = [
        factory.row(
            "assets.txt",
            ANLAGENNUMMER=f"ASSET-{index}",
            ANLAGENBEZEICHNUNG=description,
            ANLAGENGRUPPE="Machines",
        )
        for index, description in enumerate(
            ("Reparatur Förderband", "Generalüberholung Presse"), start=1
        )
    ]
    postings = [
        factory.row(
            "asset-postings.txt",
            ANLAGENNUMMER=f"ASSET-{index}",
            WERTSTELLUNG="15.06.2031",
            BELEGNUMMER=f"DOC-{index}",
            BUCHUNGSBETRAG=amount,
            BUCHUNGSART="acquisition",
        )
        for index, amount in ((1, "12000"), (2, "18000"))
    ]
    return factory.engine(assets=assets, asset_postings=postings)


def test_capitalised_repairs_positive_and_amount(tmp_path: Path) -> None:
    findings = capitalised_repairs_scenario(tmp_path).detect_capitalised_repairs()

    assert len(findings) == 1
    assert findings[0].amount == Decimal("30000")


@pytest.mark.parametrize("mutation", ["single_match", "ordinary_asset", "not_acquisition"])
def test_capitalised_repairs_clean_twins(tmp_path: Path, mutation: str) -> None:
    engine = capitalised_repairs_scenario(tmp_path)
    if mutation == "single_match":
        engine.asset_postings = engine.asset_postings[:1]
    elif mutation == "ordinary_asset":
        engine.assets[0].data["ANLAGENBEZEICHNUNG"] = "Neue Verpackungsmaschine"
    elif mutation == "not_acquisition":
        engine.asset_postings[0].data["BUCHUNGSART"] = "disposal"
    rebuild(engine)

    assert engine.detect_capitalised_repairs() == []


def cutoff_scenario(tmp_path: Path) -> AuditEngine:
    factory = ScenarioFactory(tmp_path)
    receipts = [
        factory.row(
            "receipts.csv",
            KREDITOR="VENDOR-Z",
            BETRAG_EUR="24500",
            WARENEINGANG_DATUM="20.12.2030",
            WARENEINGANG_NR="GR-1",
            BEMERKUNG="Rechnung offen",
        )
    ]
    invoices = [
        factory.row(
            "future.csv",
            RECHNUNGSNUMMER="FUTURE-1",
            KREDITOR="VENDOR-Z",
            FAKTURADATUM="12.01.2031",
            LEISTUNGSDATUM="20.12.2030",
            BETRAG_EUR="24500",
        )
    ]
    return factory.engine(receipts=receipts, future_invoices=invoices)


def test_cutoff_positive_and_amount(tmp_path: Path) -> None:
    findings = cutoff_scenario(tmp_path).detect_cutoff_failures()

    assert len(findings) == 1
    assert findings[0].amount == Decimal("24500")


@pytest.mark.parametrize(
    "mutation",
    ["same_year", "already_recorded", "closed_receipt", "vendor_mismatch", "amount_mismatch", "date_mismatch"],
)
def test_cutoff_clean_twins(tmp_path: Path, mutation: str) -> None:
    engine = cutoff_scenario(tmp_path)
    if mutation == "same_year":
        engine.future_invoices[0].data["LEISTUNGSDATUM"] = "02.01.2031"
    elif mutation == "already_recorded":
        factory = ScenarioFactory(engine.root)
        engine.gl = [factory.row("gl.txt", BUCHUNGSNUMMER="FUTURE-1")]
    elif mutation == "closed_receipt":
        engine.receipts[0].data["BEMERKUNG"] = "Rechnung bezahlt"
    elif mutation == "vendor_mismatch":
        engine.receipts[0].data["KREDITOR"] = "VENDOR-OTHER"
    elif mutation == "amount_mismatch":
        engine.receipts[0].data["BETRAG_EUR"] = "24499"
    elif mutation == "date_mismatch":
        engine.receipts[0].data["WARENEINGANG_DATUM"] = "19.12.2030"
    rebuild(engine)

    assert engine.detect_cutoff_failures() == []


def split_payment_scenario(tmp_path: Path) -> AuditEngine:
    factory = ScenarioFactory(tmp_path)
    planning = [
        factory.passage(
            "planning.docx",
            "Zahlungsfreigabe im Vier-Augen-Prinzip ab 10.000 EUR.",
        )
    ]
    payments = [
        factory.row(
            "vendor.txt",
            LIEFERANTENKONTONUMMER="VENDOR-P",
            BUCHUNGSNUMMER=f"PAY-{index}",
            BUCHUNGSDATUM="14.07.2031",
            BUCHUNGSTEXT="Zahlung",
            BUCHUNGSBETRAG=amount,
        )
        for index, amount in enumerate(("9000", "9500", "9999"), start=1)
    ]
    return factory.engine(vendor_postings=payments, planning=planning)


def test_split_payments_positive_and_threshold_evidence(tmp_path: Path) -> None:
    findings, _ = split_payment_scenario(tmp_path).detect_split_payments()

    assert len(findings) == 1
    assert findings[0].amount == Decimal("28499")
    assert findings[0].evidence[0].passage == "paragraph:1"


@pytest.mark.parametrize(
    "mutation",
    ["two_payments", "different_date", "different_vendor", "at_threshold", "below_band", "not_payment"],
)
def test_split_payments_clean_twins(tmp_path: Path, mutation: str) -> None:
    engine = split_payment_scenario(tmp_path)
    if mutation == "two_payments":
        engine.vendor_postings = engine.vendor_postings[:2]
    elif mutation == "different_date":
        engine.vendor_postings[0].data["BUCHUNGSDATUM"] = "15.07.2031"
    elif mutation == "different_vendor":
        engine.vendor_postings[0].data["LIEFERANTENKONTONUMMER"] = "VENDOR-Q"
    elif mutation == "at_threshold":
        engine.vendor_postings[0].data["BUCHUNGSBETRAG"] = "10000"
    elif mutation == "below_band":
        engine.vendor_postings[0].data["BUCHUNGSBETRAG"] = "8999"
    elif mutation == "not_payment":
        engine.vendor_postings[0].data["BUCHUNGSTEXT"] = "Gutschrift"
    rebuild(engine)

    findings, _ = engine.detect_split_payments()
    assert findings == []


def test_split_payments_without_source_threshold_is_clean(tmp_path: Path) -> None:
    engine = split_payment_scenario(tmp_path)
    engine.planning = []

    findings, suppressed = engine.detect_split_payments()

    assert findings == []
    assert suppressed == 0


def test_unreadable_threshold_marks_procedure_not_testable(tmp_path: Path) -> None:
    engine = split_payment_scenario(tmp_path)
    engine.planning = [
        ScenarioFactory(engine.root).passage(
            "policy-without-amount.docx",
            "Payments require approval according to the current policy.",
        )
    ]

    report = engine.run()
    procedure = next(
        item
        for item in report.procedures
        if item.rule_id == "SPLIT_PAYMENTS_BELOW_THRESHOLD"
    )

    assert procedure.status == "not_testable"
    assert "threshold" in (procedure.reason or "").casefold()


def test_duplicate_physical_rows_do_not_create_vendor_finding(tmp_path: Path) -> None:
    engine = vendor_scenario(tmp_path)
    invoices = [
        row
        for row in engine.vendor_postings
        if row.data.get("BUCHUNGSNUMMER", "").startswith("INV-")
    ][:2]
    payments = [
        row
        for row in engine.vendor_postings
        if row.data.get("BUCHUNGSNUMMER", "").startswith("PAY-")
    ][:2]
    engine.vendor_postings = invoices + [invoices[0]] + payments + [payments[0]]
    rebuild(engine)

    findings, _ = engine.detect_vendor_control_failures()

    assert findings == []


def test_duplicate_asset_posting_does_not_meet_two_item_minimum(tmp_path: Path) -> None:
    engine = capitalised_repairs_scenario(tmp_path)
    engine.asset_postings = [engine.asset_postings[0], engine.asset_postings[0]]
    rebuild(engine)

    assert engine.detect_capitalised_repairs() == []


def test_duplicate_payment_does_not_meet_cluster_minimum(tmp_path: Path) -> None:
    engine = split_payment_scenario(tmp_path)
    engine.vendor_postings = [
        engine.vendor_postings[0],
        engine.vendor_postings[1],
        engine.vendor_postings[0],
    ]
    rebuild(engine)

    findings, _ = engine.detect_split_payments()
    assert findings == []


@pytest.mark.parametrize(
    ("scenario_builder", "detector_name"),
    [
        (vendor_scenario, "detect_vendor_control_failures"),
        (capitalised_repairs_scenario, "detect_capitalised_repairs"),
        (cutoff_scenario, "detect_cutoff_failures"),
        (split_payment_scenario, "detect_split_payments"),
    ],
)
def test_positive_findings_are_invariant_to_source_row_order(
    tmp_path: Path,
    scenario_builder,
    detector_name: str,
) -> None:
    engine = scenario_builder(tmp_path)

    def fingerprint() -> list[tuple[str, str, Decimal | None, tuple[str, ...]]]:
        result = getattr(engine, detector_name)()
        findings = result[0] if isinstance(result, tuple) else result
        return sorted(
            (
                finding.id,
                finding.rule_id,
                finding.amount,
                tuple(finding.affected_entities),
            )
            for finding in findings
        )

    baseline = fingerprint()
    for attribute in (
        "gl",
        "vendor_postings",
        "receipts",
        "changes",
        "permissions",
        "assets",
        "asset_postings",
        "future_invoices",
    ):
        setattr(engine, attribute, list(reversed(getattr(engine, attribute))))
    rebuild(engine)

    assert fingerprint() == baseline


def test_rule_catalog_has_unique_ids_and_explicit_status() -> None:
    ids = [rule.rule_id for rule in RULE_CATALOG]

    assert len(ids) == len(set(ids))
    assert {rule.status for rule in IMPLEMENTED_RULES} == {"implemented"}
    assert {
        rule.rule_id for rule in IMPLEMENTED_RULES
    } == {
        "VENDOR_CONTROL_CHAIN",
        "CAPITALISED_REPAIRS",
        "UNRECORDED_CUTOFF_LIABILITIES",
        "SPLIT_PAYMENTS_BELOW_THRESHOLD",
        "EXPORT_COMPLETENESS_RECONCILIATION",
        "MANUAL_JOURNAL_APPROVAL_VIOLATION",
    }
