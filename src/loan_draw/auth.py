"""API keys for the HTTP API.

    LOAN_DRAW_API_KEYS="officer-a:officer:<key>,officer-b:officer:<key>,review-bot:agent:<key>"

Each entry is name:role:key. `officer` keys may approve or reject a draw; `agent` keys may start and read reviews and
never decide. Names are case-insensitive (stored lower-case) and each name has one key, so one person cannot
count as two approvers. The name of the key holder is the approver written to the ledger. No entries means every protected
route answers 401.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Literal, get_args

Role = Literal["officer", "agent"]
MIN_KEY_LENGTH = 16


@dataclass(frozen=True)
class Principal:
    name: str
    role: Role


def _digest(key: str) -> bytes:
    return hashlib.sha256(key.encode()).digest()


class Keys:
    def __init__(self, spec: str = ""):
        self._by_digest: list[tuple[bytes, Principal]] = []
        self._names: set[str] = set()
        for entry in filter(None, (e.strip() for e in spec.split(","))):
            name, role, key = (entry.split(":", 2) + ["", ""])[:3]
            name, role, key = name.strip().casefold(), role.strip(), key.strip()
            if not name or role not in get_args(Role) or len(key) < MIN_KEY_LENGTH:
                raise ValueError(f"LOAN_DRAW_API_KEYS entry for {name or '?'!r} must be name:officer|agent:key "
                                 f"with a key of at least {MIN_KEY_LENGTH} characters")
            if any(hmac.compare_digest(d, _digest(key)) for d, _ in self._by_digest):
                raise ValueError(f"LOAN_DRAW_API_KEYS gives {name!r} a key another entry already uses")
            if name in self._names:
                raise ValueError(f"LOAN_DRAW_API_KEYS lists {name!r} more than once (names are case-insensitive)")
            self._names.add(name)
            self._by_digest.append((_digest(key), Principal(name, role)))

    def lookup(self, key: str) -> Principal | None:
        digest, found = _digest(key), None
        for d, principal in self._by_digest:  # compare against every entry so timing does not reveal which matched
            if hmac.compare_digest(d, digest):
                found = principal
        return found
