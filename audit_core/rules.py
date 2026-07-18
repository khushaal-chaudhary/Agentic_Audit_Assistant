from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RuleDefinition(BaseModel):
    rule_id: str
    name: str
    status: Literal["implemented", "planned"]
    category: Literal["fraud", "misstatement", "control", "reconciliation"]
    severity: Literal["high", "medium", "low"] | None = None
    objective: str
    required_inputs: list[str] = Field(default_factory=list)
    publication_conditions: list[str] = Field(default_factory=list)
    false_positive_guards: list[str] = Field(default_factory=list)
    evidence_requirements: list[str] = Field(default_factory=list)


IMPLEMENTED_RULES = [
    RuleDefinition(
        rule_id="VENDOR_CONTROL_CHAIN",
        name="Vendor control chain",
        status="implemented",
        category="fraud",
        severity="high",
        objective=(
            "Identify unsupported vendor activity where one user controls onboarding, "
            "posting, and payment execution."
        ),
        required_inputs=[
            "General ledger",
            "Vendor subledger",
            "Goods receipts",
            "Vendor master-data changes",
            "User permissions",
        ],
        publication_conditions=[
            "The same user creates and approves the vendor.",
            "That user can create vendors, post entries, and run payments.",
            "At least three invoices and three payments exist.",
            "Linked ledger postings were made by the same user.",
            "The first invoice is within 30 days after onboarding.",
            "Linked expense rows are round multiples of 1,000.",
            "No goods receipt matches the vendor.",
        ],
        false_positive_guards=[
            "Independent approval suppresses the candidate.",
            "Any matching goods receipt suppresses the candidate.",
            "A missing receipt alone is never sufficient.",
        ],
        evidence_requirements=[
            "Master-data change row",
            "Permission row",
            "Invoice and payment rows",
            "Linked expense rows",
            "Goods-receipt absence query",
        ],
    ),
    RuleDefinition(
        rule_id="CAPITALISED_REPAIRS",
        name="Capitalised repair expenditure",
        status="implemented",
        category="misstatement",
        severity="high",
        objective="Identify multiple repair-type expenditures recorded as asset acquisitions.",
        required_inputs=["Asset master", "Asset postings"],
        publication_conditions=[
            "The posting type is an acquisition.",
            "The posting resolves to an asset-master record.",
            "The description contains a repair, replacement, overhaul, or maintenance indicator.",
            "At least two asset/posting pairs match.",
        ],
        false_positive_guards=[
            "A single repair-like description does not publish a finding.",
            "Ordinary investment descriptions are excluded.",
            "Non-acquisition postings are excluded.",
        ],
        evidence_requirements=[
            "Asset number, description, and group",
            "Posting date, document, amount, and type",
        ],
    ),
    RuleDefinition(
        rule_id="UNRECORDED_CUTOFF_LIABILITIES",
        name="Unrecorded cut-off liabilities",
        status="implemented",
        category="misstatement",
        severity="high",
        objective=(
            "Identify subsequent invoices for prior-period receipts that are absent "
            "from the period-end ledger."
        ),
        required_inputs=[
            "General ledger",
            "Goods receipts",
            "Subsequent vendor-invoice journal",
        ],
        publication_conditions=[
            "Invoice year is later than service year.",
            "The invoice number is absent from the current ledger.",
            "An open receipt matches vendor, Decimal amount, and service date.",
        ],
        false_positive_guards=[
            "Same-period invoices are excluded.",
            "Already-recorded invoices are excluded.",
            "Vendor, amount, and date must all agree.",
        ],
        evidence_requirements=[
            "Subsequent invoice row",
            "Matching open-receipt row",
            "Ledger absence query",
        ],
    ),
    RuleDefinition(
        rule_id="SPLIT_PAYMENTS_BELOW_THRESHOLD",
        name="Split payments below approval threshold",
        status="implemented",
        category="control",
        severity="medium",
        objective=(
            "Identify same-day payment clusters structured immediately below a "
            "source-documented approval threshold."
        ),
        required_inputs=["Vendor subledger", "Payment approval policy"],
        publication_conditions=[
            "The threshold is extracted from a policy passage.",
            "At least three payments share vendor and booking date.",
            "Each included payment is at least 90% of, but below, the threshold.",
            "The included aggregate is at least twice the threshold.",
        ],
        false_positive_guards=[
            "Different vendors or dates are evaluated separately.",
            "Payments at or above the threshold are excluded.",
            "The threshold is never hard-coded.",
        ],
        evidence_requirements=[
            "Policy passage containing the threshold",
            "Every qualifying payment row",
        ],
    ),
    RuleDefinition(
        rule_id="EXPORT_COMPLETENESS_RECONCILIATION",
        name="Export completeness reconciliation",
        status="implemented",
        category="reconciliation",
        severity="high",
        objective=(
            "Reconcile independent general-ledger population declarations to the physical "
            "GDPdU data-row count."
        ),
        required_inputs=[
            "General-ledger GDPdU table",
            "Export manifest",
            "Independent IT completeness confirmation",
        ],
        publication_conditions=[
            "A general-ledger row count is extracted from both control documents.",
            "The physical file is counted using its GDPdU schema.",
            "At least one of the three counts disagrees.",
        ],
        false_positive_guards=[
            "German and English thousands separators are normalized.",
            "Schema metadata and header rows are excluded from the physical data-row count.",
            "Agreement across all three sources remains clean.",
        ],
        evidence_requirements=[
            "Export-manifest PDF page and passage",
            "IT-confirmation PDF page and passage",
            "Physical table-count query locator",
        ],
    ),
    RuleDefinition(
        rule_id="MANUAL_JOURNAL_APPROVAL_VIOLATION",
        name="Material manual-journal approval violation",
        status="implemented",
        category="control",
        severity="high",
        objective=(
            "Identify material manual journals explicitly posted without independent approval."
        ),
        required_inputs=[
            "Manual-origin general-ledger rows",
            "Journal approval log",
            "JET planning threshold",
        ],
        publication_conditions=[
            "The approval log explicitly records self-approval, no approver, or a non-approved status.",
            "The absolute journal volume meets the source-defined JET threshold.",
            "Capture ID, line count, and absolute journal volume reconcile to manual ledger rows.",
        ],
        false_positive_guards=[
            "Exceptions below the source-defined threshold are suppressed.",
            "Independently approved journals remain clean.",
            "System-origin rows and unreconciled log entries are suppressed.",
        ],
        evidence_requirements=[
            "Approval-log row",
            "Planning passage containing the threshold",
            "Every positive ledger row contributing to the displayed exposure",
        ],
    ),
]


