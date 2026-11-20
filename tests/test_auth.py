from __future__ import annotations

import pytest
from conftest import TruthLLM, case
from fastapi.testclient import TestClient

from loan_draw.api import create_app
from loan_draw.ledger import Ledger

KEYS = {"officer-a": "officer-a-key-0123456789", "officer-b": "officer-b-key-0123456789",
        "review-bot": "review-bot-key-0123456789"}
CONFIG = ("officer-a:officer:officer-a-key-0123456789,officer-b:officer:officer-b-key-0123456789,"
          "review-bot:agent:review-bot-key-0123456789")


def as_(name: str) -> dict:
    return {"Authorization": f"Bearer {KEYS[name]}"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LOAN_DRAW_API_KEYS", CONFIG)
    with TestClient(create_app(llm=TruthLLM(), ledger=Ledger())) as c:
        yield c


def waiting(c: TestClient, scenario: str) -> str:
    draw_id = case(scenario)["draw_id"]
    assert c.post(f"/reviews/{draw_id}", headers=as_("review-bot")).json()["status"] == "waiting_for_officer"
    return draw_id


def test_anonymous_or_unknown_key_cannot_decide(client):
    draw_id = waiting(client, "clean")
    for headers in ({}, {"Authorization": "Bearer not-a-key"}, {"Authorization": f"Basic {KEYS['officer-a']}"}):
        for action in ("approve", "reject"):
            r = client.post(f"/reviews/{draw_id}/decision", headers=headers,
                            json={"officer": "officer-a", "action": action})
            assert r.status_code == 401
    assert client.get(f"/reviews/{draw_id}", headers=as_("officer-a")).json()["status"] == "waiting_for_officer"
    assert client.get("/ledger/verify", headers=as_("officer-a")).json()["rows"] == 0


def test_reading_and_starting_reviews_need_a_key(client):
    draw_id = case("clean")["draw_id"]
    assert client.post(f"/reviews/{draw_id}").status_code == 401
    assert client.get(f"/reviews/{draw_id}").status_code == 401
    assert client.get("/ledger/verify").status_code == 401
    assert client.get("/health").status_code == 200


def test_the_approver_is_the_key_holder_not_the_name_in_the_body(client):
    draw_id = waiting(client, "clean")
    r = client.post(f"/reviews/{draw_id}/decision", headers=as_("officer-a"),
                    json={"officer": "officer-z", "action": "approve"}).json()
    assert r["status"] == "decided" and r["outcome"] == "approved"
    assert r["detail"]["approvals"] == ["officer-a"]


def test_one_officer_cannot_be_both_approvers_by_changing_the_body(client):
    draw_id = waiting(client, "two_person")
    for spoofed in ("officer-a", "officer-b", "officer-c"):
        r = client.post(f"/reviews/{draw_id}/decision", headers=as_("officer-a"),
                        json={"officer": spoofed, "action": "approve"}).json()
        assert r["status"] == "waiting_for_officer" and r["approved_by"] == ["officer-a"]
    r = client.post(f"/reviews/{draw_id}/decision", headers=as_("officer-b"), json={"action": "approve"}).json()
    assert r["outcome"] == "approved" and r["detail"]["approvals"] == ["officer-a", "officer-b"]


def test_the_review_agent_can_start_and_read_but_never_decide(client):
    draw_id = waiting(client, "clean")
    assert client.get(f"/reviews/{draw_id}", headers=as_("review-bot")).status_code == 200
    for action in ("approve", "reject"):
        r = client.post(f"/reviews/{draw_id}/decision", headers=as_("review-bot"),
                        json={"officer": "officer-a", "action": action})
        assert r.status_code == 403
    assert client.get(f"/reviews/{draw_id}", headers=as_("officer-a")).json()["status"] == "waiting_for_officer"


def test_an_officer_can_reject(client):
    draw_id = waiting(client, "clean")
    r = client.post(f"/reviews/{draw_id}/decision", headers=as_("officer-b"), json={"action": "reject"}).json()
    assert r["outcome"] == "rejected" and r["detail"]["approvals"] == ["officer-b"]


def test_no_keys_configured_means_nobody_can_decide(monkeypatch):
    monkeypatch.delenv("LOAN_DRAW_API_KEYS", raising=False)
    draw_id = case("clean")["draw_id"]
    with TestClient(create_app(llm=TruthLLM(), ledger=Ledger())) as c:
        assert c.post(f"/reviews/{draw_id}").status_code == 401
        assert c.post(f"/reviews/{draw_id}/decision", json={"officer": "officer-a", "action": "approve"}
                      ).status_code == 401


@pytest.mark.parametrize("bad", [
    "officer-a:officer",                                 # no key
    "officer-a:admin:officer-a-key-0123456789",          # unknown role
    ":officer:officer-a-key-0123456789",                 # no name
    "officer-a:officer:short",                           # key too short to be a secret
    "officer-a:officer:same-key-0123456789,officer-b:officer:same-key-0123456789",  # one key, two people
])
def test_a_malformed_key_list_stops_start_up(monkeypatch, bad):
    monkeypatch.setenv("LOAN_DRAW_API_KEYS", bad)
    with pytest.raises(ValueError):
        create_app(llm=TruthLLM(), ledger=Ledger())
