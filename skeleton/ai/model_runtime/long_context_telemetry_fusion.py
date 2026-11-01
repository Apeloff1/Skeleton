"""Conservative, payload-free fusion of independent local pressure observations.

This diagnostic never grants inference, GPU qualification, stream execution, or
memory allocation. Sources are not simultaneous; missing evidence dominates.
An event baseline or a zero event delta is not a proof of resource safety.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
from threading import Lock
from time import monotonic_ns
from typing import Callable

from .long_context_cgroup import observe_cgroup_pressure
from .long_context_cgroup_events import CgroupEventMonitor
from .long_context_host_pressure import observe_host_pressure

_KEYS = ("cpu", "memory", "thermal", "energy")
_LEVELS = {"normal": 0, "elevated": 1, "critical": 2, "unknown": 3}
_EVENT_KEYS = frozenset(("oom", "oom_kill", "nr_throttled"))
_MAX_REASON_LENGTH = 96


def _source(value: object) -> dict[str, str]:
    """Validate even internal observer results; never trust injected fixtures."""
    if not isinstance(value, dict):
        raise ValueError("invalid observation")
    if any(value.get(key, False) is not False for key in (
        "is_admission_grant", "is_execution_lease", "device_qualified",
        "pressure_signals_attested", "scope_membership_attested",
    )):
        raise ValueError("observation claimed unsupported authority")
    signals = value.get("signals")
    if not isinstance(signals, dict) or set(signals) != set(_KEYS):
        raise ValueError("incomplete observation")
    result = {}
    for key in _KEYS:
        level = signals[key]
        if type(level) is not str or level not in _LEVELS:
            raise ValueError("invalid pressure level")
        result[key] = level
    return result


def _event(value: object) -> tuple[str, tuple[str, ...], dict[str, int] | None]:
    if not isinstance(value, dict) or any(value.get(key, False) is not False for key in (
        "is_admission_grant", "is_execution_lease", "device_qualified",
        "pressure_signals_attested", "scope_membership_attested",
    )):
        raise ValueError("invalid event observation")
    state = value.get("state")
    reasons = value.get("reasons")
    if state not in ("observed", "baseline_required"):
        raise ValueError("invalid event state")
    if not isinstance(reasons, list) or len(reasons) > 32 or any(
        type(item) is not str or not 1 <= len(item) <= _MAX_REASON_LENGTH
        or not all(c.isascii() and (c.isalnum() or c == "_") for c in item)
        for item in reasons
    ):
        raise ValueError("invalid event reasons")
    deltas = value.get("event_deltas")
    if state == "baseline_required":
        if deltas is not None:
            raise ValueError("baseline cannot contain deltas")
        return state, tuple(reasons), None
    if not isinstance(deltas, dict) or set(deltas) != _EVENT_KEYS:
        raise ValueError("missing event counters")
    if any(type(v) is not int or not 0 <= v <= 2**63 - 1
           for v in deltas.values()):
        raise ValueError("invalid event delta")
    return state, tuple(reasons), deltas


class LongContextTelemetryFusion:
    """Process-local, bounded observation state machine.

    Each sample independently re-reads host, cgroup and event telemetry.
    State transitions: baseline_required -> observed -> unavailable on any
    invalid/slow/nonmonotonic observation. All states remain non-authorizing.
    A child process must construct a fresh monitor after fork.
    """

    def __init__(
        self,
        *,
        host_root: Path = Path("/proc/pressure"),
        cgroup_root: Path = Path("/sys/fs/cgroup"),
        max_sample_ns: int = 2_000_000_000,
        clock: Callable[[], int] = monotonic_ns,
    ):
        if type(max_sample_ns) is not int or not 1 <= max_sample_ns <= 10_000_000_000:
            raise ValueError("invalid sample duration")
        if not callable(clock):
            raise ValueError("invalid monotonic clock")
        self._host_root = host_root
        self._cgroup_root = cgroup_root
        self._events = CgroupEventMonitor(cgroup_root)
        self._clock = clock
        self._max_sample_ns = max_sample_ns
        self._pid = os.getpid()
        self._lock = Lock()
        self._last_ns: int | None = None

    def sample(self) -> dict[str, object]:
        if os.getpid() != self._pid:
            raise OSError("inherited telemetry monitor after fork")
        with self._lock:
            reasons: set[str] = set()
            sources: dict[str, dict[str, str]] = {}
            state = "unavailable"
            start = self._clock()
            valid_start = type(start) is int and start >= 0
            for name, observer, root in (
                ("host", observe_host_pressure, self._host_root),
                ("cgroup", observe_cgroup_pressure, self._cgroup_root),
            ):
                try:
                    sources[name] = _source(observer(root))
                except Exception:
                    sources[name] = {key: "unknown" for key in _KEYS}
                    reasons.add(name + "_observation_unavailable")
            try:
                event_state, event_reasons, deltas = _event(self._events.sample())
                reasons.update(event_reasons)
            except (OSError, ValueError, OverflowError, TypeError, KeyError):
                event_state, deltas = "baseline_required", None
                reasons.add("event_observation_unavailable")
            end = self._clock()
            if (not valid_start or type(end) is not int or end <= start
                    or end - start > self._max_sample_ns
                    or (self._last_ns is not None and start <= self._last_ns)):
                reasons.add("observation_clock_invalid")
                event_state, deltas = "baseline_required", None
                sources = {
                    name: {key: "unknown" for key in _KEYS}
                    for name in ("host", "cgroup")
                }
            self._last_ns = (max(self._last_ns or 0, end)
                             if type(end) is int and end >= 0
                             else self._last_ns)
            combined: dict[str, str] = {}
            for key in _KEYS:
                combined[key] = max(
                    (sources[name][key] for name in ("host", "cgroup")),
                    key=_LEVELS.__getitem__,
                )
            if deltas is not None:
                if deltas["oom"] or deltas["oom_kill"]:
                    combined["memory"] = max(
                        (combined["memory"], "critical"), key=_LEVELS.__getitem__,
                    )
                    reasons.add("memory_oom_event")
                if deltas["nr_throttled"]:
                    combined["cpu"] = max(
                        (combined["cpu"], "elevated"), key=_LEVELS.__getitem__,
                    )
                    reasons.add("cpu_throttle_event")
            for key, level in combined.items():
                if level != "normal":
                    reasons.add(key + "_" + level)
            if event_state == "observed" and not any(
                name + "_observation_unavailable" in reasons
                for name in ("host", "cgroup")
            ) and "observation_clock_invalid" not in reasons:
                state = "observed"
            elif event_state == "baseline_required" and not any(
                name + "_observation_unavailable" in reasons
                for name in ("host", "cgroup")
            ) and "observation_clock_invalid" not in reasons:
                state = "baseline_required"
            result: dict[str, object] = {
                "schema": "skeleton.ai.long-context-telemetry-fusion.v1",
                "state": state,
                "signals": combined,
                "reasons": sorted(reasons),
                "event_state": event_state,
                "event_deltas": deltas,
                "sources": ("host_psi", "cgroup_v2", "cgroup_events"),
                "cross_source_snapshot_atomic": False,
                "scope_membership_attested": False,
                "pressure_signals_attested": False,
                "device_qualified": False,
                "is_admission_grant": False,
                "is_execution_lease": False,
                "requires_live_backend_revalidation": True,
            }
            # Unkeyed correlation checksum, never an authenticity signature.
            payload = json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
            result["observation_digest"] = sha256(payload).hexdigest()
            return result


__all__ = ["LongContextTelemetryFusion"]
