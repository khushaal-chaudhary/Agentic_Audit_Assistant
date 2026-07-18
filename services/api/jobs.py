from __future__ import annotations

import json
import shutil
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, TypeAdapter

from audit_core.models import DossierReport


class JobStatus(BaseModel):
    id: str
    dossier_name: str
    stage: str
    progress: int = Field(ge=0, le=100)
    message: str
    created_at: datetime
    updated_at: datetime
    report_ready: bool = False
    error: str | None = None


class ReviewDisposition(BaseModel):
    finding_id: str
    status: Literal["pending", "confirmed", "dismissed"]
    note: str = ""
    reviewer: str
    updated_at: datetime


class JobStore:
    """Small filesystem job store for the local demo; state survives API restarts."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def create(self, dossier_name: str) -> JobStatus:
        now = datetime.now(timezone.utc)
        job = JobStatus(
            id=str(uuid4()),
            dossier_name=dossier_name,
            stage="queued",
            progress=5,
            message="Dossier accepted",
            created_at=now,
            updated_at=now,
        )
        self.job_dir(job.id).mkdir(parents=True)
        self._write_status(job)
        return job

    def job_dir(self, job_id: str) -> Path:
        return self.root / job_id

    def incoming_dir(self, job_id: str) -> Path:
        path = self.job_dir(job_id) / "incoming"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def status(self, job_id: str) -> JobStatus:
        path = self.job_dir(job_id) / "status.json"
        if not path.exists():
            raise KeyError(job_id)
        return JobStatus.model_validate_json(path.read_text(encoding="utf-8"))

    def update(self, job_id: str, **changes: object) -> JobStatus:
        with self._lock:
            current = self.status(job_id)
            updated = current.model_copy(
                update={**changes, "updated_at": datetime.now(timezone.utc)}
            )
            self._write_status(updated)
            return updated

    def save_report(self, job_id: str, report: DossierReport) -> None:
        self._atomic_write(
            self.job_dir(job_id) / "report.json",
            report.model_dump_json(indent=2),
        )
        self.update(
            job_id,
            stage="complete",
            progress=100,
            message="Evidence-linked report ready",
            report_ready=True,
        )

    def report(self, job_id: str) -> DossierReport:
        path = self.job_dir(job_id) / "report.json"
        if not path.exists():
            raise FileNotFoundError(job_id)
        return DossierReport.model_validate_json(path.read_text(encoding="utf-8"))

    def reviews(self, job_id: str) -> list[ReviewDisposition]:
        self.status(job_id)
        path = self.job_dir(job_id) / "reviews.json"
        if not path.exists():
            return []
        return TypeAdapter(list[ReviewDisposition]).validate_json(
            path.read_text(encoding="utf-8")
        )

    def save_review(
        self, job_id: str, review: ReviewDisposition
    ) -> ReviewDisposition:
        with self._lock:
            reviews = {item.finding_id: item for item in self.reviews(job_id)}
            reviews[review.finding_id] = review
            ordered = sorted(reviews.values(), key=lambda item: item.finding_id)
            self._atomic_write(
                self.job_dir(job_id) / "reviews.json",
                json.dumps(
                    [item.model_dump(mode="json") for item in ordered],
                    indent=2,
                ),
            )
        return review

    def prepare_source(self, job_id: str) -> Path:
        incoming = self.incoming_dir(job_id)
        source = self.job_dir(job_id) / "source"
        source.mkdir(parents=True, exist_ok=True)
        for path in incoming.iterdir():
            if path.suffix.casefold() == ".zip":
                self._extract_zip(path, source)
            elif path.is_file():
                shutil.copy2(path, source / path.name)
        return source

    def save_source_root(self, job_id: str, source: Path) -> None:
        self._atomic_write(self.job_dir(job_id) / "source-root.txt", str(source.resolve()))

    def source_root(self, job_id: str) -> Path:
        path = self.job_dir(job_id) / "source-root.txt"
        if not path.exists():
            raise FileNotFoundError(job_id)
        return Path(path.read_text(encoding="utf-8")).resolve()

    @staticmethod
    def safe_filename(name: str) -> str:
        cleaned = Path(name.replace(chr(92), "/")).name.strip()
        if not cleaned or cleaned in {".", ".."}:
            raise ValueError("Invalid upload filename")
        return cleaned

    @staticmethod
    def _extract_zip(archive: Path, destination: Path) -> None:
        destination_resolved = destination.resolve()
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                target = (destination / member.filename).resolve()
                if destination_resolved not in target.parents and target != destination_resolved:
                    raise ValueError(f"Unsafe archive path: {member.filename}")
            bundle.extractall(destination)

    def _write_status(self, status: JobStatus) -> None:
        self._atomic_write(
            self.job_dir(status.id) / "status.json",
            status.model_dump_json(indent=2),
        )

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
