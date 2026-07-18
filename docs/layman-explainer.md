# AuditGraph explained in plain English

This is a living FAQ for demos, presentations, judges, auditors, and non-technical stakeholders.
Update it whenever the product architecture or rule coverage changes.

## The 30-second explanation

AuditGraph is a digital audit workbench. It reads a folder of financial documents, organizes the
important facts, and runs clearly defined checks across documents that would normally be reviewed
one at a time.

When it finds a suspicious pattern, it does not simply say, “This looks like fraud.” It shows the
auditor the exact document, page, row, cell, or passage supporting the conclusion. The auditor then
confirms or dismisses the exception and records a rationale.

The core promise is:

> No claim without evidence. No number without a source.

## A simple analogy

Imagine an auditor with a wall covered in invoices, ledger entries, approvals, bank records, and
policies.

AuditGraph first labels and files everything. It then connects related items with string:

- this invoice belongs to this vendor;
- this payment relates to this invoice;
- this user created and approved this vendor;
- this amount came from this source row;
- this approval threshold came from this policy paragraph.

The deterministic rules inspect those connections. The AI helps the auditor ask questions and
understand the results, but it cannot invent new evidence.

## Frequently asked questions

### What problem are we solving?

Important audit clues are often spread across different files. A ledger entry may look normal until
it is combined with a vendor change log, a permission report, a payment file, and a missing goods
receipt.

The tool performs that cross-document work automatically and gives the auditor a focused,
evidence-backed investigation queue.

### What does “deterministic” mean?

A deterministic rule is a written test with explicit conditions. Given the same source facts, it
produces the same result.

For example, a rule can require all of the following before publishing an exception:

- the same user created and approved a vendor;
- that user also had posting and payment permissions;
- repeated invoices and payments exist;
- the linked ledger entries were posted by that user;
- no matching receipt exists.

If a required condition is absent, the rule does not publish the finding.

The exact implemented logic and safeguards are maintained in
[deterministic-rules.md](deterministic-rules.md).

### How do we identify possible fraud?

We use layers:

1. Parse documents into normalized facts while retaining their source locations.
2. Connect facts that share identifiers such as vendor, invoice, document, asset, amount, or date.
3. Generate a small set of candidates using deterministic conditions.
4. Look for corroborating evidence and legitimate explanations.
5. Publish only candidates that pass the complete rule.
6. Let an auditor confirm or dismiss the result with a recorded rationale.

This is intentionally stricter than asking an AI model to “find anything suspicious.”

### How do we avoid flagging innocent discrepancies?

Each rule includes false-positive guards and clean comparison cases.

A suspicious vendor, for example, may be suppressed when there is independent approval or a valid
goods receipt. A missing receipt by itself is not enough.

The system also counts rejected candidates as suppressed leads. This demonstrates that it considered
other possibilities without presenting them as findings.

### What happens when documents are missing?

Missing evidence produces **not testable**, not a fraud finding.

This distinction matters: absence of a file may be an audit limitation, but it is not proof of
misconduct.

### How is every result connected to its evidence?

Each extracted fact carries a locator containing:

- the source document path;
- a page, row, cell range, passage, or query description;
- a readable excerpt;
- a content hash for integrity checking.

Findings contain those locators directly. Clicking a source link opens the retained document rather
than a model-generated summary.

### What does “no number without a source” mean?

All audit amounts use decimal arithmetic and are recomputed from individually cited source values.

The system never asks a language model to perform or invent financial arithmetic. If an amount is
displayed, the finding contains every source row and Decimal term used to calculate it. Reports fail
closed when the terms do not reproduce the displayed total.

### Why do we use a graph?

Financial fraud is usually about relationships, not isolated sentences.

A graph makes relationships explicit:

- findings are supported by evidence;
- calculations are derived from source values;
- payments belong to vendors;
- invoices connect to ledger documents;
- people connect to permissions and actions.

This structure makes multi-document reasoning easier to inspect and expand.

### How are we using Cognee?

Cognee receives a compact projection of the typed evidence graph and validated excerpts. It helps
with semantic discovery and relationship-oriented exploration.

Cognee is not the authority for calculations, citations, or final findings. The local evidence
ledger and deterministic engine remain authoritative, so the core audit can run without Cognee.

### How are we using OpenAI?

OpenAI is used for grounded explanations and short auditor questions.

The model receives validated findings and their evidence, not unrestricted permission to invent new
claims. The server checks model answers and rejects unsupported numbers or statements. When OpenAI
is unavailable, a deterministic fallback still answers from validated findings.

### Is this just a chatbot or RAG system?

No. Search and question answering are supporting features.

The core product is a deterministic evidence and reconciliation engine. It calculates, matches,
suppresses, and publishes findings before the conversational layer is involved.

### Why not send all the documents directly to an AI model?

That approach is harder to reproduce, more expensive, and more likely to produce unsupported
conclusions.

Our design uses code for exact amounts, dates, identities, thresholds, and matching. AI is reserved
for language and exploration after the evidence has been validated.

### How have we optimized the deterministic system?

The simplest explanation is:

> Organize once, check many times.

A naive system repeatedly scans every row for every possible comparison. AuditGraph builds lookup
indexes once per analysis run, such as:

