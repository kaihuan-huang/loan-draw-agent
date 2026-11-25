"""Append-only decision ledger. Each row stores the hash of the previous row, so an edit anywhere breaks the chain and
`verify()` says where. SQLite here; the schema is plain enough for Postgres."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

GENESIS = "0" * 64
DEFAULT_LEDGER_DB = "ledger.db"


def ledger_path() -> str:
    """The one place the ledger location is decided (env LEDGER_DB), so every entry point shares one ledger."""
    return os.environ.get("LEDGER_DB", DEFAULT_LEDGER_DB)


class TamperedLedger(RuntimeError):
    pass


class Ledger:
    def __init__(self, path: str | Path = ":memory:"):
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None, timeout=30)
        self._lock = threading.Lock()
        self._db.execute("""create table if not exists ledger (
            seq integer primary key, draw_id text not null, action text not null, body text not null,
            prev_hash text not null, hash text not null unique)""")
        self._db.execute("create unique index if not exists one_decision_per_draw on ledger(draw_id)")
        self.verify()

    @staticmethod
    def _hash(prev: str, body: str) -> str:
        return hashlib.sha256((prev + body).encode()).hexdigest()

    def append(self, draw_id: str, action: str, detail: dict) -> str:
        """One decision per draw: a second append for the same draw raises instead of double-funding it."""
        body = json.dumps({"draw_id": draw_id, "action": action, "detail": detail,
                           "at": datetime.now(UTC).isoformat(timespec="seconds")}, sort_keys=True)
        with self._lock:
            # BEGIN IMMEDIATE takes the write lock before the last hash is read, so a second writer process
            # (the API and the LangGraph server share one file) waits instead of chaining off the same row.
            self._db.execute("begin immediate")
            try:
                row = self._db.execute("select hash from ledger order by seq desc limit 1").fetchone()
                prev = row[0] if row else GENESIS
                h = self._hash(prev, body)
                self._db.execute("insert into ledger(draw_id, action, body, prev_hash, hash) values (?,?,?,?,?)",
                                 (draw_id, action, body, prev, h))
                self._db.execute("commit")
            except BaseException:
                self._db.execute("rollback")
                raise
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
