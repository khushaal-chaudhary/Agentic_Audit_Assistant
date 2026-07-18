# Deterministic audit rulebook

This is the living specification for deterministic audit logic and its required tests. It separates
implemented behavior from planned coverage and provides a review checklist for future changes.

The executable source of truth is audit_core/engine.py. If this document and the code disagree,
treat the code as current behavior and update both in the same change.

## Global invariants

Every rule must:

1. Use generic relationships and source-derived policies, never sample entities, document IDs,
   fiscal years, or expected fraud totals.
2. Use Decimal for monetary parsing, comparison, aggregation, and serialization.
3. Publish no finding without exact evidence locators and source SHA-256 values.
4. Trace every amount to every source locator and Decimal term used in its calculation.
5. Represent missing required inputs as not_testable.
6. Consider counterevidence before publication.
7. Add a clean or near-miss regression whenever a detector is introduced or broadened.
8. Keep OpenAI and Cognee non-authoritative for findings and arithmetic.

## Procedure states

| State | Meaning |
|---|---|
| completed | All required files exist and the procedure ran. It may return no findings. |
| not_testable | Required inputs are missing. No finding is inferred from their absence. |

## Execution and performance model

Source files are parsed once. The engine then builds shared in-memory indexes before any detector
runs:

- General-ledger rows by document number
- Vendor postings by vendor
- Goods receipts by vendor
- Open receipts by vendor, Decimal amount, and receipt date
- Payment rows by vendor and booking date
- Permissions by user
- Assets by asset number

Detectors query these indexes instead of repeatedly scanning whole ledgers. The main joins are
therefore approximately linear in source rows plus matched evidence, rather than vendor-by-ledger or
invoice-by-receipt Cartesian scans.

The same physical source row, identified by resolved source path and row number, is indexed only
once. This prevents an ingestion-list duplicate from manufacturing count thresholds or inflating
amounts. Separate source rows with similar business values remain distinct because they may
represent genuine duplicate transactions requiring a dedicated detector.

## Exact calculation lineage

Every amount-bearing finding contains a sum trace with:

- one Decimal term for every contributing source value;
- a label and exact evidence locator for each term;
- a currency matching the displayed finding amount.

Finding validation fails closed when a trace is absent, a term locator is missing from the finding
evidence, a locator is repeated, or the Decimal terms do not recompute the displayed total.
Calculation graph edges derive only from these exact term locators, not from unrelated corroborating
evidence such as permissions, policies, or absence queries.

## Implemented rule summary

| Rule ID | Category | Severity | Publication unit |
|---|---|---|---|
| VENDOR_CONTROL_CHAIN | fraud | high | vendor |
| CAPITALISED_REPAIRS | misstatement | high | matching asset additions as a group |
| UNRECORDED_CUTOFF_LIABILITIES | misstatement | high | matched subsequent invoices as a group |
| SPLIT_PAYMENTS_BELOW_THRESHOLD | control | medium | vendor and booking date |

Confidence values are currently fixed rule metadata, not statistical probabilities.

## VENDOR_CONTROL_CHAIN

### Objective

Identify a composite vendor fraud risk where one user controls vendor creation, accounting, and
payment activity, followed by unsupported transactions.

### Required inputs

- General ledger
- Vendor subledger
- Goods-receipt listing
- Vendor master-data change log
- User-permission report

### Candidate population

A master-data change qualifies when normalized FELD contains neuanlage and normalized ART contains
kreditor.

### Publication conditions

All conditions must be true for the same vendor:

1. GEÄNDERT_VON is present and equals GENEHMIGT_VON.
2. The user has non-empty permissions for posting, payment runs, and vendor creation.
3. At least three invoice postings exist.
4. At least three positive payment postings contain the normalized token zahlung.
5. All linked general-ledger postings were made by the same user.
6. The first invoice is from zero to 30 days after vendor creation.
7. Positive linked expense rows on accounts beginning with 6 exist and are exact multiples of 1,000.
8. No goods-receipt row matches the vendor.

Failure of any condition suppresses the candidate.

### Amount and evidence

The amount is the sum of positive linked expense rows on accounts beginning with 6. Evidence must
include the master-data row, permission row, representative invoices and payments, linked expense
rows, and the explicit goods-receipt absence query.

### Required clean and boundary tests

- Independent creator and approver
- Missing one permission
- Fewer than three invoices or payments
- A linked posting by another user
- First invoice before creation or 31 days afterward
- At least one non-round expense
- Matching goods receipt
- Missing required file produces not_testable

### Known test targets

- Permission values are tested for non-empty content instead of a normalized affirmative value.
- Payment classification depends partly on the German token zahlung.
- Expense classification assumes accounts beginning with 6.

## CAPITALISED_REPAIRS

### Objective

Identify groups of repair-type expenditures recorded as fixed-asset acquisitions.

### Required inputs

- Asset master
- Asset postings

### Publication conditions

1. Normalized BUCHUNGSART equals acquisition.
2. The posting resolves to an asset by asset number.
3. The normalized description matches reparatur, instandsetzung, austausch, generaluberholung,
   wartung, or kalteanlage.
4. At least two asset/posting pairs match.

A single matching addition does not publish a finding.

### Amount and evidence

The amount is the sum of all matching acquisition postings. Evidence includes asset number,
description, group, posting date, document number, amount, and posting type for every match.

