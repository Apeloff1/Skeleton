"""Bounded, read-only fairness proposals for durable offline token streams.

Proposals are NOT execution leases, admission grants, device qualification,
trusted pressure observations, or evidence of backend token consumption.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Literal

from .long_context_progress import LongContextProgressHead, _name
from .long_context_spool import LongContextSpoolError, _canonical, _digest

_PRESSURE = frozenset(("normal", "elevated", "critical", "unknown"))
_MAX_STREAMS = 64
_MAX_TOKENS = 65_536


def _bounded(value: object, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise LongContextSpoolError("invalid " + name)
    return value


@dataclass(frozen=True, slots=True)
class StreamDemand:
    stream_id: str
    checkpoint_digest: str
    generation: int
    max_tokens: int
    weight: int = 1
    requested_bytes: int = 0

    def __post_init__(self) -> None:
        _name(self.stream_id)
        _digest(self.checkpoint_digest, "checkpoint")
        _bounded(self.generation, "generation", 0, 2**63 - 1)
        _bounded(self.max_tokens, "max_tokens", 1, _MAX_TOKENS)
        _bounded(self.weight, "weight", 1, 8)
        _bounded(self.requested_bytes, "requested_bytes", 0, 1024**3)


@dataclass(frozen=True, slots=True)
class PressureSignals:
    cpu: Literal["normal", "elevated", "critical", "unknown"]
    memory: Literal["normal", "elevated", "critical", "unknown"]
    thermal: Literal["normal", "elevated", "critical", "unknown"]
    energy: Literal["normal", "elevated", "critical", "unknown"]
    device_kind: Literal["cpu", "gpu", "m_chip"] = "cpu"

    def __post_init__(self) -> None:
        for name in ("cpu", "memory", "thermal", "energy"):
            value = getattr(self, name)
            if type(value) is not str or value not in _PRESSURE:
                raise LongContextSpoolError("invalid " + name + " pressure")
        if type(self.device_kind) is not str or self.device_kind not in (
            "cpu", "gpu", "m_chip"
        ):
            raise LongContextSpoolError("invalid device kind")

    def holds(self) -> list[str]:
        reasons = [
            name + "_" + getattr(self, name)
            for name in ("cpu", "memory", "thermal", "energy")
            if getattr(self, name) != "normal"
        ]
        if self.device_kind != "cpu":
            reasons.append("device_not_qualified")
        return reasons


class LongContextFairPlanner:
    """Plan at most one bounded quantum per active stream in each fair cycle.

    Stable digest ordering makes plans independent of request ordering. When
    the token budget cannot include every active stream, hold the entire
    cycle. This cannot guarantee fairness across repeated client calls.
    """

    def __init__(self, heads: LongContextProgressHead):
        if not isinstance(heads, LongContextProgressHead):
            raise LongContextSpoolError("invalid head coordinator")
        self.heads = heads

    def plan(
        self, demands: tuple[StreamDemand, ...], *,
        expected_tokenizer_digest: str, signals: PressureSignals,
        total_token_budget: int, quantum_tokens: int = 256,
        max_checkpoints: int = 4096,
    ) -> dict[str, object]:
        _digest(expected_tokenizer_digest, "tokenizer")
        if type(demands) is not tuple or not 1 <= len(demands) <= _MAX_STREAMS:
            raise LongContextSpoolError("invalid stream batch")
        if not isinstance(signals, PressureSignals):
            raise LongContextSpoolError("invalid pressure signals")
        _bounded(total_token_budget, "total_token_budget", 1, _MAX_TOKENS)
        _bounded(quantum_tokens, "quantum_tokens", 1, 4096)
        _bounded(max_checkpoints, "max_checkpoints", 1, 4096)
        if len(demands) * max_checkpoints > 262_144:
            raise LongContextSpoolError("audit work bound exceeded")
        names: set[str] = set()
        requested = 0
        for demand in demands:
            if not isinstance(demand, StreamDemand):
                raise LongContextSpoolError("invalid demand")
            name = _name(demand.stream_id)
            if name in names:
                raise LongContextSpoolError("duplicate stream")
            names.add(name)
            requested += demand.requested_bytes
        if requested > 1024**3:
            raise LongContextSpoolError("aggregate disk request exceeded")
        ordered = sorted(demands, key=lambda d: _name(d.stream_id))

        with self.heads._locked() as directory:
            verified = []
            for demand in ordered:
                name = _name(demand.stream_id)
                record = self.heads._expect_observation(
                    self.heads._read(directory, name),
                    checkpoint=demand.checkpoint_digest,
                    tokenizer=expected_tokenizer_digest,
                    generation=demand.generation,
                )
                self.heads.spool.audit_history(
                    demand.checkpoint_digest,
                    expected_tokenizer_digest=expected_tokenizer_digest,
                    max_checkpoints=max_checkpoints,
                )
                if self.heads._read(directory, name) != record:
                    raise LongContextSpoolError("head changed during audit")
                verified.append((demand, record))

            capacity = self.heads.spool.capacity_snapshot(
                requested_bytes=requested,
            )
            reasons = signals.holds()
            if not capacity["request_observed_sufficient"] or (
                capacity["observed_publishable_bytes"] <= 0
            ):
                reasons.append("spool_capacity_hold")
            slots: list[dict[str, object]] = []
            if not reasons:
                windows = []
                for demand, record in verified:
                    window = self.heads.spool.audited_next_window(
                        demand.checkpoint_digest,
                        expected_tokenizer_digest=expected_tokenizer_digest,
                        max_tokens=demand.max_tokens,
                        max_checkpoints=max_checkpoints,
                    )
                    if self.heads._read(directory, _name(demand.stream_id)) != record:
                        raise LongContextSpoolError("head changed during window read")
                    if window is not None:
                        windows.append((demand, window))
                if len(windows) > total_token_budget:
                    reasons.append("fair_cycle_budget_insufficient")
                else:
                    remaining = total_token_budget
                    for demand, window in windows:
                        amount = min(
                            remaining, window.stop - window.start,
                            quantum_tokens * demand.weight,
                        )
                        if amount <= 0:
                            reasons.append("fair_cycle_budget_insufficient")
                            slots.clear()
                            break
                        slots.append({
                            "stream_digest": _name(demand.stream_id),
                            "checkpoint_digest": demand.checkpoint_digest,
                            "generation": demand.generation,
                            "window_digest": window.digest,
                            "window_start": window.start,
                            "window_stop": window.stop,
                            "proposed_tokens": amount,
                            "weight": demand.weight,
                        })
                        remaining -= amount
            for demand, record in verified:
                if self.heads._read(directory, _name(demand.stream_id)) != record:
                    raise LongContextSpoolError("head changed before return")
            state = "hold" if reasons else "proposed"
            result: dict[str, object] = {
                "schema": "skeleton.ai.long-context-fair-plan.v1",
                "state": state,
                "reasons": sorted(set(reasons)),
                "verified_heads": len(verified),
                "slots": slots if state == "proposed" else [],
                "proposed_tokens": sum(slot["proposed_tokens"] for slot in slots)
                    if state == "proposed" else 0,
                "observed_publishable_bytes": capacity["observed_publishable_bytes"],
                "pressure_signals_attested": False,
                "is_execution_lease": False,
                "is_admission_grant": False,
                "hardware_qualification": "not_assessed",
                "requires_backend_authorization": True,
            }
            result["plan_digest"] = sha256(_canonical(result)).hexdigest()
            return result


__all__ = ["StreamDemand", "PressureSignals", "LongContextFairPlanner"]
