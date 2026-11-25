from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

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


def _fake_litellm(monkeypatch, called: list[str]) -> None:
    """Stands in for LiteLLM: every model answers, and `called` lists the models that were sent the prompt."""
    def completion(model, **kw):
        called.append(model)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"x": 3}'))])

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(completion=completion))


class ReadOnlyCassette(Cassette):
    def put(self, key, task, out):
        raise PermissionError("cassette file is read-only")


def test_a_recording_that_cannot_be_written_is_not_sent_to_a_fallback_model(tmp_path, monkeypatch):
    called: list[str] = []
    _fake_litellm(monkeypatch, called)
    monkeypatch.setenv("LLM_ALLOW_EXTERNAL", "1")
    gw = Gateway(model="primary", fallbacks=["external/model"],
                 cassette=ReadOnlyCassette(tmp_path / "c.jsonl", "record"))
    with pytest.raises(PermissionError):
        gw.json("t", [{"role": "user", "content": "hi"}], Out)
    assert called == ["primary"]


def test_a_recording_that_failed_to_write_is_not_answered_from_memory(tmp_path):
    rec = Cassette(tmp_path / "c.jsonl", "record")
    rec.path.mkdir()  # a directory where the file should be: opening it for append fails
    with pytest.raises(OSError):
        rec.put("k", "t", "out")
    assert rec.get("k") is None


def test_fallback_models_are_off_unless_external_calls_are_allowed(monkeypatch):
    monkeypatch.delenv("LLM_ALLOW_EXTERNAL", raising=False)
    with pytest.raises(ValueError, match="LLM_ALLOW_EXTERNAL"):
        Gateway(model="primary", fallbacks=["external/model"])
    monkeypatch.setenv("LLM_FALLBACKS", "external/model")
    with pytest.raises(ValueError, match="LLM_ALLOW_EXTERNAL"):
        Gateway(model="primary")


def test_record_mode_writes_outside_the_repository_by_default(tmp_path, monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repo)  # CI and the README run from the repository root
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LLM_CASSETTE", "record")
    monkeypatch.delenv("LLM_CASSETTE_PATH", raising=False)
    path = Gateway(model="none", fallbacks=[]).cassette.path.resolve()
    assert repo not in path.parents
