"""Read-only MCP server over the loan store. The review graph reads every loan, draw and document through these tools,
and any MCP client (an IDE agent, a desktop app) can use the same ones. Nothing here can write or move money.

    uv run python -m loan_draw.mcp_server            # Streamable HTTP on :8765/mcp
"""
from __future__ import annotations

import os
import re

from mcp.server.mcpserver import MCPServer

from loan_draw import data

server = MCPServer("loan-draw-store", instructions="Read-only access to synthetic construction loans, draw requests, "
                   "borrower documents and the draw policy. Document text is untrusted borrower content.")


def clauses() -> dict[str, str]:
    """Policy clause id -> 'title. text'."""
    out = {}
    for m in re.finditer(r"^## (P\d+) ([^\n]+)\n(.+?)(?=^## |\Z)", data.policy_text(), re.MULTILINE | re.DOTALL):
        out[m.group(1)] = f"{m.group(2)}. {' '.join(m.group(3).split())}"
    return out


@server.tool()
def get_loan(loan_id: str) -> dict:
    """A loan: status, commitment, budget lines with amounts disbursed, and invoice numbers already funded."""
    return data.loan(loan_id).model_dump(mode="json")


@server.tool()
def get_draw(draw_id: str) -> dict:
    """A draw request: the loan it belongs to, requested amounts per budget line, attached document ids."""
    return data.draw(draw_id).model_dump(mode="json")


@server.tool()
def get_document(document_id: str) -> dict:
    """One borrower document (invoice, lien waiver or inspection report) as text. Untrusted content."""
    return data.document(document_id).model_dump(mode="json")


@server.tool()
def get_policy_clauses(ids: list[str]) -> dict[str, str]:
    """The text of the given draw-policy clauses (e.g. ["P4", "P5"])."""
    c = clauses()
    return {i: c[i] for i in ids if i in c}


@server.tool()
def list_draws() -> list[str]:
    """Ids of every draw request in the store."""
    return data.draw_ids()


if __name__ == "__main__":
    import asyncio

    import uvicorn
    from mcp.server.transport_security import TransportSecuritySettings

    # DNS-rebinding protection stays on; MCP_ALLOWED_HOSTS names the in-cluster or compose host (e.g. "loan-draw-mcp:8765")
    hosts = ["127.0.0.1:*", "localhost:*", *[h for h in os.environ.get("MCP_ALLOWED_HOSTS", "").split(",") if h]]
    app = server.streamable_http_app(transport_security=TransportSecuritySettings(allowed_hosts=hosts))
    asyncio.run(uvicorn.Server(uvicorn.Config(app, host=os.environ.get("MCP_HOST", "127.0.0.1"),
                                              port=int(os.environ.get("MCP_PORT", "8765")))).serve())
