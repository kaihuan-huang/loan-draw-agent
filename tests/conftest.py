from __future__ import annotations

import json
from pathlib import Path

import pytest

from loan_draw import data

CASES = [json.loads(line) for line in (Path(__file__).resolve().parents[1] / "evals" / "cases.jsonl").open()]
TRUTH = {doc_id: fields for c in CASES for doc_id, fields in c["truth"].items()}
BY_TEXT = {data.document(doc_id).text: doc_id for doc_id in TRUTH}


class TruthLLM:
    """Stands in for the model: returns each document's ground-truth fields and a fixed note."""

    def __init__(self, note: str = "Check the findings above [P4]."):
        self.note = note
        self.calls: list[str] = []

    def json(self, task, messages, schema):
        self.calls.append(task)
        text = messages[-1]["content"].split("<document>\n", 1)[1].rsplit("\n</document>", 1)[0]
        return dict(TRUTH[BY_TEXT[text]])  # documents in the clean scenarios have no OCR letters to fix

    def text(self, task, messages):
        self.calls.append(task)
        return self.note


def case(scenario: str) -> dict:
    return next(c for c in CASES if c["scenario"] == scenario)


@pytest.fixture
def llm():
    return TruthLLM()
