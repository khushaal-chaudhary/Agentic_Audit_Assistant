# Agentic Audit Assistant

An evidence-first audit tool for German and English financial dossiers. It parses mixed document
formats, reconciles structured records, combines control signals, and returns findings with exact
source locators. Every displayed claim resolves to a page/row/passage in a source document, and
every monetary total recomputes from those exact terms using `Decimal` arithmetic.

## Highlights

- **Six deterministic detectors implemented today** (11 more scoped in the rule catalog): vendor
  control chain, capitalised repairs, unrecorded cut-off liabilities, split payments below
  threshold, export completeness reconciliation, and manual journal approval violations.
- **GDPdU-native ingestion**: streams `index.xml`-driven, headerless German ledger exports at
  ~1M rows without loading them into memory, and joins the approval log by capture ID with a
  strict line-count + amount + manual-origin guard.
- **Schema-based discovery**: document roles are identified by field signatures and content, not
  filenames. Missing required inputs produce `not_testable` procedures, never false findings.
- **Grounded evidence graph**: calculation edges point only to exact contributing terms. Each
  finding recomputes its total from those terms on render, so tampering is detectable.
- **Locale-safe money**: `Decimal` end-to-end with German number parsing; no binary floats.
- **PDF text extraction** into page-and-line passages. Image-only PDFs are retained and marked
  unreadable — OCR is intentionally off to avoid hallucinated evidence.
- **Persisted ingestion jobs** with progress, secure source-document links, and restart-safe
  reports. Auditor dispositions require rationale-gated dismissal.
- **Optional grounded LLM Q&A** (OpenAI) with server-side citation and number validation, and a
  cost-controlled Cognee graph projection. Deterministic analysis works fully offline.

## Local demo

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\scripts\start-local.ps1
```

- API: <http://127.0.0.1:8000>
- UI: <http://127.0.0.1:3000>

The UI ships two dossier buttons in the agent bar:

- **Run sample dataset** — the bundled `Uebungsdaten_Muster_Verpackungen` teaching dossier.
- **Run final dataset ↑** — the preloaded Cortea final dossier (~1.08M ledger rows).

Uploading a ZIP that preserves its folder structure replaces both with an **Analyze upload ↑**
button. `AUDIT_SAMPLE_ROOT` and `AUDIT_FINAL_ROOT` (or the legacy `AUDIT_DEMO_ROOT`) can point
either action at a different local dossier — see `.env.example`.

Copy `.env.example` to `.env` and add OpenAI and Cognee credentials for optional cloud features.
Cognee receives the compact typed graph and validated excerpts, not raw ledger embeddings. The UI
reports credit limits explicitly if Cognee rejects a graph run.

## CLI

```powershell
.venv\Scripts\python.exe -m audit_core.cli analyze `
  "Uebungsdaten_Muster_Verpackungen\Uebungsdaten Muster Verpackungen"
```

## Public API

Served by FastAPI on port 8000. All state is local; nothing is uploaded to third parties unless
you configure OpenAI or Cognee keys.

| Method | Path                          | Purpose                                                       |
| ------ | ----------------------------- | ------------------------------------------------------------- |
| GET    | `/`                           | Health probe.                                                 |
| GET    | `/api/rules`                  | Rule catalog — `implemented` vs `planned` with metadata.      |
| POST   | `/api/dossiers/sample`        | Kick a job against the bundled sample dossier.                |
| POST   | `/api/dossiers/final`         | Kick a job against the preloaded final dossier.               |
| POST   | `/api/dossiers`               | Kick a job against an uploaded ZIP (multipart).               |
| GET    | `/api/jobs/{id}`              | Job status and progress.                                      |
| GET    | `/api/reports/{id}`           | Rendered report with grounded evidence and findings.          |
| GET    | `/api/reports/{id}/sources/…` | Signed access to individual source documents.                 |
| POST   | `/api/qa`                     | Grounded Q&A over the loaded dossier (fallback: deterministic).|

## Verify

```powershell
.venv\Scripts\python.exe -m pytest        # 70 tests, incl. clean-twin regressions
.venv\Scripts\python.exe -m ruff check .
npm --prefix apps\web run build           # Next.js 16 production build
```

## Hosting

The demo is local-first and needs no paid infrastructure. A Cloud Run-ready container is retained
as an optional deployment target. See [docs/architecture.md](docs/architecture.md).

## Documentation

- [docs/deterministic-rules.md](docs/deterministic-rules.md) — living rule specification: what each
  detector tests, its false-positive suppression, known limitations, and required tests.
- [docs/ingestion-discovery.md](docs/ingestion-discovery.md) — supported document roles, canonical
  fields, aliases, and ambiguity behavior.
- [docs/architecture.md](docs/architecture.md) — system architecture and hosting notes.
- [docs/layman-explainer.md](docs/layman-explainer.md) — non-technical explanation, common
  questions, and a suggested demo narrative.
- [docs/ai-agent-handoff.md](docs/ai-agent-handoff.md) — engineering handoff with non-negotiable
  rules for anyone (human or agent) contributing changes.

## Tools and frameworks

- **Backend**: Python 3.11, FastAPI, Uvicorn, `pydantic`, `openpyxl`, `python-docx`, `pdfplumber`,
  `pytest`, `ruff`. Decimal-only monetary arithmetic; no numeric coercion at the boundary.
- **Frontend**: Next.js 16 (Turbopack), React 19, TypeScript, Tailwind CSS.
- **Optional**: OpenAI SDK for grounded reasoning; Cognee for the typed graph projection.
- **Runtime**: local first — `scripts/start-local.ps1` runs both processes as background services
  and writes PIDs and logs under `data/runtime/`.
