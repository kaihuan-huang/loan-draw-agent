"""HTTP API for loan officers.

    POST /reviews/{draw_id}            start a review (idempotent: an existing review is returned, not restarted)
    GET  /reviews/{draw_id}            where the review is: waiting for an officer, or its recorded outcome
    POST /reviews/{draw_id}/decision   an officer's answer {"action": "approve" | "reject"}
    GET  /ledger/verify                walk the hash chain
    GET  /health                       the only route without an API key

Every other route needs `Authorization: Bearer <key>` (see `loan_draw.auth`). The approver is the key holder;
only `officer` keys can decide.

    uv run uvicorn loan_draw.api:app --port 8000
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from langgraph.types import Command
from pydantic import BaseModel

from loan_draw import data, telemetry
from loan_draw.auth import Keys, Principal
from loan_draw.graph import build
from loan_draw.ledger import Ledger, ledger_path
from loan_draw.llm import Gateway


class Answer(BaseModel):
    action: Literal["approve", "reject"]


_bearer = HTTPBearer(auto_error=False)


def _caller(request: Request, cred: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]) -> Principal:
    if cred is None or (who := request.app.state.keys.lookup(cred.credentials)) is None:
        raise HTTPException(401, "a valid API key is required", headers={"WWW-Authenticate": "Bearer"})
    return who


def _officer(who: Annotated[Principal, Depends(_caller)]) -> Principal:
    if who.role != "officer":
        raise HTTPException(403, "only a loan officer can approve or reject a draw")
    return who


Caller = Annotated[Principal, Depends(_caller)]
Officer = Annotated[Principal, Depends(_officer)]


def _view(draw_id: str, snapshot, ledger: Ledger) -> dict:
    if (d := ledger.decision(draw_id)) is not None:
        return {"draw_id": draw_id, "status": "decided", "outcome": d["action"], "detail": d["detail"]}
    pending = [i.value for t in snapshot.tasks for i in t.interrupts]
    if pending:
        return {"draw_id": draw_id, "status": "waiting_for_officer", **pending[0]}
    return {"draw_id": draw_id, "status": "running" if snapshot.next else "not_started"}


def create_app(llm=None, ledger: Ledger | None = None, checkpoint_db: str | None = None,
               api_keys: str | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        telemetry.setup()
        app.state.ledger = ledger or Ledger(ledger_path())
        db = checkpoint_db or os.environ.get("CHECKPOINT_DB")
        if db:
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
            async with AsyncSqliteSaver.from_conn_string(db) as saver:
                app.state.graph = build(llm or Gateway(), app.state.ledger, saver)
                yield
        else:
            app.state.graph = build(llm or Gateway(), app.state.ledger)
            yield

    docs = os.environ.get("LOAN_DRAW_DOCS", "").strip().lower() in ("1", "true", "yes")
    app = FastAPI(title="Loan Draw Review Agent", lifespan=lifespan,
                  docs_url="/docs" if docs else None, redoc_url="/redoc" if docs else None,
                  openapi_url="/openapi.json" if docs else None)
    app.state.keys = Keys(os.environ.get("LOAN_DRAW_API_KEYS", "") if api_keys is None else api_keys)

    def cfg(draw_id: str) -> dict:
        if draw_id not in data.draw_ids():
            raise HTTPException(404, f"no draw {draw_id}")
        return {"configurable": {"thread_id": draw_id}}

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.post("/reviews/{draw_id}")
    async def start(draw_id: str, _: Caller):
        c = cfg(draw_id)
        g = app.state.graph
        snap = await g.aget_state(c)
        view = _view(draw_id, snap, app.state.ledger)
        if view["status"] in ("decided", "waiting_for_officer"):
            return view
        # never started -> start; crashed mid-way (checkpoint with a next step, no question pending) -> resume there
        await g.ainvoke(None if snap.next else {"draw_id": draw_id}, c)
        return _view(draw_id, await g.aget_state(c), app.state.ledger)

    @app.get("/reviews/{draw_id}")
    async def status(draw_id: str, _: Caller):
        return _view(draw_id, await app.state.graph.aget_state(cfg(draw_id)), app.state.ledger)

    @app.post("/reviews/{draw_id}/decision")
    async def decide(draw_id: str, a: Answer, who: Officer):
        c = cfg(draw_id)
        g = app.state.graph
        view = _view(draw_id, await g.aget_state(c), app.state.ledger)
        if view["status"] != "waiting_for_officer":
            raise HTTPException(409, f"draw {draw_id} is not waiting for an officer ({view['status']})")
        await g.ainvoke(Command(resume={"officer": who.name, "action": a.action}), c)
        return _view(draw_id, await g.aget_state(c), app.state.ledger)

    @app.get("/ledger/verify")
    async def verify(_: Caller):
        return {"rows": app.state.ledger.verify(), "chain": "intact"}

    return app


app = create_app()
