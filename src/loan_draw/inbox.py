"""Agent Inbox adapter: the officer review, served to LangChain's open-source Agent Inbox.

The Agent Inbox (github.com/langchain-ai/agent-inbox, MIT) is a ready-made UI for LangGraph `interrupt()`s. This module
only translates: the review payload becomes a `HumanInterrupt`, and the inbox's `HumanResponse` becomes the same
`{"officer", "action"}` answer the FastAPI path sends. Every rule stays in `graph.officer_review`: a malformed answer
asks again, a held draw never reaches the officer, large draws need two different officers.

    LLM_CASSETTE=replay LLM_CASSETTE_PATH=evals/cassettes/qwen2.5-7b.jsonl uv run langgraph dev --no-browser
    uv run python scripts/inbox_start.py            # start reviews; draws waiting for an officer appear in the inbox

Only `edit` is allowed: the officer types their name and `approve` or `reject`. `accept` is off because it would
send the placeholder back unchanged; `ignore` and `response` are off because neither carries an officer.
"""
from __future__ import annotations

import re
from typing import Any

from langgraph.types import interrupt

ACTION = "decide_draw"
PLACEHOLDER = "approve or reject"

_MD = re.compile(r"([\\`*_{}\[\]()<>#+!|~])")


def _md(text: Any) -> str:
    """Escape Markdown so document-derived text (vendor names, the model's note) renders as plain text."""
    return _MD.sub(r"\\\1", str(text)).replace("\n", " ")


def describe(p: dict) -> str:
    need, done = p["approvers_needed"], p.get("approved_by", [])
    n = len(p["findings"])
    # first line is plain text: the inbox list previews it
    lines = [f"Draw {_md(p['draw_id'])} · {len(done)} of {need} approvals · {n} finding{'' if n == 1 else 's'}", ""]
    if done:
        lines += [f"**Approved so far:** {', '.join(_md(o) for o in done)} (the next approval must come from someone else)", ""]
    lines.append("**Findings**")
    if p["findings"]:
        lines += [f"- `{_md(f['clause'])}` {_md(f['severity'])} · {_md(f['message'])}" for f in p["findings"]]
    else:
        lines.append("- none")
    lines += ["", "**Note from the model** (it never decides; rules routed this draw)", "", f"> {_md(p['note'])}",
              "", "Type your name as `officer` and `approve` or `reject` as `decision`."]
    return "\n".join(lines)


def to_interrupt(p: dict) -> dict:
    return {
        "action_request": {"action": ACTION, "args": {"officer": "", "decision": PLACEHOLDER}},
        "config": {"allow_ignore": False, "allow_respond": False, "allow_edit": True, "allow_accept": False},
        "description": describe(p),
    }


def from_response(resp: Any) -> dict:
    """HumanResponse (the inbox sends a list with one) -> {"officer", "action"}; anything else -> {} (asks again)."""
    r = resp[0] if isinstance(resp, list) and resp else resp
    if not isinstance(r, dict) or r.get("type") != "edit" or not isinstance(r.get("args"), dict):
        return {}
    args = r["args"].get("args")
    if not isinstance(args, dict):
        return {}
    return {"officer": str(args.get("officer", "")).strip(), "action": str(args.get("decision", "")).strip().lower()}


def ask(payload: dict) -> dict:
    return from_response(interrupt(to_interrupt(payload)))
