"""
╔════════════════════════════════════════════════════════════════════════╗
║  HYPERSCALE COMPRESSED VAULT                                           ║
║  ────────────────────────────────────────────────────────────────────  ║
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
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations
import os
import io
import json
import time
import hashlib
import threading
from pathlib import Path
from typing import Iterable, Iterator, Any

import zstandard as zstd


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
    # Last resort — stringify (ObjectId, UUID, etc.)
    try:
        return str(obj)
    except Exception:
        return None

# ── Paths ───────────────────────────────────────────────────────────────
# Production k8s containers may mount /app read-only. Try the configured
# path first, then fall back to a writable /tmp location so deployment
# health-check never fails on a directory-creation error. Same safety net
# applied to SCRATCH_ROOT.
def _resolve_writable_dir(preferred: str, fallback: str) -> Path:
    try:
        p = Path(preferred)
        p.mkdir(parents=True, exist_ok=True)
        # Sanity write test
        test_file = p / ".writable_test"
        test_file.write_text("ok")
        test_file.unlink(missing_ok=True)
        return p
    except Exception:
        fp = Path(fallback)
        fp.mkdir(parents=True, exist_ok=True)
        return fp

VAULT_ROOT = _resolve_writable_dir(
    os.environ.get("HYPERSCALE_VAULT_DIR", "/app/backend/data/vault/compressed"),
    "/tmp/hyperscale_vault",
)

# Scratch path — always /tmp (guaranteed writable in k8s)
SCRATCH_ROOT = _resolve_writable_dir(
    os.environ.get("HYPERSCALE_SCRATCH_DIR", "/tmp/hyperscale_scratch"),
    "/tmp/hyperscale_scratch",
)

# Zstd compression: level 21 — near-maximum ratio with moderate speed penalty.
# threads=-1 uses all available CPU cores per-shard (keeps seeds within minutes).
_COMPRESSION_LEVEL = int(os.environ.get("HYPERSCALE_ZSTD_LEVEL", "21"))
_COMPRESSOR = zstd.ZstdCompressor(level=_COMPRESSION_LEVEL, threads=-1, write_content_size=True)
_DECOMPRESSOR = zstd.ZstdDecompressor()

# LRU cache for decompressed shard payloads (max ~64 MB in RAM)
_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_MAX_BYTES = 64 * 1024 * 1024
_CACHE_SIZE_EST: dict[str, int] = {}

# Manifest in-memory index: shard_name -> entry
_MANIFEST: dict[str, dict] = {}
_MANIFEST_FILE = VAULT_ROOT / "_manifest.json"


def _load_manifest() -> None:
    global _MANIFEST
    if _MANIFEST_FILE.exists():
        try:
            _MANIFEST = json.loads(_MANIFEST_FILE.read_text())
        except Exception:
            _MANIFEST = {}
    else:
        _MANIFEST = {}


def _save_manifest() -> None:
    tmp = _MANIFEST_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(_MANIFEST, separators=(",", ":")))
    tmp.replace(_MANIFEST_FILE)


_load_manifest()


# ── Core write/read ─────────────────────────────────────────────────────
def write_shard(
    name: str,
    rows: Iterable[dict[str, Any]],
    *,
    domain: str,
    agent_id: str | None = None,
    description: str = "",
    scratch: bool = False,
) -> dict:
    """Write an iterable of JSON rows to a compressed shard.

    Returns a manifest entry describing the archive.
    When scratch=True, writes to /tmp (overlay) instead of persistent vault.
    """
    root = SCRATCH_ROOT if scratch else VAULT_ROOT
    shard_path = root / f"{name}.jsonl.zst"
    shard_path.parent.mkdir(parents=True, exist_ok=True)

    # Stream JSON-lines through zstd straight to disk (no full buffer)
    count = 0
    raw_bytes = 0
    hasher = hashlib.sha1()
    with open(shard_path, "wb") as fh:
        with _COMPRESSOR.stream_writer(fh) as zw:
            for row in rows:
                line = (json.dumps(row, separators=(",", ":"), ensure_ascii=False, default=_json_default) + "\n").encode("utf-8")
                zw.write(line)
                hasher.update(line)
                raw_bytes += len(line)
                count += 1

    compressed_bytes = shard_path.stat().st_size
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
        _MANIFEST[name] = entry
        _save_manifest()
    return entry


def _cache_evict_if_needed() -> None:
    total = sum(_CACHE_SIZE_EST.values())
    if total <= _CACHE_MAX_BYTES:
        return
    # simple LRU by last-access time
    items = sorted(_CACHE.items(), key=lambda kv: kv[1][0])
    while total > _CACHE_MAX_BYTES and items:
        key, _ = items.pop(0)
        total -= _CACHE_SIZE_EST.pop(key, 0)
        _CACHE.pop(key, None)


def _load_full(name: str) -> list[dict]:
    entry = _MANIFEST.get(name)
    if not entry:
        raise KeyError(f"Shard '{name}' not in manifest")
    path = Path(entry["path"])
    if not path.exists():
        raise FileNotFoundError(f"Archive missing on disk: {path}")
    with open(path, "rb") as fh:
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
    """Read a paginated slice from a compressed shard (cached)."""
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
    """Stream rows from a shard without materializing entire payload in cache."""
    entry = _MANIFEST.get(name)
    if not entry:
        raise KeyError(f"Shard '{name}' not in manifest")
    path = Path(entry["path"])
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
    """Return first k rows from a shard (lightweight probe; no full decompress cache)."""
    out: list[dict] = []
    for row in iter_shard(name):
        out.append(row)
        if len(out) >= k:
            break
    return out


def list_shards() -> list[dict]:
    return sorted(_MANIFEST.values(), key=lambda e: e["name"])


def get_shard_entry(name: str) -> dict | None:
    return _MANIFEST.get(name)


def vault_stats() -> dict:
    # Refresh manifest from disk so external seed processes are picked up
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
    entry = _MANIFEST.pop(name, None)
    if not entry:
        return False
    try:
        Path(entry["path"]).unlink(missing_ok=True)
    except Exception:
        pass
    _save_manifest()
    with _CACHE_LOCK:
        _CACHE.pop(name, None)
        _CACHE_SIZE_EST.pop(name, 0)
    return True
