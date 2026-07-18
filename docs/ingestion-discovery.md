# Ingestion discovery contract

The ingestion layer assigns documents to audit roles from declared columns or document content.
Filenames are inventory labels, not the primary classification signal.

## Resolution states

| State | Meaning |
|---|---|
| resolved | Exactly one document matches the role signature. |
| missing | No document matches. Procedures requiring the role become not_testable. |
| ambiguous | Multiple documents match. Procedures requiring the role become not_testable. |

The engine never selects the first ambiguous match.

## Implemented roles

| Role | Required canonical fields or content |
|---|---|
| general_ledger | GL account, document number, posting date, amount, text, user |
| vendor_postings | Vendor account, document number, posting date, text, amount |
| asset_master | Asset number, description, group |
| asset_postings | Asset number, value date, document number, amount, posting type |
| goods_receipts | Receipt number/date, vendor, amount, remark |
| vendor_changes | Change date/type, account, name, field, changer, approver |
| permissions | User, posting, payment-run, vendor-creation permissions |
| future_vendor_invoices | Invoice number, vendor, invoice/service dates, amount |
| payment_policy | Payment-approval and dual-control language |

GDPdU tables use the columns declared in index.xml. CSV/TXT files use their header row. XLSX
workbooks are inspected for a matching header row. DOCX policy documents are matched from normalized
paragraph content.

## Canonical fields and aliases

The rule engine uses stable canonical field names. Discovery maps exact German names and supported
English aliases to those canonical names before analysis. Cell coordinates and original source
files remain unchanged, so evidence links still resolve to the actual input.

Aliases are deliberately explicit. Fuzzy model-based guesses are not accepted as deterministic
role resolution.

## Document coverage

Every retained file is classified as:

- recognized: assigned to one implemented role;
- ambiguous: competes for a role or matches multiple roles;
- unclassified: retained, but no implemented rule consumes its schema;
- unsupported: retained for source access, but fact extraction is not implemented.

The document inventory exposes these states. Unclassified files are not evidence that ingestion
failed; they may belong to rule families that are still planned.

## Current boundary

- General PDF fact extraction and OCR are not implemented.
- Alias coverage is finite and must be expanded with clean regression fixtures.
- One physical workbook is currently assigned at file level, not as several independent role-bearing
  sheets.
- The engine still loads resolved structured tables into memory after discovery.

Any new role or alias requires a renamed/translated clean fixture and an ambiguity regression.
