from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError, model_validator
from fastapi.responses import FileResponse

from audit_core import DossierReport, analyze_dossier
from audit_core.integrations import CogneeClient, integration_status
from audit_core.qa import GroundedAnswer, answer_question
from audit_core.parsers import file_sha256, locate_dossier_root
from audit_core.rules import RULE_CATALOG, RuleDefinition
from services.api.jobs import JobStatus, JobStore, ReviewDisposition


REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")
DEFAULT_SAMPLE = (
    REPO_ROOT / "Uebungsdaten_Muster_Verpackungen" / "Uebungsdaten Muster Verpackungen"
)
JOBS = JobStore(REPO_ROOT / "data" / "runtime" / "dossiers")
LOCAL_DEMO_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")


def allowed_origins() -> list[str]:
    configured = [
        origin.strip()
        for origin in os.getenv("ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    ]
    return list(dict.fromkeys([*LOCAL_DEMO_ORIGINS, *configured]))


class QuestionRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)


class DocumentSummary(BaseModel):
    path: str
    name: str
    extension: str
    size_bytes: int
    sha256: str
    evidence_locations: int


class ReviewRequest(BaseModel):
    status: Literal["pending", "confirmed", "dismissed"]
    note: str = Field(default="", max_length=1000)
    reviewer: str = Field(default="Local auditor", min_length=1, max_length=80)

    @model_validator(mode="after")
    def require_dismissal_rationale(self) -> "ReviewRequest":
        self.note = self.note.strip()
        self.reviewer = self.reviewer.strip()
        if not self.reviewer:
            raise ValueError("Reviewer is required")
        if self.status == "dismissed" and len(self.note) < 5:
            raise ValueError("Dismissed findings require a rationale of at least 5 characters")
        return self


app = FastAPI(
    title="Agentic Audit Assistant API",
    version="0.3.0",
    description="Deterministic, provenance-aware audit analysis.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["*"],
)


def _job(job_id: str) -> JobStatus:
    try:
        return JOBS.status(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Dossier job not found") from exc


def _report(job_id: str) -> DossierReport:
    _job(job_id)
    try:
        return JOBS.report(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail="Dossier report is not ready") from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=409,
            detail="Dossier report uses an older schema; rerun the analysis",
        ) from exc


def _process_job(job_id: str, source: Path | None = None) -> None:
    try:
        if source is None:
            JOBS.update(
                job_id,
                stage="extracting",
                progress=20,
                message="Validating and extracting uploaded files",
            )
            source = JOBS.prepare_source(job_id)
        JOBS.update(
            job_id,
            stage="analyzing",
            progress=45,
            message="Running cross-document audit procedures",
        )
        JOBS.save_source_root(job_id, locate_dossier_root(source))
        report = analyze_dossier(source)
        JOBS.update(
            job_id,
            stage="validating",
            progress=85,
            message="Checking every finding for source provenance",
        )
        JOBS.save_report(job_id, report)
    except Exception as exc:
        JOBS.update(
            job_id,
            stage="failed",
            progress=100,
            message="Dossier processing failed",
            error=str(exc),
        )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "engine": "0.3.0", "mode": "local-first"}