PLANNED_RULES = [
    (
        "BANK_CONFIRMATION_RECONCILIATION",
        "Bank confirmation reconciliation",
        "reconciliation",
        "Reconcile confirmed balances and accounts to the bank ledger.",
    ),
    (
        "PURCHASE_THREE_WAY_MATCH",
        "Purchase three-way match",
        "reconciliation",
        "Match purchase orders, goods receipts, invoices, and payments.",
    ),
    (
        "DUPLICATE_INVOICE_PAYMENT",
        "Duplicate invoices and payments",
        "fraud",
        "Detect repeated invoice identities, amounts, bank references, or payments.",
    ),
    (
        "VENDOR_BANK_CHANGE_PAYMENT",
        "Vendor bank change followed by payment",
        "fraud",
        "Link bank-account master-data changes to subsequent payment activity.",
    ),
    (
        "FINANCIAL_STATEMENT_TRACE",
        "Financial-statement traceability",
        "reconciliation",
        "Trace statement balances through trial balance and ledger source records.",
    ),
    (
        "RELATED_PARTY_CLUSTER",
        "Related-party and shared-account clustering",
        "fraud",
        "Identify vendors, employees, or customers sharing identifiers or bank accounts.",
    ),
    (
        "PERIOD_END_MANUAL_JOURNALS",
        "Period-end manual journals",
        "control",
        "Corroborate privileged manual entries and unusual period-end postings.",
    ),
    (
        "REVERSAL_REBOOKING_CHAIN",
        "Reversal and rebooking chains",
        "misstatement",
        "Trace entries reversed or rebooked across reporting periods.",
    ),
    (
        "REVENUE_CUTOFF",
        "Revenue cut-off",
        "misstatement",
        "Match revenue recognition to dispatch, service, and invoicing evidence.",
    ),
    (
        "EMPLOYEE_VENDOR_OVERLAP",
        "Employee and vendor overlap",
        "fraud",
        "Compare employee and vendor identities, addresses, and bank details.",
    ),
    (
        "DORMANT_VENDOR_REACTIVATION",
        "Dormant vendor reactivation",
        "control",
        "Identify dormant suppliers reactivated before unusual activity.",
    ),
]


RULE_CATALOG = [
    *IMPLEMENTED_RULES,
    *[
        RuleDefinition(
            rule_id=rule_id,
            name=name,
            status="planned",
            category=category,
            objective=objective,
        )
        for rule_id, name, category, objective in PLANNED_RULES
    ],
]
