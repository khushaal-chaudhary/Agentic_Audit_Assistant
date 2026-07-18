# AI agent handoff

Updated: 2026-07-18 (Europe/Berlin)

## Mission and submission

Build and submit an evidence-first audit assistant for a mixed German/English financial dossier.
The final deliverables are:

1. a GitHub repository;
2. a two-minute screen recording made with Luma;
3. a convincing run on the supplied final dossier.

The video should not spend time uploading files. Nobody will use the product interactively during
judging. Preload the final dossier and demonstrate the strongest findings, exact source passage,
exact calculation trace, and deterministic rule coverage.

## Non-negotiable repository rules

Read `AGENTS.md` before changing code. In particular:

- Every displayed claim must resolve to one or more exact source locators.
- Use `Decimal` for money. Never use binary floating point for audit calculations.
- Runtime rules must be generic. Never hard-code sample/final vendor IDs, document IDs, dates, or
  expected fraud totals.
- Missing required input produces `not_testable`, never a finding.
- Every new detector needs a clean/decoy regression test.
- Run the complete Python test suite and the frontend production build before pushing.
- `UEBUNG_GROUND-TRUTH_SEALED_Muster-Verpackungen.md` is only the sample/test dossier's local
  answer key. Do not open or commit it while designing generic rules.
- Do not commit the final dossier or its ZIP.

The final dossier and ZIP are now explicitly ignored in `.gitignore`:

- `Cortea_Track_Final_Dataset/`
- `Cortea_Track_Final_Dataset.zip`

Secrets belong only in ignored `.env`. Never print or commit API keys.

## Repository and current Git state

Remote: `https://github.com/khushaal-chaudhary/Agentic_Audit_Assistant.git`

Latest pushed commit when this handoff was written:

```text
a0d6c8b Discover audit inputs by schema and content
```

Important earlier pushed commit:

```text
b312144 Enforce exact calculation lineage
```

Unrelated untracked `.claude/` belongs to the user. Do not add or modify it.

## Completed and pushed

- Local-first FastAPI backend and Next.js frontend.
- Restart-safe local dossier jobs and source serving.
- Auditor review dispositions with rationale-gated dismissal.
- Deterministic source-linked findings.
- Exact Decimal calculation traces: every contributing term has its own source locator and the UI
  recomputes the displayed amount.
- Evidence graph schema 1.1, with calculations linked only to exact contributing locators.
- OpenAI question answering constrained to validated findings/evidence, with deterministic fallback.
- Cost-controlled Cognee projection; Cognee is optional and never authoritative.
- Schema/content-driven input discovery with explicit `resolved`, `missing`, and `ambiguous` states.
- German/English canonical column aliases.
- Required-role ambiguity fails closed and makes dependent procedures `not_testable`.
- Four implemented sample rules:
  - `VENDOR_CONTROL_CHAIN`
  - `CAPITALISED_REPAIRS`
  - `UNRECORDED_CUTOFF_LIABILITIES`
  - `SPLIT_PAYMENTS_BELOW_THRESHOLD`
- Rules UI is already functional and populated from `/api/rules`.

The schema-discovery milestone passed 57 tests, Ruff, Next.js build/lint, and a live browser check
before it was pushed.

## Current uncommitted native-PDF work

OCR was explicitly removed from scope by the user.

The working tree currently contains a nearly finished native-PDF milestone:

- `audit_core/parsers.py`
  - `PdfExtraction`
  - native `pypdf` extraction
  - bounded page-and-line passages
  - explicit `native`, `partial`, and `unreadable` states
- `audit_core/discovery.py`
  - conservative content roles for:
    - `financial_statements`
    - `export_manifest`
    - `it_completeness_confirmation`
- `audit_core/models.py`
  - PDF extraction coverage and source passages in the report
  - engine version currently changed to 0.5.0
- `services/api/main.py`
  - extraction metadata in document summaries
  - API/health version currently changed to 0.5.0
- frontend Documents view
  - extracted PDF page/passages display
- Cognee projection version changed to v6 so native passages affect the fingerprint
- documentation updated for native PDF text and OCR-disabled behavior
- `tests/test_pdf_ingestion.py` added

Focused validation already passed:

```text
10 passed
Ruff: all checks passed
```

The PDF tests cover native sample PDFs, a mixed native/blank PDF, an image-only unreadable PDF, a
clean unrelated passage, and API coverage. Full tests/build have not yet been rerun after the latest
PDF documentation/UI edits.

## Final dossier

