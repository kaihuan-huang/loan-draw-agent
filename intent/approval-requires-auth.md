# Intent: approval-requires-auth

Author: Kai. Date: 2026-11-20. Status: draft.

## Problem
`POST /reviews/{draw_id}/decision` has no authentication. The approving officer is whatever name the request body
carries, so anyone who can reach the API can approve a draw, approve a draw over $100,000 alone by sending two
different names, or reject any waiting draw for good. The other routes (start a review, read its findings, walk the
ledger) are open too.

## Proposed outcome
Every route except `/health` needs an API key. The approver recorded in the ledger is the holder of the key, never a
name in the body. Only keys with the `officer` role can approve or reject; the `agent` role (the review service and
any automation around it) can start and read reviews and nothing else. With no keys configured, nobody can decide.

## Affected users and systems
`loan-draw-agent`: `api.py`, a new `auth.py`, compose and Helm wiring, README. Loan officers and any client of the API.

## Constraints
`ENGINEERING.md` §6: a draw is approved only by a loan officer's explicit `approve`; draws over $100,000 need two
different officers. No secrets in the repository; keys come from the environment.

## Open questions
- Refuse to start when no keys are configured, instead of serving 401s (separate change; it alters the shared test
  client).
- Per-officer API keys are a prototype mechanism. A real deployment would put an identity provider (OIDC) in front.

---
Product owner decision (fill in before moving to spec/):
- [ ] Accepted — becomes `spec/<slug>.md`
- [ ] Rejected — reason:
- [ ] Deferred — reason:
