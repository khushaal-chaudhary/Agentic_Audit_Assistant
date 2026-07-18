# Repository guidance

- Treat evidence provenance as a product invariant. A displayed claim must resolve to one or more source locators.
- Use `Decimal` for money; never use binary floating point in audit calculations.
- Runtime rules must be generic. Never hard-code sample vendor IDs, document IDs, dates, or expected fraud totals.
- The sealed ground-truth file is local evaluation material and must remain ignored by Git.
- Missing inputs produce `not_testable`, not a finding.
- Add a clean/decoy regression test whenever a new detector is introduced.
- Run `py -3 -m pytest` and `npm.cmd run build` in `apps/web` before pushing meaningful changes.

