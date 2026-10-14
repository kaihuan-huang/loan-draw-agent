from __future__ import annotations

from conftest import TruthLLM, case
from fastapi.testclient import TestClient

from loan_draw.api import create_app
from loan_draw.ledger import Ledger


def client(tmp_path=None):
    db = str(tmp_path / "cp.db") if tmp_path else None
    return TestClient(create_app(llm=TruthLLM(), ledger=Ledger(), checkpoint_db=db))


def test_review_flow_and_idempotent_start(tmp_path):
    draw_id = case("clean")["draw_id"]
    with client(tmp_path) as c:
        r = c.post(f"/reviews/{draw_id}").json()
        assert r["status"] == "waiting_for_officer" and r["approvers_needed"] == 1
        assert c.post(f"/reviews/{draw_id}").json()["status"] == "waiting_for_officer"  # not restarted
        r = c.post(f"/reviews/{draw_id}/decision", json={"officer": "officer-a", "action": "approve"}).json()
        assert r == {"draw_id": draw_id, "status": "decided", "outcome": "approved",
                     "detail": {"findings": [], "approvals": ["officer-a"], "route": "officer_review"}}
        assert c.post(f"/reviews/{draw_id}/decision",
                      json={"officer": "officer-b", "action": "approve"}).status_code == 409
        assert c.get("/ledger/verify").json() == {"rows": 1, "chain": "intact"}


def test_hold_is_decided_immediately_and_cannot_be_approved():
    draw_id = case("loan_closed")["draw_id"]
    with client() as c:
        r = c.post(f"/reviews/{draw_id}").json()
        assert r["status"] == "decided" and r["outcome"] == "on_hold"
        assert c.post(f"/reviews/{draw_id}/decision",
                      json={"officer": "officer-a", "action": "approve"}).status_code == 409


def test_bad_input():
    with client() as c:
        assert c.post("/reviews/D-0").status_code == 404
        draw_id = case("clean")["draw_id"]
        c.post(f"/reviews/{draw_id}")
        assert c.post(f"/reviews/{draw_id}/decision", json={"officer": "a", "action": "yes"}).status_code == 422


class FlakyLLM(TruthLLM):
    """Fails the first extraction call, like a model server that is briefly down."""

    def __init__(self):
        super().__init__()
        self.failed = False

    def json(self, task, messages, schema):
        if not self.failed:
            self.failed = True
            raise RuntimeError("model server unavailable")
        return super().json(task, messages, schema)


# Found on the kind cluster (2026-10-14): a review that crashed mid-way kept its checkpoint, and a second start only
# reported "running" forever.
def test_start_resumes_a_review_that_failed_mid_way(tmp_path):
    draw_id = case("clean")["draw_id"]
    with TestClient(create_app(llm=FlakyLLM(), ledger=Ledger(), checkpoint_db=str(tmp_path / "cp.db")),
                    raise_server_exceptions=False) as c:
        assert c.post(f"/reviews/{draw_id}").status_code == 500
        r = c.post(f"/reviews/{draw_id}").json()
        assert r["status"] == "waiting_for_officer"
