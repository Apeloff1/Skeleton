"""Deterministic, bounded serving audit receipts without sensitive payloads."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from threading import RLock
from typing import Mapping


class AuditError(ValueError):
    pass


def _canonical(body: dict) -> bytes:
    return json.dumps(body, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


@dataclass(frozen=True, slots=True)
class AuditReceipt:
    sequence: int
    request_digest: str
    action: str
    outcome: str
    predecessor: str
    digest: str


class ServingAuditChain:
    """Append-only in-memory chain; durable storage required for production."""

    _ACTIONS = frozenset({"admission", "reservation", "dispatch", "terminal"})
    _OUTCOMES = frozenset({"accepted", "denied", "completed", "failed", "cancelled"})

    def __init__(self, max_receipts: int = 10000):
        if type(max_receipts) is not int or max_receipts <= 0:
            raise AuditError("positive receipt limit required")
        self._max = max_receipts
        self._lock = RLock()
        self._receipts: list[AuditReceipt] = []

    @staticmethod
    def _digest_body(sequence: int, request_digest: str, action: str,
                     outcome: str, predecessor: str) -> str:
        return sha256(_canonical({
            "schema": "skeleton.ai.serving-audit.v1",
            "sequence": sequence,
            "request_digest": request_digest,
            "action": action,
            "outcome": outcome,
            "predecessor": predecessor,
        })).hexdigest()

    def append(self, *, request_digest: str, action: str, outcome: str) -> AuditReceipt:
        if (not isinstance(request_digest, str) or len(request_digest) != 64
                or any(c not in "0123456789abcdef" for c in request_digest)):
            raise AuditError("canonical request digest required")
        if action not in self._ACTIONS or outcome not in self._OUTCOMES:
            raise AuditError("unsupported audit event")
        with self._lock:
            if len(self._receipts) >= self._max:
                raise AuditError("audit capacity exhausted")
            predecessor = self._receipts[-1].digest if self._receipts else "0" * 64
            sequence = len(self._receipts) + 1
            digest = self._digest_body(sequence, request_digest, action,
                                       outcome, predecessor)
            receipt = AuditReceipt(sequence, request_digest, action,
                                   outcome, predecessor, digest)
            self._receipts.append(receipt)
            return receipt

    def snapshot(self) -> tuple[AuditReceipt, ...]:
        with self._lock:
            return tuple(self._receipts)

    @classmethod
    def verify(cls, receipts: tuple[AuditReceipt, ...]) -> bool:
        if not isinstance(receipts, tuple):
            return False
        predecessor = "0" * 64
        for sequence, receipt in enumerate(receipts, start=1):
            if not isinstance(receipt, AuditReceipt):
                return False
            if receipt.sequence != sequence or receipt.predecessor != predecessor:
                return False
            if receipt.action not in cls._ACTIONS or receipt.outcome not in cls._OUTCOMES:
                return False
            if (not isinstance(receipt.request_digest, str)
                    or len(receipt.request_digest) != 64
                    or any(c not in "0123456789abcdef" for c in receipt.request_digest)):
                return False
            expected = cls._digest_body(sequence, receipt.request_digest,
                                        receipt.action, receipt.outcome, predecessor)
            if receipt.digest != expected:
                return False
            predecessor = expected
        return True
