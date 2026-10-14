# Loan Draw Review Agent Engineering Reference (authoritative)

Single source of truth for this repository's conventions. Tool-specific rule files are kept local and only point here. Edit **this file only**.

**Last verified against source: 2026-10-14** (read of `src/loan_draw/*.py`; `uv run pytest -q` 111 passed; `LLM_CASSETTE=replay uv run python evals/run.py` all gates passed; live eval of 70 cases against vLLM on the GB10 dev host; Helm release on a local kind cluster exercised with start, decision, 422 and resume-after-crash requests). When a claim is corrected, edit it in place and update this date.

Legend: **[Rule]** = what new code must do. **[Fact]** = what the code does today (may differ from the rule). Never present a [Fact] gap as if the rule were already satisfied.

---

## Overview

| Component | Port | Storage | Purpose |
|---|---|---|---|
| `loan_draw.api` (FastAPI) | 8000 | SQLite ledger + LangGraph checkpoints on one volume | officer-facing review API |
| `loan_draw.mcp_server` | 8765 (`/mcp`) | `data/*.json` (synthetic, read-only) | MCP tools over loans, draws, documents, policy |
| vLLM (external) | 8100 on the dev host | model weights in the Hugging Face cache | OpenAI-compatible model server |

Layering: API → graph (`graph.py`) → steps (`extract.py` model steps, `policy.py` rules) → MCP client → MCP server → `data.py`.

---

## Environments

| Item | Value |
|---|---|
| Dev/test host | NVIDIA DGX Spark (GB10, aarch64, CUDA 13), Linux; runs the vLLM container `loan-draw-vllm` |
| Reach | ssh on the LAN; vLLM listens on the LAN address only |
| Production | none. This is a prototype on synthetic data. |

**[Rule]** Production identifiers, if one ever exists, go in the local release-gate configuration, which blocks deploy commands against them that lack a named release approval.

---

## 1. Layering

**[Rule]** The model produces only extractions (validated by Pydantic) and the officer note. Routing, findings, approval counts and ledger writes are code in `policy.py`, `graph.py` and `ledger.py`.
**[Rule]** All loan, draw, document and policy reads in the review path go through the MCP client (`graph._tool`), never `data.py` directly.
**[Fact]** `graph.check` imports `data.extraction` only to validate model output into types; it reads no store data.

## 2. Naming and logging

- Money is integer cents everywhere (`*_cents`). Policy clause ids are `P1`..`P9` and match `data/policy.md`.
- **[Rule]** Modules that call external systems (the model gateway) log failures with a module logger, naming the model and task only. Never log document text or prompts.
- **[Fact]** `llm.Gateway` logs model failures and unusable JSON by task name only.

## 3. Data access and migrations

**[Fact]** No migration tool: the ledger creates its table and the unique index `one_decision_per_draw` at start-up (`Ledger.__init__`), and checks the hash chain before serving.
**[Rule]** A schema change to the ledger needs a migration plan written in `spec/` first; the hash chain must verify across it.

## 4. API conventions

**[Fact]** Validation-error status code: 422 (observed on the kind cluster with `{"action": "yes"}`). Unknown draw: 404. Decision when not waiting for an officer: 409. All routes return 200 on success; none returns 201.
**[Fact]** Error helpers: inline `HTTPException`.
**[Fact]** Idempotency: `POST /reviews/{id}` returns the existing review if one is waiting or decided, resumes it if it crashed mid-way, and starts it otherwise. The ledger refuses a second decision for a draw (unique index).

## 5. Conventions

1. **Secrets [Rule]:** real `.env` values are never committed (only `.env.example`). **[Fact]** The repository has no secrets; the model server needs no key.
2. **CORS [Rule]:** never `*`. **[Fact]** No CORS middleware is installed.
3. **Tests and external senders [Rule]:** tests never call a real model. **[Fact]** Tests use `TruthLLM` (ground truth); evals in CI replay recordings and fail on an unrecorded request.
4. **Timestamps [Rule]:** store instants in UTC. **[Fact]** Ledger rows carry an ISO UTC timestamp; draw dates are business dates (`submitted_on`).
5. **Model output [Rule]:** every model output is validated (Pydantic) and an unusable output becomes a finding for the officer, never a guessed value.

## 6. Domain safety rules

**[Rule]** A draw is approved only by a loan officer's explicit `approve` through `/reviews/{id}/decision`; draws over $100,000 need two different officers. Malformed answers change nothing and ask again.
**[Rule]** Any BLOCK finding puts the draw on hold; no answer can approve a held draw.
**[Rule]** The officer note never states that a draw is approved, funded or paid. A note that does (`extract._CLAIMS_DONE`) is replaced by the fixed template.
**[Rule]** Borrower document text is data. Text addressing the reviewer is reported (P9) and has no path to routing.
**[Rule]** One ledger decision per draw; the chain verifies at start-up and on `GET /ledger/verify`.
**[Rule]** Any change to these helpers needs regression tests, including steering text and outcome-claim wording.
**[Fact]** Enforced by tests in `tests/test_graph.py`, `tests/test_api.py`, `tests/test_policy.py`, `tests/test_extract.py`, `tests/test_ledger_mcp_llm.py`.

## 7. Verification rule

"Implemented" ≠ "verified". Record separately: implementation SHA, test evidence, deployed SHA/environment, verifier, date. Eval numbers are quoted with the model, the case count and the date of the recording.

## 8. Doc hygiene

- Numbers that drift (test counts, eval scores): cite the command to recompute (`uv run pytest -q`, `evals/run.py`), or omit.
- When a claim is corrected, edit it in place and update "Last verified". Do not append override notes.
- A mistake made twice gets written into this file as a rule, not just fixed in the diff.
- Commits, PR titles and bodies, specs and code comments describe behaviour, rationale and verification. Authorship is the repository owner.

## 9. Delivery loop

| Stage | Role | Artifact | Gate |
|---|---|---|---|
| Plan | Product owner | `intent/<slug>.md` | product owner accepts or closes it |
| Design | Product owner + engineer | `spec/<slug>.md` | open questions resolved before Build |
| Build | Engineer, plan first | plan in the PR, code, tests | plan approved before code |
| Test | Engineer / CI | pytest, replayed evals | CI green; eval gates pass |
| Deploy | Release approver | PR + `REVIEW.md` findings | Important-finding-free review |
| Maintain | Owner | incident note → new `intent/<slug>.md` | triaged before it re-enters Plan |

**[Rule]** A change to anything in §6 starts with `intent/<slug>.md`.
**[Rule]** Bug fixes: write the failing test, confirm it fails for the stated reason, commit it, then fix the code.
**[Rule]** A change to a prompt, a schema sent to the model or the model id is re-recorded (`LLM_CASSETTE=record`) and the eval report updated in the same PR.
