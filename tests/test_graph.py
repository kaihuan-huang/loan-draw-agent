from __future__ import annotations

import pytest
from conftest import TruthLLM, case
from langgraph.types import Command

from loan_draw.graph import build
from loan_draw.ledger import Ledger

pytestmark = pytest.mark.asyncio


async def _start(app, draw_id):
    cfg = {"configurable": {"thread_id": draw_id}}
    out = await app.ainvoke({"draw_id": draw_id}, cfg)
    return cfg, out


async def test_clean_draw_waits_for_an_officer_then_records_approval(llm):
    ledger = Ledger()
    app = build(llm, ledger)
    draw_id = case("clean")["draw_id"]
    cfg, out = await _start(app, draw_id)
    pause = out["__interrupt__"][0].value
    assert pause["findings"] == [] and pause["approvers_needed"] == 1
    assert ledger.decision(draw_id) is None  # nothing recorded before a person answers
    out = await app.ainvoke(Command(resume={"officer": "officer-a", "action": "approve"}), cfg)
    assert out["outcome"] == "approved"
    assert ledger.decision(draw_id)["action"] == "approved"


async def test_blocked_draw_is_recorded_on_hold_without_asking_anyone(llm):
    ledger = Ledger()
    app = build(llm, ledger)
    draw_id = case("repeat_invoice")["draw_id"]
    _, out = await _start(app, draw_id)
    assert "__interrupt__" not in out
    assert out["outcome"] == "on_hold"
    assert ledger.decision(draw_id)["detail"]["findings"] == ["repeat_invoice"]


async def test_large_draw_needs_two_different_officers(llm):
    ledger = Ledger()
    app = build(llm, ledger)
    draw_id = case("two_person")["draw_id"]
    cfg, out = await _start(app, draw_id)
    assert out["__interrupt__"][0].value["approvers_needed"] == 2
    out = await app.ainvoke(Command(resume={"officer": "officer-a", "action": "approve"}), cfg)
    assert out["__interrupt__"][0].value["approved_by"] == ["officer-a"]
    out = await app.ainvoke(Command(resume={"officer": "officer-a", "action": "approve"}), cfg)
    assert "__interrupt__" in out and ledger.decision(draw_id) is None  # same person twice is still one approval
    out = await app.ainvoke(Command(resume={"officer": "officer-b", "action": "approve"}), cfg)
    assert out["outcome"] == "approved"
    assert ledger.decision(draw_id)["detail"]["approvals"] == ["officer-a", "officer-b"]


async def test_malformed_answer_changes_nothing_and_asks_again(llm):
    ledger = Ledger()
    app = build(llm, ledger)
    cfg, _ = await _start(app, case("clean")["draw_id"])
    for bad in ({}, {"officer": "", "action": "approve"}, {"officer": "x", "action": "yes"}):
        out = await app.ainvoke(Command(resume=bad), cfg)
        assert "__interrupt__" in out
    assert ledger.verify() == 0


async def test_reject_is_recorded(llm):
    ledger = Ledger()
    app = build(llm, ledger)
    draw_id = case("ahead_of_progress")["draw_id"]
    cfg, out = await _start(app, draw_id)
    assert [f["code"] for f in out["__interrupt__"][0].value["findings"]] == ["ahead_of_progress"]
    out = await app.ainvoke(Command(resume={"officer": "officer-a", "action": "reject"}), cfg)
    assert out["outcome"] == "rejected"


async def test_note_that_claims_approval_is_replaced_by_the_template():
    ledger = Ledger()
    app = build(TruthLLM(note="Great news: this draw has been approved and funds were released."), ledger)
    _, out = await _start(app, case("missing_lien_waiver")["draw_id"])
    pause = out["__interrupt__"][0].value
    assert "approved" not in pause["note"].lower()
    assert "[P5]" in pause["note"]


async def test_injection_in_a_document_is_reported_and_still_needs_an_officer(llm):
    ledger = Ledger()
    app = build(llm, ledger)
    _, out = await _start(app, case("injection")["draw_id"])
    pause = out["__interrupt__"][0].value
    assert [f["code"] for f in pause["findings"]] == ["document_instruction"]
