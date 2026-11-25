from __future__ import annotations

import pytest
from conftest import TruthLLM
from fastapi.testclient import TestClient

from loan_draw.api import create_app
from loan_draw.auth import Keys, Principal
from loan_draw.ledger import Ledger

DOC_PATHS = ("/docs", "/redoc", "/openapi.json")


@pytest.mark.parametrize("bad", [
    "officer-a:officer:key-one-0123456789,officer-a:officer:key-two-0123456789",   # same name on two keys
    "officer-a:officer:key-one-0123456789,Officer-A:officer:key-two-0123456789",   # same name, different case
    "officer-a:officer:key-one-0123456789,  OFFICER-A :agent:key-two-0123456789",  # case and padding, other role
])
def test_one_name_on_two_keys_stops_start_up(bad):
    with pytest.raises(ValueError):
        Keys(bad)


def test_names_are_case_insensitive():
    who = Keys("Officer-A:officer:officer-a-key-0123456789").lookup("officer-a-key-0123456789")
    assert who == Principal("officer-a", "officer")


def test_a_colon_inside_the_key_is_part_of_the_key():
    keys = Keys("officer-a:officer:abc:def:ghi:0123456789")
    assert keys.lookup("abc:def:ghi:0123456789") == Principal("officer-a", "officer")
    assert keys.lookup("abc") is None
    assert keys.lookup("def:ghi:0123456789") is None


def _client() -> TestClient:
    return TestClient(create_app(llm=TruthLLM(), ledger=Ledger(), api_keys="officer-a:officer:officer-a-key-0123456789"))


def test_interactive_docs_are_off_by_default(monkeypatch):
    monkeypatch.delenv("LOAN_DRAW_DOCS", raising=False)
    with _client() as c:
        for path in DOC_PATHS:
            assert c.get(path).status_code == 404


def test_interactive_docs_need_an_explicit_flag(monkeypatch):
    monkeypatch.setenv("LOAN_DRAW_DOCS", "1")
    with _client() as c:
        for path in DOC_PATHS:
            assert c.get(path).status_code == 200
