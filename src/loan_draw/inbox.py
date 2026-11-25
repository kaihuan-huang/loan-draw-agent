"""Agent Inbox adapter: the officer review, served to LangChain's open-source Agent Inbox.

The Agent Inbox (github.com/langchain-ai/agent-inbox, MIT) is a ready-made UI for LangGraph `interrupt()`s. This module
only translates: the review payload becomes a `HumanInterrupt`, and the inbox's `HumanResponse` becomes the same
`{"officer", "action"}` answer the FastAPI path sends. Every rule stays in `graph.officer_review`: a malformed answer
asks again, a held draw never reaches the officer, large draws need two different officers.

The officer is never a name the inbox sends. The LangGraph server checks the caller's key (`loan_draw.inbox_auth`,
registered in langgraph.json) and puts the key holder in the run config; `ask` takes the officer from there and
counts the answer only for an `officer` key. An `agent` key, or a run with no authenticated user, asks again.

    LLM_CASSETTE=replay LLM_CASSETTE_PATH=evals/cassettes/qwen2.5-7b.jsonl uv run langgraph dev --no-browser
    uv run python scripts/inbox_start.py            # start reviews; draws waiting for an officer appear in the inbox

Only `edit` is allowed: the officer types `approve` or `reject`. `accept` is off because it would send the placeholder
back unchanged; `ignore` and `response` are off because neither carries a decision.
"""
from __future__ import annotations

import re
from typing import Any

from langgraph.config import get_config
from langgraph.types import interrupt

ACTION = "decide_draw"
PLACEHOLDER = "approve or reject"

_MD = re.compile(r"([\\`*_{}\[\]()<>#+!|~])")
# GFM autolinks bare URLs, www. hosts and emails even through backslash escapes and HTML entities (checked against
# the inbox's react-markdown 10 + remark-gfm). A word joiner (U+2060, invisible, no width) inside each trigger stops
# the match without changing what the officer reads. Display only: the ledger and the payload keep the original text.
_WJ = "⁠"
_AUTOLINK = [(re.compile(r":(?=//)"), ":" + _WJ), (re.compile(r"(?i)(www)\."), r"\1" + _WJ + "."), (re.compile("@"), _WJ + "@")]


def _md(text: Any) -> str:
    """Escape Markdown so document-derived text (vendor names, the model's note) renders as plain text, not links."""
    s = _MD.sub(r"\\\1", str(text)).replace("\n", " ")
    for pattern, repl in _AUTOLINK:
        s = pattern.sub(repl, s)
    return s


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
              "", "Type `approve` or `reject` as `decision`. The approval is recorded for the holder of your key."]
    return "\n".join(lines)


def to_interrupt(p: dict) -> dict:
    return {
        "action_request": {"action": ACTION, "args": {"decision": PLACEHOLDER}},
        "config": {"allow_ignore": False, "allow_respond": False, "allow_edit": True, "allow_accept": False},
        "description": describe(p),
    }


def from_response(resp: Any) -> dict:
    """HumanResponse (the inbox sends a list with one) -> {"action"}; anything else -> {} (asks again).

    Only the decision is read. Any other field, such as a typed officer name, is ignored.
    """
    r = resp[0] if isinstance(resp, list) and resp else resp
    if not isinstance(r, dict) or r.get("type") != "edit" or not isinstance(r.get("args"), dict):
        return {}
    args = r["args"].get("args")
    if not isinstance(args, dict):
        return {}
    return {"action": str(args.get("decision", "")).strip().lower()}


def _field(user: Any, key: str) -> Any:
    """Read a field of the server's user object: a dict in tests, an object with attributes and item access in the
    LangGraph server."""
    if isinstance(user, dict):
        return user.get(key)
    try:
        return user[key]
    except (KeyError, TypeError, IndexError):
        return getattr(user, key, None)


def key_holder_officer() -> str:
    """The officer name for this run: the holder of an `officer` key, or "" when there is none."""
    try:
        user = get_config().get("configurable", {}).get("langgraph_auth_user")
    except RuntimeError:  # called outside a run
        return ""
    if user is None:
        return ""
    permissions = _field(user, "permissions") or []
    if _field(user, "role") != "officer" or "officer" not in permissions:
        return ""
    return str(_field(user, "identity") or "").strip()


def ask(payload: dict) -> dict:
    answer = from_response(interrupt(to_interrupt(payload)))
    officer = key_holder_officer()  # read after the resume: it is the user of the run that answered
    return {"officer": officer, **answer} if answer and officer else {}
