from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from .discovery import discover_dossier
from .models import (
    CalculationTerm,
    CalculationTrace,
    DossierReport,
    EvidenceRef,
    Finding,
    ProcedureResult,
    ensure_grounded,
)
from .parsers import (
    SourceRow,
    canonicalize_rows,
    extract_jet_threshold,
    extract_payment_threshold,
    file_sha256,
    gdpdu_headers,
    iter_semicolon,
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


def _declared_gl_row_count(
    passages: list[EvidenceRef],
) -> tuple[int, EvidenceRef] | None:
    text = "\n".join(passage.excerpt for passage in passages)
    match = re.search(
        r"sachkontobuchungen(?:\.txt)?[\s\S]{0,180}?"
        r"([0-9]{1,3}(?:[.,\s][0-9]{3}){1,3}|[0-9]{5,})",
        normalize_text(text),
    )
    if not match:
        return None
    token = match.group(1)
    count = int(re.sub(r"[^0-9]", "", token))
    compact_token = re.sub(r"\s", "", token)
    reference = next(
        (
            passage
            for passage in passages
            if compact_token in re.sub(r"\s", "", normalize_text(passage.excerpt))
        ),
        passages[0] if passages else None,
    )
    return (count, reference) if reference else None


def _approval_violation_reason(row: SourceRow) -> str | None:
    creator = row.data.get("ERSTELLER", "").strip()
    approver = row.data.get("FREIGEBER", "").strip()
    status = normalize_text(row.data.get("FREIGABESTATUS"))
    if not row.data.get("ERFASSUNGSNUMMER", "").strip():
        return None
    if creator and creator == approver:
        return "creator and approver are the same user"
    if not approver:
        return "journal was posted without an approver"
    if not any(marker in status for marker in ("freigegeben", "approved", "genehmigt")):
        return "approval status is not approved"
    return None


class AuditEngine:
    def __init__(self, root: Path):
        self.root = locate_dossier_root(root)
        self.discovery = discover_dossier(self.root)
        resolutions = {item.role: item for item in self.discovery.roles}
        self._path_issues: dict[Path, str] = {}
        self._header_maps: dict[Path, dict[str, str]] = {}

        def resolve(role: str) -> Path:
            resolution = resolutions[role]
            if resolution.status == "resolved" and resolution.document:
                path = (self.root / resolution.document).resolve()
                self._header_maps[path] = resolution.header_map
                return path
            path = self.root / f"__missing_role_{role}"
            self._path_issues[path] = resolution.reason
            return path

        self.gl_path = resolve("general_ledger")
        self.manual_gl_path = resolve("manual_journal_ledger")
        self.vendor_path = resolve("vendor_postings")
        self.asset_path = resolve("asset_master")
        self.asset_posting_path = resolve("asset_postings")
        self.receipt_path = resolve("goods_receipts")
        self.change_path = resolve("vendor_changes")
        self.permission_path = resolve("permissions")
        self.future_invoice_path = resolve("future_vendor_invoices")
        self.approval_path = resolve("journal_approvals")
        self.planning_path = resolve("payment_policy")
        self.jet_planning_path = resolve("jet_policy")
        self.export_manifest_path = resolve("export_manifest")
        self.it_confirmation_path = resolve("it_completeness_confirmation")

        self.vendor_postings = self._read_table(self.vendor_path)
        self.assets = self._read_table(self.asset_path)
        self.asset_postings = self._read_table(self.asset_posting_path)
        self.receipts = self._read_table(self.receipt_path)
        self.changes = self._read_table(self.change_path)
        self.permissions = (
            canonicalize_rows(
                read_xlsx_table(
                    self.permission_path,
                    self.root,
                    self._header_maps[self.permission_path]["Benutzer"],
                ),
                self._header_maps[self.permission_path],
            )
            if self.permission_path.exists()
            else []
        )
        self.future_invoices = self._read_table(self.future_invoice_path)
        self.journal_approvals = self._read_table(self.approval_path)
        self.planning = (
            read_docx_passages(self.planning_path, self.root)
            if self.planning_path.exists()
            else []
        )
        self.jet_planning = (
            read_docx_passages(self.jet_planning_path, self.root)
            if self.jet_planning_path.exists()
            else []
        )
        self.gl: list[SourceRow] = []
        self._stream_general_ledger()
        self._build_indexes()

    def _stream_general_ledger(self) -> None:
        self._gl_streamed = True
        self.gl_by_document: dict[str, list[SourceRow]] = defaultdict(list)
        self.gl_by_capture: dict[str, list[SourceRow]] = defaultdict(list)
        self.gl_document_numbers: set[str] = set()
        self.accrual_rows: list[SourceRow] = []
        self.gl_row_count = 0
        if not self.gl_path.exists():
            return

        needed_documents = {
            row.data.get("BUCHUNGSNUMMER", "")
            for row in self.vendor_postings
            if row.data.get("BUCHUNGSNUMMER")
        }
        approval_candidates = {
            row.data.get("ERFASSUNGSNUMMER", ""): row
            for row in self.journal_approvals
            if _approval_violation_reason(row)
        }
        headers = (
            gdpdu_headers(self.gl_path.parent, self.gl_path.name)
            if (self.gl_path.parent / "index.xml").exists()
            else None
        )
        header_map = self._header_maps.get(self.gl_path, {})
        for source_row in iter_semicolon(self.gl_path, self.root, headers):
            self.gl_row_count += 1
            row = canonicalize_rows([source_row], header_map)[0] if header_map else source_row
            document_number = row.data.get("BUCHUNGSNUMMER", "")
            if document_number:
                self.gl_document_numbers.add(document_number)
            if document_number in needed_documents:
                self.gl_by_document[document_number].append(row)
            capture_number = (
                row.data.get("ERFASSUNGSNUMMER", "")
                or row.data.get("GEGENKONTO", "")
            )
            approval = approval_candidates.get(capture_number)
            if approval and all(
                (
                    row.data.get("BENUTZERKENNUNG", "")
                    == approval.data.get("ERSTELLER", ""),
                    row.data.get("ERFASSUNGSDATUM", "")
                    == approval.data.get("ERFASST_AM", ""),
                )
            ):
                self.gl_by_capture[capture_number].append(row)
            text = normalize_text(row.data.get("BUCHUNGSTEXT"))
            if "ruckstellung" in text or "unfaktur" in text:
                self.accrual_rows.append(row)
        self.gl_by_document = dict(self.gl_by_document)
        self.gl_by_capture = dict(self.gl_by_capture)

    def _build_indexes(self) -> None:
        gl_by_document: dict[str, list[SourceRow]] = defaultdict(list)
        postings_by_vendor: dict[str, list[SourceRow]] = defaultdict(list)
        receipts_by_vendor: dict[str, list[SourceRow]] = defaultdict(list)
        open_receipts_by_key: dict[
            tuple[str, Decimal, date | None], list[SourceRow]
        ] = defaultdict(list)
        payment_groups: dict[tuple[str, str], list[SourceRow]] = defaultdict(list)

        if not getattr(self, "_gl_streamed", False):
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

        if not getattr(self, "_gl_streamed", False):
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
        if not getattr(self, "_gl_streamed", False):
            self.accrual_rows = [
                row
                for row in _unique_rows(self.gl)
                if "ruckstellung" in normalize_text(row.data.get("BUCHUNGSTEXT"))
                or "unfaktur" in normalize_text(row.data.get("BUCHUNGSTEXT"))
            ]
            self.gl_row_count = len(self.gl)

    def _read_table(self, path: Path) -> list[SourceRow]:
        if not path.exists():
            return []
        index_path = path.parent / "index.xml"
        rows = (
            read_semicolon(path, self.root, gdpdu_headers(path.parent, path.name))
            if index_path.exists()
            else read_semicolon(path, self.root)
        )
        return canonicalize_rows(rows, self._header_maps.get(path, {}))

    def _procedure(self, rule_id: str, paths: list[Path]) -> ProcedureResult:
        missing = [path.name for path in paths if not path.exists()]
        if missing:
            issues = getattr(self, "_path_issues", {})
            return ProcedureResult(
                rule_id=rule_id,
                status="not_testable",
                reason="Missing required inputs: "
                + "; ".join(
                    issues.get(path, path.name)
                    for path in paths
                    if not path.exists()
                ),
            )
        return ProcedureResult(rule_id=rule_id, status="completed")

    def _role_passages(self, role_name: str) -> list[EvidenceRef]:
        resolution = next(
            (role for role in self.discovery.roles if role.role == role_name),
            None,
        )
        if not resolution or not resolution.document:
            return []
        return [
            passage
            for passage in self.discovery.source_passages
            if passage.document == resolution.document
        ]

    def _completeness_counts(
        self,
    ) -> tuple[tuple[int, EvidenceRef], tuple[int, EvidenceRef]] | None:
        export_count = _declared_gl_row_count(self._role_passages("export_manifest"))
        confirmation_count = _declared_gl_row_count(
            self._role_passages("it_completeness_confirmation")
        )
        if not export_count or not confirmation_count:
            return None
        return export_count, confirmation_count

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
            self._procedure(
                "EXPORT_COMPLETENESS_RECONCILIATION",
                [self.gl_path, self.export_manifest_path, self.it_confirmation_path],
            ),
            self._procedure(
                "MANUAL_JOURNAL_APPROVAL_VIOLATION",
                [self.manual_gl_path, self.approval_path, self.jet_planning_path],
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
        if procedures[4].status == "completed" and self._completeness_counts() is None:
            procedures[4] = ProcedureResult(
                rule_id="EXPORT_COMPLETENESS_RECONCILIATION",
                status="not_testable",
                reason="Could not extract a general-ledger row count from both control documents",
            )
        if (
            procedures[5].status == "completed"
            and extract_jet_threshold(self.jet_planning) is None
        ):
            procedures[5] = ProcedureResult(
                rule_id="MANUAL_JOURNAL_APPROVAL_VIOLATION",
                status="not_testable",
                reason="No JET clearly-trivial threshold could be extracted from the planning document",
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
        if procedures[4].status == "completed":
            findings.extend(self.detect_export_completeness_mismatch())
        if procedures[5].status == "completed":
            detected, detector_suppressed = self.detect_manual_journal_approval_violations()
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
            ingestion=getattr(self, "discovery", None),
        )
        ensure_grounded(report)
        return report

    def detect_export_completeness_mismatch(self) -> list[Finding]:
        counts = self._completeness_counts()
        if counts is None:
            return []
        (export_count, export_ref), (confirmation_count, confirmation_ref) = counts
        physical_count = self.gl_row_count
        if len({export_count, confirmation_count, physical_count}) == 1:
            return []
        physical_ref = _query_evidence(
            self.gl_path,
            self.root,
            "count physical GDPdU data rows using the declared index.xml schema",
            f"Physical general-ledger table contains {physical_count} data rows.",
        )
        return [
            Finding(
                id=_finding_id(
                    "EXPORT_COMPLETENESS_RECONCILIATION",
                    str(export_count),
                    str(confirmation_count),
                    str(physical_count),
                ),
                rule_id="EXPORT_COMPLETENESS_RECONCILIATION",
                category="control",
                severity="high",
                confidence=Decimal("0.99"),
                title="Independent ledger-completeness records disagree",
                summary=(
                    f"The export manifest declares {export_count} general-ledger rows, the IT "
                    f"confirmation declares {confirmation_count}, and the physical GDPdU table "
                    f"contains {physical_count}. The population cannot be treated as reconciled."
                ),
                affected_entities=["General ledger", "GDPdU export"],
                evidence=[export_ref, confirmation_ref, physical_ref],
                counterevidence_considered=[
                    "German thousands separators are normalized before comparison.",
                    "The physical count excludes schema metadata and counts only data rows.",
                    "No finding is published when both declarations and the file agree.",
                ],
                next_step=(
                    "Regenerate and sign the completeness confirmations, reconcile the omitted or "
                    "additional rows, and verify the file hash before relying on the population."
                ),
            )
        ]

    def detect_manual_journal_approval_violations(self) -> tuple[list[Finding], int]:
        threshold_result = extract_jet_threshold(
            getattr(self, "jet_planning", self.planning)
        )
        if not threshold_result:
            return [], 0
        threshold, threshold_ref = threshold_result
        findings: list[Finding] = []
        suppressed = 0
        for approval in _unique_rows(self.journal_approvals):
            reason = _approval_violation_reason(approval)
            if not reason:
                continue
            declared_absolute = parse_decimal(approval.data.get("SUMME_ABS_EUR"))
            if declared_absolute < threshold:
                suppressed += 1
                continue
            capture_number = approval.data.get("ERFASSUNGSNUMMER", "")
            linked_rows = _unique_rows(self.gl_by_capture.get(capture_number, []))
            manual_markers = {"erstellte journale", "created journals", "manual journal"}
            has_manual_origin = any(
                normalize_text(row.data.get(field)) in manual_markers
                for row in linked_rows
                for field in ("PERIODENZUGEHÖRIGKEIT", "BUCHUNGSTYP", "JOURNAL_ORIGIN")
            )
            try:
                expected_lines = int(approval.data.get("ANZAHL_ZEILEN", ""))
            except ValueError:
                suppressed += 1
                continue
            linked_absolute = sum(
                (abs(parse_decimal(row.data.get("BUCHUNGSBETRAG"))) for row in linked_rows),
                Decimal("0"),
            )
            if (
                not linked_rows
                or not has_manual_origin
                or len(linked_rows) != expected_lines
                or abs(linked_absolute - declared_absolute) > Decimal("0.01")
            ):
                suppressed += 1
                continue
            positive_rows = [
                row
                for row in linked_rows
                if parse_decimal(row.data.get("BUCHUNGSBETRAG")) > 0
            ]
            if not positive_rows:
                suppressed += 1
                continue
            approval_ref = approval.evidence(
                "ERFASSUNGSNUMMER",
                "JOURNALNAME",
                "ANZAHL_ZEILEN",
                "SUMME_ABS_EUR",
                "ERSTELLER",
                "FREIGEBER",
                "FREIGABESTATUS",
            )
            posting_refs = [
                row.evidence(
                    "SACHKONTONUMMER",
                    "BUCHUNGSNUMMER",
                    "BUCHUNGSDATUM",
                    "BUCHUNGSBETRAG",
                    "BUCHUNGSTEXT",
                    "ERFASSUNGSNUMMER",
                    "BENUTZERKENNUNG",
                )
                for row in positive_rows
            ]
            exposure = sum(
                (parse_decimal(row.data.get("BUCHUNGSBETRAG")) for row in positive_rows),
                Decimal("0"),
            )
            journal_name = approval.data.get("JOURNALNAME") or capture_number
            findings.append(
                Finding(
                    id=_finding_id(
                        "MANUAL_JOURNAL_APPROVAL_VIOLATION",
                        capture_number,
                    ),
                    rule_id="MANUAL_JOURNAL_APPROVAL_VIOLATION",
                    category="control",
                    severity="high",
                    confidence=Decimal("0.99"),
                    title=f"Material manual journal {journal_name} bypassed independent approval",
                    summary=(
                        f"The approval log states that the {reason}. The linked manual journal "
                        "reconciles to the log and exceeds the planning document's source-defined "
                        "JET threshold."
                    ),
                    amount=exposure,
                    currency="EUR",
                    calculation=CalculationTrace(
                        currency="EUR",
                        terms=[
                            CalculationTerm(
                                label=(
                                    row.data.get("BUCHUNGSNUMMER")
                                    or f"ledger row {row.row_number}"
                                ),
                                value=parse_decimal(row.data.get("BUCHUNGSBETRAG")),
                                evidence=reference,
                            )
                            for row, reference in zip(
                                positive_rows, posting_refs, strict=True
                            )
                        ],
                    ),
                    affected_entities=[
                        capture_number,
                        journal_name,
                        approval.data.get("ERSTELLER", ""),
                    ],
                    evidence=[approval_ref, threshold_ref, *posting_refs],
                    counterevidence_considered=[
                        "Approval exceptions below the source-defined JET threshold are suppressed.",
                        "Only manual-origin ledger rows are linked.",
                        "Declared line count and absolute journal volume must reconcile to the ledger.",
                        "Independently approved journals remain clean.",
                    ],
                    next_step=(
                        "Obtain the business support and independent retrospective approval; inspect "
                        "the preparer's access and related period-end entries."
                    ),
                )
            )
        return findings, suppressed

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
            expense_evidence = [
                row.evidence(
                    "SACHKONTONUMMER",
                    "BUCHUNGSNUMMER",
                    "BUCHUNGSDATUM",
                    "BUCHUNGSBETRAG",
                    "BUCHUNGSTEXT",
                    "BENUTZERKENNUNG",
                )
                for row in expense_lines
            ]
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
            evidence.extend(expense_evidence)
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
                    calculation=CalculationTrace(
                        currency="EUR",
                        terms=[
                            CalculationTerm(
                                label=row.data.get("BUCHUNGSNUMMER")
                                or f"ledger row {row.row_number}",
                                value=parse_decimal(row.data.get("BUCHUNGSBETRAG")),
                                evidence=reference,
                            )
                            for row, reference in zip(
                                expense_lines, expense_evidence, strict=True
                            )
                        ],
                    ),
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
        calculation_terms: list[CalculationTerm] = []
        for asset, posting in matches:
            evidence.append(
                asset.evidence("ANLAGENNUMMER", "ANLAGENBEZEICHNUNG", "ANLAGENGRUPPE")
            )
            posting_reference = posting.evidence(
                "ANLAGENNUMMER",
                "WERTSTELLUNG",
                "BELEGNUMMER",
                "BUCHUNGSBETRAG",
                "BUCHUNGSART",
            )
            evidence.append(posting_reference)
            calculation_terms.append(
                CalculationTerm(
                    label=posting.data.get("BELEGNUMMER")
                    or f"asset posting row {posting.row_number}",
                    value=parse_decimal(posting.data.get("BUCHUNGSBETRAG")),
                    evidence=posting_reference,
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
                calculation=CalculationTrace(
                    currency="EUR",
                    terms=calculation_terms,
                ),
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
        evidence: list[EvidenceRef] = []
        calculation_terms = []
        for invoice, receipt in matches:
            invoice_reference = invoice.evidence(
                "RECHNUNGSNUMMER",
                "KREDITOR",
                "FAKTURADATUM",
                "LEISTUNGSDATUM",
                "BETRAG_EUR",
            )
            evidence.extend(
                (
                    invoice_reference,
                    receipt.evidence(
                        "WARENEINGANG_NR",
                        "WARENEINGANG_DATUM",
                        "KREDITOR",
                        "BETRAG_EUR",
                        "BEMERKUNG",
                    ),
                )
            )
            calculation_terms.append(
                CalculationTerm(
                    label=invoice.data.get("RECHNUNGSNUMMER")
                    or f"invoice row {invoice.row_number}",
                    value=parse_decimal(invoice.data.get("BETRAG_EUR")),
                    evidence=invoice_reference,
                )
            )
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
                calculation=CalculationTrace(
                    currency="EUR",
                    terms=calculation_terms,
                ),
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
            payment_evidence = [
                row.evidence(
                    "LIEFERANTENKONTONUMMER",
                    "BUCHUNGSNUMMER",
                    "BUCHUNGSDATUM",
                    "BUCHUNGSTEXT",
                    "BUCHUNGSBETRAG",
                )
                for row in near
            ]
            evidence.extend(payment_evidence)
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
                    calculation=CalculationTrace(
                        currency="EUR",
                        terms=[
                            CalculationTerm(
                                label=row.data.get("BUCHUNGSNUMMER")
                                or f"payment row {row.row_number}",
                                value=parse_decimal(row.data.get("BUCHUNGSBETRAG")),
                                evidence=reference,
                            )
                            for row, reference in zip(
                                near, payment_evidence, strict=True
                            )
                        ],
                    ),
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
