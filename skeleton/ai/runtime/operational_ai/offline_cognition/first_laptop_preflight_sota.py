"""Fail-closed, source-bound first-laptop preflight (quarantined candidate).

This module does not attest a real model, device, or release on its own.
A trusted caller must supply a verifier for the exact source, rights and epoch.
No verifier means a hold, never synthetic readiness.
"""
from __future__ import annotations

import copy
import json
import math
import re
from collections import deque
from dataclasses import dataclass, field
from hashlib import sha256
from threading import Lock
from time import monotonic_ns
from typing import Any, Callable

from ..authority.canonical import canonical_bytes as canonical

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MAX_EVIDENCE_BYTES = 32 * 1024
_MAX_EPOCH = 2**31 - 1


@dataclass(frozen=True)
class StageResult:
    stage: str
    passed: bool
    score: float
    evidence_sha: str
    epoch: int = 0
    held_reason: str | None = None


@dataclass
class AdaptiveScoreStack:
    ram_headroom: float
    cpu_affinity: float
    disk_free: float
    entropy: float = 0.0
    history: deque = field(default_factory=lambda: deque(maxlen=16))

    def aggregate(self) -> float:
        base = self.ram_headroom * 0.4 + self.cpu_affinity * 0.3 + self.disk_free * 0.3
        self.history.append(base)
        avg = sum(self.history) / len(self.history)
        return avg * (1.0 + self.entropy * 0.15)


