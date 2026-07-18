# Evidence graph schema

The authoritative graph projection is built by audit_core.graph. It is versioned and validated
before upload to Cognee.

## Node types

- dossier: one processed evidence set.
- procedure: a generic audit test with completed or not_testable status.
- finding: a published exception; it never stores an amount directly.
- calculation: a decimal string and currency produced by deterministic rule aggregation.
- locator: an exact row, cell, page, passage, or query excerpt with a source SHA-256.
- document: a source path and SHA-256.
- entity: an affected vendor, user, account, date, or other identifier.

## Allowed edges

- dossier CONTAINS procedure
- procedure PRODUCED finding
- finding SUPPORTED_BY locator
- locator LOCATED_IN document
- finding AFFECTS entity
- finding HAS_CALCULATION calculation
- calculation DERIVED_FROM locator

Validation fails closed if a finding lacks SUPPORTED_BY, a calculation lacks DERIVED_FROM, or a
calculation is not connected to a finding. This makes the source chain independent of Cognee's
generated semantic relationships.