Use this root (not the enclosing `__MACOSX` folder):

```text
Cortea_Track_Final_Dataset/Daten BSP
```

It contains about 1.08 million general-ledger rows plus:

- subledger-to-GL reconciliation;
- extended 2025 invoice journal;
- January 2026 invoice journal;
- subsequent-period postings;
- manual journal approval log;
- shareholder/related-party list;
- credit limits;
- debtor and creditor open-item workbooks;
- legal/insolvency cases;
- current/prior-year trial balances and a year-end adjustment bridge;
- debtor master-data changes;
- customer/vendor status history;
- dispatch records;
- a bill-and-hold agreement;
- export and IT completeness confirmations;
- draft financial statements and notes.

The final dossier has no supplied answer key. The number of genuine frauds, misstatements, and
control exceptions is unknown and must not be assumed. It is legitimate to inspect the source
documents, but all implemented logic must remain generic and must be tested against clean twins.

## High-value final-dossier observations

These are source observations for designing generic procedures, not values to hard-code:

- The GDPdU export confirmation declares 1,083,723 GL rows.
- The separate IT completeness confirmation declares 1,083,713 GL rows.
- The declarations also contain different debit/credit volumes.
- The physical GL file is large enough that the current object-per-row load may cause excessive
  memory use.
- The planning document defines source-based journal-entry criteria, including after-hours entries,
  late/backdated entries, management users, rare accounts, round amounts, approval violations, and
  year-end postings.
- The approval log exposes creator, approver, status, timestamps, and absolute journal amount.
- The extended sales journal can be matched to dispatch records. A bill-and-hold agreement is
  explicit counterevidence for one no-dispatch sale and must suppress that legitimate case.
- The trial-balance bridge contains a top-side adjustment that is not posted in the GL; the draft
  financial statements refer to it.
- The financial-statement notes disclose open-item and related-party facts that can be reconciled to
  supporting schedules.

## Recommended detector order

Implement only procedures that can require corroboration and suppress innocent explanations.

### 1. Export/completeness declaration reconciliation

Recommended ID: `EXPORT_COMPLETENESS_RECONCILIATION`

Generic logic:

- extract the declared GL row count and, if reliably parseable, control totals from the export
  manifest and independent IT confirmation;
- compare both declarations to the physical GDPdU row count;
- publish only on an actual mismatch;
- cite both PDF pages/passages and a query locator for the physical file count;
- do not attach a monetary `amount` unless every term can be sourced and recomputed.

Required clean tests:

- both declarations and actual count agree;
- one control document is absent -> `not_testable`;
- number formatting with dots/commas and English wording;
- unrelated numbers near the file name do not get selected.

### 2. Manual journal approval violations

Recommended ID: `MANUAL_JOURNAL_APPROVAL_VIOLATION`

Generic logic:

- resolve the approval log by schema, not filename;
- match manual GL journals to approval rows by journal/capture identifier;
- publish only explicit control failures such as creator equals approver, missing approver, or a
  non-approved status;
- require linked GL rows and approval-log evidence;
- calculate exposure from exact linked source rows or use the source-declared absolute journal
  amount with a single exact term;
- missing approval input -> `not_testable`.

Required clean tests:

- independent approved journal stays clean;
- batch/system journal stays clean unless the policy explicitly places it in scope;
- absent log -> `not_testable`;
- duplicate source files/rows do not double the finding.

### 3. Revenue cut-off with bill-and-hold counterevidence

Recommended ID: `REVENUE_CUTOFF`

Generic logic:

- match positive goods-sale invoices to dispatch records using invoice and dispatch identifiers;
- focus on the source-defined year-end window, not a hard-coded calendar year;
- treat later/no dispatch as a candidate only for goods deliveries;
- suppress a candidate when a signed bill-and-hold agreement identifies the invoice and documents
  customer request, segregation, risk/title transfer, and delivery deadline;
- require invoice, dispatch absence/query, and any agreement passages as evidence/counterevidence;
- do not flag service invoices merely because no warehouse dispatch exists.

Required clean tests:

- normal invoice/dispatch match;
- valid bill-and-hold case stays clean;
- service invoice stays clean;
- unsupported year-end goods invoice publishes;
- missing dispatch population -> `not_testable`.

### 4. Financial-statement traceability

Recommended ID: `FINANCIAL_STATEMENT_TRACE`

This is valuable but more complex. Implement only after the first three are robust. Reconcile
specific statement captions to the trial-balance/subledger bridge with explicit mapping evidence.
Do not infer account groupings from number prefixes without a source mapping.

