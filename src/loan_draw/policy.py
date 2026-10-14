"""Deterministic draw checks. These decide; the model only extracts fields and writes the explanation.

Each finding cites a clause of data/policy.md. A BLOCK finding means the draw goes back on hold; anything else goes to
a loan officer, who is the only one who can approve.
"""
from __future__ import annotations

import re
from datetime import timedelta

from loan_draw.models import (
    DrawRequest,
    Extraction,
    Finding,
    InspectionFields,
    InvoiceFields,
    LienWaiverFields,
    Loan,
    LoanStatus,
    Route,
    Severity,
)

PERCENT_TOLERANCE = 5            # points of slack between inspected progress and money out on a line
INSPECTION_MAX_AGE_DAYS = 30
TWO_PERSON_THRESHOLD_CENTS = 100_000_00

# Text in a borrower document that tries to steer the review. It is data, never an instruction: flag it, ignore it.
_STEERING = re.compile(
    r"\b(ignore|skip|bypass|disregard)\b.{0,40}\b(check|rule|policy|instruction|review)s?\b"
    r"|\b(auto[- ]?approve|approve (this|the) draw|mark (it|this) (as )?approved|you are now)\b",
    re.IGNORECASE | re.DOTALL)


def _f(code: str, sev: Severity, clause: str, msg: str) -> Finding:
    return Finding(code=code, severity=sev, clause=clause, message=msg)


def check(loan: Loan, draw: DrawRequest, docs: dict[str, str], ex: dict[str, Extraction | None]) -> list[Finding]:
    """`docs` is document id -> raw text, `ex` is document id -> extraction (None when the model's output was unusable)."""
    out: list[Finding] = []
    B, R = Severity.BLOCK, Severity.REVIEW

    if loan.status not in (LoanStatus.ACTIVE, LoanStatus.FUNDED):
        out.append(_f("loan_not_drawable", B, "P1", f"Loan status is {loan.status.value}; draws need active or funded."))

    if loan.disbursed_cents + draw.total_cents > loan.commitment_cents:
        out.append(_f("over_commitment", B, "P2", "Disbursed plus requested exceeds the loan commitment."))

    invoices = [e for e in ex.values() if isinstance(e, InvoiceFields)]
    waivers = [e for e in ex.values() if isinstance(e, LienWaiverFields)]
    inspections = [e for e in ex.values() if isinstance(e, InspectionFields)]

    for doc_id, e in ex.items():
        if e is None:
            out.append(_f("unreadable_document", R, "P4", f"Document {doc_id} could not be read into fields."))

    for doc_id, text in docs.items():
        if _STEERING.search(text):
            out.append(_f("document_instruction", R, "P9",
                          f"Document {doc_id} contains text addressed to the reviewer; it was ignored."))

    inspection = max(inspections, key=lambda i: i.inspected_on or draw.submitted_on - timedelta(days=9999), default=None)
    if inspection is None or inspection.inspected_on is None:
        out.append(_f("no_inspection", R, "P6", "No dated inspection report is attached."))
    elif (draw.submitted_on - inspection.inspected_on).days > INSPECTION_MAX_AGE_DAYS:
        out.append(_f("stale_inspection", R, "P6",
                      f"Inspection is {(draw.submitted_on - inspection.inspected_on).days} days old (limit "
                      f"{INSPECTION_MAX_AGE_DAYS})."))

    for req in draw.lines:
        line = loan.lines.get(req.line)
        if line is None:
            out.append(_f("unknown_line", B, "P2", f"Budget line '{req.line}' is not on this loan."))
            continue
        if line.disbursed_cents + req.amount_cents > line.budget_cents:
            out.append(_f("over_line_budget", B, "P2", f"Line '{req.line}' would exceed its budget."))
        if inspection and inspection.inspected_on and req.line in inspection.percent_complete:
            allowed = line.budget_cents * min(100, inspection.percent_complete[req.line] + PERCENT_TOLERANCE) // 100
            if line.disbursed_cents + req.amount_cents > allowed:
                out.append(_f("ahead_of_progress", R, "P3",
                              f"Line '{req.line}' would be funded ahead of inspected progress "
                              f"({inspection.percent_complete[req.line]}%)."))
        elif inspection and inspection.inspected_on:
            out.append(_f("line_not_inspected", R, "P3", f"Inspection does not report progress on '{req.line}'."))

        support = [i for i in invoices if i.line == req.line and i.total_cents]
        if sum(i.total_cents or 0 for i in support) < req.amount_cents:
            out.append(_f("missing_invoice", R, "P4", f"Invoices do not cover the amount requested on '{req.line}'."))

    for inv in invoices:
        if inv.invoice_number and inv.invoice_number in loan.funded_invoices:
            out.append(_f("repeat_invoice", B, "P7", f"Invoice {inv.invoice_number} was already funded on this loan."))
        if inv.vendor:
            covered = sum(w.amount_cents or 0 for w in waivers
                          if w.signed and w.vendor and w.vendor.lower() == inv.vendor.lower())
            if covered < (inv.total_cents or 0):
                out.append(_f("missing_lien_waiver", R, "P5", f"No signed lien waiver covers {inv.vendor}."))

    return _dedupe(out)


def _dedupe(fs: list[Finding]) -> list[Finding]:
    seen, out = set(), []
    for f in fs:
        if (f.code, f.message) not in seen:
            seen.add((f.code, f.message))
            out.append(f)
    return out


def route(findings: list[Finding]) -> Route:
    """Any BLOCK sends the draw back on hold. Everything else, clean draws included, waits for a loan officer."""
    return "hold" if any(f.severity is Severity.BLOCK for f in findings) else "officer_review"


def approvers_needed(draw: DrawRequest) -> int:
    return 2 if draw.total_cents > TWO_PERSON_THRESHOLD_CENTS else 1
