"""Lazy ctypes bridge to the GameForge Rust ``gf-ffi`` court.

This is the canonical Python home for the binding that previously lived only
inside the ``satellites/gameforge-rs`` snapshot. Importing this module never
loads native code; callers opt in by constructing :class:`Zaibatsu` or using
:meth:`Zaibatsu.open_default`.
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
from pathlib import Path
from typing import Any

_LIBRARY_ENV = "GAMEFORGE_FFI_LIBRARY"


def _library_names() -> tuple[str, ...]:
    if sys.platform == "win32":
        return ("gf_ffi.dll", "gameforge_ffi.dll")
    if sys.platform == "darwin":
        return ("libgf_ffi.dylib", "libgameforge_ffi.dylib")
    return ("libgf_ffi.so", "libgameforge_ffi.so")


def resolve_library_path(explicit: str | Path | None = None) -> Path | None:
    """Resolve an existing gf-ffi library without loading it.

    Resolution order is explicit path, ``GAMEFORGE_FFI_LIBRARY``, then common
    in-repo build locations. Missing native artifacts are a normal state in CI
    and pure-Python deployments, so this function returns ``None`` rather than
    failing at import time.
    """
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(Path(explicit).expanduser())
    configured = os.environ.get(_LIBRARY_ENV, "").strip()
    if configured:
        candidates.append(Path(configured).expanduser())

    backend_dir = Path(__file__).resolve().parents[1]
    repo_dir = backend_dir.parent
    for name in _library_names():
        candidates.extend(
            (
                backend_dir / "native" / name,
                repo_dir / "satellites" / "gameforge-rs" / "target" / "release" / name,
                repo_dir / "satellites" / "gameforge-rs" / "target" / "debug" / name,
            )
        )

    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_file():
            return resolved
    return None


class NativeUnavailable(RuntimeError):
    """Raised when a caller explicitly requests the Rust court but none exists."""


class _Lib:
    def __init__(self, path: str | Path) -> None:
        lib = ctypes.CDLL(str(path))
        lib.gf_zaibatsu_create.restype = ctypes.c_void_p
        lib.gf_zaibatsu_create.argtypes = []
        lib.gf_zaibatsu_destroy.restype = None
        lib.gf_zaibatsu_destroy.argtypes = [ctypes.c_void_p]
        lib.gf_free_string.restype = None
        lib.gf_free_string.argtypes = [ctypes.c_void_p]

        def json_fn(name: str, argtypes: list[Any]) -> None:
            fn = getattr(lib, name)
            fn.restype = ctypes.c_void_p
            fn.argtypes = argtypes

        c = ctypes.c_char_p
        json_fn("gf_propose", [ctypes.c_void_p, c, c, c, c, c])
        json_fn("gf_fabric_tail", [ctypes.c_void_p, c, ctypes.c_uint32])
        json_fn("gf_legion_found", [ctypes.c_void_p, c, c])
        json_fn("gf_legion_enlist", [ctypes.c_void_p, c, c])
        json_fn("gf_swarm_submit", [ctypes.c_void_p, c, c, c, c])
        json_fn("gf_swarm_wave", [ctypes.c_void_p])
        json_fn("gf_governance_decide", [ctypes.c_void_p, c, c, ctypes.c_uint32])
        json_fn("gf_cognition_hold", [ctypes.c_void_p, c, ctypes.c_bool])
        json_fn("gf_cognition_testify", [ctypes.c_void_p, c, c, ctypes.c_bool, ctypes.c_double])
        json_fn("gf_status", [ctypes.c_void_p])
        lib.gf_fabric_seq.restype = ctypes.c_uint64
        lib.gf_fabric_seq.argtypes = [ctypes.c_void_p]
        lib.gf_lafs_put.restype = ctypes.c_void_p
        lib.gf_lafs_put.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]
        self.lib = lib

    def call_json(self, name: str, *args: Any) -> Any:
        ptr = getattr(self.lib, name)(*args)
        if not ptr:
            raise RuntimeError(f"{name} returned null")
        try:
            raw = ctypes.cast(ptr, ctypes.c_char_p).value
            if raw is None:
                raise RuntimeError(f"{name} returned an empty pointer")
            out = json.loads(raw.decode("utf-8"))
        finally:
            self.lib.gf_free_string(ptr)
        if isinstance(out, dict) and "error" in out:
            raise RuntimeError(str(out["error"]))
        return out


def _b(value: str) -> bytes:
    return value.encode("utf-8")


class Zaibatsu:
    """Owned handle to one in-process Rust Zaibatsu court."""

    def __init__(self, library_path: str | Path) -> None:
        self.library_path = Path(library_path).resolve()
        self._lib = _Lib(self.library_path)
        self._h = self._lib.lib.gf_zaibatsu_create()
        if not self._h:
            raise NativeUnavailable("gf_zaibatsu_create returned null")

    @classmethod
    def open_default(cls) -> "Zaibatsu":
        path = resolve_library_path()
        if path is None:
            raise NativeUnavailable(
                f"gf-ffi library not found; set {_LIBRARY_ENV} or build satellites/gameforge-rs"
            )
        return cls(path)

    def close(self) -> None:
        if self._h:
            self._lib.lib.gf_zaibatsu_destroy(self._h)
            self._h = None

    def __enter__(self) -> "Zaibatsu":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def _handle(self) -> int:
        if not self._h:
            raise RuntimeError("Zaibatsu handle is closed")
        return self._h

    def propose(self, ledger: str, kind: str, proposal_id: str, attester: str, value: Any) -> dict:
        return self._lib.call_json(
            "gf_propose", self._handle(), _b(ledger), _b(kind), _b(proposal_id),
            _b(attester), _b(json.dumps(value, separators=(",", ":"))),
        )

    def fabric_tail(self, ledger: str, limit: int = 128) -> list:
        if not 1 <= limit <= 10_000:
            raise ValueError("limit must be between 1 and 10000")
        return self._lib.call_json("gf_fabric_tail", self._handle(), _b(ledger), limit)

    def fabric_seq(self) -> int:
        return int(self._lib.lib.gf_fabric_seq(self._handle()))

    def found_legion(self, name: str, motto: str) -> dict:
        return self._lib.call_json("gf_legion_found", self._handle(), _b(name), _b(motto))

    def enlist(self, legion: str, capability: str) -> str:
        return self._lib.call_json(
            "gf_legion_enlist", self._handle(), _b(legion), _b(capability)
        )["member_id"]

    def submit_task(self, task_id: str, capability: str, payload: Any, deps: list[str] | None = None) -> dict:
        return self._lib.call_json(
            "gf_swarm_submit", self._handle(), _b(task_id), _b(capability),
            _b(json.dumps(payload, separators=(",", ":"))),
            _b(json.dumps(deps or [], separators=(",", ":"))),
        )

    def ready_wave(self) -> list:
        return self._lib.call_json("gf_swarm_wave", self._handle())

    def decide(self, domain: str, action: str, actor_weight: int = 0) -> dict:
        if not 0 <= actor_weight <= 2**32 - 1:
            raise ValueError("actor_weight must fit uint32")
        return self._lib.call_json(
            "gf_governance_decide", self._handle(), _b(domain), _b(action), actor_weight
        )

    def hold_belief(self, predicate: str, polarity: bool) -> str:
        return self._lib.call_json(
            "gf_cognition_hold", self._handle(), _b(predicate), polarity
        )["belief_id"]

    def testify(self, belief_id: str, witness: str, supports: bool, weight: float = 0.5) -> float:
        if not 0.0 <= weight <= 1.0:
            raise ValueError("weight must be between 0 and 1")
        return float(
            self._lib.call_json(
                "gf_cognition_testify", self._handle(), _b(belief_id), _b(witness), supports, weight
            )["confidence"]
        )

    def put_chunk(self, data: bytes) -> str:
        if not isinstance(data, bytes):
            raise TypeError("data must be bytes")
        return self._lib.call_json(
            "gf_lafs_put", self._handle(), data, len(data)
        )["digest"]

    def status(self) -> dict:
        return self._lib.call_json("gf_status", self._handle())


__all__ = ["NativeUnavailable", "Zaibatsu", "resolve_library_path"]
