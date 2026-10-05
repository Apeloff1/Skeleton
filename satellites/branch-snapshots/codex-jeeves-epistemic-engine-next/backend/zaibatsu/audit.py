"""WORM audit — a hash-chained, fsync'd ledger of what the gate saw.

Every entry chains to its predecessor:

    hash_n = SHA256(seq | ts | correlation | actor | action | verdict | hash_{n-1})

The chain head is the empire's word: recompute from genesis and any
tampered byte anywhere in history breaks every head after it. The log is
append-only at the API level — there is no update, no delete, no rewrite.
A corrupted chain stops the gate at startup; it does not get repaired,
it gets investigated.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, asdict

GENESIS = "genesis"


@dataclass(frozen=True)
class AuditEntry:
    seq: int
    ts: float
    correlation: str
    actor: str
    action: str
    verdict: str
    detail: str
    prev_hash: str
    hash: str

    @staticmethod
    def compute(seq: int, ts: float, correlation: str, actor: str,
                action: str, verdict: str, detail: str, prev_hash: str) -> str:
        canon = f"{seq}|{ts}|{correlation}|{actor}|{action}|{verdict}|{detail}|{prev_hash}"
        return hashlib.sha256(canon.encode("utf-8")).hexdigest()


class ChainBroken(Exception):
    def __init__(self, seq: int, why: str):
        super().__init__(f"audit chain broken at seq {seq}: {why}")
        self.seq = seq
        self.why = why


class AuditLog:
    """Append-only hash-chained JSONL log. Thread-safe; fsync per entry."""

    def __init__(self, path: str):
        self._path = path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        self._seq, self._head = self._load_and_verify()

    def _load_and_verify(self) -> tuple[int, str]:
        if not os.path.exists(self._path):
            return 0, GENESIS
        seq, prev = 0, GENESIS
        with open(self._path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                raw = json.loads(line)
                expect = AuditEntry.compute(
                    raw["seq"], raw["ts"], raw["correlation"], raw["actor"],
                    raw["action"], raw["verdict"], raw["detail"], prev,
                )
                if raw["hash"] != expect:
                    raise ChainBroken(raw["seq"], "entry hash does not match content")
                if raw["prev_hash"] != prev:
                    raise ChainBroken(raw["seq"], "prev_hash does not chain")
                seq, prev = raw["seq"], raw["hash"]
        return seq, prev

    def append(self, correlation: str, actor: str, action: str,
               verdict: str, detail: str = "") -> AuditEntry:
        with self._lock:
            seq = self._seq + 1
            ts = time.time()
            h = AuditEntry.compute(seq, ts, correlation, actor, action,
                                   verdict, detail, self._head)
            entry = AuditEntry(seq, ts, correlation, actor, action,
                               verdict, detail, self._head, h)
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(asdict(entry), separators=(",", ":")) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            self._seq, self._head = seq, h
            return entry

    @property
    def head(self) -> str:
        return self._head

    @property
    def seq(self) -> int:
        return self._seq
