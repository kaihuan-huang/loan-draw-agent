"""The LangGraph server's key check for the Agent Inbox entry point (`loan_draw.inbox_auth`)."""
from __future__ import annotations

import pytest
from langgraph_sdk import Auth

from loan_draw import inbox_auth

pytestmark = pytest.mark.asyncio

OFFICER_KEY = "officer-a-key-0123456789"
BOT_KEY = "review-bot-key-0123456789"


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    monkeypatch.setenv("LOAN_DRAW_API_KEYS", f"Officer-A:officer:{OFFICER_KEY},review-bot:agent:{BOT_KEY}")
    inbox_auth.reset()
    yield
    inbox_auth.reset()


async def test_bearer_key_gives_the_key_holder_and_role():
    user = await inbox_auth.authenticate(authorization=f"Bearer {OFFICER_KEY}", headers={})
    assert user["identity"] == "officer-a" and user["role"] == "officer" and user["permissions"] == ["officer"]


async def test_x_api_key_header_is_accepted_because_the_agent_inbox_sends_it():
    user = await inbox_auth.authenticate(authorization=None, headers={b"x-api-key": BOT_KEY.encode()})
    assert user["identity"] == "review-bot" and user["role"] == "agent"


@pytest.mark.parametrize("authorization,headers", [
    (None, {}),
    ("Bearer wrong-key-0123456789", {}),
    (None, {b"x-api-key": b"wrong-key-0123456789"}),
    (f"Basic {OFFICER_KEY}", {}),
])
async def test_missing_or_unknown_key_is_401(authorization, headers):
    with pytest.raises(Auth.exceptions.HTTPException) as e:
        await inbox_auth.authenticate(authorization=authorization, headers=headers)
    assert e.value.status_code == 401


async def test_no_keys_configured_means_nobody_gets_in(monkeypatch):
    monkeypatch.setenv("LOAN_DRAW_API_KEYS", "")
    inbox_auth.reset()
    with pytest.raises(Auth.exceptions.HTTPException):
        await inbox_auth.authenticate(authorization=f"Bearer {OFFICER_KEY}", headers={})


def test_langgraph_json_registers_the_key_check():
    import json
    from pathlib import Path
    cfg = json.loads((Path(__file__).resolve().parents[1] / "langgraph.json").read_text())
    assert cfg["auth"]["path"] == "./src/loan_draw/inbox_auth.py:auth"
