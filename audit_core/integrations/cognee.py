from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from audit_core.models import DossierReport


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

    def dataset_name(self, dossier_name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", dossier_name.casefold()).strip("_")
        return f"audit_{slug}"[:80]

    def sync_report(self, report: DossierReport, *, cognify: bool = True) -> dict[str, Any]:
        dataset = self.dataset_name(report.dossier_name)
        content = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2).encode()
        files = [("data", ("audit-report.json", content, "application/json"))]
        form = {"datasetName": dataset, "run_in_background": "false"}
        with httpx.Client(base_url=self.base_url, headers=self.headers, timeout=120) as client:
            add_response = client.post("/api/v1/add", data=form, files=files)
            add_response.raise_for_status()
            result: dict[str, Any] = {"dataset": dataset, "add": add_response.json()}
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