@app.post(
    "/api/dossiers",
    response_model=JobStatus,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_dossier(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
) -> JobStatus:
    if not files:
        raise HTTPException(status_code=422, detail="Add at least one source file")
    first_name = JOBS.safe_filename(files[0].filename or "uploaded-dossier")
    job = JOBS.create(Path(first_name).stem)
    try:
        for index, upload in enumerate(files):
            filename = JOBS.safe_filename(upload.filename or f"source-{index + 1}")
            target = JOBS.incoming_dir(job.id) / filename
            if target.exists():
                target = target.with_name(f"{target.stem}-{index + 1}{target.suffix}")
            size = 0
            with target.open("wb") as destination:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    if size > 250 * 1024 * 1024:
                        raise HTTPException(status_code=413, detail="A source file exceeds 250 MB")
                    destination.write(chunk)
            await upload.close()
    except Exception:
        JOBS.update(
            job.id,
            stage="failed",
            progress=100,
            message="Upload failed",
            error="The uploaded files could not be stored",
        )
        raise
    JOBS.update(job.id, stage="uploaded", progress=10, message="Sources stored locally")
    background_tasks.add_task(_process_job, job.id)
    return JOBS.status(job.id)


@app.post(
    "/api/dossiers/sample",
    response_model=JobStatus,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_sample_dossier(background_tasks: BackgroundTasks) -> JobStatus:
    sample = Path(os.getenv("AUDIT_SAMPLE_ROOT", str(DEFAULT_SAMPLE)))
    if not sample.exists():
        raise HTTPException(status_code=404, detail="Sample dossier is not available")
    job = JOBS.create(sample.name)
    background_tasks.add_task(_process_job, job.id, sample)
    return job


@app.get("/api/dossiers/{job_id}/status", response_model=JobStatus)
def dossier_status(job_id: str) -> JobStatus:
    return _job(job_id)


@app.get("/api/dossiers/{job_id}/report", response_model=DossierReport)
def dossier_report(job_id: str) -> DossierReport:
    return _report(job_id)


@app.get(
    "/api/dossiers/{job_id}/reviews",
    response_model=list[ReviewDisposition],
)
def dossier_reviews(job_id: str) -> list[ReviewDisposition]:
    _report(job_id)
    return JOBS.reviews(job_id)


@app.put(
    "/api/dossiers/{job_id}/reviews/{finding_id}",
    response_model=ReviewDisposition,
)
def update_dossier_review(
    job_id: str,
    finding_id: str,
    request: ReviewRequest,
) -> ReviewDisposition:
    report = _report(job_id)
    if not any(finding.id == finding_id for finding in report.findings):
        raise HTTPException(status_code=404, detail="Finding not found in this dossier")
    return JOBS.save_review(
        job_id,
        ReviewDisposition(
            finding_id=finding_id,
            status=request.status,
            note=request.note,
            reviewer=request.reviewer,
            updated_at=datetime.now(timezone.utc),
        ),
    )


@app.get("/api/dossiers/{job_id}/documents", response_model=list[DocumentSummary])
def dossier_documents(job_id: str) -> list[DocumentSummary]:
    report = _report(job_id)
    try:
        root = JOBS.source_root(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail="Dossier sources are not ready") from exc
    evidence_counts: dict[str, int] = {}
    for finding in report.findings:
        for reference in finding.evidence:
            evidence_counts[reference.document] = (
                evidence_counts.get(reference.document, 0) + 1
            )
    return [
        DocumentSummary(
            path=path.relative_to(root).as_posix(),
            name=path.name,
            extension=path.suffix.casefold().lstrip(".") or "file",
            size_bytes=path.stat().st_size,
            sha256=file_sha256(str(path)),
            evidence_locations=evidence_counts.get(path.relative_to(root).as_posix(), 0),
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


@app.get("/api/dossiers/{job_id}/documents/{document_path:path}")
def dossier_document(job_id: str, document_path: str) -> FileResponse:
    _job(job_id)
    try:
        root = JOBS.source_root(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail="Dossier sources are not ready") from exc
    target = (root / document_path).resolve()
    if (root not in target.parents and target != root) or not target.is_file():
        raise HTTPException(status_code=404, detail="Source document not found")
    return FileResponse(target, filename=target.name)


@app.post("/api/dossiers/{job_id}/questions", response_model=GroundedAnswer)
def ask_dossier(job_id: str, request: QuestionRequest) -> GroundedAnswer:
    return answer_question(_report(job_id), request.question)


@app.post("/api/dossiers/{job_id}/cognee-sync")
def sync_dossier_to_cognee(job_id: str) -> dict:
    if not integration_status()["cognee"]["configured"]:
        raise HTTPException(status_code=412, detail="Cognee is not configured")
    try:
        return CogneeClient().sync_report(_report(job_id), JOBS.source_root(job_id))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 402:
            try:
                cognee_detail = exc.response.json().get("detail")
            except ValueError:
                cognee_detail = None
            raise HTTPException(
                status_code=402,
                detail=cognee_detail
                or "Cognee estimates this graph build exceeds the available credits.",
            ) from exc
        raise HTTPException(
            status_code=502,
            detail=f"Cognee sync failed with status {exc.response.status_code}",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Cognee sync failed: {exc}") from exc


@app.get("/api/integrations/status")
def integrations_status() -> dict[str, dict[str, str | bool]]:
    return integration_status()


@app.get("/api/rules", response_model=list[RuleDefinition])
def rules_catalog() -> list[RuleDefinition]:
    return RULE_CATALOG


# Compatibility endpoints retained for scripts created against the first local baseline.
@app.post("/api/demo/analyze", response_model=DossierReport)
def analyze_demo() -> DossierReport:
    sample = Path(os.getenv("AUDIT_SAMPLE_ROOT", str(DEFAULT_SAMPLE)))
    if not sample.exists():
        raise HTTPException(status_code=404, detail="Sample dossier is not available")
    try:
        return analyze_dossier(sample)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/demo/cognee-sync")
def sync_demo_to_cognee() -> dict:
    report = analyze_demo()
    try:
        return CogneeClient().sync_report(report, Path(os.getenv("AUDIT_SAMPLE_ROOT", str(DEFAULT_SAMPLE))))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Cognee sync failed: {exc}") from exc