## Memory/performance risk before the final run

The current engine materializes every GL row as a `SourceRow` containing a dictionary. That was
acceptable for the sample but may exhaust memory on 1.08 million rows.

Before running the final dossier, change large-table processing to one of these safe patterns:

1. preferred: one streaming pass over the GL that retains only rows/aggregates needed by the active
   detectors and evidence locators;
2. acceptable: ingest into an ignored local SQLite database in chunks and query indexed canonical
   columns;
3. do not solve this by sending the raw ledger to Cognee or OpenAI.

Preserve raw row numbers and source excerpts during streaming so findings still link to exact rows.
Use `Decimal` during parsing/aggregation. Add a scale regression using generated rows or a bounded
memory assertion if practical.

The current discovery layer also reads delimited files once for profiling and the engine reads them
again. Avoid adding more full passes over the GL.

## Discovery changes needed for new rules

Extend `audit_core/discovery.py` with explicit schema roles and German/English aliases for only the
new required inputs, for example:

- manual journal approval log;
- extended sales invoice journal;
- dispatch register;
- export/IT declarations (already descriptive PDF roles in the uncommitted work);
- trial balance and bridge if statement tracing is implemented.

Do not rely on filenames. Duplicate role candidates must become `ambiguous`, and dependent
procedures must become `not_testable`.

## Rules documentation and UI

The Rules page is generated from `audit_core/rules.py` via `/api/rules`. To update the UI:

1. add each genuinely implemented detector to `IMPLEMENTED_RULES` with:
   - objective;
   - required inputs;
   - publication conditions;
   - false-positive guards;
   - evidence requirements;
2. remove that detector from `PLANNED_RULES`;
3. add the full specification and clean-test requirements to `docs/deterministic-rules.md`;
4. verify the browser page shows accurate implemented/planned counts.

Never mark a planned rule implemented merely to improve the demo.

## Suggested two-minute recording

Do not show upload. Preload a completed final-dossier job.

Suggested timing:

- 0:00-0:12 — State the problem: layered fraud, false positives are costly, every claim must be
  source-linked.
- 0:12-0:28 — Show final dossier coverage: mixed formats, recognized roles, extracted PDF pages,
  and any explicit `not_testable`/unreadable state.
- 0:28-1:05 — Open the strongest finding. Read the concise conclusion and exposure, then show the
  exact Decimal calculation trace.
- 1:05-1:32 — Open two source links from different documents, ideally a row/cell and a PDF page
  passage, proving the cross-document chain.
- 1:32-1:48 — Show the Rules page: publication conditions and false-positive guards. Mention the
  valid bill-and-hold example or another clean decoy that is suppressed.
- 1:48-2:00 — Close with local-first/free architecture, optional Cognee/OpenAI, and the GitHub link.

Keep the strongest finding selected before recording. Avoid waiting for ingestion or model calls.
Use 125-150% browser zoom if necessary so source locators and amounts remain legible in the video.

## Local demo commands

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\stop-local.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-local.ps1
```

Health:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
curl.exe --max-time 10 -sS -o NUL -w "%{http_code}" http://127.0.0.1:3000/
```

Use `127.0.0.1`, not `localhost`: another unrelated Next.js project was observed listening on a
different localhost interface/port binding during development.

## Required final validation

From repository root:

```powershell
py -3 -m pytest
```

If the active environment is required:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check audit_core services tests
git diff --check
```

From `apps/web`:

```powershell
npm.cmd run build
npm.cmd run lint
```

Then perform a live browser rehearsal:

- final dossier report loads;
- no console errors;
- all finding evidence links return HTTP 200;
- PDF links open on the cited page;
- each displayed amount has a visible exact calculation trace;
- Rules page counts and rule details match the backend catalogue;
- Documents page reports native/partial/unreadable PDF coverage accurately.

## Commit discipline

- Stage explicit files only.
- Never use `git add .` while evaluation data and `.claude/` are present.
- Confirm the final dossier, `.env`, runtime data, and sealed ground truth remain ignored.
- Commit and push only after tests, build, lint, and browser rehearsal pass.

Likely final sequence:

1. finish/validate native PDF work;
2. fix final-dossier memory path;
3. implement the highest-value generic detectors with clean twins;
4. update rule catalogue/docs/UI;
5. run final dossier and preload its report;
6. rehearse the two-minute path;
7. commit, push, record, and submit the GitHub link plus video.
