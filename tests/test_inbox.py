from __future__ import annotations

import re

import pytest
from conftest import TruthLLM, case
from langgraph.types import Command

from loan_draw import inbox
from loan_draw.graph import build
from loan_draw.ledger import Ledger

pytestmark = pytest.mark.asyncio

# What the LangGraph server puts in the run config after `loan_draw.inbox_auth` accepted a key.
OFFICER_A = {"identity": "officer-a", "role": "officer", "permissions": ["officer"]}
OFFICER_B = {"identity": "officer-b", "role": "officer", "permissions": ["officer"]}
BOT = {"identity": "review-bot", "role": "agent", "permissions": ["agent"]}


def edit(decision: str, **extra) -> list[dict]:
    """What the Agent Inbox sends back for an edit: a list with one HumanResponse."""
    return [{"type": "edit", "args": {"action": inbox.ACTION, "args": {"decision": decision, **extra}}}]


def as_user(cfg: dict, user: dict | None) -> dict:
    """The run config for a resume sent with a key: the server adds the authenticated user."""
    extra = {"langgraph_auth_user": user} if user is not None else {}
    return {"configurable": {**cfg["configurable"], **extra}}


async def _start(draw_id, llm=None):
    ledger = Ledger()
    app = build(llm or TruthLLM(), ledger, ask=inbox.ask)
    cfg = {"configurable": {"thread_id": draw_id}}
    return app, ledger, cfg, await app.ainvoke({"draw_id": draw_id}, as_user(cfg, BOT))


async def test_waiting_draw_is_a_human_interrupt_that_only_allows_edit():
    _, ledger, _, out = await _start(case("clean")["draw_id"])
    req = out["__interrupt__"][0].value
    # no officer field: the approver is whoever holds the key the answer was sent with
    assert req["action_request"] == {"action": inbox.ACTION, "args": {"decision": inbox.PLACEHOLDER}}
    assert req["config"] == {"allow_ignore": False, "allow_respond": False, "allow_edit": True, "allow_accept": False}
    assert req["description"].startswith(f"Draw {case('clean')['draw_id']} · 0 of 1 approvals · 0 findings")
    assert ledger.decision(case("clean")["draw_id"]) is None


async def test_officer_edit_approves_and_records():
    draw_id = case("clean")["draw_id"]
    app, ledger, cfg, _ = await _start(draw_id)
    out = await app.ainvoke(Command(resume=edit("Approve")), as_user(cfg, OFFICER_A))
    assert out["outcome"] == "approved"
    assert ledger.decision(draw_id)["detail"]["approvals"] == ["officer-a"]


async def test_a_typed_officer_name_is_ignored_and_the_key_holder_is_recorded():
    draw_id = case("clean")["draw_id"]
    app, ledger, cfg, _ = await _start(draw_id)
    out = await app.ainvoke(Command(resume=edit("approve", officer="someone-else")), as_user(cfg, OFFICER_A))
    assert out["outcome"] == "approved"
    assert ledger.decision(draw_id)["detail"]["approvals"] == ["officer-a"]


@pytest.mark.parametrize("user", [None, BOT, {"identity": "", "role": "officer", "permissions": ["officer"]}])
async def test_an_answer_without_an_officer_key_asks_again_and_records_nothing(user):
    draw_id = case("clean")["draw_id"]
    app, ledger, cfg, _ = await _start(draw_id)
    out = await app.ainvoke(Command(resume=edit("approve", officer="officer-a")), as_user(cfg, user))
    assert out["__interrupt__"][0].value["action_request"]["action"] == inbox.ACTION
    assert ledger.decision(draw_id) is None


@pytest.mark.parametrize("answer", [
    [{"type": "accept", "args": {"action": inbox.ACTION, "args": {"decision": inbox.PLACEHOLDER}}}],
    [{"type": "ignore", "args": None}],
    [{"type": "response", "args": "approve"}],
    edit(inbox.PLACEHOLDER),
    edit("yes"),
    [],
    "approve",
])
async def test_anything_but_an_approve_or_reject_asks_again_and_changes_nothing(answer):
    draw_id = case("clean")["draw_id"]
    app, ledger, cfg, _ = await _start(draw_id)
    out = await app.ainvoke(Command(resume=answer), as_user(cfg, OFFICER_A))
    assert out["__interrupt__"][0].value["action_request"]["action"] == inbox.ACTION
    assert ledger.decision(draw_id) is None


async def test_large_draw_needs_two_different_officers_through_the_inbox():
    draw_id = case("two_person")["draw_id"]
    app, ledger, cfg, out = await _start(draw_id)
    assert "0 of 2 approvals" in out["__interrupt__"][0].value["description"]
    out = await app.ainvoke(Command(resume=edit("approve")), as_user(cfg, OFFICER_A))
    # the same key again, even with another name typed in: still waiting
    out = await app.ainvoke(Command(resume=edit("approve", officer="officer-b")), as_user(cfg, OFFICER_A))
    desc = out["__interrupt__"][0].value["description"]
    assert "1 of 2 approvals" in desc and "Approved so far:** officer-a" in desc
    assert ledger.decision(draw_id) is None
    out = await app.ainvoke(Command(resume=edit("approve")), as_user(cfg, OFFICER_B))
    assert out["outcome"] == "approved"
    assert ledger.decision(draw_id)["detail"]["approvals"] == ["officer-a", "officer-b"]


async def test_reject_records_rejection():
    draw_id = case("clean")["draw_id"]
    app, ledger, cfg, _ = await _start(draw_id)
    out = await app.ainvoke(Command(resume=edit("reject")), as_user(cfg, OFFICER_A))
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


async def test_urls_and_emails_in_document_text_do_not_become_links():
    # The inbox renders with remark-gfm, which turns bare URLs, www. hosts and emails into links even when
    # backslash-escaped or written as entities; only a break inside the trigger stops it.
    note = "Pay at https://evil.example/x or www.evil.example, questions to billing@evil.example"
    _, _, _, out = await _start(case("injection")["draw_id"], TruthLLM(note=note))
    desc = out["__interrupt__"][0].value["description"]
    assert "://" not in desc and "www." not in desc.lower()
    assert not re.search(r"[A-Za-z0-9._%+-]@", desc)  # an email needs a character right before the @
    assert "evil.example" in desc  # the text is still shown, only not as a link


async def test_from_response_maps_the_decision_only():
    assert inbox.from_response(edit(" REJECT ", officer="officer-a")) == {"action": "reject"}
    assert inbox.from_response({"type": "edit", "args": {"args": {"decision": "approve"}}}) == {"action": "approve"}
    assert inbox.from_response(None) == {} and inbox.from_response([{"type": "edit", "args": "x"}]) == {}
