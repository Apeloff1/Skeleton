"""Read-only, fail-closed Linux cgroup-v2 swap spill headroom.

Swap capacity is NOT RAM capacity. This probe never enables disk spill,
allocates swap, or qualifies a GPU. It only supplies a conservative bound
for a separate, explicitly authorized spill policy.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import stat
import sys

from .offline_cgroup_memory_headroom import (
    CgroupMemoryUnavailable,
    _open_cgroup_directory,
    _read_self_cgroup_path,
    _read_value,
)

_DEFAULT_CGROUP_ROOT = "/sys/fs/cgroup"
_MAX_COUNTER = (1 << 63) - 1


class CgroupSwapUnavailable(RuntimeError):
    """Swap counters were incomplete, unsafe or changed during observation."""


@dataclass(frozen=True, slots=True)
class CgroupSwapHeadroom:
    limit_bytes: int | None
    used_bytes: int
    headroom_bytes: int | None
    pressure_ppm: int
    spill_allowed: bool

    def __post_init__(self) -> None:
        if type(self.used_bytes) is not int or not 0 <= self.used_bytes <= _MAX_COUNTER:
            raise ValueError("invalid cgroup swap usage")
        if self.limit_bytes is None:
            if (self.headroom_bytes is not None
                    or type(self.pressure_ppm) is not int or self.pressure_ppm != 0
                    or type(self.spill_allowed) is not bool
                    or self.spill_allowed is not False):
                raise ValueError("unbounded swap is not measured spill authority")
            return
        limit = self.limit_bytes
        if type(limit) is not int or not 0 <= limit <= _MAX_COUNTER:
            raise ValueError("invalid cgroup swap limit")
        headroom = max(0, limit - self.used_bytes)
        pressure = (min(1_000_000, self.used_bytes * 1_000_000 // limit)
                    if limit else (1_000_000 if self.used_bytes else 0))
        reserve = max(4 << 20, limit // 20)
        if (type(self.headroom_bytes) is not int or self.headroom_bytes != headroom
                or type(self.pressure_ppm) is not int or self.pressure_ppm != pressure
                or type(self.spill_allowed) is not bool
                or self.spill_allowed != (headroom > reserve)):
            raise ValueError("inconsistent cgroup swap observation")


def _sample_directory(directory_fd: int) -> CgroupSwapHeadroom | None:
    """Double-read current and max from pinned inodes, choosing worst case."""
    try:
        try:
            before_used = _read_value(directory_fd, "memory.swap.current", allow_max=False)
            before_limit = _read_value(directory_fd, "memory.swap.max", allow_max=True)
        except FileNotFoundError:
            present = []
            for name in ("memory.swap.current", "memory.swap.max"):
                try:
                    os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                    present.append(name)
                except FileNotFoundError:
                    pass
            if present:
                raise CgroupSwapUnavailable("partial cgroup swap controller")
            return None
        after_used = _read_value(directory_fd, "memory.swap.current", allow_max=False)
        after_limit = _read_value(directory_fd, "memory.swap.max", allow_max=True)
    except (OSError, CgroupMemoryUnavailable) as exc:
        raise CgroupSwapUnavailable("untrusted cgroup swap counters") from exc
    if before_used is None or after_used is None:
        raise CgroupSwapUnavailable("missing cgroup swap usage")
    used = max(before_used, after_used)
    limits = [x for x in (before_limit, after_limit) if x is not None]
    if not limits:
        return CgroupSwapHeadroom(None, used, None, 0, False)
    limit = min(limits)
    headroom = max(0, limit - used)
    pressure = (min(1_000_000, used * 1_000_000 // limit)
                if limit else (1_000_000 if used else 0))
    return CgroupSwapHeadroom(
        limit, used, headroom, pressure,
        headroom > max(4 << 20, limit // 20),
    )


def probe_cgroup_swap_headroom(root: str | None = None) -> CgroupSwapHeadroom | None:
    """Observe every current process ancestor; unknown is never spare swap.

    A caller-selected root probes only that directory, for controlled fixtures.
    Production walks the process' unified cgroup ancestry using pinned FDs,
    revalidates the final inode and membership, and takes the tightest finite
    remaining headroom. A second probe is required at actual spill dispatch.
    """
    if sys.platform != "linux":
        return None
    if root is None:
        root = _DEFAULT_CGROUP_ROOT
    if type(root) is not str or not root.startswith("/") or "\x00" in root:
        raise ValueError("absolute cgroup root required")
    if any(part in (".", "..") for part in root.split("/")):
        raise ValueError("cgroup parent traversal forbidden")
    production = root == _DEFAULT_CGROUP_ROOT
    parts = _read_self_cgroup_path() if production else ()
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = _open_cgroup_directory(root)
    except OSError as exc:
        raise CgroupSwapUnavailable("cgroup swap root unavailable") from exc
    samples: list[CgroupSwapHeadroom] = []
    missing = False
    try:
        for depth in range(len(parts) + 1):
            sample = _sample_directory(fd)
            if sample is None:
                missing = True
            else:
                samples.append(sample)
            if depth < len(parts):
                try:
                    child_fd = os.open(parts[depth], flags, dir_fd=fd)
                except OSError as exc:
                    raise CgroupSwapUnavailable("cgroup swap membership unavailable") from exc
                os.close(fd)
                fd = child_fd
        if production:
            try:
                fresh_fd = _open_cgroup_directory(os.path.join(root, *parts))
            except OSError as exc:
                raise CgroupSwapUnavailable("cgroup swap membership replaced") from exc
            try:
                original = os.fstat(fd)
                fresh = os.fstat(fresh_fd)
                if (not stat.S_ISDIR(original.st_mode)
                        or (original.st_dev, original.st_ino)
                        != (fresh.st_dev, fresh.st_ino)):
                    raise CgroupSwapUnavailable("cgroup swap membership inode replaced")
            finally:
                os.close(fresh_fd)
    finally:
        os.close(fd)
    if production and _read_self_cgroup_path() != parts:
        raise CgroupSwapUnavailable("cgroup swap membership changed")
    if missing:
        # A missing ancestor could have a stricter limit than every sample.
        return None
    finite = [item for item in samples if item.headroom_bytes is not None]
    if not finite:
        return CgroupSwapHeadroom(
            None, max((x.used_bytes for x in samples), default=0), None, 0, False,
        )
    # Any ancestor that denies spill wins. A larger child cannot override it.
    denied = [item for item in finite if not item.spill_allowed]
    return min(denied or finite, key=lambda item: item.headroom_bytes)


__all__ = [
    "CgroupSwapHeadroom", "CgroupSwapUnavailable", "probe_cgroup_swap_headroom",
]
