from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_serializer, model_validator


class EvidenceRef(BaseModel):
    document: str
    locator_type: Literal["row", "cell", "passage", "page", "query"]
    row: int | None = None
    columns: list[str] = Field(default_factory=list)
    sheet: str | None = None
    cell_range: str | None = None
    page: int | None = None
    passage: str | None = None
    query: str | None = None
    excerpt: str
    sha256: str


class CalculationTerm(BaseModel):
    label: str = Field(min_length=1)
    value: Decimal
    evidence: EvidenceRef

    @field_serializer("value")
    def serialize_value(self, value: Decimal) -> str:
        return format(value, "f")


class CalculationTrace(BaseModel):
    operation: Literal["sum"] = "sum"
    currency: str
    terms: list[CalculationTerm] = Field(min_length=1)


class Finding(BaseModel):
    id: str
    rule_id: str
    category: Literal["fraud", "misstatement", "control"]
    severity: Literal["high", "medium", "low"]
    confidence: Decimal
    title: str
    summary: str
    amount: Decimal | None = None
    currency: str | None = None
    calculation: CalculationTrace | None = None
    affected_entities: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef]
    counterevidence_considered: list[str] = Field(default_factory=list)
    next_step: str

    @field_serializer("confidence", "amount")
    def serialize_decimal(self, value: Decimal | None) -> str | None:
        return None if value is None else format(value, "f")

    @model_validator(mode="after")
    def validate_calculation_lineage(self) -> "Finding":
        if self.amount is None:
            if self.calculation is not None:
                raise ValueError("A calculation trace requires a displayed amount")
            return self
        if self.calculation is None:
            raise ValueError("Displayed amounts require an exact calculation trace")
        if self.currency != self.calculation.currency:
            raise ValueError("Finding and calculation currencies must match")
        total = sum((term.value for term in self.calculation.terms), Decimal("0"))
        if total != self.amount:
            raise ValueError(
                f"Calculation terms total {total} but finding amount is {self.amount}"
            )
        term_keys = [
            term.evidence.model_dump_json(exclude_none=True)
            for term in self.calculation.terms
        ]
        if len(term_keys) != len(set(term_keys)):
            raise ValueError("Calculation terms cannot repeat the same evidence locator")
        evidence_keys = {
            reference.model_dump_json(exclude_none=True)
            for reference in self.evidence
        }
        if missing := set(term_keys) - evidence_keys:
            raise ValueError(
                f"Calculation terms contain {len(missing)} locator(s) absent from finding evidence"
            )
        return self


class ProcedureResult(BaseModel):
    rule_id: str
    status: Literal["completed", "not_testable"]
    reason: str | None = None


class IngestionDocument(BaseModel):
    document: str
    format: str
    status: Literal["recognized", "ambiguous", "unclassified", "unsupported"]
    role_matches: list[str] = Field(default_factory=list)
    reason: str
    extraction_status: Literal["native", "partial", "unreadable", "not_applicable"] = (
        "not_applicable"
    )
    page_count: int | None = None
    extracted_pages: int = 0
    passage_count: int = 0


class IngestionRole(BaseModel):
    role: str
    status: Literal["resolved", "ambiguous", "missing"]
    document: str | None = None
    header_map: dict[str, str] = Field(default_factory=dict)
    reason: str


class IngestionCoverage(BaseModel):
    documents: list[IngestionDocument] = Field(default_factory=list)
    roles: list[IngestionRole] = Field(default_factory=list)
    source_passages: list[EvidenceRef] = Field(default_factory=list)


class DossierReport(BaseModel):
    dossier_name: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    files_scanned: int
    tests_run: int
    findings: list[Finding]
    procedures: list[ProcedureResult] = Field(default_factory=list)
    suppressed_leads: int = 0
    ingestion: IngestionCoverage | None = None
    engine_version: str = "0.5.0"


def ensure_grounded(report: DossierReport) -> None:
    """Fail closed when a finding or numeric result lacks exact source evidence."""
    for finding in report.findings:
        if not finding.evidence:
            raise ValueError(f"Finding {finding.id} has no evidence")
        if finding.amount is not None:
            if finding.calculation is None:
                raise ValueError(f"Numeric finding {finding.id} has no calculation trace")
            if not all(term.evidence.excerpt for term in finding.calculation.terms):
                raise ValueError(
                    f"Numeric finding {finding.id} has an empty calculation source excerpt"
                )
