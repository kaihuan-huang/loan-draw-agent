"""Start reviews on a running LangGraph server so draws waiting for an officer show up in the Agent Inbox.

    uv run python scripts/inbox_start.py                      # every draw
    uv run python scripts/inbox_start.py D-5001 D-5003        # some draws
    LANGGRAPH_URL=http://127.0.0.1:2024 (default)

One thread per draw (a stable UUID derived from the draw id), so running this twice does not start a review twice;
a review that stopped mid-way is resumed, as `POST /reviews/{id}` does. A draw that left the inbox with no decision
(the inbox's "Mark as Resolved" button ends a thread without an answer, and cannot be turned off) is reviewed again:
run this after anyone uses that button, or on a schedule.
Held draws are recorded on hold without asking anyone and never appear in the inbox.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid

from langgraph_sdk import get_client

from loan_draw import data

GRAPH = "loan_draw"


def thread_id(draw_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"loan-draw/{draw_id}"))


async def main(draw_ids: list[str]) -> None:
    client = get_client(url=os.environ.get("LANGGRAPH_URL", "http://127.0.0.1:2024"))
    for draw_id in draw_ids:
        tid = thread_id(draw_id)
        await client.threads.create(thread_id=tid, metadata={"draw_id": draw_id}, if_exists="do_nothing")
        state = await client.threads.get_state(tid)
        waiting = any(t.get("interrupts") for t in state.get("tasks", []))
        if waiting or (state.get("values", {}).get("outcome")):
            print(f"{draw_id}: {'waiting for an officer' if waiting else state['values']['outcome']} (already started)")
            continue
        # never started -> start; stopped mid-way (a next step, no question pending) -> resume there, like the API does;
        # ended with no outcome (the inbox's "Mark as Resolved" ends a thread without an answer) -> review again
        reopened = bool(state.get("values")) and not state.get("next")
        await client.runs.wait(tid, GRAPH, input=None if state.get("next") else {"draw_id": draw_id})
        state = await client.threads.get_state(tid)
        status = "waiting for an officer" if state.get("next") else state["values"].get("outcome")
        print(f"{draw_id}: {status}" + (" (reopened: it had left the inbox without a decision)" if reopened else ""))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or data.draw_ids()))
