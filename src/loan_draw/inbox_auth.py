"""Key check for the LangGraph server that serves the Agent Inbox entry point (registered in langgraph.json).

Uses the same keys as the HTTP API (`LOAN_DRAW_API_KEYS`, see `loan_draw.auth`). A request needs a known key, sent as
`Authorization: Bearer <key>` or as the `x-api-key` header, which is where the Agent Inbox sends the key typed into its
settings. The key holder becomes the run's user; `loan_draw.inbox.ask` counts an answer only for an `officer` key.
No keys configured means every request is refused.
"""
from __future__ import annotations

import os

from langgraph_sdk import Auth

from loan_draw.auth import Keys

auth = Auth()
_keys: Keys | None = None


def reset() -> None:
    """Forget the loaded keys (tests change LOAN_DRAW_API_KEYS)."""
    global _keys
    _keys = None


def _load() -> Keys:
    global _keys
    if _keys is None:
        _keys = Keys(os.environ.get("LOAN_DRAW_API_KEYS", ""))
    return _keys


def _credential(authorization: str | None, headers: dict) -> str:
    if authorization:
        scheme, _, token = authorization.partition(" ")
        return token.strip() if scheme.lower() == "bearer" else ""
    raw = headers.get(b"x-api-key") or headers.get("x-api-key") or b""
    return (raw.decode() if isinstance(raw, bytes) else str(raw)).strip()


@auth.authenticate
async def authenticate(authorization: str | None, headers: dict) -> Auth.types.MinimalUserDict:
    key = _credential(authorization, headers)
    who = _load().lookup(key) if key else None
    if who is None:
        raise Auth.exceptions.HTTPException(status_code=401, detail="a valid API key is required")
    return {"identity": who.name, "role": who.role, "permissions": [who.role]}
