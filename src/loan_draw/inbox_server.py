"""Entry point for `langgraph dev` / LangGraph server (langgraph.json). Builds the ledger and graph once, at load.

Kept apart from `inbox.py` so importing the adapter (tests, other code) opens no ledger file.
"""
from __future__ import annotations

from loan_draw import inbox
from loan_draw.graph import build
from loan_draw.ledger import Ledger, ledger_path
from loan_draw.llm import Gateway

graph = build(Gateway(), Ledger(ledger_path()), ask=inbox.ask, standalone=False)
