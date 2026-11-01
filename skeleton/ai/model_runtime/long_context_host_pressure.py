"""Read-only bounded host PSI observation for offline long-context diagnostics.

A kernel counter is not an execution lease, identity proof, hardware
qualification or authorization. Thermal and energy remain UNKNOWN until
separately qualified telemetry is available. No device is admitted here.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import os
from pathlib import Path
import re
import stat

_MAX_PSI_BYTES = 4096
_PSI_LINE = re.compile(
    rb"(some|full) avg10=([0-9]+(?:\.[0-9]{1,2})?) "
    rb"avg60=([0-9]+(?:\.[0-9]{1,2})?) "
    rb"avg300=([0-9]+(?:\.[0-9]{1,2})?) total=([0-9]+)"
)


def _secure_directory(path: Path) -> int:
    """Open every ancestor without following a symlink, with bounded depth."""
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise OSError("secure pressure observation unavailable")
    parts = Path(os.path.abspath(path)).parts
    if not 2 <= len(parts) <= 32:
        raise OSError("invalid pressure directory depth")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(parts[0], flags)
    try:
        for part in parts[1:]:
            if not part or part in (".", ".."):
                raise OSError("invalid pressure directory")
            nxt = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = nxt
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.geteuid()):
            raise OSError("untrusted pressure directory")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read_psi(directory: int, name: str) -> bytes:
    """Pin the PSI file and reject path swaps, symlinks and oversized reads."""
    if name not in ("cpu", "memory"):
        raise ValueError("unsupported PSI source")
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(name, flags, dir_fd=directory)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_uid not in (0, os.geteuid()):
            raise OSError("untrusted PSI inode")
        raw = os.read(fd, _MAX_PSI_BYTES + 1)
        after = os.fstat(fd)
        named = os.stat(name, dir_fd=directory, follow_symlinks=False)
        identity = lambda x: (x.st_dev, x.st_ino, x.st_mode, x.st_uid)
        if (len(raw) > _MAX_PSI_BYTES or not raw
                or identity(before) != identity(after)
                or identity(after) != identity(named)):
            raise OSError("PSI file changed or exceeded byte bound")
        return raw
    finally:
        os.close(fd)


def _avg10(raw: bytes) -> Decimal:
    """Strictly parse one kernel PSI 'some' record; reject duplicate fields."""
    if type(raw) is not bytes:
        raise ValueError("invalid PSI payload")
    lines = raw.splitlines()
    if not 1 <= len(lines) <= 2:
        raise ValueError("invalid PSI line count")
    seen = set()
    avg = None
    for line in lines:
        match = _PSI_LINE.fullmatch(line)
        if match is None or match.group(1) in seen:
            raise ValueError("malformed PSI record")
        seen.add(match.group(1))
        for value in match.group(2, 3, 4):
            try:
                numeric = Decimal(value.decode("ascii"))
            except (InvalidOperation, UnicodeError) as exc:
                raise ValueError("invalid PSI number") from exc
            if not 0 <= numeric <= 100:
                raise ValueError("PSI percentage out of range")
        if match.group(1) == b"some":
            avg = Decimal(match.group(2).decode("ascii"))
    if avg is None:
        raise ValueError("PSI some record missing")
    return avg


def _state(avg: Decimal, *, elevated: int, critical: int) -> str:
    if avg >= critical:
        return "critical"
    if avg >= elevated:
        return "elevated"
    return "normal"


def observe_host_pressure(
    pressure_root: Path = Path("/proc/pressure"),
) -> dict[str, object]:
    """Observe Linux CPU/memory pressure; all missing evidence holds closed.

    pressure_root is an explicit test seam, not an operator CLI input.
    This never claims thermal/energy safety, GPU readiness or admission.
    """
    cpu = memory = "unknown"
    source = "unavailable"
    if os.name == "posix" and os.path.exists("/proc/pressure"):
        # The default path is the kernel source. Explicit test roots remain
        # read-only fixtures, never authorization-capable replacements.
        directory = -1
        try:
            directory = _secure_directory(pressure_root)
            pinned = os.fstat(directory)
            cpu = _state(_avg10(_read_psi(directory, "cpu")),
                         elevated=10, critical=50)
            memory = _state(_avg10(_read_psi(directory, "memory")),
                            elevated=5, critical=20)
            reopened = _secure_directory(pressure_root)
            try:
                visible = os.fstat(reopened)
                if (pinned.st_dev, pinned.st_ino) != (visible.st_dev, visible.st_ino):
                    raise OSError("pressure directory replaced")
            finally:
                os.close(reopened)
            source = "linux_proc_psi_observation"
        except (OSError, ValueError, OverflowError):
            cpu = memory = "unknown"
            source = "unavailable"
        finally:
            if directory >= 0:
                os.close(directory)
    signals = {"cpu": cpu, "memory": memory, "thermal": "unknown",
               "energy": "unknown"}
    holds = sorted(key + "_" + value for key, value in signals.items()
                   if value != "normal")
    return {
        "schema": "skeleton.ai.long-context-host-pressure.v1",
        "source": source,
        "signals": signals,
        "hold_reasons": holds,
        "pressure_signals_attested": False,
        "device_qualified": False,
        "is_admission_grant": False,
        "is_execution_lease": False,
        "requires_live_backend_revalidation": True,
    }


__all__ = ["observe_host_pressure"]
