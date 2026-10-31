"""CPU-only, content-addressed spill and restore of actual transformer KV state.

This does not serialize Metal/CUDA tensors or silently move accelerator state.
The restored cache is admitted only against the same immutable native model.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
import os
from pathlib import Path
import shutil
import stat
from typing import Any

from skeleton.cortex.transformer import KVCache

from .native_llm_runtime import NativeLLMRuntime
from .runtime_contracts import RuntimeContractError

_SCHEMA = "skeleton.ai.cpu-kv-spill.v1"
_MAX_BYTES = 32 * 1024 * 1024


class CpuKVSpillError(RuntimeContractError):
    """A CPU KV spill cannot be safely committed or restored."""


def _positive(value: int, name: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise CpuKVSpillError(f"invalid {name}")
    return value


def _digest(value: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise CpuKVSpillError("invalid spill digest")
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CpuKVSpillError("duplicate KV spill JSON key")
        result[key] = value
    return result


def _finite(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise CpuKVSpillError("KV spill contains invalid numeric tensor element")
    return float(value)


def _integer(value: object, name: str, maximum: int, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise CpuKVSpillError(f"invalid {name}")
    return value


def _cpu_runtime(runtime: NativeLLMRuntime) -> None:
    if not isinstance(runtime, NativeLLMRuntime):
        raise CpuKVSpillError("NativeLLMRuntime required")
    runtime.assert_model_unchanged()
    runtime.tokenizer.assert_unchanged()
    model = runtime.model
    if (model.device != "cpu" or model.resident or getattr(model, "_accel", None) is not None
            or getattr(model, "use_mod", False) or runtime.device.actual != "cpu"):
        raise CpuKVSpillError("only exact nonresident CPU transformer KV state is supported")


def _revision(runtime: NativeLLMRuntime) -> tuple[object, ...]:
    model = runtime.model
    return (model.steps, model.fitted, model.tied, model.device, model.resident)


def _validate_payload(data: object, runtime: NativeLLMRuntime) -> dict[str, Any]:
    _cpu_runtime(runtime)
    model = runtime.model
    keys = {
        "schema", "model_digest", "tokenizer_digest", "architecture_digest",
        "ctx", "n_layers", "dim", "tokens", "keys", "values",
        "next_position", "reset_count", "last_logits",
    }
    if not isinstance(data, dict) or set(data) != keys or data.get("schema") != _SCHEMA:
        raise CpuKVSpillError("unsupported CPU KV spill envelope")
    if (data["model_digest"] != runtime.model_digest
            or data["tokenizer_digest"] != runtime.tokenizer.digest
            or data["architecture_digest"] != runtime.architecture.digest):
        raise CpuKVSpillError("KV spill model/tokenizer/architecture identity mismatch")
    ctx = _integer(data["ctx"], "context", runtime.limits.max_context, minimum=2)
    if ctx > model.ctx or data["n_layers"] != model.n_layers or data["dim"] != model.dim:
        raise CpuKVSpillError("KV spill tensor architecture mismatch")
    tokens = data["tokens"]
    if (not isinstance(tokens, list) or not 1 <= len(tokens) <= ctx
            or any(isinstance(t, bool) or not isinstance(t, int)
                   or t < 0 or t >= model.V for t in tokens)):
        raise CpuKVSpillError("invalid KV token window")
    next_position = _integer(data["next_position"], "next_position", 2**31 - 1)
    if next_position < len(tokens):
        raise CpuKVSpillError("KV position precedes cached tokens")
    _integer(data["reset_count"], "reset_count", 2**31 - 1)
    # Reject impossible shape before allocating a tensor copy.
    estimated = len(tokens) * model.n_layers * model.dim * 2 * 8
    if estimated > runtime.limits.max_kv_bytes or estimated > _MAX_BYTES:
        raise CpuKVSpillError("KV tensor footprint exceeds runtime budget")
    for name in ("keys", "values"):
        layers = data[name]
        if not isinstance(layers, list) or len(layers) != model.n_layers:
            raise CpuKVSpillError("KV layer count mismatch")
        for layer in layers:
            if not isinstance(layer, list) or len(layer) != len(tokens):
                raise CpuKVSpillError("KV token-axis mismatch")
            for vector in layer:
                if not isinstance(vector, list) or len(vector) != model.dim:
                    raise CpuKVSpillError("KV vector shape mismatch")
                for value in vector:
                    _finite(value)
    logits = data["last_logits"]
    if logits is not None:
        if not isinstance(logits, list) or len(logits) != model.V:
            raise CpuKVSpillError("KV cached logits shape mismatch")
        for value in logits:
            _finite(value)
    return data


class CpuKVSpillStore:
    """Immutable CPU KV snapshots with bounded reads and crash-safe publication."""

    def __init__(
        self, directory: str | Path, *, max_snapshot_bytes: int = _MAX_BYTES,
        disk_reserve_bytes: int = 128 * 1024 * 1024,
    ) -> None:
        _positive(max_snapshot_bytes, "max_snapshot_bytes", _MAX_BYTES)
        if (isinstance(disk_reserve_bytes, bool) or not isinstance(disk_reserve_bytes, int)
                or not 0 <= disk_reserve_bytes <= 2**63 - 1):
            raise CpuKVSpillError("invalid disk reserve")
        self.root = Path(directory)
        self.max_snapshot_bytes = max_snapshot_bytes
        self.disk_reserve_bytes = disk_reserve_bytes
        if self.root.is_symlink():
            raise CpuKVSpillError("KV spill root must not be symlinked")
        try:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            if not self.root.is_dir() or self.root.is_symlink():
                raise CpuKVSpillError("KV spill root is not a directory")
            if os.name == "posix" and self.root.stat().st_mode & 0o022:
                raise CpuKVSpillError("KV spill root is group/world writable")
        except OSError as exc:
            raise CpuKVSpillError("cannot initialize KV spill directory") from exc

    def _path(self, digest: str) -> Path:
        return self.root / _digest(digest)[:2] / digest

    def _read(self, digest: str) -> bytes:
        path = self._path(digest)
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            if path.is_symlink() or path.parent.is_symlink():
                raise CpuKVSpillError("symlinked KV spill rejected")
            fd = os.open(path, flags)
            with os.fdopen(fd, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise CpuKVSpillError("KV spill must be a regular file")
                raw = stream.read(self.max_snapshot_bytes + 1)
        except OSError as exc:
            raise CpuKVSpillError("KV spill unavailable") from exc
        if len(raw) > self.max_snapshot_bytes or sha256(raw).hexdigest() != digest:
            raise CpuKVSpillError("KV spill byte budget or digest mismatch")
        return raw

    def _publish(self, digest: str, raw: bytes) -> None:
        path = self._path(digest)
        if len(raw) > self.max_snapshot_bytes:
            raise CpuKVSpillError("KV snapshot exceeds byte budget")
        try:
            if path.parent.is_symlink():
                raise CpuKVSpillError("symlinked KV spill bucket rejected")
            path.parent.mkdir(mode=0o700, exist_ok=True)
            if path.parent.is_symlink():
                raise CpuKVSpillError("symlinked KV spill bucket rejected")
            if path.exists() or path.is_symlink():
                if self._read(digest) != raw:
                    raise CpuKVSpillError("immutable KV spill collision")
                return
            free = shutil.disk_usage(self.root).free
            if free < self.disk_reserve_bytes or free - self.disk_reserve_bytes < len(raw):
                raise CpuKVSpillError("disk reserve prevents KV spill")
            tmp = path.with_name("." + digest + "." + os.urandom(8).hex() + ".tmp")
            try:
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
                with os.fdopen(os.open(tmp, flags, 0o600), "wb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    os.link(tmp, path, follow_symlinks=False)
                except FileExistsError:
                    if self._read(digest) != raw:
                        raise CpuKVSpillError("concurrent KV spill mismatch")
                if os.name == "posix":
                    fd = os.open(path.parent, os.O_RDONLY)
                    try:
                        os.fsync(fd)
                    finally:
                        os.close(fd)
            finally:
                tmp.unlink(missing_ok=True)
        except OSError as exc:
            raise CpuKVSpillError("KV spill publication failed") from exc

    def stage(self, runtime: NativeLLMRuntime, cache: KVCache) -> str:
        """Persist a primed CPU KV cache without granting future model authority."""
        _cpu_runtime(runtime)
        model = runtime.model
        if not isinstance(cache, KVCache):
            raise CpuKVSpillError("KVCache required")
        if (cache.owner is not model or cache.revision != _revision(runtime)
                or cache.n_layers != model.n_layers or not 2 <= cache.ctx <= runtime.limits.max_context
                or cache.reserved_bytes != 0):
            raise CpuKVSpillError("KV cache is stale, accelerator-backed or incompatible")
        data = {
            "schema": _SCHEMA,
            "model_digest": runtime.model_digest,
            "tokenizer_digest": runtime.tokenizer.digest,
            "architecture_digest": runtime.architecture.digest,
            "ctx": cache.ctx,
            "n_layers": cache.n_layers,
            "dim": model.dim,
            "tokens": list(cache.tokens),
            "keys": [[list(vector) for vector in layer] for layer in cache.K],
            "values": [[list(vector) for vector in layer] for layer in cache.V],
            "next_position": cache.next_position,
            "reset_count": cache.reset_count,
            "last_logits": None if cache.last_logits is None else list(cache.last_logits),
        }
        _validate_payload(data, runtime)
        raw = _canonical(data)
        digest = sha256(raw).hexdigest()
        self._publish(digest, raw)
        return digest

    def restore(self, runtime: NativeLLMRuntime, digest: str) -> KVCache:
        """Validate full cache before creating a new model-bound CPU KV object."""
        _cpu_runtime(runtime)
        raw = self._read(digest)
        try:
            data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                              parse_constant=lambda _: (_ for _ in ()).throw(CpuKVSpillError("nonfinite KV JSON")))
        except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
            raise CpuKVSpillError("invalid KV spill JSON") from exc
        data = _validate_payload(data, runtime)
        if _canonical(data) != raw:
            raise CpuKVSpillError("noncanonical KV spill")
        cache = KVCache(runtime.model.n_layers, data["ctx"])
        cache.K = [[list(map(float, row)) for row in layer] for layer in data["keys"]]
        cache.V = [[list(map(float, row)) for row in layer] for layer in data["values"]]
        cache.tokens = list(data["tokens"])
        cache.next_position = data["next_position"]
        cache.reset_count = data["reset_count"]
        cache.last_logits = None if data["last_logits"] is None else list(map(float, data["last_logits"]))
        cache.owner = runtime.model
        cache.revision = _revision(runtime)
        cache.reserved_bytes = 0
        return cache


__all__ = ["CpuKVSpillStore", "CpuKVSpillError"]