### Required clean and boundary tests

- One matching acquisition only
- Large round ordinary investment
- Repair description with a non-acquisition posting
- Posting with no asset-master match
- New productive equipment
- Mixed case, umlauts, and transliterated German
- English repair, maintenance, and overhaul descriptions
- Missing asset input produces not_testable

### Known test targets

- Posting type currently requires the English value acquisition.
- The keyword list can miss synonyms or overmatch equipment names.
- The two-match minimum reduces false positives but may miss one material item.

## UNRECORDED_CUTOFF_LIABILITIES

### Objective

Identify subsequent-period invoices for prior-period receipts that are absent from the current
general ledger.

### Required inputs

- General ledger
- Goods-receipt listing
- Subsequent vendor-invoice journal

### Publication conditions

For each subsequent invoice:

1. Invoice and service dates parse successfully.
2. Invoice year is later than service year.
3. Invoice number is absent from current general-ledger document numbers.
4. A receipt remark contains the normalized phrase rechnung offen.
5. Receipt vendor equals invoice vendor.
6. Receipt amount equals invoice amount using Decimal.
7. Receipt date equals invoice service date.

One or more matched pairs publish a grouped finding.

### Amount and evidence

The amount is the sum of matched invoice amounts. Evidence includes every invoice/receipt pair, the
general-ledger absence query, and up to two other accrual rows when available. Other accrual rows are
context only; they do not offset or suppress a match.

### Required clean and boundary tests

- Invoice and service dates in the same year
- Invoice already in the ledger
- Receipt not marked open
- Vendor, amount, or date mismatch
- German and international amount formats
- A legitimate accrual using another document reference
- Missing subsequent journal produces not_testable

### Known test targets

- Open-receipt classification relies on rechnung offen.
- Invoice absence uses exact document-number equality.
- Calendar-year comparison does not yet support non-calendar fiscal periods.

## SPLIT_PAYMENTS_BELOW_THRESHOLD

### Objective

Identify same-day payment clusters structured below a documented approval threshold.

### Required inputs

- Vendor subledger
- Control document containing the payment threshold

### Threshold extraction

The engine searches payment-approval or four-eyes passages and extracts an amount following the
German terms ab or uber. The passage is retained as evidence. Failure to extract a threshold marks
the procedure not_testable.

### Candidate population

- Positive vendor postings
- Posting text contains the normalized token zahlung
- Grouped by vendor and exact booking-date value

### Publication conditions

1. At least three payments are at least 90 percent of the threshold.
2. Every included payment is strictly below the threshold.
3. Their aggregate is at least twice the threshold.

### Amount and evidence

The amount is the sum of qualifying payments. Evidence includes the policy passage and every
qualifying payment row.

### Required clean and boundary tests

- Two near-threshold payments
- Three payments on different dates or to different vendors
- Payment exactly at the threshold
- Payment immediately below 90 percent
- Aggregate immediately below and exactly at twice the threshold
- Negative invoice entries
- Missing threshold document produces not_testable
- German and English policy wording

### Known test targets

- Payment classification depends on zahlung.
- Grouping uses the raw booking-date string.
- Threshold extraction recognizes limited German phrasing.
- With three payments each at least 90 percent of the threshold, the current aggregate test of twice
  the threshold is mathematically redundant. Keep it documented until the heuristic is deliberately
  recalibrated with clean-twin evidence.

## Required test matrix for every rule

| Test class | Requirement |
|---|---|
| Positive | Minimal evidence set publishes exactly one expected finding |
| Clean twin | One fraud-relevant fact changes and the otherwise identical case stays clean |
| Boundary | Every inclusive and exclusive edge is tested |
| Missing input | Required absence produces not_testable |
| Counterevidence | A legitimate explanation suppresses the candidate |
| Locale | German and English text plus German and international money formats |
| Metamorphic | Random IDs, shifted years, reordered rows, and irrelevant files preserve results |
| Provenance | Every locator resolves and every amount recomputes from cited values |
| Duplicate resistance | Duplicate files or rows do not silently inflate findings |
| Adversarial | Malformed values and prompt-like text cannot create unsupported claims |

## Planned detector backlog

These are not implemented and must not appear as completed procedures:

- Bank confirmation to bank-ledger reconciliation
- Invoice, purchase-order, receipt, and payment matching
- Duplicate invoices and duplicate payments
- Vendor bank-account changes followed by payments
- General-ledger to financial-statement traceability
- Related-party and shared-bank-account clustering
- Manual journals near period end
- Reversal and rebooking chains
- Revenue cut-off and unsupported receivables
- Payroll and employee/vendor identity overlap
- Dormant vendor reactivation

Each backlog rule must first receive a written specification, clean twins, and counterevidence.

## Rule-change template

For every proposed detector document:

- Objective
- Required inputs
- Candidate population
- Publication conditions
- Amount or calculation
- Required evidence
- Counterevidence and suppression
- Clean and boundary tests
- Known limitations

## Change discipline

For every logic change:

1. Update this document.
2. Update the positive test.
3. Add a clean twin or near-miss regression.
4. Run py -3 -m pytest.
5. Run npm.cmd run build in apps/web when the report or UI contract changes.
6. Confirm the sealed evaluation file remains ignored by Git.
