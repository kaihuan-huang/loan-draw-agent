# Spec: agent-inbox

From: `intent/agent-inbox.md` (draft, not yet accepted). Author: Kaihuan Huang, reviewed by <product owner>. Status: draft.

## Requirements
1. Every draw routed to `officer_review` appears in the Agent Inbox as one thread with the action `decide_draw`.
2. The description shows the draw id, approvals so far and needed, every finding (clause, severity, message) and the
   model's note, and says the model does not decide.
3. The officer answers by editing one field, `decision` (`approve` or `reject`). Accept, ignore and free-text
   response are disabled. The approver is the holder of the `officer` API key the answer was sent with
   (`LOAN_DRAW_API_KEYS`, as for the HTTP API); a typed name is ignored, an `agent` key or no key asks again, and one
   key cannot fill both approvals of a draw over $100,000.
4. The answer goes through `graph.officer_review` unchanged: anything but a named approve or reject asks again and
   records nothing; a second approval from the same officer does not count; a held draw never asks.
5. Document-derived text and the note render as plain text (no links, images or HTML).
6. The FastAPI path (`/reviews/...`) behaves exactly as before.

## Design
- `graph.build(..., ask=interrupt, standalone=True)`: `ask` is how the officer is asked. Default: today's `interrupt`
  with the plain payload. `standalone=False` compiles without a checkpointer for a LangGraph server.
- `loan_draw/inbox.py`: `to_interrupt(payload)` → `HumanInterrupt`; `from_response(HumanResponse list)` →
  `{action}` or `{}`; `ask` adds the key holder as `officer`. Markdown is escaped with `_md`.
- `loan_draw/inbox_server.py` + `langgraph.json`: the graph for `langgraph dev` / LangGraph server, built once at load.
- `loan_draw/inbox_auth.py`, registered as `auth` in `langgraph.json`: the server refuses any request without a known
  key (`Authorization: Bearer <key>` or `x-api-key`, which is where the Agent Inbox sends the key from its settings)
  and makes the key holder the run's user. `inbox.ask` reads that user from the run config after the resume and keeps
  the answer only for an `officer` key. The officer check is in the graph, so it holds whatever the server's other
  authorization handlers allow.
- `scripts/inbox_start.py`: starts reviews on the server (one thread per draw, UUID5 of the draw id); resumes a review
  that stopped mid-way; reviews again a draw that ended with no outcome.
- `langgraph-cli[inmem]` in a separate dependency group `inbox`; CI's `uv sync --frozen` does not install it.

## Security & compliance check
- **PII**: none; synthetic data. Descriptions carry vendor names and amounts already shown to officers by the API.
- **Money / state**: approval still needs the explicit approve and the two-person rule (tests in `tests/test_inbox.py`).
  The ledger write is unchanged (`record`, one decision per draw). The API and `inbox_server.py` take the ledger path
  from one function, `ledger.ledger_path()` (env `LEDGER_DB`, default `ledger.db`), so both write the same ledger;
  with different paths one draw could get a decision in each (test in `tests/test_api.py`).
- **§6**: the rule text changes from "through `/reviews/{id}/decision`" to "through `/reviews/{id}/decision` or the
  Agent Inbox entry point, both answered by `graph.officer_review`"; in both, the officer is the holder of an
  `officer` key (main's approval-requires-auth change), never a typed name.
- **Feature flag**: off by default. Nothing runs unless the LangGraph server entry point is started.
- **Known gaps** (verified 2026-11-02 against agent-inbox `f1616f3`, langgraph-api 0.17.0):
  1. ~~Officer identity is typed text.~~ Resolved: the approver is the key holder (`inbox_auth`), verified on
     `langgraph dev` 2026-11-25. Keys remain a prototype mechanism, as for the API; production puts an identity
     provider in front. The Agent Inbox keeps the key in the browser's local storage, in the field it labels
     "LangSmith API Key".
  2. "Mark as Resolved" calls `threads.updateState(asNode: END)`: the thread ends, no ledger row is written, the draw
     leaves the inbox. Observed on D-5051. Mitigation: `scripts/inbox_start.py` reviews it again (observed: back to
     waiting). No money can move this way. The reopened thread keeps its checkpoint, so approvals given before
     "Mark as Resolved" still count toward the two-person rule; reopening does not clear them (intended, not changed).
  2a. `scripts/inbox_start.py` is for a single operator: its check (is the thread waiting or decided?) and its run are
     not atomic, so two copies started at once on the same draw could both start a run. Money is not at risk: the
     ledger's unique index allows one decision per draw. A per-draw lock was left out as more machinery than one
     operator needs; add one if several people run the script.
  3. The inbox's Markdown component enables `rehype-raw`; escaping is therefore required, and tested.
     remark-gfm also autolinks bare URLs, `www.` hosts and emails, and backslash escapes or HTML entities do not
     stop it; `_md` inserts a word joiner (U+2060) inside `://`, `www.` and `@` (display only). Checked against the
     inbox's own react-markdown 10 + remark-gfm + rehype-raw.
  4. agent-inbox `f1616f3` with react-markdown 10 crashes when a thread is opened (`className` prop removed).
     `docs/agent-inbox-react-markdown-10.patch` is the local fix used for verification.
  5. `langgraph dev` needs `--allow-blocking`: the ledger (SQLite) and the in-process MCP server read synchronously
     inside the async run. The FastAPI path has the same reads; moving to Postgres (README "Limits") removes this.
  6. `langgraph dev` checks keys (`inbox_auth`) but is a development server: in-memory threads, localhost only,
     no TLS. Not for shared use.

## Open questions / conflicts
See `intent/agent-inbox.md` questions 1 and 2.

---
Product owner sign-off:
- [ ] Approved as written — proceed to the build plan
- [ ] Approved with changes — listed above, re-check before Build
- [ ] Rejected — reason:
