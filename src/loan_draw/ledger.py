"""Append-only decision ledger. Each row stores the hash of the previous row, so an edit anywhere breaks the chain and
`verify()` says where. SQLite here; the schema is plain enough for Postgres."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

GENESIS = "0" * 64


class TamperedLedger(RuntimeError):
    pass


class Ledger:
    def __init__(self, path: str | Path = ":memory:"):
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        self._db.execute("""create table if not exists ledger (
            seq integer primary key, draw_id text not null, action text not null, body text not null,
            prev_hash text not null, hash text not null unique)""")
        self._db.execute("create unique index if not exists one_decision_per_draw on ledger(draw_id)")
        self._db.commit()
        self.verify()

    @staticmethod
    def _hash(prev: str, body: str) -> str:
        return hashlib.sha256((prev + body).encode()).hexdigest()

    def append(self, draw_id: str, action: str, detail: dict) -> str:
        """One decision per draw: a second append for the same draw raises instead of double-funding it."""
        with self._lock:
            row = self._db.execute("select hash from ledger order by seq desc limit 1").fetchone()
            prev = row[0] if row else GENESIS
            body = json.dumps({"draw_id": draw_id, "action": action, "detail": detail,
                               "at": datetime.now(UTC).isoformat(timespec="seconds")}, sort_keys=True)
            h = self._hash(prev, body)
            with self._db:  # commit, or roll back so a refused duplicate does not leave the database locked
                self._db.execute("insert into ledger(draw_id, action, body, prev_hash, hash) values (?,?,?,?,?)",
                                 (draw_id, action, body, prev, h))
            return h

    def decision(self, draw_id: str) -> dict | None:
        row = self._db.execute("select body from ledger where draw_id = ?", (draw_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def verify(self) -> int:
        prev = GENESIS
        n = 0
        for seq, body, p, h in self._db.execute("select seq, body, prev_hash, hash from ledger order by seq"):
            if p != prev or h != self._hash(prev, body):
                raise TamperedLedger(f"ledger row {seq} does not match its hash chain")
            prev, n = h, n + 1
        return n