- ledger entries by document number;
- postings and receipts by vendor;
- open receipts by vendor, decimal amount, and date;
- payments by vendor and booking date;
- permissions by user;
- assets by asset number.

Each rule then reads only its relevant group instead of repeatedly searching the entire dossier.

We also:

- parse each dataset once per run;
- remove duplicate physical rows before counting evidence;
- generate candidates before performing deeper checks;
- stop a rule when required inputs are unavailable;
- run inexpensive deterministic checks before optional AI calls;
- reuse the same validated evidence locators across findings, questions, and source navigation.

This reduces unnecessary comparisons, model usage, and false-positive review work.

### What prevents duplicate documents or rows from inflating a finding?

Physical source rows are identified by their resolved file path and row number. Duplicate references
to the same physical row are removed before thresholds or totals are evaluated.

Automated regressions verify that duplicated rows cannot create a finding that would otherwise fail
the rule.

### How do we test the system?

Each implemented rule is tested with several scenario types:

- a minimal positive case;
- clean twins where one important fact changes;
- boundary and missing-input cases;
- legitimate counterevidence;
- duplicated rows;
- reordered source data;
- provenance and decimal-amount checks.

The sample dossier is an integration test. Synthetic scenarios are especially important because
they prove the rule is generic rather than memorized from the sample.

### How will it work on the final dossier?

Rules use field meanings and relationships, not hard-coded vendor names, document numbers, dates, or
expected fraud totals.

The final dossier can contain different entities and values. The same generic logic parses,
connects, and evaluates them.

### How are German and English documents handled?

The ingestion layer recognizes implemented document roles from declared columns or policy content,
not primarily from filenames. Supported German and English header aliases map to stable internal
fields while preserving the original source for the auditor. Missing or duplicate role matches are
reported instead of guessed.

Financial amounts are parsed with locale-aware decimal handling, including German and international
formats. Original source text remains visible in the evidence panel.

### Does the system replace the auditor?

No. It reduces search and reconciliation work.

The system publishes evidence-backed exceptions. The auditor interprets business context, requests
additional support, confirms or dismisses findings, and owns the final conclusion.

### How does the review workflow work?

An auditor can:

- open a review item and land on the correct evidence-backed finding;
- record a rationale;
- confirm an exception;
- dismiss it only when a rationale is supplied;
- reset the disposition when more evidence arrives.

Dispositions are stored with the local dossier and restored after a page refresh.

### Where does the system run?

The complete demo runs locally:

- the browser interface runs on the laptop;
- the Python API performs ingestion and analysis;
- source documents, reports, and review dispositions remain under ignored local runtime storage.

The frontend can later be hosted on Vercel and the API container can run on Cloud Run. Cloud
deployment is optional; it is not required for the demo.

### What information leaves the laptop?

Deterministic processing and source serving are local.

When optional integrations are enabled, only the scoped content required for that operation is sent:
validated finding context for OpenAI explanations and a compact graph projection for Cognee. Raw
ledger arithmetic remains local.

### What are the current limitations?

- Only rules marked **implemented** in the rulebook are executed.
- Planned rule cards are coverage goals, not completed tests.
- PDFs containing real text are split into page-linked passages. Scanned image documents are
  visibly marked unreadable because OCR is intentionally not part of the demo.
- Business explanations outside the supplied dossier still require auditor follow-up.
- Local review records are designed for a single-user demo; production needs authentication and
  role-based sign-off.

Being explicit about limitations is part of the audit design.

## Suggested demo explanation

Use this sequence:

1. “We load a mixed folder of German and English audit documents.”
2. “The system converts them into evidence-linked facts.”
3. “Deterministic rules connect facts across files and suppress weak candidates.”
4. “Here are the remaining exceptions requiring judgement.”
5. Open one finding and click its exact source locations.
6. Ask a short question and expand the answer’s citations.
7. Open the rulebook to show the conditions and false-positive guards.
8. Record a review disposition and explain that the auditor remains in control.

## Useful one-line answers

- **What is the AI doing?** Explaining and navigating validated evidence; it is not inventing the
  audit result.
- **What is Cognee doing?** Projecting the evidence relationships for semantic and graph
  exploration.
- **What is deterministic code doing?** Performing the exact matching, arithmetic, thresholds,
  suppression, and publication decisions.
- **Why should an auditor trust it?** They do not need to trust a hidden answer; they can inspect
  every source and every rule.
- **What makes it efficient?** Indexed lookups replace repeated full-dataset comparisons, and AI is
  used only after validation.
- **What makes it generalizable?** Rules use relationships and field meanings rather than
  sample-specific names or totals.

## Small glossary

- **Candidate** — A pattern worth testing further, not yet a finding.
- **Counterevidence** — Evidence that provides a legitimate explanation and suppresses a candidate.
- **Deterministic rule** — A reproducible test with explicit inputs and conditions.
- **Evidence locator** — The exact document and page, row, cell, passage, or query supporting a
  claim.
- **Evidence graph** — Structured relationships among documents, facts, calculations, and findings.
- **Finding** — A corroborated exception published for auditor judgement.
- **Not testable** — The required evidence was unavailable; no conclusion was reached.
- **Suppressed lead** — A candidate rejected because it lacked corroboration or had counterevidence.