def _finite(value: Any) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def _sha(value: Any) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _snapshot(value: Any) -> tuple[dict, str] | None:
    """Copy only finite canonical objects; do not trust a mutable caller mapping."""
    if type(value) is not dict:
        return None
    try:
        blob = canonical(value)
        if type(blob) is not bytes or len(blob) > _MAX_EVIDENCE_BYTES:
            return None
        snapshot = json.loads(blob, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if type(snapshot) is not dict:
            return None
        return snapshot, sha256(blob).hexdigest()
    except (ValueError, TypeError, OverflowError, RecursionError, UnicodeError):
        return None


def _score(telemetry: dict) -> tuple[AdaptiveScoreStack, float] | None:
    keys = ("ram_free", "ram_total", "cpu_affinity", "disk_free", "disk_total", "entropy")
    if any(k not in telemetry or not _finite(telemetry[k]) for k in keys):
        return None
    ram_free, ram_total = telemetry["ram_free"], telemetry["ram_total"]
    disk_free, disk_total = telemetry["disk_free"], telemetry["disk_total"]
    affinity, entropy = telemetry["cpu_affinity"], telemetry["entropy"]
    if not (0 < ram_total <= 2**60 and 0 <= ram_free <= ram_total
            and 0 < disk_total <= 2**64 and 0 <= disk_free <= disk_total
            and 0 <= affinity <= 1 and 0 <= entropy <= 1):
        return None
    stack = AdaptiveScoreStack(ram_free / ram_total, affinity, disk_free / disk_total, entropy)
    score = stack.aggregate()  # Exactly one scoring sample per invocation.
    if not math.isfinite(score):
        return None
    return stack, score


class FirstLaptopPreflightSOTA:
    def __init__(self, *, stages: int = 6):
        if type(stages) is not int or stages != 6:
            raise ValueError("exact six-stage preflight contract required")
        self.stages = stages
        self.results: list[StageResult] = []
        self.provenance: str | None = None
        self.recovery_log: deque = deque(maxlen=32)
        self._run_lock = Lock()

    def _held(self, reason: str, epoch: int | None, results: list[StageResult]) -> dict:
        self.results = list(results)
        self.provenance = None
        entry = {"epoch": epoch, "failed": [r.stage for r in results if not r.passed],
                 "reason": reason}
        self.recovery_log.append(entry)
        return {"schema": "preflight-held.v3", "passed": False,
                "reason": reason, "epoch": epoch,
                "stages": [r.stage for r in results], "recovery": dict(entry)}

    def run(self, telemetry: dict, source_report: dict, rights: dict, *, epoch: int = 0,
            provenance_verifier: Callable[[dict, dict, int], bool] | None = None) -> dict:
        # Nonblocking admission prevents concurrent callers from sharing stage custody.
        if not self._run_lock.acquire(blocking=False):
            return {"schema": "preflight-held.v3", "passed": False,
                    "reason": "preflight-busy", "epoch": None, "stages": []}
        try:
            return self._run_locked(telemetry, source_report, rights, epoch, provenance_verifier)
        finally:
            self._run_lock.release()

    def _run_locked(self, telemetry: Any, source_report: Any, rights: Any,
                    epoch: Any, verifier: Any) -> dict:
        start = monotonic_ns()
        results: list[StageResult] = []
        # Clear stale success, including on a malformed subsequent call.
        self.results = []
        self.provenance = None
        if type(epoch) is not int or not 0 <= epoch <= _MAX_EPOCH:
            return self._held("invalid-epoch", None, results)
        telemetry_snapshot = _snapshot(telemetry)
        source_snapshot = _snapshot(source_report)
        rights_snapshot = _snapshot(rights)
        if not all((telemetry_snapshot, source_snapshot, rights_snapshot)):
            return self._held("invalid-bounded-evidence", epoch, results)
        telemetry_data, telemetry_sha = telemetry_snapshot
        source_data, source_sha = source_snapshot
        rights_data, rights_sha = rights_snapshot
        measured = _score(telemetry_data)
        if measured is None:
            return self._held("invalid-hardware-telemetry", epoch, results)
        stack, score = measured
        hardware_ok = score > 0.35
        results.append(StageResult("hardware", hardware_ok, score, telemetry_sha, epoch))
        if not hardware_ok:
            return self._held("hardware-score-below-threshold", epoch, results)

        source_ok = (source_data.get("installed") is True
                     and source_data.get("rights_ok") is True
                     and type(source_data.get("epoch")) is int
                     and source_data["epoch"] == epoch
                     and all(_sha(source_data.get(k)) for k in (
                         "model_sha256", "tokenizer_sha256", "source_tree_sha256")))
        results.append(StageResult("source", source_ok, float(source_ok), source_sha, epoch))
        if not source_ok:
            return self._held("source-identity-unverified", epoch, results)

        capacity_ok = telemetry_data.get("capacity_lease") is True
        results.append(StageResult("capacity", capacity_ok, float(capacity_ok), telemetry_sha, epoch))
        if not capacity_ok:
            return self._held("capacity-lease-unverified", epoch, results)

        rights_ok = (rights_data.get("approved") is True
                     and type(rights_data.get("approval_epoch")) is int
                     and rights_data["approval_epoch"] == epoch
                     and _sha(rights_data.get("reviewer_sha256")))
        results.append(StageResult("rights", rights_ok, float(rights_ok), rights_sha, epoch))
        if not rights_ok:
            return self._held("rights-approval-unverified", epoch, results)

        entropy_ok = stack.entropy < 0.9
        results.append(StageResult("entropy", entropy_ok, 1.0-stack.entropy, telemetry_sha, epoch))
        if not entropy_ok:
            return self._held("entropy-pressure-exceeded", epoch, results)

        # A source-provided boolean is NOT proof; require an independently wired
        # trusted verifier to inspect precisely the bounded snapshots for this epoch.
        # Seal identity before invoking an external verifier. Its arguments are
        # isolated copies so mutation cannot change the receipt or escape guards.
        receipt = sha256(canonical({"epoch": epoch, "source": source_data,
                                    "rights": rights_data})).hexdigest()
        provenance_ok = False
        if callable(verifier):
            try:
                provenance_ok = verifier(
                    copy.deepcopy(source_data), copy.deepcopy(rights_data), epoch
                ) is True
            except Exception:
                provenance_ok = False
        results.append(StageResult("provenance", provenance_ok,
                                   float(provenance_ok), receipt, epoch))
        if not provenance_ok:
            return self._held("trusted-provenance-unverified", epoch, results)
        self.results = list(results)
        self.provenance = receipt
        return {"schema": "first-laptop-preflight.v3-sota", "passed": True,
                "score": score, "stages": len(results),
                "latency_ns": max(0, monotonic_ns() - start),
                "provenance": receipt, "epoch": epoch, "recovery": None}
