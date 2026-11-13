"""Linux/X11 export: ELF executable, x86_64 or arm64."""
from __future__ import annotations

from pathlib import Path

from .base import PlatformSpec, read_head, require_in

ELF = b"\x7fELF"
_MACHINES = {0x3E: "x86_64", 0xB7: "arm64", 0x03: "x86_32", 0x28: "arm32"}


def elf_arch(head: bytes) -> str | None:
    if head[:4] != ELF or len(head) < 20:
        return None
    little = head[5] == 1
    mach = int.from_bytes(head[18:20], "little" if little else "big")
    return _MACHINES.get(mach, f"0x{mach:x}")


def check_artifact(path: Path) -> list[str]:
    arch = elf_arch(read_head(path))
    return [] if arch else [f"{path.name} is not an ELF executable"]


SPEC = PlatformSpec(
    name="Linux",
    extensions=(".x86_64", ".arm64", ".x86_32", ".arm32"),
    option_checks=(require_in("binary_format/architecture", ("x86_64", "x86_32", "arm64", "arm32", "rv64")),),
    artifact_check=check_artifact,
)
