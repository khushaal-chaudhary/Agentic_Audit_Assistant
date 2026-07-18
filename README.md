# Agentic Audit Assistant

An evidence-first audit tool for German and English financial dossiers. It parses mixed document
formats, reconciles structured records, combines control signals, and returns findings with exact
source locators.

## Current baseline

- GDPdU `index.xml`-driven parsing for headerless ledger exports.
- Locale-safe `Decimal` handling for German monetary values.
- CSV/TXT, XLSX, DOCX, and PDF source adapters.
- Generic detectors for vendor-control conflicts, capitalised repairs, cut-off failures, and split payments.
- Persisted ZIP ingestion jobs with progress, secure source-document links, and restart-safe reports.
- Persisted auditor dispositions with rationale-gated dismissal and direct finding navigation.
- A typed evidence graph in which findings and decimal calculations must resolve to source locators.
- Grounded OpenAI Q&A with deterministic fallback and server-side citation/number validation.
- Cost-controlled Cognee graph projection; deterministic analysis works without cloud services.

## Local demo

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\scripts\start-local.ps1
```

The script starts the API on `http://127.0.0.1:8000` and the UI on
`http://127.0.0.1:3000`.
Run the bundled sample directly, or upload the dossier ZIP so its folder structure is preserved.

Copy `.env.example` to `.env` and add the OpenAI and Cognee credentials for optional cloud
features. Cognee receives the compact typed graph and validated excerpts rather than expensive raw
ledger embeddings. The UI reports credit limits explicitly if Cognee still rejects a graph run.

## CLI

```powershell
.venv\Scripts\python.exe -m audit_core.cli analyze `
  "Uebungsdaten_Muster_Verpackungen\Uebungsdaten Muster Verpackungen"
```

## Hosting

The demo is local-first and needs no paid infrastructure. A Cloud Run-ready container is retained as
an optional deployment target. See `docs/architecture.md`.

## Audit logic

The living specification for implemented rules, false-positive suppression, known limitations, and
required tests is in [docs/deterministic-rules.md](docs/deterministic-rules.md).

For a non-technical product explanation, common questions, and a suggested demo narrative, see
[docs/layman-explainer.md](docs/layman-explainer.md).
