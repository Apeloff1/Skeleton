"""Circuit breaker policy for isolating repeatedly failing swarm workers."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import RLock
from math import isfinite
from time import monotonic
from typing import Callable, Mapping


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(slots=True)
class Circuit:
    state: CircuitState = CircuitState.CLOSED
    failures: int = 0
    opened_at: float | None = None
    probes: int = 0
    probe_in_flight: bool = False


class CircuitBreaker:
    STATE_VERSION = 1

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        recovery_seconds: float = 30,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if failure_threshold < 1 or recovery_seconds <= 0:
            raise ValueError("invalid circuit breaker configuration")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.failure_threshold = failure_threshold
        self.recovery_seconds = float(recovery_seconds)
        self.clock = clock
        self._circuits: dict[str, Circuit] = {}
        self._lock = RLock()

    def circuit(self, key: str) -> Circuit:
        with self._lock:
            return self._circuits.setdefault(key, Circuit())

    def allow(self, key: str) -> bool:
        with self._lock:
            c = self._circuits.setdefault(key, Circuit())
            if c.state is CircuitState.OPEN:
                if c.opened_at is None or self._now() - c.opened_at < self.recovery_seconds:
                    return False
                c.state = CircuitState.HALF_OPEN
                c.probe_in_flight = False
            if c.state is CircuitState.HALF_OPEN:
                if c.probe_in_flight:
                    return False
                c.probe_in_flight = True
                c.probes += 1
                return True
            return True

    def success(self, key: str) -> Circuit:
        with self._lock:
            c = self._circuits.setdefault(key, Circuit())
            c.state = CircuitState.CLOSED
            c.failures = 0
            c.opened_at = None
            c.probe_in_flight = False
            return c

    def failure(self, key: str) -> Circuit:
        with self._lock:
            c = self._circuits.setdefault(key, Circuit())
            c.failures += 1
            if c.state is CircuitState.HALF_OPEN or c.failures >= self.failure_threshold:
                c.state = CircuitState.OPEN
                c.opened_at = self._now()
                c.probe_in_flight = False
            return c

    def snapshot(self) -> dict[str, dict[str, object]]:
        with self._lock:
            return {
                key: {
                    "state": value.state.value,
                    "failures": value.failures,
                    "opened_at": value.opened_at,
                    "probes": value.probes,
                    "probe_in_flight": value.probe_in_flight,
                }
                for key, value in sorted(self._circuits.items())
            }

    def _now(self) -> float:
        value = self.clock()
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RuntimeError("circuit clock must return a finite number")
        value = float(value)
        if not isfinite(value):
            raise RuntimeError("circuit clock must return a finite number")
        return value

    def export_state(self) -> dict[str, object]:
        """Serialize breaker state without persisting process-local monotonic epochs."""
        now = self._now()
        with self._lock:
            circuits: dict[str, dict[str, object]] = {}
            for key, value in sorted(self._circuits.items()):
                remaining = None
                if value.state is CircuitState.OPEN and value.opened_at is not None:
                    remaining = max(
                        0.0,
                        self.recovery_seconds - max(0.0, now - value.opened_at),
                    )
                circuits[key] = {
                    "state": value.state.value,
                    "failures": value.failures,
                    "probes": value.probes,
                    "probe_in_flight": value.probe_in_flight,
                    "recovery_remaining_seconds": remaining,
                }
            return {
                "version": self.STATE_VERSION,
                "failure_threshold": self.failure_threshold,
                "recovery_seconds": self.recovery_seconds,
                "circuits": circuits,
            }

    @classmethod
    def from_state(
        cls,
        state: Mapping[str, object],
        *,
        clock: Callable[[], float] = monotonic,
    ) -> "CircuitBreaker":
        required = {
            "version", "failure_threshold", "recovery_seconds", "circuits"
        }
        if not isinstance(state, Mapping) or set(state) != required:
            raise ValueError("invalid circuit breaker state envelope")
        if state.get("version") != cls.STATE_VERSION:
            raise ValueError("unsupported circuit breaker state version")
        failure_threshold = state.get("failure_threshold")
        recovery_seconds = state.get("recovery_seconds")
        if (
            isinstance(failure_threshold, bool)
            or not isinstance(failure_threshold, int)
            or failure_threshold < 1
        ):
            raise ValueError("invalid restored failure_threshold")
        if (
            isinstance(recovery_seconds, bool)
            or not isinstance(recovery_seconds, (int, float))
            or not isfinite(float(recovery_seconds))
            or float(recovery_seconds) <= 0
        ):
            raise ValueError("invalid restored recovery_seconds")
        breaker = cls(
            failure_threshold=failure_threshold,
            recovery_seconds=float(recovery_seconds),
            clock=clock,
        )
        raw_circuits = state.get("circuits")
        if not isinstance(raw_circuits, Mapping):
            raise ValueError("restored circuits must be a mapping")
        now = breaker._now()
        for raw_key, raw in raw_circuits.items():
            if not isinstance(raw_key, str) or not raw_key.strip():
                raise ValueError("circuit key must be normalized text")
            key = raw_key.strip()
            if key != raw_key or not isinstance(raw, Mapping):
                raise ValueError("invalid circuit record")
            fields = {
                "state", "failures", "probes", "probe_in_flight",
                "recovery_remaining_seconds",
            }
            if set(raw) != fields:
                raise ValueError("circuit record fields mismatch")
            try:
                state_value = CircuitState(str(raw.get("state")))
            except ValueError as exc:
                raise ValueError("invalid circuit state") from exc
            failures = raw.get("failures")
            probes = raw.get("probes")
            probe_in_flight = raw.get("probe_in_flight")
            if (
                isinstance(failures, bool) or not isinstance(failures, int)
                or failures < 0
                or isinstance(probes, bool) or not isinstance(probes, int)
                or probes < 0
                or not isinstance(probe_in_flight, bool)
            ):
                raise ValueError("invalid circuit counters")
            remaining_raw = raw.get("recovery_remaining_seconds")
            circuit = Circuit(
                state=state_value,
                failures=failures,
                probes=probes,
                probe_in_flight=False,
            )
            if state_value is CircuitState.OPEN:
                if (
                    isinstance(remaining_raw, bool)
                    or not isinstance(remaining_raw, (int, float))
                    or not isfinite(float(remaining_raw))
                    or float(remaining_raw) < 0
                    or float(remaining_raw) > breaker.recovery_seconds
                ):
                    raise ValueError("invalid circuit recovery remainder")
                remaining = float(remaining_raw)
                circuit.opened_at = now - (breaker.recovery_seconds - remaining)
            elif state_value is CircuitState.HALF_OPEN:
                # A crash makes the prior probe outcome unknowable. Re-open for
                # one full cooldown instead of accidentally treating it as safe.
                circuit.state = CircuitState.OPEN
                circuit.opened_at = now
            else:
                if remaining_raw is not None:
                    raise ValueError("closed circuit cannot retain cooldown")
                circuit.opened_at = None
            breaker._circuits[key] = circuit
        return breaker

