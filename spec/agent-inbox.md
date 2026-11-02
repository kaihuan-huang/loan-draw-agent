# Spec: agent-inbox

From: `intent/agent-inbox.md` (draft, not yet accepted). Author: Kaihuan Huang, reviewed by <product owner>. Status: draft.

## Requirements
1. Every draw routed to `officer_review` appears in the Agent Inbox as one thread with the action `decide_draw`.
2. The description shows the draw id, approvals so far and needed, every finding (clause, severity, message) and the
   model's note, and says the model does not decide.
3. The officer answers by editing two fields, `officer` and `decision` (`approve` or `reject`). Accept, ignore and
   free-text response are disabled.
4. The answer goes through `graph.officer_review` unchanged: anything but a named approve or reject asks again and
   records nothing; a second approval from the same officer does not count; a held draw never asks.
5. Document-derived text and the note render as plain text (no links, images or HTML).
6. The FastAPI path (`/reviews/...`) behaves exactly as before.

## Design
- `graph.build(..., ask=interrupt, standalone=True)`: `ask` is how the officer is asked. Default: today's `interrupt`
  with the plain payload. `standalone=False` compiles without a checkpointer for a LangGraph server.
- `loan_draw/inbox.py`: `to_interrupt(payload)` → `HumanInterrupt`; `from_response(HumanResponse list)` →
  `{officer, action}` or `{}`; `ask = from_response ∘ interrupt ∘ to_interrupt`. Markdown is escaped with `_md`.
- `loan_draw/inbox_server.py` + `langgraph.json`: the graph for `langgraph dev` / LangGraph server, built once at load.
- `scripts/inbox_start.py`: starts reviews on the server (one thread per draw, UUID5 of the draw id); resumes a review
  that stopped mid-way; reviews again a draw that ended with no outcome.
- `langgraph-cli[inmem]` in a separate dependency group `inbox`; CI's `uv sync --frozen` does not install it.

## Security & compliance check
- **PII**: none; synthetic data. Descriptions carry vendor names and amounts already shown to officers by the API.
- **Money / state**: approval still needs the explicit approve and the two-person rule (tests in `tests/test_inbox.py`).
  The ledger write is unchanged (`record`, one decision per draw).
- **§6**: the rule text changes from "through `/reviews/{id}/decision`" to "through `/reviews/{id}/decision` or the
  Agent Inbox entry point, both answered by `graph.officer_review`".
- **Feature flag**: off by default. Nothing runs unless the LangGraph server entry point is started.
- **Known gaps** (verified 2026-11-02 against agent-inbox `f1616f3`, langgraph-api 0.17.0):
  1. Officer identity is typed text, as in the API path. Production needs authenticated identity.
  2. "Mark as Resolved" calls `threads.updateState(asNode: END)`: the thread ends, no ledger row is written, the draw
     leaves the inbox. Observed on D-5051. Mitigation: `scripts/inbox_start.py` reviews it again (observed: back to
     waiting). No money can move this way.
  3. The inbox's Markdown component enables `rehype-raw`; escaping is therefore required, and tested.
  4. agent-inbox `f1616f3` with react-markdown 10 crashes when a thread is opened (`className` prop removed).
     `docs/agent-inbox-react-markdown-10.patch` is the local fix used for verification.
  5. `langgraph dev` needs `--allow-blocking`: the ledger (SQLite) and the in-process MCP server read synchronously
     inside the async run. The FastAPI path has the same reads; moving to Postgres (README "Limits") removes this.
  6. `langgraph dev` has no auth and listens on localhost only. Not for shared use.

## Open questions / conflicts
See `intent/agent-inbox.md` questions 1 and 2.

---
Product owner sign-off:
- [ ] Approved as written — proceed to the build plan
- [ ] Approved with changes — listed above, re-check before Build
- [ ] Rejected — reason:
