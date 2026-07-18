from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from .models import DossierReport, EvidenceRef, Finding, ProcedureResult, ensure_grounded
from .parsers import (
    SourceRow,
    extract_payment_threshold,
    file_sha256,
    gdpdu_headers,
    locate_dossier_root,
    normalize_text,
    parse_date,
    parse_decimal,
    read_docx_passages,
    read_semicolon,
    read_xlsx_table,
    relative_name,
)


def _finding_id(rule_id: str, *keys: str) -> str:
    return str(uuid5(NAMESPACE_URL, "|".join((rule_id, *keys))))


def _query_evidence(path: Path, root: Path, query: str, excerpt: str) -> EvidenceRef:
    return EvidenceRef(
        document=relative_name(path, root),
        locator_type="query",
        query=query,
        excerpt=excerpt,
        sha256=file_sha256(str(path)),
    )


def _unique_rows(rows: list[SourceRow]) -> list[SourceRow]:
    seen: set[tuple[str, int]] = set()
    unique: list[SourceRow] = []
    for row in rows:
        key = (str(row.source.resolve()), row.row_number)
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def _find_companion(folder: Path, *name_fragments: str, suffix: str) -> Path:
    normalized_fragments = tuple(normalize_text(fragment) for fragment in name_fragments)
    matches = sorted(
        path
        for path in folder.glob(f"*{suffix}")
        if all(fragment in normalize_text(path.stem) for fragment in normalized_fragments)
    )
    if len(matches) > 1:
        raise ValueError(
            f"Ambiguous companion document for {name_fragments}: "
            + ", ".join(path.name for path in matches)
        )
    if matches:
        return matches[0]
    return folder / f"__missing_{'_'.join(normalized_fragments)}{suffix}"


class AuditEngine:
    def __init__(self, root: Path):
        self.root = locate_dossier_root(root)
        self.gl_path = self.root / "Sachkonten" / "Sachkontobuchungen.txt"
        self.vendor_path = self.root / "Kreditoren" / "Lieferantenbuchungen.txt"
        self.asset_path = self.root / "AV" / "Anlagen.txt"
        self.asset_posting_path = self.root / "AV" / "Anlagenbuchungen.txt"
        docs = self.root / "Begleitdokumente"
        self.receipt_path = _find_companion(docs, "wareneingangsliste", suffix=".csv")
        self.change_path = _find_companion(docs, "stammdatenaenderungen", suffix=".csv")
        self.permission_path = _find_companion(docs, "berechtigungsauswertung", suffix=".xlsx")
        self.future_invoice_path = _find_companion(
            docs, "fakturajournal", "kreditoren", suffix=".csv"
        )
        self.planning_path = _find_companion(docs, "pruefungsplanung", suffix=".docx")

        self.gl = self._read_gdpdu(self.gl_path)
        self.vendor_postings = self._read_gdpdu(self.vendor_path)
        self.assets = self._read_gdpdu(self.asset_path)
        self.asset_postings = self._read_gdpdu(self.asset_posting_path)
        self.receipts = self._read_rows(self.receipt_path)
        self.changes = self._read_rows(self.change_path)
        self.permissions = (
            read_xlsx_table(self.permission_path, self.root, "Benutzer")
            if self.permission_path.exists()
            else []
        )
        self.future_invoices = self._read_rows(self.future_invoice_path)
        self.planning = (
            read_docx_passages(self.planning_path, self.root)
            if self.planning_path.exists()
            else []
        )
        self._build_indexes()

    def _build_indexes(self) -> None:
        gl_by_document: dict[str, list[SourceRow]] = defaultdict(list)
        postings_by_vendor: dict[str, list[SourceRow]] = defaultdict(list)
        receipts_by_vendor: dict[str, list[SourceRow]] = defaultdict(list)
        open_receipts_by_key: dict[
            tuple[str, Decimal, date | None], list[SourceRow]
        ] = defaultdict(list)
        payment_groups: dict[tuple[str, str], list[SourceRow]] = defaultdict(list)

        for row in _unique_rows(self.gl):
            gl_by_document[row.data.get("BUCHUNGSNUMMER", "")].append(row)
        for row in _unique_rows(self.vendor_postings):
            vendor = row.data.get("LIEFERANTENKONTONUMMER", "")
            postings_by_vendor[vendor].append(row)
            amount = parse_decimal(row.data.get("BUCHUNGSBETRAG"))
            if amount > 0 and "zahlung" in normalize_text(row.data.get("BUCHUNGSTEXT")):
                payment_groups[(vendor, row.data.get("BUCHUNGSDATUM", ""))].append(row)
        for row in _unique_rows(self.receipts):
            vendor = row.data.get("KREDITOR", "")
            receipts_by_vendor[vendor].append(row)
            if "rechnung offen" in normalize_text(row.data.get("BEMERKUNG")):
                key = (
                    vendor,
                    parse_decimal(row.data.get("BETRAG_EUR")),
                    parse_date(row.data.get("WARENEINGANG_DATUM")),
                )
                open_receipts_by_key[key].append(row)

        self.gl_by_document = dict(gl_by_document)
        self.gl_document_numbers = set(gl_by_document)
        self.postings_by_vendor = dict(postings_by_vendor)
        self.receipts_by_vendor = dict(receipts_by_vendor)
        self.open_receipts_by_key = dict(open_receipts_by_key)
        self.payment_groups = dict(payment_groups)
        self.permission_by_user = {
            row.data.get("Benutzer", ""): row for row in self.permissions
        }
        self.assets_by_id = {
            row.data.get("ANLAGENNUMMER", ""): row for row in self.assets
        }
        self.accrual_rows = [
            row
            for row in _unique_rows(self.gl)
            if "ruckstellung" in normalize_text(row.data.get("BUCHUNGSTEXT"))
            or "unfaktur" in normalize_text(row.data.get("BUCHUNGSTEXT"))
        ]

    def _read_gdpdu(self, path: Path) -> list[SourceRow]:
        if not path.exists() or not (path.parent / "index.xml").exists():
            return []
        return read_semicolon(path, self.root, gdpdu_headers(path.parent, path.name))

    def _read_rows(self, path: Path) -> list[SourceRow]:
        return read_semicolon(path, self.root) if path.exists() else []

    @staticmethod
    def _procedure(rule_id: str, paths: list[Path]) -> ProcedureResult:
        missing = [path.name for path in paths if not path.exists()]
        if missing:
            return ProcedureResult(
                rule_id=rule_id,
                status="not_testable",
                reason="Missing required inputs: " + ", ".join(missing),
            )
        return ProcedureResult(rule_id=rule_id, status="completed")

    def run(self) -> DossierReport:
        findings: list[Finding] = []
        suppressed = 0
        procedures = [
            self._procedure(
                "VENDOR_CONTROL_CHAIN",
                [
                    self.gl_path,
                    self.vendor_path,
                    self.receipt_path,
                    self.change_path,
                    self.permission_path,
                ],
            ),
            self._procedure(
                "CAPITALISED_REPAIRS", [self.asset_path, self.asset_posting_path]
            ),
            self._procedure(
                "UNRECORDED_CUTOFF_LIABILITIES",
                [self.gl_path, self.receipt_path, self.future_invoice_path],
            ),
            self._procedure(
                "SPLIT_PAYMENTS_BELOW_THRESHOLD", [self.vendor_path, self.planning_path]
            ),
        ]
        if (
            procedures[3].status == "completed"
            and extract_payment_threshold(self.planning) is None
        ):
            procedures[3] = ProcedureResult(
                rule_id="SPLIT_PAYMENTS_BELOW_THRESHOLD",
                status="not_testable",
                reason="No payment approval threshold could be extracted from the control document",
            )

        if procedures[0].status == "completed":
            detected, detector_suppressed = self.detect_vendor_control_failures()
            findings.extend(detected)
            suppressed += detector_suppressed
        if procedures[1].status == "completed":
            findings.extend(self.detect_capitalised_repairs())
        if procedures[2].status == "completed":
            findings.extend(self.detect_cutoff_failures())
        if procedures[3].status == "completed":
            detected, detector_suppressed = self.detect_split_payments()
            findings.extend(detected)
            suppressed += detector_suppressed

        findings = list({finding.id: finding for finding in findings}.values())
        report = DossierReport(
            dossier_name=self.root.name,
            files_scanned=sum(1 for path in self.root.rglob("*") if path.is_file()),
            tests_run=sum(item.status == "completed" for item in procedures),
            findings=sorted(
                findings, key=lambda item: (item.severity != "high", -item.confidence)
            ),
            procedures=procedures,
            suppressed_leads=suppressed,
        )
        ensure_grounded(report)
        return report

    def detect_vendor_control_failures(self) -> tuple[list[Finding], int]:
        findings: list[Finding] = []
        suppressed = 0
        for change in sorted(
            _unique_rows(self.changes),
            key=lambda row: (
                row.data.get("KONTO", ""),
                row.data.get("DATUM", ""),
                str(row.source),
                row.row_number,
            ),
        ):
            field = normalize_text(change.data.get("FELD"))
            if "neuanlage" not in field or "kreditor" not in normalize_text(change.data.get("ART")):
                continue
            vendor_id = change.data.get("KONTO", "")
            user = change.data.get("GEAENDERT_VON", "")
            approver = change.data.get("GENEHMIGT_VON", "")
            permission = self.permission_by_user.get(user)
            postings = self.postings_by_vendor.get(vendor_id, [])
            invoices = [
                row
                for row in postings
                if parse_decimal(row.data.get("BUCHUNGSBETRAG")) < 0
                and "zahlung" not in normalize_text(row.data.get("BUCHUNGSTEXT"))
            ]
            payments = [
                row
                for row in postings
                if parse_decimal(row.data.get("BUCHUNGSBETRAG")) > 0
                and "zahlung" in normalize_text(row.data.get("BUCHUNGSTEXT"))
            ]
            has_sod_conflict = bool(
                permission
                and permission.data.get("Buchen")
                and permission.data.get("Zahlungslauf")
                and permission.data.get("Stammdaten/Kreditor anlegen")
            )
            document_numbers = sorted(
                {row.data.get("BUCHUNGSNUMMER", "") for row in invoices}
            )
            related_gl = [
                row
                for document_number in document_numbers
                for row in self.gl_by_document.get(document_number, [])
            ]
            same_user_postings = bool(related_gl) and all(
                row.data.get("BENUTZERKENNUNG") == user for row in related_gl
            )
            creation_date = parse_date(change.data.get("DATUM"))
            invoice_dates = [
                parsed
                for row in invoices
                if (parsed := parse_date(row.data.get("BUCHUNGSDATUM"))) is not None
            ]
            first_invoice_date = min(invoice_dates, default=None)
            rapid_onboarding = bool(
                creation_date
                and first_invoice_date
                and timedelta(0) <= first_invoice_date - creation_date <= timedelta(days=30)
            )
            expense_lines = [
                row
                for row in related_gl
                if row.data.get("SACHKONTONUMMER", "").startswith("6")
                and parse_decimal(row.data.get("BUCHUNGSBETRAG")) > 0
            ]
            round_invoices = bool(expense_lines) and all(
                parse_decimal(row.data.get("BUCHUNGSBETRAG")) % Decimal("1000") == 0
                for row in expense_lines
            )
            no_receipts = not self.receipts_by_vendor.get(vendor_id)
            strong = all(
                (
                    user and user == approver,
                    has_sod_conflict,
                    len(invoices) >= 3,
                    len(payments) >= 3,
                    same_user_postings,
                    rapid_onboarding,
                    round_invoices,
                    no_receipts,
                )
            )
            if not strong:
                suppressed += 1
                continue

            net_total = sum(
                (parse_decimal(row.data.get("BUCHUNGSBETRAG")) for row in expense_lines),
                Decimal("0"),
            )
            name = change.data.get("NAME") or vendor_id
            evidence = [
                change.evidence(
                    "KONTO", "NAME", "FELD", "GEAENDERT_VON", "GENEHMIGT_VON"
                ),
                permission.evidence(
                    "Benutzer", "Buchen", "Zahlungslauf", "Stammdaten/Kreditor anlegen"
                ),
            ]
            evidence.extend(
                row.evidence(
                    "LIEFERANTENKONTONUMMER",
                    "BUCHUNGSNUMMER",
                    "BUCHUNGSDATUM",
                    "BUCHUNGSTEXT",
                    "BUCHUNGSBETRAG",
                )
                for row in invoices[:2] + payments[:2]
            )
            evidence.extend(
                row.evidence(
                    "SACHKONTONUMMER",
                    "BUCHUNGSNUMMER",
                    "BUCHUNGSBETRAG",
                    "BENUTZERKENNUNG",
                )
                for row in expense_lines[:2]
            )
            evidence.append(
                _query_evidence(
                    self.receipt_path,
                    self.root,
                    f"KREDITOR={vendor_id}",
                    f"No goods-receipt row matched vendor {vendor_id}.",
                )
            )
            findings.append(
                Finding(
                    id=_finding_id("VENDOR_CONTROL_CHAIN", vendor_id),
                    rule_id="VENDOR_CONTROL_CHAIN",
                    category="fraud",
                    severity="high",
                    confidence=Decimal("0.98"),
                    title=f"Vendor control chain indicates unsupported payments to {name}",
                    summary=(
                        "The vendor was created and approved by the same user, that user can create "
                        "vendors, post entries and run payments, and repeated round invoices were "
                        "booked shortly after onboarding without a matching goods receipt."
                    ),
                    amount=net_total,
                    currency="EUR",
                    affected_entities=[vendor_id, name, user],
                    evidence=evidence,
                    counterevidence_considered=[
                        "New vendors with independent approval are suppressed.",
                        "New vendors with matching deliveries are suppressed.",
                        "A missing goods receipt alone is not enough to publish a finding.",
                    ],
                    next_step=(
                        "Obtain the contract, deliverables, bank-account ownership and payment approvals."
                    ),
                )
            )
        return findings, suppressed

    def detect_capitalised_repairs(self) -> list[Finding]:
        repair_pattern = re.compile(
            r"reparatur|instandsetzung|austausch|generaluberholung|wartung|kalteanlage",
            re.IGNORECASE,
        )
        matches: list[tuple[SourceRow, SourceRow]] = []
        for posting in _unique_rows(self.asset_postings):
            if normalize_text(posting.data.get("BUCHUNGSART")) != "acquisition":
                continue
            asset = self.assets_by_id.get(posting.data.get("ANLAGENNUMMER", ""))
            if not asset:
                continue
            description = normalize_text(asset.data.get("ANLAGENBEZEICHNUNG"))
            if repair_pattern.search(description):
                matches.append((asset, posting))
        if len(matches) < 2:
            return []
        matches.sort(
            key=lambda pair: (
                pair[1].data.get("BELEGNUMMER", ""),
                pair[0].data.get("ANLAGENNUMMER", ""),
            )
        )
        total = sum(
            (parse_decimal(posting.data.get("BUCHUNGSBETRAG")) for _, posting in matches),
            Decimal("0"),
        )
        evidence: list[EvidenceRef] = []
        for asset, posting in matches:
            evidence.append(
                asset.evidence("ANLAGENNUMMER", "ANLAGENBEZEICHNUNG", "ANLAGENGRUPPE")
            )
            evidence.append(
                posting.evidence(
                    "ANLAGENNUMMER",
                    "WERTSTELLUNG",
                    "BELEGNUMMER",
                    "BUCHUNGSBETRAG",
                    "BUCHUNGSART",
                )
            )
        return [
            Finding(
                id=_finding_id(
                    "CAPITALISED_REPAIRS",
                    *(posting.data["BELEGNUMMER"] for _, posting in matches),
                ),
                rule_id="CAPITALISED_REPAIRS",
                category="misstatement",
                severity="high",
                confidence=Decimal("0.96"),
                title="Repair-type expenditures were capitalised as fixed assets",
                summary=(
                    "Multiple asset additions carry repair, replacement or overhaul descriptions. "
                    "The grouping excludes ordinary investment descriptions and requires acquisition postings."
                ),
                amount=total,
                currency="EUR",
                affected_entities=[asset.data["ANLAGENNUMMER"] for asset, _ in matches],
                evidence=evidence,
                counterevidence_considered=[
                    "Large or round acquisitions are not flagged without repair-type descriptions.",
                    "Productive equipment described as a new investment is excluded.",
                ],
                next_step=(
                    "Inspect invoices and the capitalization policy; reclassify non-enhancing repairs to expense."
                ),
            )
        ]

    def detect_cutoff_failures(self) -> list[Finding]:
        matches: list[tuple[SourceRow, SourceRow]] = []
        for invoice in _unique_rows(self.future_invoices):
            invoice_date = parse_date(invoice.data.get("FAKTURADATUM"))
            service_date = parse_date(invoice.data.get("LEISTUNGSDATUM"))
            if not invoice_date or not service_date or invoice_date.year <= service_date.year:
                continue
            if invoice.data.get("RECHNUNGSNUMMER") in self.gl_document_numbers:
                continue
            vendor = invoice.data.get("KREDITOR")
            amount = parse_decimal(invoice.data.get("BETRAG_EUR"))
            receipt = next(
                iter(self.open_receipts_by_key.get((vendor, amount, service_date), [])),
                None,
            )
            if receipt:
                matches.append((invoice, receipt))
        if not matches:
            return []
        matches.sort(
            key=lambda pair: (
                pair[0].data.get("RECHNUNGSNUMMER", ""),
                pair[0].data.get("KREDITOR", ""),
            )
        )
        total = sum(
            (parse_decimal(invoice.data.get("BETRAG_EUR")) for invoice, _ in matches),
            Decimal("0"),
        )
        evidence = [
            ref
            for invoice, receipt in matches
            for ref in (
                invoice.evidence(
                    "RECHNUNGSNUMMER",
                    "KREDITOR",
                    "FAKTURADATUM",
                    "LEISTUNGSDATUM",
                    "BETRAG_EUR",
                ),
                receipt.evidence(
                    "WARENEINGANG_NR",
                    "WARENEINGANG_DATUM",
                    "KREDITOR",
                    "BETRAG_EUR",
                    "BEMERKUNG",
                ),
            )
        ]
        evidence.extend(
            row.evidence(
                "SACHKONTONUMMER", "BUCHUNGSDATUM", "BUCHUNGSBETRAG", "BUCHUNGSTEXT"
            )
            for row in self.accrual_rows[:2]
        )
        evidence.append(
            _query_evidence(
                self.gl_path,
                self.root,
                "future invoice document numbers against BUCHUNGSNUMMER",
                (
                    "No current-year journal rows matched the subsequent invoice numbers; "
                    "other year-end accrual rows exist."
                ),
            )
        )
        return [
            Finding(
                id=_finding_id(
                    "UNRECORDED_CUTOFF_LIABILITIES",
                    *(invoice.data["RECHNUNGSNUMMER"] for invoice, _ in matches),
                ),
                rule_id="UNRECORDED_CUTOFF_LIABILITIES",
                category="misstatement",
                severity="high",
                confidence=Decimal("0.97"),
                title=(
                    "Prior-period deliveries were recorded in the subsequent period "
                    "without matching accruals"
                ),
                summary=(
                    "Subsequent invoices have prior-year service dates and matching open goods "
                    "receipts, while their document numbers are absent from the current-year ledger."
                ),
                amount=total,
                currency="EUR",
                affected_entities=sorted(
                    {invoice.data["KREDITOR"] for invoice, _ in matches}
                ),
                evidence=evidence,
                counterevidence_considered=[
                    "A separate year-end accrual proves the company uses accrual accounting.",
                    "Only invoices with matching prior-period open receipts are included.",
                ],
                next_step=(
                    "Agree the open receipts to subsequent invoices and propose a year-end accrual."
                ),
            )
        ]

    def detect_split_payments(self) -> tuple[list[Finding], int]:
        threshold_result = extract_payment_threshold(self.planning)
        if not threshold_result:
            return [], 0
        threshold, threshold_evidence = threshold_result
        findings: list[Finding] = []
        suppressed = 0
        for vendor, booking_date in sorted(self.payment_groups):
            rows = self.payment_groups[(vendor, booking_date)]
            near = sorted(
                (
                    row
                    for row in rows
                    if threshold * Decimal("0.90")
                    <= parse_decimal(row.data.get("BUCHUNGSBETRAG"))
                    < threshold
                ),
                key=lambda row: (
                    row.data.get("BUCHUNGSNUMMER", ""),
                    str(row.source),
                    row.row_number,
                ),
            )
            if len(near) < 3:
                if near:
                    suppressed += 1
                continue
            total = sum(
                (parse_decimal(row.data.get("BUCHUNGSBETRAG")) for row in near),
                Decimal("0"),
            )
            if total < threshold * 2:
                suppressed += 1
                continue
            evidence = [threshold_evidence]
            evidence.extend(
                row.evidence(
                    "LIEFERANTENKONTONUMMER",
                    "BUCHUNGSNUMMER",
                    "BUCHUNGSDATUM",
                    "BUCHUNGSTEXT",
                    "BUCHUNGSBETRAG",
                )
                for row in near
            )
            findings.append(
                Finding(
                    id=_finding_id(
                        "SPLIT_PAYMENTS_BELOW_THRESHOLD", vendor, booking_date
                    ),
                    rule_id="SPLIT_PAYMENTS_BELOW_THRESHOLD",
                    category="control",
                    severity="medium",
                    confidence=Decimal("0.99"),
                    title=(
                        f"Same-day payments to vendor {vendor} cluster below "
                        "the approval threshold"
                    ),
                    summary=(
                        "Several payments to the same vendor on one day fall immediately below "
                        "the documented dual-approval threshold and exceed it in aggregate."
                    ),
                    amount=total,
                    currency="EUR",
                    affected_entities=[vendor, booking_date],
                    evidence=evidence,
                    counterevidence_considered=[
                        "Two unrelated near-threshold payments across different dates are suppressed.",
                        "The threshold is extracted from the control document rather than hard-coded.",
                    ],
                    next_step=(
                        "Inspect the payment batch, invoice linkage and dual-approval records."
                    ),
                )
            )
        return findings, suppressed


def analyze_dossier(path: str | Path) -> DossierReport:
    return AuditEngine(Path(path)).run()
