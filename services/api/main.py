from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from audit_core import DossierReport, analyze_dossier
from audit_core.integrations import CogneeClient, integration_status


REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")
DEFAULT_SAMPLE = (
    REPO_ROOT / "Uebungsdaten_Muster_Verpackungen" / "Uebungsdaten Muster Verpackungen"
)

app = FastAPI(
    title="Agentic Audit Assistant API",
    version="0.1.0",
    description="Deterministic, provenance-aware audit analysis.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "engine": "0.1.0", "mode": "local-first"}


@app.post("/api/demo/analyze", response_model=DossierReport)
def analyze_demo() -> DossierReport:
    sample = Path(os.getenv("AUDIT_SAMPLE_ROOT", str(DEFAULT_SAMPLE)))
    if not sample.exists():
        raise HTTPException(status_code=404, detail="Sample dossier is not available")
    try:
        return analyze_dossier(sample)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/integrations/status")
def integrations_status() -> dict[str, dict[str, str | bool]]:
    return integration_status()


@app.post("/api/demo/cognee-sync")
def sync_demo_to_cognee() -> dict:
    status = integration_status()
    if not status["cognee"]["configured"]:
        raise HTTPException(
            status_code=412,
            detail="Set COGNEE_API_URL and COGNEE_API_KEY in the local .env file",
        )
    report = analyze_dossier(Path(os.getenv("AUDIT_SAMPLE_ROOT", str(DEFAULT_SAMPLE))))
    try:
        return CogneeClient().sync_report(report)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Cognee sync failed: {exc}") from exc
