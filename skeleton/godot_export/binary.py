"""Godot binary pin verification (GFB-01 / GFB-02, GF-P0-134).

The native smoke uses Godot 4.7.2 pinned by sha256; certification must refuse
to vouch for results produced by a different engine.
"""
from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import version as gv
from .report import CaseResult
from .runner import GodotRunner

DEFAULT_PIN_VERSION = "4.7.2"
ENV_BINARY = "GODOT_BIN"


@dataclass(frozen=True)
class Pin:
    version: str = DEFAULT_PIN_VERSION
    sha256: str | None = None


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def locate(explicit: str | None = None) -> str | None:
    for cand in (explicit, os.environ.get(ENV_BINARY)):
        if cand and (Path(cand).is_file() or shutil.which(cand)):
            return cand
    for name in ("godot", "godot4", "Godot_v4"):
        found = shutil.which(name)
        if found:
            return found
    return None


def check_version(runner: GodotRunner, pin: Pin, cwd: Path) -> CaseResult:
    res = runner.version(cwd)
    if not res.ok:
        return CaseResult("GFB-01", False, {"exit": res.code, "tail": res.output[-300:]})
    line = res.output.strip().splitlines()[0] if res.output.strip() else ""
    try:
        v = gv.parse(line)
    except ValueError:
        return CaseResult("GFB-01", False, {"unparseable": line[:120]})
    want = gv.parse(pin.version)
    ok = (v.major, v.minor, v.patch) == (want.major, want.minor, want.patch) and v.status == want.status
    return CaseResult("GFB-01", ok, {"actual": line[:120], "pin": pin.version})


def check_sha(binary: Path, pin: Pin) -> CaseResult:
    if pin.sha256 is None:
        return CaseResult("GFB-02", True, "no sha256 pin configured")
    if not binary.is_file():
        return CaseResult("GFB-02", False, f"binary not a file: {binary}")
    actual = sha256_file(binary)
    return CaseResult("GFB-02", actual == pin.sha256.lower(), {"actual": actual, "pin": pin.sha256})
