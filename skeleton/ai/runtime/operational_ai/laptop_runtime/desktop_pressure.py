"""Observed runtime pressure supervisor for an isolated local GGUF child.

A live local model is not safe merely because admission succeeded before the
first token. The OS, cgroup quota, state filesystem and process residency
can change while the native worker is running. This module monitors those
actual values and, when operator-enabled, terminally revokes a process under
sustained pressure rather than risking machine-wide OOM or corrupt SQLite.

This is NOT a GPU/VRAM governor, a swap/offload engine, a model speed claim,
a device qualification or a source of implicit authority to retry inference.
Every untrusted measurement has finite bounds; unknown telemetry is a hold.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat
import subprocess
import threading
import time
from typing import Callable

from .device_observer import inspect_device
from .desktop_capacity_plan import observe_cgroup, CgroupObservation

MIB = 1024 * 1024
GIB = 1024 * MIB
MAX_SYSTEM_BYTES = (1 << 53) - 1


class DesktopPressureHold(ValueError):
    """The local child cannot be monitored under bounded system pressure."""


@dataclass(frozen=True, slots=True)
class PressurePolicy:
    minimum_available_ram_bytes: int = 512 * MIB
    minimum_state_disk_bytes: int = 256 * MIB
    maximum_native_rss_bytes: int = 0
    sample_interval_ms: int = 500
    consecutive_critical_samples: int = 2
    maximum_observation_errors: int = 1

    def __post_init__(self):
        for name, lo, hi in (
            ("minimum_available_ram_bytes", 64 * MIB, 16 * GIB),
            ("minimum_state_disk_bytes", 64 * MIB, 16 * GIB),
            ("maximum_native_rss_bytes", 0, 20_000_000_000),
            ("sample_interval_ms", 100, 5000),
            ("consecutive_critical_samples", 1, 8),
            ("maximum_observation_errors", 0, 3),
        ):
            value = getattr(self, name)
            if type(value) is not int or not lo <= value <= hi:
                raise DesktopPressureHold("invalid finite native pressure " + name)


@dataclass(frozen=True, slots=True)
class PressureSample:
    observed_monotonic_ms: int
    host_available_bytes: int
    cgroup_available_bytes: int | None
    effective_available_bytes: int
    state_disk_available_bytes: int
    native_rss_bytes: int
    native_start_ticks: int
    pressure_reasons: tuple[str, ...]

    def __post_init__(self):
        if type(self.observed_monotonic_ms) is not int or self.observed_monotonic_ms < 0:
            raise DesktopPressureHold("invalid monotonic pressure timestamp")
        for name in (
            "host_available_bytes", "effective_available_bytes",
            "state_disk_available_bytes", "native_rss_bytes", "native_start_ticks",
        ):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= MAX_SYSTEM_BYTES:
                raise DesktopPressureHold("untyped or unreasonable pressure measurement")
        if self.cgroup_available_bytes is not None and (
            type(self.cgroup_available_bytes) is not int
            or not 0 <= self.cgroup_available_bytes <= MAX_SYSTEM_BYTES
        ):
            raise DesktopPressureHold("invalid cgroup headroom")
        if (
            type(self.pressure_reasons) is not tuple
            or any(reason not in (
                "host-ram-floor", "cgroup-ram-floor",
                "native-resident-ceiling", "state-disk-floor",
            ) for reason in self.pressure_reasons)
        ):
            raise DesktopPressureHold("unknown pressure reason cannot be trusted")

    @property
    def critical(self) -> bool:
        return bool(self.pressure_reasons)

    def public_receipt(self) -> dict[str, object]:
        return {
            "schema": "jeeves.desktop.native-pressure-observation.v1",
            "host_available_bytes": self.host_available_bytes,
            "cgroup_available_bytes": self.cgroup_available_bytes,
            "effective_available_bytes": self.effective_available_bytes,
            "state_disk_available_bytes": self.state_disk_available_bytes,
            "native_rss_bytes": self.native_rss_bytes,
            "pressure_reasons": list(self.pressure_reasons),
            "measurement_only": True,
            "device_qualified": False,
            "release_certified": False,
        }


def _kernel_text(path: Path, *, maximum_bytes: int = 256) -> str:
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise DesktopPressureHold("POSIX nofollow procfs required")
    descriptor = os.open(
        path, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        st = os.fstat(descriptor)
        if not stat.S_ISREG(st.st_mode):
            raise DesktopPressureHold("native pressure telemetry not regular kernel text")
        raw = os.read(descriptor, maximum_bytes + 1)
        if not 1 <= len(raw) <= maximum_bytes:
            raise DesktopPressureHold("missing or unbounded procfs response")
        return raw.decode("ascii", "strict").strip()
    except (UnicodeError, OSError) as exc:
        raise DesktopPressureHold("invalid kernel pressure text") from exc
    finally:
        os.close(descriptor)


def _process_start_ticks(pid: int) -> int:
    """Read Linux start time to fence recycled process IDs at observation."""
    if type(pid) is not int or not 1 <= pid <= 1 << 30:
        raise DesktopPressureHold("untrusted native child PID")
    text = _kernel_text(Path("/proc") / str(pid) / "stat", maximum_bytes=4096)
    if not text.startswith(str(pid) + " ("):
        raise DesktopPressureHold("native PID changed during kernel inspection")
    closing = text.rfind(") ")
    if closing < 0:
        raise DesktopPressureHold("malformed native process kernel identity")
    fields = text[closing + 2:].split()
    # /proc/<pid>/stat field 22 = starttime, after pid+comm field 3 is index 0.
    if len(fields) < 20 or not fields[19].isdigit():
        raise DesktopPressureHold("native start time unavailable")
    value = int(fields[19])
    if not 1 <= value <= MAX_SYSTEM_BYTES:
        raise DesktopPressureHold("invalid native startup epoch")
    return value


def _resident_bytes(pid: int) -> int:
    statm = _kernel_text(Path("/proc") / str(pid) / "statm", maximum_bytes=128)
    tokens = statm.split()
    if len(tokens) < 2 or not tokens[1].isdigit():
        raise DesktopPressureHold("unavailable native resident page count")
    pages = int(tokens[1])
    size = os.sysconf("SC_PAGE_SIZE")
    if type(size) is not int or size < 512 or size > 65536:
        raise DesktopPressureHold("invalid OS memory page size")
    result = pages * size
    if not 0 <= result <= MAX_SYSTEM_BYTES:
        raise DesktopPressureHold("implausible native resident usage")
    return result


def observe_pressure(
    *, pid: int, original_start_ticks: int,
    state_dir: Path, policy: PressurePolicy,
) -> PressureSample:
    """Observe current actual host/cgroup/disk/native RSS; never guess GPU."""
    if type(policy) is not PressurePolicy:
        raise DesktopPressureHold("typed native pressure policy required")
    if (
        not isinstance(state_dir, Path)
        or not state_dir.is_absolute()
        or ".." in state_dir.parts
        or chr(0) in str(state_dir)
    ):
        raise DesktopPressureHold("absolute private SQLite state root required")
    if _process_start_ticks(pid) != original_start_ticks:
        raise DesktopPressureHold("native process epoch changed")
    host = inspect_device(state_dir)
    control = observe_cgroup()
    if (
        type(host) is not dict
        or host.get("measurement_only") is not True
        or host.get("qualified_device") is not False
        or type(control) is not CgroupObservation
    ):
        raise DesktopPressureHold("typed device/cgroup observations unavailable")
    available = host.get("memory_available_bytes")
    disk = host.get("state_storage_available_bytes")
    cgroup_free = control.memory_available_bytes
    if (
        type(available) is not int
        or not 0 <= available <= MAX_SYSTEM_BYTES
        or type(disk) is not int
        or not 0 <= disk <= MAX_SYSTEM_BYTES
    ):
        raise DesktopPressureHold("unknown live RAM or disk pressure")
    effective = min(
        available, cgroup_free if cgroup_free is not None else available,
    )
    resident = _resident_bytes(pid)
    if _process_start_ticks(pid) != original_start_ticks:
        raise DesktopPressureHold("native process replaced during resource sample")
    reasons = []
    if available < policy.minimum_available_ram_bytes:
        reasons.append("host-ram-floor")
    if cgroup_free is not None and cgroup_free < policy.minimum_available_ram_bytes:
        reasons.append("cgroup-ram-floor")
    if disk < policy.minimum_state_disk_bytes:
        reasons.append("state-disk-floor")
    if policy.maximum_native_rss_bytes and resident > policy.maximum_native_rss_bytes:
        reasons.append("native-resident-ceiling")
    return PressureSample(
        observed_monotonic_ms=int(time.monotonic() * 1000),
        host_available_bytes=available,
        cgroup_available_bytes=cgroup_free,
        effective_available_bytes=effective,
        state_disk_available_bytes=disk,
        native_rss_bytes=resident,
        native_start_ticks=original_start_ticks,
        pressure_reasons=tuple(reasons),
    )


class NativePressureSupervisor:
    """Bounded single-child lifecycle observer with monotonic terminal holds.

    It never starts or restarts native inference; its only active capability
    is calling the parent-provided revoke callback for the same Popen child.
    Caller owns the isolated child and is responsible for terminating it.
    """

    def __init__(
        self, process: subprocess.Popen, *, state_dir: Path,
        policy: PressurePolicy, revoke: Callable[[str], None],
        observation=observe_pressure,
    ):
        if (
            not isinstance(process, subprocess.Popen)
            or type(policy) is not PressurePolicy
            or not callable(revoke)
            or not callable(observation)
        ):
            raise DesktopPressureHold("typed owned native subprocess required")
        if not isinstance(state_dir, Path) or not state_dir.is_absolute():
            raise DesktopPressureHold("canonical native state directory required")
        self.process = process
        self.state_dir = state_dir
        self.policy = policy
        self._revoke = revoke
        self._observation = observation
        self._stop_event = threading.Event()
        self._mutex = threading.RLock()
        self._started = False
        self._thread: threading.Thread | None = None
        self._reason: str | None = None
        self._last: PressureSample | None = None
        self._critical_count = 0
        self._errors = 0
        self._start_ticks: int | None = None

    @property
    def reason(self) -> str | None:
        with self._mutex:
            return self._reason

    @property
    def latest(self) -> dict[str, object] | None:
        with self._mutex:
            return self._last.public_receipt() if self._last is not None else None

    def _observe(self) -> PressureSample:
        if self.process.poll() is not None:
            raise DesktopPressureHold("native child already stopped")
        sample = self._observation(
            pid=self.process.pid,
            original_start_ticks=self._start_ticks,
            state_dir=self.state_dir,
            policy=self.policy,
        )
        if type(sample) is not PressureSample:
            raise DesktopPressureHold("untyped native pressure sample")
        if self.process.poll() is not None:
            raise DesktopPressureHold("native child exited during observation")
        return sample

    def _admit(self, sample: PressureSample) -> str | None:
        with self._mutex:
            self._last = sample
            self._errors = 0
            if sample.critical:
                self._critical_count += 1
            else:
                self._critical_count = 0
            if self._critical_count >= self.policy.consecutive_critical_samples:
                return sample.pressure_reasons[0]
        return None

    def _fatal(self, reason: str):
        allowed = {
            "host-ram-floor", "cgroup-ram-floor", "state-disk-floor",
            "native-resident-ceiling", "telemetry-unavailable",
        }
        if reason not in allowed:
            reason = "telemetry-unavailable"
        with self._mutex:
            if self._reason is not None or self._stop_event.is_set():
                return
            self._reason = reason
            self._stop_event.set()
        try:
            # Host callback revokes exactly the original isolated Popen
            # object and preserves any uncertain SQLite model effect.
            self._revoke(reason)
        except BaseException:
            pass

    def start(self) -> PressureSample:
        with self._mutex:
            if self._started:
                raise DesktopPressureHold("native pressure guard already started")
            self._started = True
        try:
            self._start_ticks = _process_start_ticks(self.process.pid)
            first = self._observe()
            self._admit(first)
            if first.critical:
                # If the first sample is critical, do not accept a new
                # native model session even before hysteresis completes.
                self._fatal(first.pressure_reasons[0])
                raise DesktopPressureHold("native admitted without RAM/disk headroom")
            self._thread = threading.Thread(
                target=self._monitor, name="jeeves-native-pressure-guard",
                daemon=True,
            )
            self._thread.start()
            return first
        except BaseException:
            self.stop()
            raise

    def _monitor(self):
        while not self._stop_event.wait(self.policy.sample_interval_ms / 1000.0):
            if self.process.poll() is not None:
                return
            try:
                sample = self._observe()
                reason = self._admit(sample)
                if reason is not None:
                    self._fatal(reason)
                    return
            except BaseException:
                with self._mutex:
                    self._errors += 1
                    exceeded = self._errors > self.policy.maximum_observation_errors
                if exceeded:
                    self._fatal("telemetry-unavailable")
                    return

    def stop(self) -> None:
        self._stop_event.set()
        # Never join here: parent shutdown may be invoked by the supervisor's
        # own callback, and child cancellation must not deadlock the UI.


__all__ = [
    "DesktopPressureHold", "PressurePolicy", "PressureSample",
    "NativePressureSupervisor", "observe_pressure",
]
