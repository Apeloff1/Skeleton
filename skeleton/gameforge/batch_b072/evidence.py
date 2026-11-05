"""B072 — Replayable test evidence.

Success criterion: "Failures emit compact seeds/inputs/state hashes sufficient
for deterministic reproduction."

A test records ``(tick, input)`` pairs and per-checkpoint state hashes into an
:class:`InputRecorder`. On failure, :meth:`InputRecorder.evidence` produces a
:class:`FailureEvidence` whose compact JSON form can be fed to :func:`replay`
to re-run a step function and verify every checkpoint hash matches.
"""
from __future__ import annotations

import base64
import hashlib
import json
import zlib
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Tuple

SCHEMA = "gameforge.evidence/v1"


class EvidenceError(ValueError):
    pass


def state_hash(state: Any) -> str:
    """Canonical JSON SHA-256 (sorted keys); state must be JSON-serialisable."""
    try:
        blob = json.dumps(state, sort_keys=True, separators=(",", ":"))
    except TypeError as exc:
        raise EvidenceError(f"state not serialisable: {exc}") from exc
    return hashlib.sha256(blob.encode()).hexdigest()


@dataclass(frozen=True)
class FailureEvidence:
    test_id: str
    seed: int
    inputs: Tuple[Tuple[int, Any], ...]
    checkpoints: Tuple[Tuple[int, str], ...]
    message: str = ""

    def to_compact(self) -> str:
        doc = {"schema": SCHEMA, "test_id": self.test_id, "seed": self.seed,
               "inputs": [list(i) for i in self.inputs],
               "checkpoints": [list(c) for c in self.checkpoints], "message": self.message}
        raw = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode()

    @classmethod
    def from_compact(cls, blob: str) -> "FailureEvidence":
        try:
            doc = json.loads(zlib.decompress(base64.urlsafe_b64decode(blob.encode())))
        except Exception as exc:  # noqa: BLE001 - any decode failure is the same error
            raise EvidenceError("corrupt evidence blob") from exc
        if doc.get("schema") != SCHEMA:
            raise EvidenceError(f"unknown schema {doc.get('schema')!r}")
        return cls(doc["test_id"], doc["seed"], tuple((t, v) for t, v in doc["inputs"]),
                   tuple((t, h) for t, h in doc["checkpoints"]), doc.get("message", ""))


class InputRecorder:
    def __init__(self, test_id: str, seed: int) -> None:
        self.test_id, self.seed = test_id, seed
        self._inputs: List[Tuple[int, Any]] = []
        self._checkpoints: List[Tuple[int, str]] = []

    def record_input(self, tick: int, value: Any) -> None:
        if self._inputs and tick < self._inputs[-1][0]:
            raise EvidenceError("inputs must be recorded in tick order")
        self._inputs.append((tick, value))

    def checkpoint(self, tick: int, state: Any) -> str:
        h = state_hash(state)
        self._checkpoints.append((tick, h))
        return h

    def evidence(self, message: str = "") -> FailureEvidence:
        return FailureEvidence(self.test_id, self.seed, tuple(self._inputs),
                               tuple(self._checkpoints), message)


def replay(ev: FailureEvidence, init: Callable[[int], Dict], step: Callable[[Dict, int, Any], Dict],
           last_tick: int) -> Dict:
    """Re-run ``step`` for ticks 0..last_tick; raise on first checkpoint mismatch."""
    inputs: Dict[int, List[Any]] = {}
    for t, v in ev.inputs:
        inputs.setdefault(t, []).append(v)
    expected = dict(ev.checkpoints)
    state = init(ev.seed)
    for tick in range(last_tick + 1):
        for v in inputs.get(tick, [None]):
            state = step(state, tick, v)
        if tick in expected and state_hash(state) != expected[tick]:
            raise EvidenceError(f"divergence at tick {tick}")
    return state
