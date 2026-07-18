from __future__ import annotations

import os
import re
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, Field

from .models import DossierReport, EvidenceRef, Finding
from .parsers import normalize_text


class GroundedClaim(BaseModel):
    statement: str
    finding_ids: list[str]
    evidence: list[EvidenceRef]


class GroundedAnswer(BaseModel):
    status: Literal["answered", "not_testable"]
    claims: list[GroundedClaim] = Field(default_factory=list)
    provider: Literal["openai", "deterministic"]
    note: str


class _ModelClaim(BaseModel):
    statement: str
    finding_ids: list[str]


class _ModelAnswer(BaseModel):
    claims: list[_ModelClaim]


def _number_key(value: str) -> str:
    return "".join(character for character in value if character.isdigit())


def _numbers_supported(statement: str, findings: list[Finding]) -> bool:
    requested = [_number_key(value) for value in re.findall(r"\d[\d.,\s]*", statement)]
    requested = [value for value in requested if value]
    if not requested:
        return True
    available_parts: list[str] = []
    for finding in findings:
        available_parts.extend(
            [
                finding.id,
                finding.title,
                finding.summary,
                " ".join(finding.affected_entities),
                "" if finding.amount is None else format(finding.amount, "f"),
                " ".join(reference.excerpt for reference in finding.evidence),
            ]
        )
    available = {_number_key(value) for value in available_parts}
    available_blob = " ".join(available)
    return all(value in available_blob for value in requested)


def _resolve_claims(report: DossierReport, claims: list[_ModelClaim]) -> list[GroundedClaim]:
    by_id = {finding.id: finding for finding in report.findings}
    resolved: list[GroundedClaim] = []
    for claim in claims:
        ids = list(dict.fromkeys(value for value in claim.finding_ids if value in by_id))
        findings = [by_id[value] for value in ids]
        statement = claim.statement.strip()
        for finding_id in ids:
            statement = statement.replace(f"Finding {finding_id}", "The cited finding")
            statement = statement.replace(finding_id, "the cited finding")
        if not findings or not _numbers_supported(statement, findings):
            continue
        evidence: list[EvidenceRef] = []
        seen: set[tuple[str, str, str]] = set()
        for finding in findings:
            for reference in finding.evidence:
                key = (reference.sha256, reference.locator_type, reference.excerpt)
                if key not in seen:
                    seen.add(key)
                    evidence.append(reference)
        if evidence:
            resolved.append(
                GroundedClaim(
                    statement=statement,
                    finding_ids=ids,
                    evidence=evidence,
                )
            )
    return resolved


def _context(report: DossierReport) -> str:
    records = []
    for finding in report.findings:
        records.append(
            {
                "finding_id": finding.id,
                "category": finding.category,
                "title": finding.title,
                "summary": finding.summary,
                "amount": None if finding.amount is None else format(finding.amount, "f"),
                "currency": finding.currency,
                "affected_entities": finding.affected_entities,
                "evidence": [
                    {
                        "document": item.document,
                        "locator_type": item.locator_type,
                        "row": item.row,
                        "page": item.page,
                        "passage": item.passage,
                        "excerpt": item.excerpt,
                    }
                    for item in finding.evidence
                ],
            }
        )
    import json

    return json.dumps(records, ensure_ascii=False)


def _fallback(report: DossierReport, question: str) -> GroundedAnswer:
    tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", normalize_text(question))
        if len(token) >= 3
    }
    generic = {"was", "what", "which", "show", "tell", "please", "audit", "findings"}
    tokens -= generic
    ranked: list[tuple[int, Finding]] = []
    for finding in report.findings:
        searchable = normalize_text(
            " ".join((finding.category, finding.title, finding.summary, *finding.affected_entities))
        )
        score = sum(token in searchable for token in tokens)
        if score:
            ranked.append((score, finding))
    ranked.sort(key=lambda item: (-item[0], item[1].id))
    model_claims = [
        _ModelClaim(
            statement=f"{finding.title}. {finding.summary}",
            finding_ids=[finding.id],
        )
        for _, finding in ranked[:3]
    ]
    claims = _resolve_claims(report, model_claims)
    return GroundedAnswer(
        status="answered" if claims else "not_testable",
        claims=claims,
        provider="deterministic",
        note=(
            "Answer limited to evidence already validated by audit procedures."
            if claims
            else "The processed dossier does not contain enough validated evidence to answer this question."
        ),
    )


def answer_question(report: DossierReport, question: str) -> GroundedAnswer:
    if not os.getenv("OPENAI_API_KEY", "").strip():
        return _fallback(report, question)
    try:
        response = OpenAI().responses.parse(
            model=os.getenv("OPENAI_REASONING_MODEL", "gpt-5.4-mini"),
            store=False,
            max_output_tokens=900,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are an evidence-bound audit assistant. Answer in the user's language. "
                        "Return short factual claims only. Every claim must cite one or more exact "
                        "finding_id values from the supplied records. Do not infer missing facts. "
                        "Put finding IDs only in finding_ids; never repeat a UUID in statement. "
                        "Do not introduce any number unless that number appears in a cited record. "
                        "If the records do not answer the question, return an empty claims list."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Question: {question}\n\nValidated audit records:\n{_context(report)}",
                },
            ],
            text_format=_ModelAnswer,
        )
        parsed = response.output_parsed
        if parsed is None:
            return _fallback(report, question)
        claims = _resolve_claims(report, parsed.claims)
        if not claims:
            return _fallback(report, question)
        return GroundedAnswer(
            status="answered",
            claims=claims,
            provider="openai",
            note="Each claim was constrained to validated finding IDs and resolved to source evidence.",
        )
    except Exception:
        return _fallback(report, question)
