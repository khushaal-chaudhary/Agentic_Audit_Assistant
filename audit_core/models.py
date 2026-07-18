from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_serializer


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
    affected_entities: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef]
    counterevidence_considered: list[str] = Field(default_factory=list)
    next_step: str

    @field_serializer("confidence", "amount")
    def serialize_decimal(self, value: Decimal | None) -> str | None:
        return None if value is None else format(value, "f")


class DossierReport(BaseModel):
    dossier_name: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    files_scanned: int
    tests_run: int
    findings: list[Finding]
    suppressed_leads: int = 0
    engine_version: str = "0.1.0"


def ensure_grounded(report: DossierReport) -> None:
    """Fail closed when a finding or numeric result lacks source evidence."""
    for finding in report.findings:
        if not finding.evidence:
            raise ValueError(f"Finding {finding.id} has no evidence")
        if finding.amount is not None and not any(ref.excerpt for ref in finding.evidence):
            raise ValueError(f"Numeric finding {finding.id} has no source excerpt")

