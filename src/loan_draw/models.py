"""Domain types. Money is always integer cents; the model never produces a decision, only extractions and prose."""
from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class LoanStatus(StrEnum):
    ACTIVE = "active"
    FUNDED = "funded"
    CLOSED = "closed"
    DEFAULT = "default"


class BudgetLine(BaseModel):
    budget_cents: int = Field(ge=0)
    disbursed_cents: int = Field(ge=0, default=0)


class Loan(BaseModel):
    id: str
    borrower: str
    status: LoanStatus
    commitment_cents: int = Field(ge=0)
    lines: dict[str, BudgetLine]
    funded_invoices: list[str] = []  # invoice numbers already paid on this loan

    @property
    def disbursed_cents(self) -> int:
        return sum(b.disbursed_cents for b in self.lines.values())


class RequestedLine(BaseModel):
    line: str
    amount_cents: int = Field(gt=0)


class Document(BaseModel):
    id: str
    kind: Literal["invoice", "lien_waiver", "inspection"]
    text: str  # what the borrower uploaded, as text; untrusted


class DrawRequest(BaseModel):
    id: str
    loan_id: str
    submitted_on: date
    lines: list[RequestedLine]
    document_ids: list[str]

    @property
    def total_cents(self) -> int:
        return sum(r.amount_cents for r in self.lines)


# What the model reads out of one document. Every field is optional: a missing value becomes a finding, never a guess.
class InvoiceFields(BaseModel):
    kind: Literal["invoice"] = "invoice"
    vendor: str | None = None
    invoice_number: str | None = None
    line: str | None = None
    total_cents: int | None = None


class LienWaiverFields(BaseModel):
    kind: Literal["lien_waiver"] = "lien_waiver"
    vendor: str | None = None
    amount_cents: int | None = None
    signed: bool | None = None


class InspectionFields(BaseModel):
    kind: Literal["inspection"] = "inspection"
    inspected_on: date | None = None
    percent_complete: dict[str, int] = {}  # budget line -> 0..100


Extraction = InvoiceFields | LienWaiverFields | InspectionFields


class Severity(StrEnum):
    BLOCK = "block"    # the draw cannot be approved as submitted
    REVIEW = "review"  # a loan officer must look before approving


class Finding(BaseModel):
    code: str
    severity: Severity
    clause: str  # policy clause id, e.g. "P4"
    message: str


Route = Literal["hold", "officer_review"]


class Decision(BaseModel):
    draw_id: str
    action: Literal["approve", "reject", "hold"]
    approvers: list[str] = []
    note: str = ""
