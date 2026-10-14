"""Read the synthetic store (data/*.json). The MCP server is the only caller in the review path."""
from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from pydantic import TypeAdapter

from loan_draw.models import Document, DrawRequest, Extraction, Loan

DATA = Path(__file__).resolve().parents[2] / "data"
_EXTRACTION = TypeAdapter(Extraction)


@cache
def _rows(name: str, root: Path = DATA) -> dict[str, dict]:
    return {r["id"]: r for r in json.loads((root / f"{name}.json").read_text())}


def loan(loan_id: str) -> Loan:
    return Loan.model_validate(_rows("loans")[loan_id])


def draw(draw_id: str) -> DrawRequest:
    return DrawRequest.model_validate(_rows("draws")[draw_id])


def document(doc_id: str) -> Document:
    return Document.model_validate(_rows("documents")[doc_id])


def draw_ids() -> list[str]:
    return sorted(_rows("draws"))


def policy_text() -> str:
    return (DATA / "policy.md").read_text()


def extraction(obj: dict) -> Extraction:
    return _EXTRACTION.validate_python(obj)
