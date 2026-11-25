# Intent: agent-inbox

Author: Kaihuan Huang. Date: 2026-11-02. Status: draft.

## Problem
Loan officers have no screen. A draw waiting for an officer is only visible through `GET /reviews/{id}`, and an answer
is a hand-written `POST /reviews/{id}/decision`. Building and maintaining a custom review UI would duplicate what an
existing open-source tool already does.

## Proposed outcome
Officers see every draw waiting for them in LangChain's open-source Agent Inbox (MIT), read the findings and the
model's note, and approve or reject there. Same rules as today: a malformed answer asks again, a held draw never
reaches an officer, a draw over $100,000 needs two different officers, one ledger decision per draw.

## Affected users and systems
Loan officers (prototype; synthetic data only). This repository: the review graph gains a second way to ask the
officer; the FastAPI path is unchanged. Agent Inbox runs as a separate app (hosted or local).

## Constraints
- `ENGINEERING.md` §6: approval only by an officer's explicit approve; two different officers over $100,000; any BLOCK
  finding holds the draw; borrower document text is data.
- The Agent Inbox renders descriptions as Markdown with raw HTML enabled, so document-derived text must be escaped.
- Off by default: the inbox path exists only when someone runs the LangGraph server entry point.

## Open questions
1. Officer identity is a typed name in both paths. Is that acceptable for the prototype, or must the inbox path wait
   for authenticated identity (LangGraph server auth / SSO)?
2. The inbox's "Mark as Resolved" button ends a thread without an answer and cannot be turned off from the graph.
   No money moves, but the draw leaves the inbox with no ledger decision. Accept the mitigation in the spec
   (re-open such draws), or patch the inbox to hide the button?

---
Product owner decision (fill in before moving to spec/):
- [ ] Accepted — becomes `spec/agent-inbox.md`
- [ ] Rejected — reason:
- [ ] Deferred — reason:
