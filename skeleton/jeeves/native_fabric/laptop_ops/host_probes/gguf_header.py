"""Read-only, eight-byte GGUF header observation on a canonical local file.

This does NOT verify a model's full content digest, tokenizer pairing,
installed source, legal rights or inference fitness. The canonical guarded
GGUF loader must independently attest those properties before use.

On POSIX only, the final path component is opened with O_NOFOLLOW and a
bounded regular-file read. Unknown platforms or symlink paths are held.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat

from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold

_MIN_HEADER = 8
_MAX_FILE_BYTES = 100 * 1024**3
_SUPPORTED_VERSIONS = frozenset((2, 3))
_REASONS = frozenset((
    "header_plausible", "unavailable", "short_file", "size_out_of_range",
    "wrong_magic", "unsupported_version",
))


def _checked_path(value: object) -> Path:
    if (not isinstance(value, Path) or not value.is_absolute()
            or ".." in value.parts or "\x00" in str(value)):
        raise LaptopGateHold("absolute canonical installed GGUF path required")
    return value


@dataclass(frozen=True, slots=True)
class GGUFHeaderObservation:
    reason: str
    size_bytes: int | None
    gguf_version: int | None
    descriptor_nofollow: bool

    def __post_init__(self) -> None:
        if self.reason not in _REASONS:
            raise LaptopGateHold("unrecognized bounded model header status")
        if type(self.descriptor_nofollow) is not bool:
            raise LaptopGateHold("strict descriptor observation flag required")
        if self.size_bytes is not None and (
            type(self.size_bytes) is not int
            or not 0 <= self.size_bytes <= _MAX_FILE_BYTES
        ):
            raise LaptopGateHold("invalid bounded GGUF file size")
        if self.gguf_version is not None and (
            type(self.gguf_version) is not int
            or not 0 <= self.gguf_version <= 0xFFFFFFFF
        ):
            raise LaptopGateHold("invalid GGUF header version")
        if self.reason == "header_plausible" and (
            self.size_bytes is None
            or self.size_bytes < _MIN_HEADER
            or self.gguf_version not in _SUPPORTED_VERSIONS
            or not self.descriptor_nofollow
        ):
            raise LaptopGateHold("incomplete plausible GGUF header observation")

    @property
    def header_plausible(self) -> bool:
        return self.reason == "header_plausible"

    def to_record(self) -> dict[str, object]:
        """No model path, data bytes, private prompt or installer approval."""
        return {
            "schema": "jeeves.laptop_ops.gguf_header.v1",
            "header_plausible": self.header_plausible,
            "reason": self.reason,
            "size_bytes": self.size_bytes,
            "gguf_version": self.gguf_version,
            "descriptor_nofollow": self.descriptor_nofollow,
            "complete_file_sha256_verified": False,
            "tokenizer_source_verified": False,
            "model_license_approved": False,
            "native_model_started": False,
            "physical_device_qualified": False,
            "release_certified": False,
        }


def probe_gguf_header(model_file: Path) -> GGUFHeaderObservation:
    """Inspect only eight bytes from a non-symlink regular file, never execute."""
    path = _checked_path(model_file)
    # Windows lacks this POSIX no-follow guarantee: never treat an ordinary
    # Windows path read as trustworthy installed-model verification.
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if os.name != "posix" or type(nofollow) is not int:
        return GGUFHeaderObservation("unavailable", None, None, False)
    flags = os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    fd: int | None = None
    try:
        fd = os.open(path, flags)
        observed = os.fstat(fd)
        if not stat.S_ISREG(observed.st_mode):
            return GGUFHeaderObservation("unavailable", None, None, True)
        file_size = observed.st_size
        if type(file_size) is not int or not 0 <= file_size <= _MAX_FILE_BYTES:
            return GGUFHeaderObservation("size_out_of_range", None, None, True)
        if file_size < _MIN_HEADER:
            return GGUFHeaderObservation("short_file", file_size, None, True)
        header = os.read(fd, _MIN_HEADER)
        if len(header) != _MIN_HEADER:
            return GGUFHeaderObservation("short_file", file_size, None, True)
        if header[:4] != b"GGUF":
            return GGUFHeaderObservation("wrong_magic", file_size, None, True)
        version = int.from_bytes(header[4:8], "little")
        if version not in _SUPPORTED_VERSIONS:
            return GGUFHeaderObservation(
                "unsupported_version", file_size, version, True
            )
        return GGUFHeaderObservation(
            "header_plausible", file_size, version, True
        )
    except (OSError, TypeError, ValueError, OverflowError):
        return GGUFHeaderObservation("unavailable", None, None, True)
    finally:
        if fd is not None:
            os.close(fd)


__all__ = ["GGUFHeaderObservation", "probe_gguf_header"]
