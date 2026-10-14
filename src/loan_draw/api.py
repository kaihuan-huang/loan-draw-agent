"""HTTP API for loan officers.

    POST /reviews/{draw_id}            start a review (idempotent: an existing review is returned, not restarted)
    GET  /reviews/{draw_id}            where the review is: waiting for an officer, or its recorded outcome
    POST /reviews/{draw_id}/decision   an officer's answer {"officer": "...", "action": "approve" | "reject"}
    GET  /ledger/verify                walk the hash chain
    GET  /health

    uv run uvicorn loan_draw.api:app --port 8000
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from langgraph.types import Command
from pydantic import BaseModel

from loan_draw import data, telemetry
from loan_draw.graph import build
from loan_draw.ledger import Ledger
from loan_draw.llm import Gateway


class Answer(BaseModel):
    officer: str
    action: Literal["approve", "reject"]


def _view(draw_id: str, snapshot, ledger: Ledger) -> dict:
    if (d := ledger.decision(draw_id)) is not None:
        return {"draw_id": draw_id, "status": "decided", "outcome": d["action"], "detail": d["detail"]}
    pending = [i.value for t in snapshot.tasks for i in t.interrupts]
    if pending:
        return {"draw_id": draw_id, "status": "waiting_for_officer", **pending[0]}
    return {"draw_id": draw_id, "status": "running" if snapshot.next else "not_started"}


def create_app(llm=None, ledger: Ledger | None = None, checkpoint_db: str | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        telemetry.setup()
        app.state.ledger = ledger or Ledger(os.environ.get("LEDGER_DB", ":memory:"))
        db = checkpoint_db or os.environ.get("CHECKPOINT_DB")
        if db:
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
            async with AsyncSqliteSaver.from_conn_string(db) as saver:
                app.state.graph = build(llm or Gateway(), app.state.ledger, saver)
                yield
        else:
            app.state.graph = build(llm or Gateway(), app.state.ledger)
            yield

    app = FastAPI(title="Loan Draw Review Agent", lifespan=lifespan)

    def cfg(draw_id: str) -> dict:
        if draw_id not in data.draw_ids():
            raise HTTPException(404, f"no draw {draw_id}")
        return {"configurable": {"thread_id": draw_id}}

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.post("/reviews/{draw_id}")
    async def start(draw_id: str):
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
    async def status(draw_id: str):
        return _view(draw_id, await app.state.graph.aget_state(cfg(draw_id)), app.state.ledger)

    @app.post("/reviews/{draw_id}/decision")
    async def decide(draw_id: str, a: Answer):
        c = cfg(draw_id)
        g = app.state.graph
        view = _view(draw_id, await g.aget_state(c), app.state.ledger)
        if view["status"] != "waiting_for_officer":
            raise HTTPException(409, f"draw {draw_id} is not waiting for an officer ({view['status']})")
        await g.ainvoke(Command(resume=a.model_dump()), c)
        return _view(draw_id, await g.aget_state(c), app.state.ledger)

    @app.get("/ledger/verify")
    async def verify():
        return {"rows": app.state.ledger.verify(), "chain": "intact"}

    return app


app = create_app()
