from __future__ import annotations

import sqlite3

import pytest
from conftest import case
from mcp import Client
from pydantic import BaseModel

from loan_draw.ledger import Ledger, TamperedLedger
from loan_draw.llm import Cassette, CassetteMiss, Gateway, _strip_fence
from loan_draw.mcp_server import clauses, server


def test_ledger_chain_and_one_decision_per_draw(tmp_path):
    path = tmp_path / "l.db"
    led = Ledger(path)
    led.append("D-1", "approved", {"a": 1})
    led.append("D-2", "on_hold", {})
    assert led.verify() == 2
    with pytest.raises(sqlite3.IntegrityError):
        led.append("D-1", "approved", {"a": 1})
    db = sqlite3.connect(path)
    db.execute("update ledger set body = replace(body, 'on_hold', 'approved') where draw_id = 'D-2'")
    db.commit()
    with pytest.raises(TamperedLedger):
        Ledger(path)


@pytest.mark.asyncio
async def test_mcp_tools_are_read_only_and_serve_the_store():
    async with Client(server) as c:
        names = {t.name for t in (await c.list_tools()).tools}
        assert names == {"get_loan", "get_draw", "get_document", "get_policy_clauses", "list_draws"}
        r = await c.call_tool("get_draw", {"draw_id": case("clean")["draw_id"]})
        assert not r.is_error
        r = await c.call_tool("get_loan", {"loan_id": "L-0"})
        assert r.is_error


def test_policy_clauses_parse():
    c = clauses()
    assert list(c) == [f"P{i}" for i in range(1, 10)]
    assert c["P7"].startswith("Repeat funding.")


class Out(BaseModel):
    x: int


def test_replay_answers_from_the_recording_and_fails_on_a_new_request(tmp_path):
    path = tmp_path / "c.jsonl"
    msgs = [{"role": "user", "content": "hi"}]
    rec = Cassette(path, "record")
    rec.put(Cassette.key("t", msgs, Out.model_json_schema()), "t", '```json\n{"x": 3}\n```')
    gw = Gateway(model="none", fallbacks=[], cassette=Cassette(path, "replay"))
    assert gw.json("t", msgs, Out) == {"x": 3}
    with pytest.raises(CassetteMiss):
        gw.json("t", [{"role": "user", "content": "changed prompt"}], Out)


def test_unusable_json_is_none_not_a_guess(tmp_path):
    path = tmp_path / "c.jsonl"
    msgs = [{"role": "user", "content": "hi"}]
    Cassette(path, "record").put(Cassette.key("t", msgs, Out.model_json_schema()), "t", "the total is three")
    assert Gateway(model="none", fallbacks=[], cassette=Cassette(path, "replay")).json("t", msgs, Out) is None


def test_strip_fence():
    assert _strip_fence('```json\n{"a":1}\n```') == '{"a":1}'
    assert _strip_fence('{"a":1}') == '{"a":1}'
