# Loan Draw Review Agent PR Review Policy (authoritative)

Applies to every repository in this workspace. Defines the review passes for every PR; a human code owner still approves the merge (`ENGINEERING.md` §9). This file informs that approval, it does not replace it.

## Passes

Run these in order. Tag every finding with its pass.

1. **Bugs** — logic errors, broken edge cases, regressions against a `ENGINEERING.md` `[Rule]` item.
2. **Security & PII** — secrets in the diff; phone/email/message-body logged or returned unmasked; `CORS *`; auth bypass; string-built SQL or raw queries where the rule says otherwise.
3. **Money & state** — anything touching payment, order or account state: idempotency, locking, double-charge or double-send risk.
4. **Domain safety** — anything touching a §6 action: check line by line against `ENGINEERING.md` §6 (confirmation words, "done" only on a real downstream status, source of user-facing contact data, feature-flag default).
5. **Plan compliance** — the diff matches the `plan.md` approved for this change. Flag anything done that was not planned, or planned but not done.

## Important vs. nit

- **Important**: breaks behaviour, leaks PII, bypasses a §6 rule, ships a risky feature default-on, or makes an unmigrated schema change against an existing database.
- **Nit**: style, naming, non-user-facing refactors.

Cap nits at five per review; summarise the rest as a count. Do not report generated boilerplate or anything CI already enforces (lint, type-check).

## Release gate

A PR touching a §6 flow, a payment route or a schema migration needs an Important-finding-free review **and** a named release approval before it deploys (`ENGINEERING.md` §9). Everything else needs the review and the normal code-owner approval.
