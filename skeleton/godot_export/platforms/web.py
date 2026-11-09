"""Web export: .html shell + .wasm + .pck + .js side by side."""
from __future__ import annotations

from pathlib import Path

from .base import PlatformSpec, read_head, require_in

WASM = b"\0asm"


def check_artifact(path: Path) -> list[str]:
    problems = []
    stem = path.with_suffix("")
    for ext in (".js", ".wasm", ".pck"):
        if not stem.with_suffix(ext).is_file():
            problems.append(f"missing {stem.name}{ext}")
    wasm = stem.with_suffix(".wasm")
    if wasm.is_file() and read_head(wasm, 4) != WASM:
        problems.append(f"{wasm.name} lacks wasm magic")
    if path.is_file() and b"<html" not in read_head(path, 4096).lower():
        problems.append(f"{path.name} is not an HTML shell")
    return problems


SPEC = PlatformSpec(
    name="Web",
    extensions=(".html",),
    option_checks=(require_in("variant/thread_support", (True, False)),),
    artifact_check=check_artifact,
)
