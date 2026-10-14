# Loan Draw Review Agent workspace

Everything that belongs to the Loan Draw Review Agent workspace but to none of its repositories:

| Path | What it is |
|---|---|
| `ENGINEERING.md`, `REVIEW.md` | Conventions, the delivery loop (§9) and the review passes. `ENGINEERING.md` is the single authoritative copy. |
| `REVIEW.md` | PR review passes and the release gate; single authoritative copy. |
| `intent/`, `spec/` | Product-owner-approved intent and design specs, shared across all repos (§9 Plan/Design). Start from `TEMPLATE.md` in each. Committed as a whole: never paste a raw phone number, email or message body into a file here; mask it. |
| `docs/handoff/` | Dated handoff notes and PR bodies. Start here when resuming work. |

Repositories live under `./` as their own git repositories and are ignored here. The `.gitignore` denies everything by default, so company documents, spreadsheets and transcripts in the workspace root cannot be committed by accident.

Resume: read the newest file in `docs/handoff/`.
