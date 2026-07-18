from __future__ import annotations

import json
import hashlib
import mimetypes
import os
import re
from pathlib import Path
from typing import Any

import httpx

from audit_core.graph import graph_json
from audit_core.models import DossierReport
from audit_core.parsers import decode_text


class CogneeClient:
    """Small Cognee Cloud REST adapter; credentials stay in local environment variables."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or os.getenv("COGNEE_API_URL", "")).rstrip("/")
        self.api_key = api_key or os.getenv("COGNEE_API_KEY", "")
        if not self.base_url or not self.api_key:
            raise RuntimeError("Set COGNEE_API_URL and COGNEE_API_KEY before using Cognee")

    @property
    def headers(self) -> dict[str, str]:
        return {"X-Api-Key": self.api_key}

    def health(self) -> bool:
        response = httpx.get(f"{self.base_url}/health", headers=self.headers, timeout=15)
        response.raise_for_status()
        return True

    def dataset_name(self, dossier_name: str, fingerprint: str = "") -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", dossier_name.casefold()).strip("_")
        suffix = f"_{fingerprint}" if fingerprint else ""
        return f"audit_{slug}{suffix}"[:80]

    def sync_report(
        self,
        report: DossierReport,
        source_root: Path | None = None,
        *,
        cognify: bool = True,
        include_sources: bool = False,
    ) -> dict[str, Any]:
        hashes = sorted(
            {reference.sha256 for finding in report.findings for reference in finding.evidence}
        )
        fingerprint = hashlib.sha256(
            ("projection-v3|" + "|".join(hashes)).encode()
        ).hexdigest()[:10]
        dataset = self.dataset_name(report.dossier_name, fingerprint)
        content = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2).encode()
        files = [
            ("data", ("audit-report.json", content, "application/json")),
            ("data", ("audit-evidence-graph.json", graph_json(report), "application/json")),
        ]
        supported = {".pdf", ".csv", ".txt", ".md", ".json", ".docx"}
        excluded = 0
        if source_root and include_sources:
            for path in sorted(source_root.rglob("*")):
                if not path.is_file():
                    continue
                if path.suffix.casefold() not in supported or path.stat().st_size > 25 * 1024 * 1024:
                    excluded += 1
                    continue
                relative = path.relative_to(source_root)
                upload_name = "__".join(relative.parts)
                mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                payload = (
                    decode_text(path).encode("utf-8")
                    if path.suffix.casefold() in {".csv", ".txt", ".md", ".json"}
                    else path.read_bytes()
                )
                files.append(("data", (upload_name, payload, mime)))
        elif source_root:
            excluded = sum(1 for path in source_root.rglob("*") if path.is_file())
        form = {"datasetName": dataset, "run_in_background": "false"}
        with httpx.Client(base_url=self.base_url, headers=self.headers, timeout=120) as client:
            add_response = client.post("/api/v1/add", data=form, files=files)
            conflict_detail = add_response.text.casefold()
            reused = add_response.status_code == 409 and any(
                marker in conflict_detail
                for marker in ("already exists", "already present", "duplicate")
            )
            if not reused:
                add_response.raise_for_status()
            result: dict[str, Any] = {
                "dataset": dataset,
                "uploaded_files": len(files),
                "excluded_files": excluded,
                "projection_only": not include_sources,
                "add": (
                    {"status": "already_present", "detail": add_response.text[:500]}
                    if reused
                    else add_response.json()
                ),
            }
            if cognify:
                graph_response = client.post(
                    "/api/v1/cognify",
                    json={
                        "datasets": [dataset],
                        "run_in_background": True,
                        "custom_prompt": (
                            "Build an audit evidence graph. Preserve vendor, user, account, document, "
                            "finding and evidence-locator identifiers exactly. Do not invent amounts."
                        ),
                    },
                )
                graph_response.raise_for_status()
                result["cognify"] = graph_response.json()
            return result

    def search(
        self,
        dataset: str,
        query: str,
        *,
        search_type: str = "GRAPH_COMPLETION",
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        response = httpx.post(
            f"{self.base_url}/api/v1/search",
            headers={**self.headers, "Content-Type": "application/json"},
            json={
                "datasets": [dataset],
                "query": query,
                "search_type": search_type,
                "top_k": top_k,
            },
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, list) else [payload]
