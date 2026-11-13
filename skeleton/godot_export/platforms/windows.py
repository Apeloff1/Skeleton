"""Windows Desktop export: PE executable."""
from __future__ import annotations

from pathlib import Path

from .base import PlatformSpec, read_head, require_in, require_pattern

_MACHINES = {0x8664: "x86_64", 0x14C: "x86_32", 0xAA64: "arm64"}


def pe_arch(path: Path) -> str | None:
    head = read_head(path, 4096)
    if head[:2] != b"MZ" or len(head) < 0x40:
        return None
    off = int.from_bytes(head[0x3C:0x40], "little")
    if head[off:off + 4] != b"PE\0\0":
        return None
    mach = int.from_bytes(head[off + 4:off + 6], "little")
    return _MACHINES.get(mach, f"0x{mach:x}")


def check_artifact(path: Path) -> list[str]:
    return [] if pe_arch(path) else [f"{path.name} is not a PE executable"]


SPEC = PlatformSpec(
    name="Windows Desktop",
    extensions=(".exe",),
    option_checks=(
        require_in("binary_format/architecture", ("x86_64", "x86_32", "arm64")),
        require_pattern("application/file_version", r"(\d+\.){3}\d+|"),
        require_pattern("application/product_version", r"(\d+\.){3}\d+|"),
    ),
    artifact_check=check_artifact,
)
