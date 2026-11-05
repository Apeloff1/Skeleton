"""
╔═══════════════════════════════════════════════════════════════════════╗
║  HYPERSCALE COMPRESSED VAULT                                           ║
║  ──────────────────────────────────────────────────────────────────────  ║
║  Stores massive knowledge databases as zstd-level-22 compressed        ║
║  JSONL archives on disk (typical 15-25× compression ratio).            ║
║  MongoDB only holds tiny manifest pointers, so the 9.8G volume         ║
║  stays safe while delivering multi-GB of decompressed content.         ║
║                                                                        ║
║  Public API:                                                           ║
║    • write_shard(name, rows, domain)  → manifest entry                 ║
║    • read_shard(name, limit, offset)  → list[dict]                     ║
║    • iter_shard(name)                 → streaming iterator             ║
║    • vault_stats()                    → on-disk + decompressed totals  ║
║    • list_shards()                    → all manifest entries           ║
╚═════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations
import os
import io
import json
import time
import hashlib
import tempfile
import threading
import re
import stat
from contextlib import contextmanager
from itertools import islice
from .vault_secure_fs import anchored_directory, ensure_directory, read_regular, atomic_write, unlink_regular, VaultPathError
from pathlib import Path
from typing import Iterable, Iterator, Any

_COMPRESSOR_OBJ = None
_DECOMPRESSOR_OBJ = None


def _ensure_zstd():
    """Import zstandard on first shard read/write, not at module import."""
    global _COMPRESSOR_OBJ, _DECOMPRESSOR_OBJ
    if _COMPRESSOR_OBJ is not None and _DECOMPRESSOR_OBJ is not None:
        return
    import zstandard as zstd

    _COMPRESSOR_OBJ = zstd.ZstdCompressor(
        level=_COMPRESSION_LEVEL, threads=-1, write_content_size=True
    )
    _DECOMPRESSOR_OBJ = zstd.ZstdDecompressor()


class _CodecProxy:
    def __init__(self, kind: str):
        self._kind = kind

    def __getattr__(self, name: str):
        _ensure_zstd()
        target = _COMPRESSOR_OBJ if self._kind == "c" else _DECOMPRESSOR_OBJ
        return getattr(target, name)


def _json_default(obj: Any):
    """Make datetime / ObjectId / bytes / sets JSON-serializable inside shards."""
    import datetime as _dt
    if isinstance(obj, (_dt.datetime, _dt.date)):
        return obj.isoformat()
    if isinstance(obj, (_dt.timedelta,)):
        return obj.total_seconds()
    if isinstance(obj, (set, frozenset)):
        return list(obj)
    if isinstance(obj, bytes):
        import base64
        return {"__b64__": base64.b64encode(obj).decode("ascii")}
    try:
        return str(obj)
    except Exception:
        return None


# ── Paths ────────────────────────────────────────────────────────────
def _resolve_writable_dir(preferred: str, fallback: str) -> Path:
    """Initialize only descriptor-anchored directories; do not follow links."""
    try:
        return ensure_directory(Path(preferred))
    except (OSError, VaultPathError):
        return ensure_directory(Path(fallback))


# Route imports must not create directories or read on-disk vault manifests.
# Resolve the writable configured location only at the first storage operation.
VAULT_ROOT = Path(os.environ.get("HYPERSCALE_VAULT_DIR", "/app/backend/data/vault/compressed"))
SCRATCH_ROOT = Path(os.environ.get("HYPERSCALE_SCRATCH_DIR", "/tmp/hyperscale_scratch"))
_STORAGE_LOCK = threading.Lock()
_STORAGE_READY = False
_STORAGE_IDENTITY: dict[bool, tuple[int, int]] = {}

def _ensure_storage() -> None:
    global VAULT_ROOT, SCRATCH_ROOT, _MANIFEST_FILE, _STORAGE_READY
    if _STORAGE_READY:
        return
    with _STORAGE_LOCK:
        if _STORAGE_READY:
            return
        vault = _resolve_writable_dir(str(VAULT_ROOT), "/tmp/hyperscale_vault")
        scratch = _resolve_writable_dir(str(SCRATCH_ROOT), "/tmp/hyperscale_scratch")
        VAULT_ROOT, SCRATCH_ROOT = vault, scratch
        _MANIFEST_FILE = vault / "_manifest.json"
        # Bind all later opens to these exact directory inodes, even when
        # a parent path is renamed and replaced by another real directory.
        with anchored_directory(vault) as fd:
            info = os.fstat(fd)
            _STORAGE_IDENTITY[False] = (info.st_dev, info.st_ino)
        with anchored_directory(scratch) as fd:
            info = os.fstat(fd)
            _STORAGE_IDENTITY[True] = (info.st_dev, info.st_ino)
        _load_manifest()
        _STORAGE_READY = True

_COMPRESSION_LEVEL = int(os.environ.get("HYPERSCALE_ZSTD_LEVEL", "21"))
_COMPRESSOR = _CodecProxy("c")
_DECOMPRESSOR = _CodecProxy("d")

_MAX_SHARD_SCAN_BYTES = 512 * 1024 * 1024
_MAX_COMPRESSED_BYTES = 512 * 1024 * 1024
_MAX_ROW_CHARS = 1 * 1024 * 1024
_MAX_SHARD_ROWS = 1_000_000
_MAX_PAGE_LIMIT = 1_000
_MAX_PAGE_OFFSET = 1_000_000

_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_MAX_BYTES = 64 * 1024 * 1024
_CACHE_SIZE_EST: dict[str, int] = {}
_MANIFEST: dict[str, dict] = {}
_MANIFEST_FILE = VAULT_ROOT / "_manifest.json"


@contextmanager
def _storage_fd(scratch: bool = False):
    root = SCRATCH_ROOT if scratch else VAULT_ROOT
    with anchored_directory(root) as fd:
        info = os.fstat(fd)
        if _STORAGE_IDENTITY.get(scratch) != (info.st_dev, info.st_ino):
            raise VaultPathError("vault storage directory identity changed")
        yield fd


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate vault JSON field")
        result[key] = value
    return result


def _deny_nonfinite(value):
    raise ValueError("vault JSON contains nonfinite number")


def _load_manifest() -> None:
    global _MANIFEST
    with _storage_fd() as directory:
        try:
            with read_regular(directory, "_manifest.json", max_bytes=8 * 1024 * 1024) as stream:
                data = json.loads(
                    stream.read().decode("utf-8"),
                    object_pairs_hook=_unique_pairs,
                    parse_constant=_deny_nonfinite,
                )
        except FileNotFoundError:
            _MANIFEST = {}
            return
    if not isinstance(data, dict) or any(
        not isinstance(name, str) or not isinstance(entry, dict)
        for name, entry in data.items()
    ):
        raise ValueError("invalid vault manifest structure")
    _MANIFEST = data


def _save_manifest() -> None:
    _ensure_storage()
    payload = json.dumps(
        _MANIFEST, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    if len(payload) > 8 * 1024 * 1024:
        raise ValueError("vault manifest exceeds byte budget")
    with _storage_fd() as directory:
        atomic_write(directory, "_manifest.json", lambda fh: fh.write(payload))


# No on-disk manifest reads during import.


_SAFE_SHARD_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}")


def _safe_name(name: str) -> str:
    """Accept only a short ASCII identifier, never a path fragment."""
    if not isinstance(name, str) or not _SAFE_SHARD_NAME.fullmatch(name):
        raise ValueError("invalid shard name")
    if name in {".", ".."} or name.endswith("."):
        raise ValueError("invalid shard name")
    return name


def _shard_path(name: str, scratch: bool = False) -> Path:
    """Construct a logical shard name; actual I/O is directory-fd anchored."""
    safe = _safe_name(name)
    _ensure_storage()
    root = SCRATCH_ROOT if scratch else VAULT_ROOT
    return root / f"{safe}.jsonl.zst"


# ── Core write/read ───────────────────────────────────────────────
def write_shard(
    name: str,
    rows: Iterable[dict[str, Any]],
    *,
    domain: str,
    agent_id: str | None = None,
    description: str = "",
    scratch: bool = False,
) -> dict:
    """Publish a complete, bounded compressed shard with descriptor custody."""
    name = _safe_name(name)
    shard_path = _shard_path(name, scratch)
    count = 0
    raw_bytes = 0
    hasher = hashlib.sha1()

    def _compress(handle) -> None:
        nonlocal count, raw_bytes
        with _COMPRESSOR.stream_writer(handle) as writer:
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError("vault rows must be JSON objects")
                line = (
                    json.dumps(
                        row, separators=(",", ":"), ensure_ascii=False,
                        default=_json_default, allow_nan=False,
                    ) + "\n"
                ).encode("utf-8")
                if len(line) > _MAX_ROW_CHARS:
                    raise ValueError("vault row exceeds line byte budget")
                if count >= _MAX_SHARD_ROWS or raw_bytes + len(line) > _MAX_SHARD_SCAN_BYTES:
                    raise ValueError("vault write exceeds row/byte budget")
                writer.write(line)
                hasher.update(line)
                raw_bytes += len(line)
                count += 1

    with _storage_fd(scratch) as directory:
        compressed_bytes = atomic_write(
            directory, shard_path.name, _compress, max_bytes=_MAX_COMPRESSED_BYTES,
        )

    entry = {
        "name": name,
        "domain": domain,
        "agent_id": agent_id or f"agent_{name}",
        "description": description,
        "path": str(shard_path),
        "scratch": scratch,
        "rows": count,
        "raw_bytes": raw_bytes,
        "compressed_bytes": compressed_bytes,
        "compression_ratio": round(raw_bytes / max(compressed_bytes, 1), 2),
        "sha1": hasher.hexdigest(),
        "created_at": time.time(),
    }
    if not scratch:
        old_entry = _MANIFEST.get(name)
        _MANIFEST[name] = entry
        try:
            _save_manifest()
        except BaseException:
            if old_entry is None:
                _MANIFEST.pop(name, None)
            else:
                _MANIFEST[name] = old_entry
            raise
    with _CACHE_LOCK:
        _CACHE.pop(name, None)
        _CACHE_SIZE_EST.pop(name, None)
    return entry


def _cache_evict_if_needed() -> None:
    total = sum(_CACHE_SIZE_EST.values())
    if total <= _CACHE_MAX_BYTES:
        return
    items = sorted(_CACHE.items(), key=lambda kv: kv[1][0])
    while total > _CACHE_MAX_BYTES and items:
        key, _ = items.pop(0)
        total -= _CACHE_SIZE_EST.pop(key, 0)
        _CACHE.pop(key, None)


def _load_full(name: str) -> list[dict]:
    _ensure_storage()
    name = _safe_name(name)
    if name not in _MANIFEST:
        raise KeyError(f"Shard '{name}' not in manifest")
    path = _shard_path(name)
    if not path.exists():
        raise FileNotFoundError(f"Archive missing on disk: {path}")
    with path.open("rb") as fh:
        with _DECOMPRESSOR.stream_reader(fh) as zr:
            data = zr.read()
    rows: list[dict] = []
    for line in data.splitlines():
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def read_shard(name: str, limit: int = 50, offset: int = 0) -> list[dict]:
    name = _safe_name(name)
    with _CACHE_LOCK:
        cached = _CACHE.get(name)
        if cached is not None:
            _CACHE[name] = (time.time(), cached[1])
            rows = cached[1]
        else:
            rows = _load_full(name)
            size_est = sum(len(json.dumps(r)) for r in rows[:32]) * max(len(rows) // 32, 1)
            _CACHE[name] = (time.time(), rows)
            _CACHE_SIZE_EST[name] = size_est
            _cache_evict_if_needed()
    return rows[offset : offset + limit]


def iter_shard(name: str) -> Iterator[dict]:
    _ensure_storage()
    name = _safe_name(name)
    if name not in _MANIFEST:
        raise KeyError(f"Shard '{name}' not in manifest")
    path = _shard_path(name)
    with open(path, "rb") as fh:
        with _DECOMPRESSOR.stream_reader(fh) as zr:
            buf = io.TextIOWrapper(zr, encoding="utf-8")
            for line in buf:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    continue


def sample_shard(name: str, k: int = 5) -> list[dict]:
    out: list[dict] = []
    for row in iter_shard(name):
        out.append(row)
        if len(out) >= k:
            break
    return out


def list_shards() -> list[dict]:
    _ensure_storage()
    return sorted(_MANIFEST.values(), key=lambda e: e["name"])


def get_shard_entry(name: str) -> dict | None:
    _ensure_storage()
    return _MANIFEST.get(_safe_name(name))


def vault_stats() -> dict:
    _ensure_storage()
    _load_manifest()
    shards = list(_MANIFEST.values())
    total_raw = sum(s.get("raw_bytes", 0) for s in shards)
    total_comp = sum(s.get("compressed_bytes", 0) for s in shards)
    total_rows = sum(s.get("rows", 0) for s in shards)
    return {
        "shard_count": len(shards),
        "total_rows": total_rows,
        "total_raw_bytes": total_raw,
        "total_compressed_bytes": total_comp,
        "avg_compression_ratio": round(total_raw / max(total_comp, 1), 2),
        "vault_root": str(VAULT_ROOT),
        "scratch_root": str(SCRATCH_ROOT),
    }


def purge_cache() -> int:
    with _CACHE_LOCK:
        n = len(_CACHE)
        _CACHE.clear()
        _CACHE_SIZE_EST.clear()
    return n


def delete_shard(name: str) -> bool:
    _ensure_storage()
    name = _safe_name(name)
    entry = _MANIFEST.pop(name, None)
    if not entry:
        return False
    try:
        _shard_path(name).unlink(missing_ok=True)
    except Exception:
        pass
    _save_manifest()
    with _CACHE_LOCK:
        _CACHE.pop(name, None)
        _CACHE_SIZE_EST.pop(name, 0)
    return True
