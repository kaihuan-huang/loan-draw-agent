# Loan Draw Review Agent Engineering Reference (authoritative)

Single source of truth for this workspace's conventions. Tool-specific rule files are kept local and only point here. Edit **this file only**.

**Last verified against source: 2026-10-14** (state how: grep/read of which repos; which test suites ran; which deployments were checked). When a claim is corrected, edit it in place and update this date.

Legend: **[Rule]** = what new code must do. **[Fact]** = what the code does today (may differ from the rule). Never present a [Fact] gap as if the rule were already satisfied.

---

## Overview

<!-- One row per service/app. Ports are dev defaults; container, host and proxy ports differ per deployment. -->

| Service | Port | Storage | Purpose |
|---|---|---|---|
| `<repo-name>` | `<dev port>` | `<db>` | `<one line>` |

Target layering: `<e.g. Router → Service → Model>`.

---

## Environments

<!-- Dev/test hosts, their reachability and hard constraints (CPU arch, GPU sharing, shared services). Verified facts only, with the date. -->

| Item | Value |
|---|---|
| Dev/test host | `<name, hardware, OS>` |
| Reach | `<ssh user@host>`; `<vpn/tailnet address>` |
| Production | `<where; who may deploy; env file location>` |

**[Rule]** Production identifiers (env files, hostnames, SSH users) are listed in the local release-gate configuration, which blocks deploy commands against them that lack a named release approval. The dev/test host is deliberately **not** listed there.

---

## 1. Layering

**[Rule]** `<what new code must do>`
**[Fact]** Existing violations (do not copy, do not mass-refactor without a task): `<paths>`.

## 2. Naming and logging

- `<model/service/schema naming pattern>`
- **[Rule]** Modules that call external systems (payments, SMS, LLMs, third-party APIs) log failures with a module logger. Never log secrets, phone numbers, emails or message bodies.

## 3. Data access and migrations

**[Rule]** Schema changes go through the migration tool (`<alembic / prisma / ...>`). "Migrations ran automatically" may only be written when a migration command is part of the start-up path and was observed running.
**[Fact]** `<current state per repo>`

## 4. API conventions

**[Fact]** Validation-error status code: `<422 / 400>` (verify with a minimal request, do not assume). Create routes: check each decorator for 201 vs 200.
**[Fact]** Error helpers: `<where centralised, or "inline">`.
**[Fact]** Idempotency: `<same key + same payload → ?; same key + different payload → ?>`.

## 5. Conventions

1. **Secrets [Rule]:** real `.env` values are never committed (only `.env.example`). A history/secret scan `<has / has not>` been run.
2. **CORS [Rule]:** never `*`.
3. **Tests and external senders [Rule]:** test suites stub SMS/email/payment clients at import time so a test can never send anything real.
4. **Timestamps [Rule]:** store instants in UTC; keep business-local date/time as separate, clearly named fields. **[Fact]** `<what today's columns actually do>`.
5. **Feature flags [Rule]:** risky or new features ship default-off. State the code default, the compose/deploy default and the production value separately. **[Fact]** `<flags that are default-on today>`.

## 6. Domain safety rules

<!-- The irreversible, user-facing actions of THIS product: booking, payment, order state, sending a message, deleting data. One block per action. This is the section that reviewers check line by line (REVIEW.md pass 4). -->

**[Rule]** `<Action X>` is performed only on a bare, explicit confirmation of the current summary; questions, negations and messages carrying extra content never trigger it.
**[Rule]** The system says "`<done/confirmed>`" only when the downstream call returned that status; otherwise "received, not yet confirmed".
**[Rule]** Inside a deterministic flow the model never supplies field values; rules extract and validate.
**[Rule]** User-facing contact details, URLs and statuses come from configuration or trusted data, never from model text.
**[Rule]** Any change to these helpers needs negative-language and informational-message regression tests.

## 7. Verification rule

"Implemented" ≠ "verified". Record separately: implementation SHA, test evidence, deployed SHA/environment, verifier, date. Never mark a feature complete from file existence, a passing `/health`, or a historical report. Old reports are dated snapshots, not current status.

## 8. Doc hygiene

- Numbers that drift (file counts, versions, test counts): cite the command to recompute, or omit.
- When a claim is corrected, edit it in place and update "Last verified". Do not append override notes.
- Keep one authoritative copy of a rule; other files link here.
- A mistake made twice gets written into this file as a rule, not just fixed in the diff.
- Commits, PR titles and bodies, handoffs, ADRs, specs and code comments describe behaviour, rationale and verification. Authorship is the repository owner.

## 9. Delivery loop

Six stages, each owned by a **role**, not a headcount. One person can hold several roles; the artifact and the approval gate stay separate so the process keeps its shape as the team grows.

| Stage | Role | Artifact | Gate |
|---|---|---|---|
| Plan | Product owner | `intent/<slug>.md` (workspace root) | product owner accepts or closes it |
| Design | Product owner + engineer | `spec/<slug>.md` (workspace root) | product owner signs off; open questions resolved before Build |
| Build | Engineer, plan first | `plan.md` in the PR, code, tests | engineer approves the plan before code is written |
| Test | Engineer / CI | test run, eval evidence | CI green; eval pass rate where an eval suite exists |
| Deploy | Release approver | PR + `REVIEW.md` findings | Important-finding-free review, plus a named release approval for §6 / payment / migration changes |
| Maintain | On-call | incident note → new `intent/<slug>.md` | on-call triages before it re-enters Plan |

**[Rule]** A change to a live user-facing flow (anything in §6, payments, data deletion) starts with `intent/<slug>.md`, not straight into a build plan. A fix scoped to one file and one bug can start directly from a plan.
**[Rule]** `intent/` and `spec/` live at the workspace root, sibling to the repositories, because features routinely cross repos. Start from `intent/TEMPLATE.md` and `spec/TEMPLATE.md`.
**[Rule]** Product-owner sign-off is a real decision, recorded in the file itself (accepted / rejected / deferred, with reason) and committed in the same commit.
**[Rule]** Bug fixes: write the failing test, confirm it fails for the stated reason, commit it, then fix the code. Never edit the test to make it pass.
**[Rule]** Every production incident becomes a new `intent/<slug>.md` before it becomes a fix, even a one-line one.
**[Fact]** Enforcement:
- A local release gate blocks production deploy and migration commands without `RELEASE_APPROVAL`, and blocks force-pushes and pushes to `main`; changing an existing test file needs explicit agreement.
- `REVIEW.md` defines the PR review passes and the release gate; apply it manually in every review until an automated reviewer exists.
- Repo hygiene: before the first push and every release, the hygiene scan reports 0 authorship/assistant-origin wording and 0 committed assistant configuration; provider, dependency, licence, fixture and upstream references are reviewed and kept.
