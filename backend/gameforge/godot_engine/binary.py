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
GODOT_SHA256 is an operator-provided full digest, checked before execution.
GODOT_FINGERPRINT remains a compatibility check and never qualifies full
integrity. Unpinned development launches remain subject to the execution guard.
No binary is chmodded or executed after a failed admission.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import re
import os
import shutil
import stat
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from core.exec_guard import execution_disabled_message, require_execution_allowed

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
    sha256: str | None = None

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
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "size_mb": round(self.size_bytes / (1 << 20), 1),
            "supports_check_only": self.supports_check_only,
            "supports_export_web": self.supports_export_web,
            "probed_at": self.probed_at,
        }


@dataclass(frozen=True)
class EngineAdmission:
    path: Path
    identity: tuple
    sha256: str
    fingerprint: str
    integrity: str

    def assert_current(self) -> None:
        if not require_execution_allowed("Godot engine execution"):
            raise PermissionError("Godot execution disabled")
        pin = os.environ.get("GODOT_SHA256", "").strip().lower()
        sample = os.environ.get("GODOT_FINGERPRINT", "").strip().lower()
        if pin and not hmac.compare_digest(pin, self.sha256):
            raise PermissionError("Godot SHA-256 changed")
        if sample and not hmac.compare_digest(sample, self.fingerprint):
            raise PermissionError("Godot fingerprint changed")
        if (pin != "") != (self.integrity == "verified"):
            raise PermissionError("Godot integrity policy changed")
        if GodotBinary._identity(self.path.stat()) != self.identity:
            raise RuntimeError("Godot executable changed before launch")


async def reap_process(proc) -> None:
    """Reap an owned child after timeout, cancellation or output failure."""
    if proc.returncode is None:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
    # Drain pipes too: Process.wait alone can deadlock with saturated pipes.
    await asyncio.wait_for(proc.communicate(), timeout=10)


@dataclass
class GodotBinary:
    path: Path
    source: str                    # "env" | "repo" | "path"
    profile: EngineProfile | None = None
    notes: list[str] = field(default_factory=list)

    _probe_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _profile_identity: tuple | None = field(default=None, init=False, repr=False)

    @staticmethod
    def _identity(st: os.stat_result) -> tuple:
        return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)

    def prepare_execution(self) -> "EngineAdmission":
        """Hash the executable before any launch; never change file permissions."""
        if not require_execution_allowed("Godot engine execution"):
            raise PermissionError(execution_disabled_message("Godot engine execution"))
        path = self.path.resolve(strict=True)
        full_pin = os.environ.get("GODOT_SHA256", "").strip().lower()
        sample_pin = os.environ.get("GODOT_FINGERPRINT", "").strip().lower()
        if full_pin and not re.fullmatch(r"[0-9a-f]{64}", full_pin):
            raise ValueError("invalid Godot SHA-256 configuration")
        if sample_pin and not re.fullmatch(r"[0-9a-f]{16}", sample_pin):
            raise ValueError("invalid Godot fingerprint configuration")
        with path.open("rb") as stream:
            first = os.fstat(stream.fileno())
            if not stat.S_ISREG(first.st_mode) or not 0 < first.st_size <= 1 << 30:
                raise ValueError("invalid Godot executable size or type")
            digest = hashlib.sha256()
            sample = hashlib.sha256(str(first.st_size).encode())
            chunk = stream.read(_HASH_CHUNK)
            sample.update(chunk)
            digest.update(chunk)
            total = len(chunk)
            while chunk:
                chunk = stream.read(_HASH_CHUNK)
                total += len(chunk)
                if total > first.st_size:
                    raise RuntimeError("Godot executable changed during read")
                digest.update(chunk)
            if first.st_size > _HASH_CHUNK:
                stream.seek(first.st_size - _HASH_CHUNK)
                sample.update(stream.read(_HASH_CHUNK))
            identity = self._identity(first)
            if total != first.st_size or identity != self._identity(os.fstat(stream.fileno())):
                raise RuntimeError("Godot executable changed during read")
        sha256, fingerprint = digest.hexdigest(), sample.hexdigest()[:16]
        if full_pin and not hmac.compare_digest(full_pin, sha256):
            raise PermissionError("Godot SHA-256 mismatch")
        if sample_pin and not hmac.compare_digest(sample_pin, fingerprint):
            raise PermissionError("Godot fingerprint mismatch")
        if not os.access(path, os.X_OK):
            raise PermissionError("Godot executable is not marked executable")
        admission = EngineAdmission(path, identity, sha256, fingerprint,
                                    "verified" if full_pin else "unchecked")
        admission.assert_current()
        return admission

    def ensure_executable(self) -> None:
        """Compatibility entry point: admission, never chmod an unknown file."""
        self.prepare_execution()

    async def _run(self, *args: str, timeout: int = 30,
                   admission: "EngineAdmission | None" = None) -> tuple[int, str, str]:
        admission = admission or await asyncio.to_thread(self.prepare_execution)
        admission.assert_current()
        proc = await asyncio.create_subprocess_exec(
            str(admission.path), *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        async def bounded_read(stream):
            data = bytearray()
            while part := await stream.read(65536):
                if len(data) + len(part) > 1 << 20:
                    raise RuntimeError("Godot probe output limit exceeded")
                data.extend(part)
            return bytes(data)

        async def finish():
            out, err, rc = await asyncio.gather(
                bounded_read(proc.stdout), bounded_read(proc.stderr), proc.wait()
            )
            return rc, out.decode(errors="replace"), err.decode(errors="replace")

        try:
            return await asyncio.wait_for(finish(), timeout=timeout)
        finally:
            if proc.returncode is None:
                await reap_process(proc)

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
        """The legacy sampled fingerprint detects mismatches, not full integrity."""
        expected = os.environ.get("GODOT_FINGERPRINT", "").strip().lower()
        return "mismatch" if expected and not hmac.compare_digest(expected, fingerprint) else "unchecked"

    async def probe(self, force: bool = False) -> EngineProfile:
        async with self._probe_lock:
            admission = await asyncio.to_thread(self.prepare_execution)
            key = (*admission.identity, admission.sha256, admission.integrity)
            if self.profile and not force and self._profile_identity == key:
                return self.profile
            self.profile = None
            self._profile_identity = None
            rc, out, _ = await self._run("--version", admission=admission)
            if rc != 0:
                raise RuntimeError("Godot version probe failed")
            version = out.strip()
            if not re.fullmatch(r"[0-9][A-Za-z0-9. +_-]{0,127}", version):
                raise RuntimeError("invalid Godot version response")
            parts = version.split(".")
            major = int(parts[0]) if parts[0].isdigit() else 0
            minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
            rc2, _, _ = await self._run("--headless", "--quit", timeout=45, admission=admission)
            admission.assert_current()
            self.profile = EngineProfile(
                version=version, major=major, minor=minor,
                headless_ok=rc2 == 0, fingerprint=admission.fingerprint,
                size_bytes=admission.identity[2], integrity=admission.integrity,
                sha256=admission.sha256,
            )
            self._profile_identity = key
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
        return None
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
        return {"available": b.path.is_file(), "source": b.source}
    except FileNotFoundError:
        return {"available": False, "error": "godot_binary_unavailable"}
