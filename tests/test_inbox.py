from __future__ import annotations

import pytest
from conftest import TruthLLM, case
from langgraph.types import Command

from loan_draw import inbox
from loan_draw.graph import build
from loan_draw.ledger import Ledger

pytestmark = pytest.mark.asyncio


def edit(officer: str, decision: str) -> list[dict]:
    """What the Agent Inbox sends back for an edit: a list with one HumanResponse."""
    return [{"type": "edit", "args": {"action": inbox.ACTION, "args": {"officer": officer, "decision": decision}}}]


async def _start(draw_id, llm=None):
    ledger = Ledger()
    app = build(llm or TruthLLM(), ledger, ask=inbox.ask)
    cfg = {"configurable": {"thread_id": draw_id}}
    return app, ledger, cfg, await app.ainvoke({"draw_id": draw_id}, cfg)


async def test_waiting_draw_is_a_human_interrupt_that_only_allows_edit():
    _, ledger, _, out = await _start(case("clean")["draw_id"])
    req = out["__interrupt__"][0].value
    assert req["action_request"] == {"action": inbox.ACTION, "args": {"officer": "", "decision": inbox.PLACEHOLDER}}
    assert req["config"] == {"allow_ignore": False, "allow_respond": False, "allow_edit": True, "allow_accept": False}
    assert req["description"].startswith(f"Draw {case('clean')['draw_id']} · 0 of 1 approvals · 0 findings")
    assert ledger.decision(case("clean")["draw_id"]) is None


async def test_officer_edit_approves_and_records():
    draw_id = case("clean")["draw_id"]
    app, ledger, cfg, _ = await _start(draw_id)
    out = await app.ainvoke(Command(resume=edit("officer-a", "Approve")), cfg)
    assert out["outcome"] == "approved"
    assert ledger.decision(draw_id)["detail"]["approvals"] == ["officer-a"]


@pytest.mark.parametrize("answer", [
    [{"type": "accept", "args": {"action": inbox.ACTION, "args": {"officer": "", "decision": inbox.PLACEHOLDER}}}],
    [{"type": "ignore", "args": None}],
    [{"type": "response", "args": "approve"}],
    edit("officer-a", inbox.PLACEHOLDER),
    edit("", "approve"),
    edit("officer-a", "yes"),
    [],
    "approve",
])
async def test_anything_but_a_named_approve_or_reject_asks_again_and_changes_nothing(answer):
    draw_id = case("clean")["draw_id"]
    app, ledger, cfg, _ = await _start(draw_id)
    out = await app.ainvoke(Command(resume=answer), cfg)
    assert out["__interrupt__"][0].value["action_request"]["action"] == inbox.ACTION
    assert ledger.decision(draw_id) is None


async def test_large_draw_needs_two_different_officers_through_the_inbox():
    draw_id = case("two_person")["draw_id"]
    app, ledger, cfg, out = await _start(draw_id)
    assert "0 of 2 approvals" in out["__interrupt__"][0].value["description"]
    out = await app.ainvoke(Command(resume=edit("officer-a", "approve")), cfg)
    out = await app.ainvoke(Command(resume=edit("officer-a", "approve")), cfg)  # same officer again: still waiting
    desc = out["__interrupt__"][0].value["description"]
    assert "1 of 2 approvals" in desc and "Approved so far:** officer-a" in desc
    assert ledger.decision(draw_id) is None
    out = await app.ainvoke(Command(resume=edit("officer-b", "approve")), cfg)
    assert out["outcome"] == "approved"


async def test_reject_records_rejection():
    draw_id = case("clean")["draw_id"]
    app, ledger, cfg, _ = await _start(draw_id)
    out = await app.ainvoke(Command(resume=edit("officer-a", "reject")), cfg)
    assert out["outcome"] == "rejected" and ledger.decision(draw_id)["action"] == "rejected"


async def test_held_draw_never_reaches_the_inbox():
    _, _, _, out = await _start(case("repeat_invoice")["draw_id"])
    assert "__interrupt__" not in out and out["outcome"] == "on_hold"


async def test_document_text_and_note_render_as_plain_text():
    note = "Looks fine ![x](https://evil.example/p.png) [approve](https://evil.example) <b>now</b>"
    _, _, _, out = await _start(case("injection")["draw_id"], TruthLLM(note=note))
    desc = out["__interrupt__"][0].value["description"]
    assert "![x](" not in desc and "[approve](" not in desc and "<b>" not in desc
    assert "document\\_instruction" not in desc  # codes are not shown; the finding message is
    assert "contains text addressed to the reviewer" in desc


async def test_from_response_maps_edit_and_rejects_everything_else():
    assert inbox.from_response(edit(" officer-a ", " REJECT ")) == {"officer": "officer-a", "action": "reject"}
    assert inbox.from_response({"type": "edit", "args": {"args": {"officer": "o", "decision": "approve"}}})["action"] == "approve"
    assert inbox.from_response(None) == {} and inbox.from_response([{"type": "edit", "args": "x"}]) == {}
