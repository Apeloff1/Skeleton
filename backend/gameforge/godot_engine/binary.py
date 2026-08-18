"""
godot_engine.binary — locate, verify, and probe the in-repo Godot binary.

Resolution order:
    1. ``GODOT_BINARY`` env var (absolute path override)
    2. ``<backend>/godot`` — the binary committed in this repo
    3. ``godot`` on PATH (developer machines with a system install)

The binary is verified executable (chmod +x applied if the checkout lost the
bit) and probed with ``--version`` on first use; the result is cached.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_BINARY = _BACKEND_DIR / "godot"


@dataclass
class GodotBinary:
    """A verified Godot executable."""

    path: Path
    source: str                       # "env" | "repo" | "path"
    version: str | None = None
    verified: bool = False
    notes: list[str] = field(default_factory=list)

    def ensure_executable(self) -> None:
        mode = self.path.stat().st_mode
        if not mode & stat.S_IXUSR:
            self.path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            self.notes.append("restored +x permission bit")

    def probe(self, timeout: int = 30) -> str:
        """Run ``--version`` and cache the reported version string."""
        if self.version:
            return self.version
        self.ensure_executable()
        out = subprocess.run(
            [str(self.path), "--version"],
            capture_output=True, text=True, timeout=timeout,
        )
        if out.returncode != 0:
            raise RuntimeError(
                f"godot --version exited {out.returncode}: {out.stderr.strip()[:500]}"
            )
        self.version = out.stdout.strip()
        self.verified = True
        return self.version

    def info(self) -> dict:
        return {
            "path": str(self.path),
            "source": self.source,
            "exists": self.path.exists(),
            "size_bytes": self.path.stat().st_size if self.path.exists() else None,
            "version": self.version,
            "verified": self.verified,
            "notes": self.notes,
        }


def _candidate() -> tuple[Path, str] | None:
    env = os.environ.get("GODOT_BINARY")
    if env and Path(env).is_file():
        return Path(env), "env"
    if _REPO_BINARY.is_file():
        return _REPO_BINARY, "repo"
    on_path = shutil.which("godot")
    if on_path:
        return Path(on_path), "path"
    return None


_binary: GodotBinary | None = None


def get_binary() -> GodotBinary:
    """Return the resolved Godot binary (cached). Raises if none found."""
    global _binary
    if _binary is not None:
        return _binary
    cand = _candidate()
    if cand is None:
        raise FileNotFoundError(
            "No Godot binary found. Expected the in-repo binary at "
            f"{_REPO_BINARY}, or set GODOT_BINARY, or install godot on PATH."
        )
    _binary = GodotBinary(path=cand[0], source=cand[1])
    return _binary


def binary_status() -> dict:
    """Non-raising status report for health endpoints."""
    try:
        b = get_binary()
        info = b.info()
        info["available"] = True
        return info
    except FileNotFoundError as e:
        return {"available": False, "error": str(e)}
