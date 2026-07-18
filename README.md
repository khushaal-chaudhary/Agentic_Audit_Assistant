# Agentic Audit Assistant

An evidence-first audit tool for German and English financial dossiers. It parses mixed document
formats, reconciles structured records, combines control signals, and returns findings with exact
source locators.

## Current baseline

- GDPdU `index.xml`-driven parsing for headerless ledger exports.
- Locale-safe `Decimal` handling for German monetary values.
- CSV/TXT, XLSX, DOCX, and PDF source adapters.
- Generic detectors for vendor-control conflicts, capitalised repairs, cut-off failures, and split payments.
- FastAPI report endpoint and a Next.js investigation interface.
- Cognee and OpenAI hooks; deterministic analysis works without either service.

## Local demo

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\scripts\start-local.ps1
```

The script starts the API on `http://localhost:8000` and the UI on `http://localhost:3000`.

## CLI

```powershell
.venv\Scripts\python.exe -m audit_core.cli analyze `
  "Uebungsdaten_Muster_Verpackungen\Uebungsdaten Muster Verpackungen"
```

## Hosting

The demo is local-first and needs no paid infrastructure. A Cloud Run-ready container is retained as
an optional deployment target. See `docs/architecture.md`.

