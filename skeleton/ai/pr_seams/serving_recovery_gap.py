"""Close native LLM serving recovery gaps

Plane: serving_recovery_gap
PR: https://github.com/Apeloff1/Skeleton/pull/3475
Branch: automation/native-llm-serving-recovery-fix-20261007
Law: stored_prose=0. Pointer citations only. No network. No torch.
Parent cite: #80 and #3475.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Mapping, Sequence

LAW = "stored_prose=0"
CITATION = "https://github.com/Apeloff1/Skeleton/pull/3475"
KIND = "serving-recovery"


def _canon(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _h(prefix: str, payload: object) -> str:
    return prefix + sha256(_canon(payload).encode("utf-8")).hexdigest()


def _id(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    if "\n" in value or len(value) > 240:
        raise ValueError(f"{name} must be a pointer clause")
    return value.strip()


def _u(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative int")
    return value


def card(hit: bool, **extra: object) -> dict:
    body = {
        "kind": KIND,
        "hit": bool(hit),
        "law": LAW,
        "citation": CITATION,
        "stored_prose": 0,
    }
    body.update(extra)
    if body["stored_prose"] != 0:
        raise PermissionError("stored prose is forbidden")
    return body

GAPS = ("orphan-kv", "stale-lease", "partial-stop", "unacked-token")


@dataclass(frozen=True)
class Gap:
    gap_id: str
    name: str
    session_id: str
    observed_ns: int

    @classmethod
    def create(cls, name: str, session_id: str, observed_ns: int):
        if name not in GAPS:
            raise ValueError("unknown serving gap")
        _id(session_id, "session_id")
        _u(observed_ns, "observed_ns")
        payload = {"name": name, "session_id": session_id, "observed_ns": observed_ns}
        return cls(_h("gap-sha256:", payload), name, session_id, observed_ns)


@dataclass(frozen=True)
class Close:
    close_id: str
    gap_id: str
    action: str
    closed_ns: int


def close_gap(gap: Gap, closed_ns: int) -> Close:
    _u(closed_ns, "closed_ns")
    if closed_ns < gap.observed_ns:
        raise PermissionError("close precedes observation")
    action = {
        "orphan-kv": "drop-kv",
        "stale-lease": "revoke-lease",
        "partial-stop": "force-stop",
        "unacked-token": "replay-token",
    }[gap.name]
    payload = {"gap_id": gap.gap_id, "action": action, "closed_ns": closed_ns}
    return Close(_h("close-sha256:", payload), gap.gap_id, action, closed_ns)


def exit_card(gap: Gap, closed: Close) -> dict:
    return card(True, gap_id=gap.gap_id, close_id=closed.close_id, action=closed.action, session_id=gap.session_id)
