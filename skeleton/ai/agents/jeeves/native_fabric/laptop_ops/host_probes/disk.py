"""Advisory local state-storage free space measured without writing a file.

POSIX uses a descriptor-anchored final directory, prevents final-component
symlink following and reads fstatvfs only. Windows falls back to read-only
disk_usage metadata and explicitly does not claim descriptor anchoring.
This is not an installed model, filesystem-custody or release attestation.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import stat

from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold

_MAX_RESERVATION = 1 << 40
_MAX_OBSERVED_BYTES = (1 << 63) - 1


def _safe_directory(path: object) -> Path:
    if (not isinstance(path, Path) or not path.is_absolute()
            or ".." in path.parts or "\x00" in str(path)):
        raise LaptopGateHold("absolute canonical storage directory required")
    return path


def _posix_disk(path: Path) -> tuple[int, int] | None:
    """Do not follow the final symlink or retain filesystem descriptors."""
    if not all(hasattr(os, name) for name in
               ("O_NOFOLLOW", "O_DIRECTORY", "fstatvfs", "fstat")):
        return None
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY
    flags |= getattr(os, "O_CLOEXEC", 0)
    fd: int | None = None
    try:
        fd = os.open(path, flags)
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            return None
        vfs = os.fstatvfs(fd)
        return int(vfs.f_blocks) * int(vfs.f_frsize), (
            int(vfs.f_bavail) * int(vfs.f_frsize)
        )
    except (OSError, TypeError, ValueError, OverflowError):
        return None
    finally:
        if fd is not None:
            os.close(fd)


def _windows_disk(path: Path) -> tuple[int, int] | None:
    """Advisory metadata only; not a Windows path-security proof."""
    try:
        if path.is_symlink() or not path.is_dir():
            return None
        size = shutil.disk_usage(path)
        return int(size.total), int(size.free)
    except (OSError, TypeError, ValueError):
        return None


@dataclass(frozen=True, slots=True)
class DiskObservation:
    reserved_bytes: int
    total_bytes: int | None
    available_bytes: int | None
    source: str

    def __post_init__(self) -> None:
        if (type(self.reserved_bytes) is not int
                or not 1 <= self.reserved_bytes <= _MAX_RESERVATION):
            raise LaptopGateHold("finite local state reservation required")
        if self.source not in ("posix_fstatvfs", "windows_disk_usage", "unknown"):
            raise LaptopGateHold("unrecognized filesystem observation source")
        if (self.total_bytes is None) != (self.available_bytes is None):
            raise LaptopGateHold("partial filesystem space observation")
        if self.total_bytes is None:
            if self.source != "unknown":
                raise LaptopGateHold("unknown filesystem must be marked unknown")
        elif (type(self.total_bytes) is not int
                or type(self.available_bytes) is not int
                or self.total_bytes <= 0
                or not 0 <= self.available_bytes <= self.total_bytes <= _MAX_OBSERVED_BYTES
                or self.source == "unknown"):
            raise LaptopGateHold("invalid filesystem capacity counters")

    @property
    def fits_observed_space(self) -> bool:
        return (self.available_bytes is not None
                and self.reserved_bytes <= self.available_bytes)

    def to_record(self) -> dict[str, object]:
        """Never disclose the local state directory or claim model approval."""
        return {
            "schema": "jeeves.laptop_ops.host_storage.v1",
            "reserved_bytes": self.reserved_bytes,
            "total_bytes": self.total_bytes,
            "available_bytes": self.available_bytes,
            "source": self.source,
            "final_directory_descriptor_anchored": self.source == "posix_fstatvfs",
            "fits_observed_space": self.fits_observed_space,
            "filesystem_custody_qualified": False,
            "native_model_started": False,
            "physical_device_qualified": False,
            "release_certified": False,
        }


def observe_disk(directory: Path, reserved_bytes: int) -> DiskObservation:
    """Fail closed on missing storage, unknown metadata or invalid request."""
    path = _safe_directory(directory)
    if type(reserved_bytes) is not int or not 1 <= reserved_bytes <= _MAX_RESERVATION:
        raise LaptopGateHold("invalid native storage reservation")
    windows = os.name == "nt"
    raw = _windows_disk(path) if windows else _posix_disk(path)
    label = "windows_disk_usage" if windows else "posix_fstatvfs"
    if raw is not None:
        try:
            return DiskObservation(reserved_bytes, raw[0], raw[1], label)
        except (TypeError, ValueError, IndexError, LaptopGateHold):
            pass
    return DiskObservation(reserved_bytes, None, None, "unknown")


__all__ = ["DiskObservation", "observe_disk"]
