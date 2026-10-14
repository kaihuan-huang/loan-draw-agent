"""The review workflow as a LangGraph state graph.

    load (MCP) -> extract (model) -> check (rules) -> explain (model) -> hold ......................-> record
                                                                     \\-> officer review (interrupt) -> record

The model reads documents and writes the note; rules decide the route. A draw on hold is recorded and stops. Every
other draw pauses at `interrupt()` until a loan officer answers; draws over the two-person threshold need a second,
different officer. The thread id is the draw id, so a review survives restarts with a persistent checkpointer.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from mcp import Client

from loan_draw import extract as X
from loan_draw import policy
from loan_draw.ledger import Ledger
from loan_draw.llm import LLM
from loan_draw.models import Document, DrawRequest, Finding, Loan
from loan_draw.telemetry import span


class State(TypedDict, total=False):
    draw_id: str
    loan: dict
    draw: dict
    documents: dict[str, dict]
    extractions: dict[str, dict | None]
    findings: list[dict]
    route: str
    note: str
    note_from_template: bool
    approvals: list[str]
    outcome: str


def _mcp_target():
    from loan_draw.mcp_server import server
    return os.environ.get("MCP_URL") or server


async def _tool(client: Client, name: str, args: dict) -> Any:
    r = await client.call_tool(name, args)
    if r.is_error:
        raise LookupError(f"{name}({args}) failed: {r.content[0].text if r.content else ''}")
    if r.structured_content is not None:
        sc = r.structured_content
        return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
    return json.loads(r.content[0].text)


def build(llm: LLM, ledger: Ledger, checkpointer=None):
    async def load(s: State) -> State:
        with span("load", draw_id=s["draw_id"]):
            async with Client(_mcp_target()) as c:
                d = await _tool(c, "get_draw", {"draw_id": s["draw_id"]})
                loan = await _tool(c, "get_loan", {"loan_id": d["loan_id"]})
                docs = {i: await _tool(c, "get_document", {"document_id": i}) for i in d["document_ids"]}
        return {"draw": d, "loan": loan, "documents": docs}

    async def extract(s: State) -> State:
        async def one(doc: dict):
            with span("extract", document=doc["id"], kind=doc["kind"]):
                e = await asyncio.to_thread(X.extract, llm, Document.model_validate(doc), sorted(s["loan"]["lines"]))
            return doc["id"], (e.model_dump(mode="json") if e else None)
        pairs = await asyncio.gather(*(one(d) for d in s["documents"].values()))
        return {"extractions": dict(pairs)}

    def check(s: State) -> State:
        from loan_draw import data
        ex = {i: (data.extraction(v) if v else None) for i, v in s["extractions"].items()}
        with span("check"):
            fs = policy.check(Loan.model_validate(s["loan"]), DrawRequest.model_validate(s["draw"]),
                              {i: d["text"] for i, d in s["documents"].items()}, ex)
        return {"findings": [f.model_dump(mode="json") for f in fs], "route": policy.route(fs)}

    async def explain(s: State) -> State:
        fs = [Finding.model_validate(f) for f in s["findings"]]
        async with Client(_mcp_target()) as c:
            clauses = await _tool(c, "get_policy_clauses", {"ids": sorted({f.clause for f in fs})})
        with span("explain"):
            note, tpl = await asyncio.to_thread(X.explain, llm, fs, s["route"], clauses)
        return {"note": note, "note_from_template": tpl}

    def officer_review(s: State) -> Command:
        need = policy.approvers_needed(DrawRequest.model_validate(s["draw"]))
        approvals = list(s.get("approvals", []))
        answer = interrupt({"draw_id": s["draw_id"], "route": s["route"], "findings": s["findings"],
                            "note": s["note"], "approvers_needed": need, "approved_by": approvals})
        officer = str(answer.get("officer", "")).strip()
        action = answer.get("action")
        if not officer or action not in ("approve", "reject"):
            return Command(goto="officer_review")  # malformed answer: ask again, change nothing
        if action == "reject":
            return Command(goto="record", update={"outcome": "rejected", "approvals": approvals + [officer]})
        if officer not in approvals:
            approvals.append(officer)
        if len(approvals) >= need:
            return Command(goto="record", update={"outcome": "approved", "approvals": approvals})
        return Command(goto="officer_review", update={"approvals": approvals})

    def record(s: State) -> State:
        outcome = s.get("outcome") or ("on_hold" if s["route"] == "hold" else "unknown")
        if ledger.decision(s["draw_id"]) is None:
            ledger.append(s["draw_id"], outcome, {"findings": [f["code"] for f in s["findings"]],
                                                   "approvals": s.get("approvals", []), "route": s["route"]})
        return {"outcome": outcome}

    g = StateGraph(State)
    for name, fn in [("load", load), ("extract", extract), ("check", check), ("explain", explain),
                     ("officer_review", officer_review), ("record", record)]:
        g.add_node(name, fn)
    g.add_edge(START, "load")
    g.add_edge("load", "extract")
    g.add_edge("extract", "check")
    g.add_edge("check", "explain")
    g.add_conditional_edges("explain", lambda s: "record" if s["route"] == "hold" else "officer_review",
                            ["record", "officer_review"])
    g.add_edge("record", END)
    return g.compile(checkpointer=checkpointer or InMemorySaver())
