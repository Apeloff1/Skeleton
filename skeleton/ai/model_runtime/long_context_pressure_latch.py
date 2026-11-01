"""Fail-closed hysteresis over read-only local pressure observations.

Never authorizes inference, KV allocation, devices, disk, or stream execution.
Restart and fork invalidate the in-memory streak; a digest is not a signature.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from threading import Lock
from time import monotonic_ns
from typing import Callable

from .long_context_telemetry_fusion import LongContextTelemetryFusion

_SIGNAL_KEYS = frozenset(("cpu", "memory", "thermal", "energy"))
_EVENT_KEYS = frozenset(("oom", "oom_kill", "nr_throttled"))
_FALSE_KEYS = frozenset((
    "cross_source_snapshot_atomic", "scope_membership_attested",
    "pressure_signals_attested", "device_qualified",
    "is_admission_grant", "is_execution_lease",
))
_FIELDS = _FALSE_KEYS | frozenset((
    "schema", "state", "signals", "reasons", "event_state", "event_deltas",
    "sources", "requires_live_backend_revalidation", "observation_digest",
))
_UNKNOWN = {name: "unknown" for name in _SIGNAL_KEYS}


def _inspect(value: object) -> tuple[str, dict[str, str], str | None]:
    """Reject malformed, stale-looking, or authority-bearing envelopes."""
    if type(value) is not dict or set(value) != _FIELDS:
        return "invalid_envelope", dict(_UNKNOWN), None
    if value["schema"] != "skeleton.ai.long-context-telemetry-fusion.v1":
        return "invalid_schema", dict(_UNKNOWN), None
    if any(value[k] is not False for k in _FALSE_KEYS):
        return "forged_authority", dict(_UNKNOWN), None
    if value["requires_live_backend_revalidation"] is not True:
        return "missing_revalidation", dict(_UNKNOWN), None
    if value["sources"] != ("host_psi", "cgroup_v2", "cgroup_events"):
        return "invalid_sources", dict(_UNKNOWN), None
    signals = value["signals"]
    if type(signals) is not dict or set(signals) != _SIGNAL_KEYS or any(
        type(v) is not str or v not in ("normal", "elevated", "critical", "unknown")
        for v in signals.values()
    ):
        return "invalid_signals", dict(_UNKNOWN), None
    reasons = value["reasons"]
    if type(reasons) is not list or len(reasons) > 32 or any(
        type(s) is not str or not 1 <= len(s) <= 96
        or not all(c.isascii() and (c.isalnum() or c == "_") for c in s)
        for s in reasons
    ):
        return "invalid_reasons", dict(_UNKNOWN), None
    digest = value["observation_digest"]
    if type(digest) is not str or len(digest) != 64 or any(
        c not in "0123456789abcdef" for c in digest
    ):
        return "invalid_digest", dict(_UNKNOWN), None
    try:
        encoded = json.dumps(
            {k: v for k, v in value.items() if k != "observation_digest"},
            sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode()
    except (TypeError, ValueError, OverflowError):
        return "invalid_encoding", dict(_UNKNOWN), None
    if len(encoded) > 8192 or sha256(encoded).hexdigest() != digest:
        return "digest_mismatch", dict(_UNKNOWN), None
    if value["state"] not in ("observed", "baseline_required", "unavailable"):
        return "invalid_state", dict(_UNKNOWN), None
    if value["event_state"] not in ("observed", "baseline_required"):
        return "invalid_event_state", dict(_UNKNOWN), None
    deltas = value["event_deltas"]
    if value["event_state"] == "observed":
        if type(deltas) is not dict or set(deltas) != _EVENT_KEYS or any(
            type(n) is not int or not 0 <= n <= 2**63 - 1
            for n in deltas.values()
        ):
            return "invalid_event_deltas", dict(_UNKNOWN), None
    elif deltas is not None:
        return "invalid_baseline", dict(_UNKNOWN), None
    if value["state"] != "observed" or value["event_state"] != "observed":
        return "baseline_unproven", dict(_UNKNOWN), None
    if any(v != "normal" for v in signals.values()):
        return "pressure_non_normal", dict(signals), digest
    if reasons or any(deltas.values()):
        return "event_or_reason_hold", dict(signals), digest
    return "normal_observed", dict(signals), digest


class LongContextPressureLatch:
    """hold -> warming -> repeated_normal_observed, never an admission grant."""

    def __init__(self, monitor: LongContextTelemetryFusion, *,
                 required_samples: int = 3,
                 max_gap_ns: int = 2_000_000_000,
                 clock: Callable[[], int] = monotonic_ns) -> None:
        if not isinstance(monitor, LongContextTelemetryFusion):
            raise ValueError("invalid monitor")
        if type(required_samples) is not int or not 2 <= required_samples <= 16:
            raise ValueError("invalid sample count")
        if type(max_gap_ns) is not int or not 1 <= max_gap_ns <= 10_000_000_000:
            raise ValueError("invalid gap")
        if not callable(clock):
            raise ValueError("invalid clock")
        self._monitor, self._clock = monitor, clock
        self._required, self._max_gap_ns = required_samples, max_gap_ns
        self._pid, self._lock = os.getpid(), Lock()
        self._last_ns: int | None = None
        self._streak, self._reset_epoch = 0, 0

    def sample(self) -> dict[str, object]:
        if os.getpid() != self._pid:
            raise OSError("inherited pressure latch after fork")
        with self._lock:
            try:
                now = self._clock()
            except Exception:
                now = None
            valid_clock = type(now) is int and now >= 0
            regression = not valid_clock or (
                self._last_ns is not None and now <= self._last_ns)
            gap = bool(valid_clock and self._last_ns is not None
                       and now - self._last_ns > self._max_gap_ns)
            if valid_clock:
                self._last_ns = max(self._last_ns or 0, now)
            try:
                reason, signals, digest = _inspect(self._monitor.sample())
            except Exception:
                reason, signals, digest = "monitor_unavailable", dict(_UNKNOWN), None
            if regression:
                reason, signals, digest = "clock_invalid", dict(_UNKNOWN), None
            if gap:
                self._streak = 0
            if reason == "normal_observed":
                self._streak = min(self._required, self._streak + 1)
                state = ("repeated_normal_observed" if self._streak == self._required
                         else "warming")
                reasons = [] if state == "repeated_normal_observed" else [
                    "insufficient_consecutive_observations"]
                if gap:
                    reasons.append("clock_gap_reset")
            else:
                self._streak, state, reasons = 0, "hold", [reason]
                self._reset_epoch += 1
            return {
                "schema": "skeleton.ai.long-context-pressure-latch.v1",
                "state": state, "reasons": reasons, "signals": signals,
                "consecutive_normal_observations": self._streak,
                "required_observations": self._required,
                "reset_epoch": self._reset_epoch,
                "last_observation_digest": digest,
                "observation_digest_is_authenticity_proof": False,
                "cross_source_snapshot_atomic": False,
                "pressure_signals_attested": False, "device_qualified": False,
                "is_admission_grant": False, "is_execution_lease": False,
                "requires_live_backend_revalidation": True,
                "restart_state_durable": False,
            }


__all__ = ["LongContextPressureLatch"]
