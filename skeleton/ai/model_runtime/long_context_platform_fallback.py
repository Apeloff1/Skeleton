"""Conservative CPU fallback planning for offline model runtimes.

No output grants execution, reserves memory, or qualifies CPU/GPU/Metal.
Backend authorization and live KV, tokenizer, memory, disk and pressure
revalidation remain mandatory even when a CPU candidate is observed.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
import platform
from threading import Lock
from time import monotonic_ns
from typing import Callable

from .long_context_pressure_latch import _inspect
from .long_context_spool import LongContextSpoolError
from .long_context_telemetry_fusion import LongContextTelemetryFusion

_SCHEMA = "skeleton.ai.long-context-platform-fallback.v1"
_MAX = 2**63 - 1


def _integer(value: object, name: str, minimum: int, maximum: int) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise LongContextSpoolError("invalid " + name)


def _name(value: object) -> None:
    if (type(value) is not str or not 1 <= len(value) <= 96
            or not value[0].isascii() or not value[0].isalnum()
            or any(not ch.isascii() or not (ch.isalnum() or ch in "_.-")
                   for ch in value)):
        raise LongContextSpoolError("invalid fallback identity")


@dataclass(frozen=True, slots=True)
class PlatformFallbackRequest:
    principal: str
    stream_id: str
    requested_device: str
    max_tokens: int
    requested_bytes: int

    def __post_init__(self) -> None:
        _name(self.principal)
        _name(self.stream_id)
        if type(self.requested_device) is not str or self.requested_device not in (
            "cpu", "gpu", "m_chip"
        ):
            raise LongContextSpoolError("invalid requested device")
        _integer(self.max_tokens, "fallback token budget", 1, 4096)
        _integer(self.requested_bytes, "fallback memory budget", 1, 1024**3)


@dataclass(frozen=True, slots=True)
class PlatformFallbackPolicy:
    required_normal_samples: int = 3
    cooldown_ns: int = 500_000_000
    max_sample_ns: int = 2_000_000_000
    allow_cpu_fallback: bool = True

    def __post_init__(self) -> None:
        _integer(self.required_normal_samples, "normal sample count", 2, 16)
        _integer(self.cooldown_ns, "fallback cooldown", 1, 10_000_000_000)
        _integer(self.max_sample_ns, "fallback observation duration", 1, 10_000_000_000)
        if type(self.allow_cpu_fallback) is not bool:
            raise LongContextSpoolError("invalid CPU fallback policy")


class LongContextPlatformFallback:
    """hold -> warming -> cpu_candidate; any anomaly -> hold.

    Per-process, per-request evidence only. Repeated normal samples never
    attest hardware, driver support, GPU memory or inference authorization.
    """

    def __init__(
        self, fusion: object | None = None, *,
        policy: PlatformFallbackPolicy = PlatformFallbackPolicy(),
        clock: Callable[[], int] = monotonic_ns,
    ) -> None:
        if not isinstance(policy, PlatformFallbackPolicy) or not callable(clock):
            raise LongContextSpoolError("invalid fallback dependency")
        if fusion is None:
            fusion = LongContextTelemetryFusion()
        if not callable(getattr(fusion, "sample", None)):
            raise LongContextSpoolError("invalid fallback observer")
        self._fusion, self._policy, self._clock = fusion, policy, clock
        self._pid = os.getpid()
        self._lock = Lock()
        self._last_ns: int | None = None
        self._hold_until = 0
        self._normal = 0
        self._request: PlatformFallbackRequest | None = None
        self._closed = False
        self._revocations = 0
        try:
            host = platform.system().lower()
        except Exception:
            host = "unknown"
        self._platform = host if host in ("linux", "darwin", "windows") else "unknown"

    @staticmethod
    def _safe(value: object) -> bool:
        # Share the canonical bounded, exact-field and checksum-verified
        # telemetry contract with the live planner and pressure latch.
        # The checksum detects corruption, never authenticates sensors.
        status, _signals, digest = _inspect(value)
        return status == "normal_observed" and digest is not None

    def _receipt(self, request: PlatformFallbackRequest,
                 state: str, reason: str) -> dict[str, object]:
        return {
            "schema": _SCHEMA, "state": state, "reason": reason,
            "requested_device": request.requested_device,
            "candidate_device": "cpu" if state == "cpu_candidate" else None,
            "platform_observed": self._platform,
            "stream_digest": sha256(request.stream_id.encode("ascii")).hexdigest(),
            "normal_samples": self._normal,
            "required_normal_samples": self._policy.required_normal_samples,
            "revocations": self._revocations,
            "hardware_qualification": "not_assessed",
            "device_qualified": False, "gpu_qualified": False,
            "m_chip_qualified": False, "is_admission_grant": False,
            "is_execution_lease": False, "is_memory_allocation": False,
            "cross_process_exclusive": False, "telemetry_attested": False,
            "restart_state_durable": False,
            "requires_live_backend_revalidation": True,
        }

    def _hold(self, timestamp: int | None) -> None:
        if self._normal:
            self._revocations += 1
        self._normal = 0
        if type(timestamp) is int and 0 <= timestamp <= _MAX:
            self._hold_until = min(
                _MAX, max(self._hold_until, timestamp + self._policy.cooldown_ns))

    def sample(self, request: PlatformFallbackRequest) -> dict[str, object]:
        if not isinstance(request, PlatformFallbackRequest):
            raise LongContextSpoolError("invalid fallback request")
        if os.getpid() != self._pid:
            raise LongContextSpoolError("fallback observer inherited after fork")
        with self._lock:
            if self._closed:
                raise LongContextSpoolError("fallback observer closed")
            if request != self._request:
                self._normal = 0
                self._request = request
            try:
                start = self._clock()
            except Exception:
                start = None
            if (type(start) is not int or not 0 <= start <= _MAX
                    or (self._last_ns is not None and start <= self._last_ns)):
                self._hold(None)
                return self._receipt(request, "hold", "clock_unverified")
            try:
                observation = self._fusion.sample()
            except Exception:
                observation = None
            try:
                end = self._clock()
            except Exception:
                end = None
            if (type(end) is not int or not start < end <= _MAX
                    or end - start > self._policy.max_sample_ns):
                self._hold(start)
                return self._receipt(request, "hold", "sample_duration_unverified")
            self._last_ns = end
            if not self._safe(observation):
                self._hold(end)
                return self._receipt(request, "hold", "telemetry_unverified")
            if self._platform == "unknown":
                self._hold(end)
                return self._receipt(request, "hold", "platform_unverified")
            if request.requested_device != "cpu" and not self._policy.allow_cpu_fallback:
                self._hold(end)
                return self._receipt(request, "hold", "cpu_fallback_disabled")
            if end < self._hold_until:
                self._normal = 0
                return self._receipt(request, "hold", "cooldown_active")
            self._normal = min(self._policy.required_normal_samples, self._normal + 1)
            if self._normal < self._policy.required_normal_samples:
                return self._receipt(request, "warming", "repeat_live_observation")
            return self._receipt(request, "cpu_candidate",
                                 "backend_must_independently_revalidate")

    def close(self) -> None:
        if os.getpid() != self._pid:
            raise LongContextSpoolError("fallback observer inherited after fork")
        with self._lock:
            self._normal = 0
            self._request = None
            self._closed = True


__all__ = ["PlatformFallbackRequest", "PlatformFallbackPolicy",
           "LongContextPlatformFallback"]
