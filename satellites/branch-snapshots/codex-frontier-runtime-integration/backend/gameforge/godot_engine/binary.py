"""
godot_engine.binary — the engine crate: locate, verify, and profile the
in-repo Godot binary.

The crate
---------
The Godot editor binary is a first-class tracked asset shipped at
``<backend>/godot`` (Linux x86_64, ~103 MB). This module is the only code
allowed to touch it: everything else (project scaffolding, headless
pipeline, the ``/api/godot-engine`` routes) goes through :func:`get_binary`.

Resolution order: ``GODOT_BINARY`` env → ``<backend>/godot`` → ``PATH``.

Integrity
---------
Set ``GODOT_FINGERPRINT`` to the expected cheap SHA-256 (size + first/last
MiB — hashing all 103 MB on every call would be wasteful). After probing,
the profile reports ``integrity`` as ``"verified"`` / ``"mismatch"`` /
``"unchecked"`` and the /api/godot-engine/status endpoint surfaces it.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import stat
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_BINARY = _BACKEND_DIR / "godot"

_HASH_CHUNK = 1 << 20  # 1 MiB


@dataclass
class EngineProfile:
    """Everything the app knows about the engine it owns."""

    version: str
    major: int
    minor: int
    headless_ok: bool
    fingerprint: str
    size_bytes: int
    integrity: str = "unchecked"          # "verified" | "mismatch" | "unchecked"
    probed_at: float = field(default_factory=time.time)

    @property
    def supports_check_only(self) -> bool:
        return self.major >= 4

    @property
    def supports_export_web(self) -> bool:
        return (self.major, self.minor) >= (4, 0)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "major": self.major,
            "minor": self.minor,
            "headless_ok": self.headless_ok,
            "fingerprint": self.fingerprint,
            "integrity": self.integrity,
            "size_bytes": self.size_bytes,
            "size_mb": round(self.size_bytes / (1 << 20), 1),
            "supports_check_only": self.supports_check_only,
            "supports_export_web": self.supports_export_web,
            "probed_at": self.probed_at,
        }


@dataclass
class GodotBinary:
    path: Path
    source: str                    # "env" | "repo" | "path"
    profile: EngineProfile | None = None
    notes: list[str] = field(default_factory=list)

    def ensure_executable(self) -> None:
        mode = self.path.stat().st_mode
        if not mode & stat.S_IXUSR:
            self.path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            self.notes.append("restored +x bit")

    async def _run(self, *args: str, timeout: int = 30) -> tuple[int, str, str]:
        self.ensure_executable()
        proc = await asyncio.create_subprocess_exec(
            str(self.path), *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return -1, "", f"timed out after {timeout}s"
        return proc.returncode, out.decode(errors="replace"), err.decode(errors="replace")

    def fingerprint(self) -> str:
        """Cheap identity: sha256 of size + first/last MiB. Sub-second on 103MB."""
        size = self.path.stat().st_size
        h = hashlib.sha256(str(size).encode())
        with self.path.open("rb") as f:
            h.update(f.read(_HASH_CHUNK))
            if size > _HASH_CHUNK:
                f.seek(max(0, size - _HASH_CHUNK))
                h.update(f.read(_HASH_CHUNK))
        return h.hexdigest()[:16]

    def verify_integrity(self, fingerprint: str) -> str:
        """Compare against the expected fingerprint from GODOT_FINGERPRINT.

        Returns "verified" / "mismatch" / "unchecked". A mismatch never
        blocks the engine — it is surfaced in the profile and notes so the
        status endpoint can report a tampered or corrupted binary.
        """
        expected = os.environ.get("GODOT_FINGERPRINT", "").strip().lower()
        if not expected:
            return "unchecked"
        if fingerprint == expected:
            return "verified"
        self.notes.append(
            f"integrity mismatch: expected {expected}, got {fingerprint}"
        )
        return "mismatch"

    async def probe(self, force: bool = False) -> EngineProfile:
        """Profile the engine; cached after first success."""
        if self.profile and not force:
            return self.profile
        rc, out, err = await self._run("--version")
        if rc != 0:
            raise RuntimeError(f"godot --version failed ({rc}): {err.strip()[:300]}")
        version = out.strip()
        # Tolerate suffixes like "4.2.1.stable.official" — only major/minor matter.
        parts = version.split(".")
        major = int(parts[0]) if parts and parts[0].isdigit() else 0
        minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        rc2, _, _ = await self._run("--headless", "--quit", timeout=45)
        fp = self.fingerprint()
        self.profile = EngineProfile(
            version=version,
            major=major,
            minor=minor,
            headless_ok=(rc2 == 0),
            fingerprint=fp,
            size_bytes=self.path.stat().st_size,
            integrity=self.verify_integrity(fp),
        )
        return self.profile

    def info(self) -> dict:
        d = {
            "path": str(self.path),
            "source": self.source,
            "exists": self.path.exists(),
            "size_bytes": self.path.stat().st_size if self.path.exists() else None,
            "notes": self.notes,
        }
        if self.profile:
            d["profile"] = self.profile.to_dict()
        return d


def _candidate(notes: list[str]) -> tuple[Path, str] | None:
    env = os.environ.get("GODOT_BINARY")
    if env:
        if Path(env).is_file():
            return Path(env), "env"
        notes.append(f"GODOT_BINARY set but not a file: {env!r} — falling through")
    if _REPO_BINARY.is_file():
        return _REPO_BINARY, "repo"
    on_path = shutil.which("godot")
    if on_path:
        return Path(on_path), "path"
    return None


_binary: GodotBinary | None = None
_binary_lock = threading.Lock()


def get_binary() -> GodotBinary:
    """Return the singleton engine handle. Thread-safe first-touch."""
    global _binary
    if _binary is not None:
        return _binary
    with _binary_lock:
        if _binary is not None:
            return _binary
        notes: list[str] = []
        cand = _candidate(notes)
        if cand is None:
            raise FileNotFoundError(
                f"No Godot binary: expected {_REPO_BINARY}, GODOT_BINARY, or godot on PATH."
            )
        _binary = GodotBinary(path=cand[0], source=cand[1], notes=notes)
        return _binary


def binary_status() -> dict:
    try:
        b = get_binary()
        return {**b.info(), "available": True}
    except FileNotFoundError as e:
        return {"available": False, "error": str(e)}
