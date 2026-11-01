"""Descriptor-pinned, bounded Linux cgroup-v2 memory headroom observation.

A cgroup event counter is not a capacity measurement. This module reads the
current usage and BOTH hard and soft ceilings at a single cgroup directory.
It never changes cgroup limits, grants GPU capacity or reserves memory.
Missing v2 files mean unknown capacity; malformed or partially readable
files mean an unsafe measurement and MUST stop admission.
"""
from __future__ import annotations

from dataclasses import dataclass
import errno
import os
import stat
import sys

_MAX_COUNTER = (1 << 63) - 1
_MAX_READ = 128


class CgroupMemoryUnavailable(RuntimeError):
    """Linux cgroup memory capacity could not be trusted."""


@dataclass(frozen=True, slots=True)
class CgroupMemoryHeadroom:
    """One bounded observation, not a durable reservation or device proof."""

    limit_bytes: int | None
    used_bytes: int
    headroom_bytes: int | None
    pressure_ppm: int
    hard_hold: bool

    def __post_init__(self) -> None:
        if type(self.used_bytes) is not int or not 0 <= self.used_bytes <= _MAX_COUNTER:
            raise ValueError("invalid cgroup memory usage")
        if self.limit_bytes is None:
            if (self.headroom_bytes is not None
                    or type(self.pressure_ppm) is not int
                    or self.pressure_ppm != 0
                    or type(self.hard_hold) is not bool
                    or self.hard_hold):
                raise ValueError("unlimited cgroup cannot claim bounded headroom")
            return
        if (type(self.limit_bytes) is not int
                or not 1 <= self.limit_bytes <= _MAX_COUNTER
                or type(self.headroom_bytes) is not int
                or self.headroom_bytes != max(0, self.limit_bytes - self.used_bytes)
                or type(self.pressure_ppm) is not int
                or self.pressure_ppm != min(
                    1_000_000, self.used_bytes * 1_000_000 // self.limit_bytes
                )
                or type(self.hard_hold) is not bool
                or self.hard_hold != (
                    self.headroom_bytes <= max(64 << 20, self.limit_bytes // 20)
                )):
            raise ValueError("inconsistent cgroup memory observation")


def _read_value(dir_fd: int, name: str, *, allow_max: bool) -> int | None:
    """Open one sysfs inode without following symlinks; bound the entire read."""
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(name, flags, dir_fd=dir_fd)
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise CgroupMemoryUnavailable("cgroup memory counter open denied") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise CgroupMemoryUnavailable("cgroup memory counter is not regular")
        raw = os.read(fd, _MAX_READ + 1)
        if not raw or len(raw) > _MAX_READ:
            raise CgroupMemoryUnavailable("cgroup memory counter read exceeds budget")
        after = os.fstat(fd)
        current = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        if ((before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
                or (before.st_dev, before.st_ino) != (current.st_dev, current.st_ino)
                or not stat.S_ISREG(current.st_mode)):
            raise CgroupMemoryUnavailable("cgroup memory counter inode changed")
        try:
            value = raw.decode("ascii").strip()
        except UnicodeDecodeError as exc:
            raise CgroupMemoryUnavailable("non-ASCII cgroup memory counter") from exc
        if value == "max" and allow_max:
            return None
        if not value or not value.isascii() or not value.isdecimal():
            raise CgroupMemoryUnavailable("invalid cgroup memory counter")
        number = int(value)
        if number > _MAX_COUNTER:
            raise CgroupMemoryUnavailable("unbounded cgroup memory counter")
        return number
    except OSError as exc:
        raise CgroupMemoryUnavailable("cgroup memory counter changed during read") from exc
    finally:
        os.close(fd)


def _open_cgroup_directory(root: str) -> int:
    """Walk every absolute path component with O_NOFOLLOW, never resolve()."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    current = os.open("/", flags)
    try:
        for part in root.split("/"):
            if not part:
                continue
            following = os.open(part, flags, dir_fd=current)
            os.close(current)
            current = following
        if not stat.S_ISDIR(os.fstat(current).st_mode):
            raise CgroupMemoryUnavailable("cgroup directory inode not a directory")
        return current
    except BaseException:
        os.close(current)
        raise


def _probe_single_cgroup_memory_headroom(
    root: str, *, directory_fd: int | None = None,
) -> CgroupMemoryHeadroom | None:
    """Observe one Linux cgroup-v2 memory limit, never infer missing capacity.

    Reads current before and after the limits, taking the larger usage;
    reads both limits twice, taking the tighter ceiling. This is deliberately
    conservative across ordinary concurrent allocation and limit changes,
    but is not an atomic kernel snapshot. Execution must re-probe per token.
    """
    if sys.platform != "linux":
        return None
    if type(root) is not str or not root.startswith("/") or "\x00" in root:
        raise ValueError("absolute cgroup root required")
    if any(part in (".", "..") for part in root.split("/")):
        raise ValueError("cgroup parent traversal forbidden")
    try:
        directory = (os.dup(directory_fd) if directory_fd is not None
                     else _open_cgroup_directory(root))
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise CgroupMemoryUnavailable("cgroup directory unavailable") from exc
    try:
        try:
            used_before = _read_value(directory, "memory.current", allow_max=False)
            maximum_before = _read_value(directory, "memory.max", allow_max=True)
        except FileNotFoundError:
            # Cgroup v1 and hosts without the v2 memory controller are unknown.
            # An incomplete v2 pair must not become an unlimited reading.
            present = []
            for name in ("memory.current", "memory.max"):
                try:
                    os.stat(name, dir_fd=directory, follow_symlinks=False)
                    present.append(name)
                except FileNotFoundError:
                    pass
            if present:
                raise CgroupMemoryUnavailable("partial cgroup memory capacity")
            return None
        try:
            high_before = _read_value(directory, "memory.high", allow_max=True)
        except FileNotFoundError:
            high_before = None
        used_after = _read_value(directory, "memory.current", allow_max=False)
        maximum_after = _read_value(directory, "memory.max", allow_max=True)
        try:
            high_after = _read_value(directory, "memory.high", allow_max=True)
        except FileNotFoundError:
            high_after = None
        assert used_before is not None and used_after is not None
        used = max(used_before, used_after)
        limits = [n for n in (maximum_before, maximum_after, high_before, high_after)
                  if n is not None]
        if not limits:
            return CgroupMemoryHeadroom(None, used, None, 0, False)
        ceiling = min(limits)
        if ceiling <= 0:
            raise CgroupMemoryUnavailable("zero cgroup memory ceiling")
        headroom = max(0, ceiling - used)
        pressure = min(1_000_000, used * 1_000_000 // ceiling)
        # Preserve system headroom even if the host reports spare RAM.
        reserve = max(64 << 20, ceiling // 20)
        return CgroupMemoryHeadroom(
            ceiling, used, headroom, pressure, headroom <= reserve,
        )
    except (OSError, AssertionError) as exc:
        raise CgroupMemoryUnavailable("incomplete cgroup memory observation") from exc
    finally:
        os.close(directory)



# This is the conventional cgroup-v2 mount. A caller-selected fixture path is
# deliberately probed as a single directory, never interpreted as /proc data.
_DEFAULT_CGROUP_ROOT = "/sys/fs/cgroup"
_MAX_CGROUP_DEPTH = 32
_MAX_CGROUP_MEMBERSHIP_BYTES = 4096


def _read_self_cgroup_path() -> tuple[str, ...]:
    """Read bounded unified cgroup membership without trusting path traversal.

    The process can be moved between cgroups; the public probe compares the
    membership before and after sampling and callers re-probe before tokens.
    """
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open("/proc/self/cgroup", flags)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise CgroupMemoryUnavailable("cgroup membership is not regular")
            raw = os.read(fd, _MAX_CGROUP_MEMBERSHIP_BYTES + 1)
        finally:
            os.close(fd)
    except OSError as exc:
        raise CgroupMemoryUnavailable("cgroup membership unavailable") from exc
    if not raw or len(raw) > _MAX_CGROUP_MEMBERSHIP_BYTES:
        raise CgroupMemoryUnavailable("cgroup membership exceeds bound")
    try:
        lines = raw.decode("utf-8", errors="strict").splitlines()
    except UnicodeError as exc:
        raise CgroupMemoryUnavailable("invalid cgroup membership encoding") from exc
    unified = [line[3:] for line in lines if line.startswith("0::")]
    if len(unified) != 1 or not unified[0].startswith("/"):
        raise CgroupMemoryUnavailable("unique unified cgroup membership required")
    path = unified[0]
    if (not path or "\x00" in path
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in path)):
        raise CgroupMemoryUnavailable("invalid cgroup membership path")
    if path == "/":
        return ()
    parts = path[1:].split("/")
    if (len(parts) > _MAX_CGROUP_DEPTH
            or any(not part or part in (".", "..") for part in parts)):
        raise CgroupMemoryUnavailable("unsafe or overdeep cgroup membership")
    return tuple(parts)


def probe_cgroup_memory_headroom(
    root: str | None = None,
) -> CgroupMemoryHeadroom | None:
    """Conservatively bound the CURRENT process by every cgroup ancestor.

    A host-root-only sample can miss a container's much smaller child limit.
    For the canonical mount, observe the current process membership and each
    ancestor from root through leaf. The tightest finite headroom wins; any
    ancestor hard hold wins over all apparent free RAM. Unknown or changing
    membership fails closed. This is still an observation, not a reservation.
    """
    if root is None:
        root = _DEFAULT_CGROUP_ROOT
    if sys.platform != "linux":
        return None
    if root != _DEFAULT_CGROUP_ROOT:
        return _probe_single_cgroup_memory_headroom(root)
    parts = _read_self_cgroup_path()
    samples: list[CgroupMemoryHeadroom] = []
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        current_fd = _open_cgroup_directory(root)
    except OSError as exc:
        raise CgroupMemoryUnavailable("cgroup mount root unavailable") from exc
    try:
        # Keep the same pinned ancestor chain throughout sampling. Never
        # reconstruct each child path from names between samples.
        for depth in range(len(parts) + 1):
            observation = _probe_single_cgroup_memory_headroom(
                root, directory_fd=current_fd,
            )
            if observation is None:
                raise CgroupMemoryUnavailable("unmeasured cgroup ancestor capacity")
            samples.append(observation)
            if depth < len(parts):
                try:
                    child_fd = os.open(parts[depth], flags, dir_fd=current_fd)
                except OSError as exc:
                    raise CgroupMemoryUnavailable("cgroup membership leaf unavailable") from exc
                os.close(current_fd)
                current_fd = child_fd
        # A renamed/replaced leaf can leave a valid but detached directory FD.
        # Verify the canonical path still resolves to the sampled leaf.
        try:
            fresh_fd = _open_cgroup_directory(os.path.join(root, *parts))
        except OSError as exc:
            raise CgroupMemoryUnavailable("cgroup membership path replaced") from exc
        try:
            before = os.fstat(current_fd)
            after = os.fstat(fresh_fd)
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise CgroupMemoryUnavailable("cgroup membership inode replaced")
        finally:
            os.close(fresh_fd)
    finally:
        os.close(current_fd)
    if _read_self_cgroup_path() != parts:
        raise CgroupMemoryUnavailable("process cgroup membership changed")
    finite = [item for item in samples if item.headroom_bytes is not None]
    if not finite:
        # Every ancestor explicitly reported max; never invent finite capacity.
        return CgroupMemoryHeadroom(
            None, max(item.used_bytes for item in samples), None, 0, False,
        )
    held = [item for item in finite if item.hard_hold]
    if held:
        # A large parent may be inside its own reserve even if the child is not.
        # The live sampler will admit zero slots for this result.
        return min(held, key=lambda item: item.headroom_bytes)
    return min(finite, key=lambda item: item.headroom_bytes)




__all__ = [
    "CgroupMemoryHeadroom", "CgroupMemoryUnavailable",
    "probe_cgroup_memory_headroom",
]
