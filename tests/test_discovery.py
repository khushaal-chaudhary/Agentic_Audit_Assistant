from __future__ import annotations

import shutil
from pathlib import Path

from audit_core import analyze_dossier
from audit_core.discovery import REQUIRED_ROLES, discover_dossier


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "Uebungsdaten_Muster_Verpackungen" / "Uebungsdaten Muster Verpackungen"


def test_sample_resolves_every_required_role_from_schema_or_content() -> None:
    coverage = discover_dossier(SAMPLE)
    roles = {role.role: role for role in coverage.roles}

    assert set(roles) == set(REQUIRED_ROLES)
    assert all(role.status == "resolved" for role in roles.values())
    assert roles["goods_receipts"].document.endswith("Wareneingangsliste_2025.csv")
    assert roles["payment_policy"].document.endswith("Pruefungsplanung_JET_2025.docx")


def test_english_headers_resolve_to_canonical_fields(tmp_path: Path) -> None:
    source = tmp_path / "random-name.csv"
    source.write_text(
        "goods_receipt_number;goods_receipt_date;vendor_id;amount_eur;remark\n"
        "GR-1;2031-12-20;V-1;1250;invoice open\n",
        encoding="utf-8",
    )

    coverage = discover_dossier(tmp_path)
    receipts = next(role for role in coverage.roles if role.role == "goods_receipts")

    assert receipts.status == "resolved"
    assert receipts.document == "random-name.csv"
    assert receipts.header_map == {
        "WARENEINGANG_NR": "goods_receipt_number",
        "WARENEINGANG_DATUM": "goods_receipt_date",
        "KREDITOR": "vendor_id",
        "BETRAG_EUR": "amount_eur",
        "BEMERKUNG": "remark",
    }


def test_duplicate_schema_candidates_are_ambiguous(tmp_path: Path) -> None:
    header = "WARENEINGANG_NR;WARENEINGANG_DATUM;KREDITOR;BETRAG_EUR;BEMERKUNG\n"
    (tmp_path / "one.csv").write_text(header, encoding="utf-8")
    (tmp_path / "two.csv").write_text(header, encoding="utf-8")

    coverage = discover_dossier(tmp_path)
    receipts = next(role for role in coverage.roles if role.role == "goods_receipts")
    documents = {
        document.document: document for document in coverage.documents
    }

    assert receipts.status == "ambiguous"
    assert documents["one.csv"].status == "ambiguous"
    assert documents["two.csv"].status == "ambiguous"


def test_renamed_companion_files_preserve_sample_findings(tmp_path: Path) -> None:
    dossier = tmp_path / "renamed-dossier"
    shutil.copytree(SAMPLE, dossier)
    companion = dossier / "Begleitdokumente"
    renames = {
        "Wareneingangsliste_2025.csv": "input-a.csv",
        "Stammdatenaenderungen_2025.csv": "input-b.csv",
        "Berechtigungsauswertung_2025.xlsx": "input-c.xlsx",
        "Fakturajournal_Januar_2026_Kreditoren.csv": "input-d.csv",
        "Pruefungsplanung_JET_2025.docx": "input-e.docx",
    }
    for original, renamed in renames.items():
        (companion / original).rename(companion / renamed)

    report = analyze_dossier(dossier)

    assert {finding.rule_id for finding in report.findings} == {
        "VENDOR_CONTROL_CHAIN",
        "CAPITALISED_REPAIRS",
        "UNRECORDED_CUTOFF_LIABILITIES",
        "SPLIT_PAYMENTS_BELOW_THRESHOLD",
    }
    assert report.ingestion is not None
    assert all(role.status == "resolved" for role in report.ingestion.roles)


def test_ambiguous_required_role_becomes_not_testable(tmp_path: Path) -> None:
    dossier = tmp_path / "ambiguous-dossier"
    shutil.copytree(SAMPLE, dossier)
    receipts = next((dossier / "Begleitdokumente").glob("Wareneingangsliste*.csv"))
    shutil.copy2(receipts, receipts.with_name("duplicate-receipts.csv"))

    report = analyze_dossier(dossier)
    by_rule = {procedure.rule_id: procedure for procedure in report.procedures}

    assert by_rule["VENDOR_CONTROL_CHAIN"].status == "not_testable"
    assert by_rule["UNRECORDED_CUTOFF_LIABILITIES"].status == "not_testable"
    assert "Multiple schema/content matches" in (
        by_rule["VENDOR_CONTROL_CHAIN"].reason or ""
    )
    assert all(
        finding.rule_id
        not in {"VENDOR_CONTROL_CHAIN", "UNRECORDED_CUTOFF_LIABILITIES"}
        for finding in report.findings
    )
