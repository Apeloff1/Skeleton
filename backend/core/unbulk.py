"""
core/unbulk.py — UNIFIED COMPRESSION / "UNBULK" SYSTEM.

One coherent layer that shrinks the app's footprint by storing large content
gzip/zstd-compressed and decompressing ONLY on demand (with a bounded LRU
cache), on top of the existing primitives:
  • core.compressed_vault  — zstd knowledge shards (decompress-on-demand)
  • core.cold_storage       — freeze/thaw Mongo collections to zstd
  • this module             — transparent gzip codec for doc fields + on-disk
                              build manifests + a unified savings report + a
                              source-module inventory.

Design goals (per product spec):
  1c — compress large DATA while leaving heavy seed imports deferred by callers.
  2b+2c — target big knowledge/seed data + API responses (GZip middleware, on).
  4a — TRANSPARENT: pack on write, unpack on read; callers never think about it.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import os
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

_MAGIC = "GZ1:"  # marks a packed payload so unpack() is back-compat safe
MAX_PACKED_BYTES = 8 * 1024 * 1024
MAX_UNPACKED_BYTES = 32 * 1024 * 1024
_MAX_BASE64_BYTES = ((MAX_PACKED_BYTES + 2) // 3) * 4 + 4

# ── codec stats (since boot) ─────────────────────────────────────────────────
_STATS = {
    "packed": 0, "raw_bytes_in": 0, "packed_bytes_out": 0,
    "unpacked": 0, "cache_hits": 0, "cache_misses": 0,
}
_LOCK = threading.Lock()

# ── decompress-on-demand LRU cache (hash → decoded object) ───────────────────
_CACHE: "OrderedDict[str, Any]" = OrderedDict()
_CACHE_MAX = int(os.environ.get("UNBULK_CACHE_MAX", "512"))


def pack(obj: Any) -> str:
    """gzip(JSON) → base64, prefixed with a magic header. Transparent on write."""
    raw = json.dumps(obj, separators=(",", ":"), default=str).encode("utf-8")
    if len(raw) > MAX_UNPACKED_BYTES:
        raise ValueError("payload exceeds uncompressed size limit")
    comp = gzip.compress(raw, compresslevel=6)
    if len(comp) > MAX_PACKED_BYTES:
        raise ValueError("payload exceeds compressed size limit")
    out = _MAGIC + base64.b64encode(comp).decode("ascii")
    with _LOCK:
        _STATS["packed"] += 1
        _STATS["raw_bytes_in"] += len(raw)
        _STATS["packed_bytes_out"] += len(out)
    return out


def is_packed(blob: Any) -> bool:
    return isinstance(blob, str) and blob.startswith(_MAGIC)


def _decode_packed_payload(blob: str) -> bytes:
    """Decode a GZ1 payload without permitting unbounded expansion."""
    encoded = blob[len(_MAGIC):]
    if len(encoded) > _MAX_BASE64_BYTES:
        raise ValueError("compressed payload exceeds size limit")
    try:
        compressed = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid packed payload encoding") from exc
    if len(compressed) > MAX_PACKED_BYTES:
        raise ValueError("compressed payload exceeds size limit")

    with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb") as stream:
        raw = stream.read(MAX_UNPACKED_BYTES + 1)
    if len(raw) > MAX_UNPACKED_BYTES:
        raise ValueError("decompressed payload exceeds size limit")
    return raw


def _read_bounded_gzip_file(path: Path) -> bytes:
    """Read and decompress a gzip file under the same expansion limits."""
    with path.open("rb") as handle:
        compressed = handle.read(MAX_PACKED_BYTES + 1)
    if len(compressed) > MAX_PACKED_BYTES:
        raise ValueError("compressed manifest exceeds size limit")
    with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb") as stream:
        raw = stream.read(MAX_UNPACKED_BYTES + 1)
    if len(raw) > MAX_UNPACKED_BYTES:
        raise ValueError("decompressed manifest exceeds size limit")
    return raw


def unpack(blob: Any) -> Any:
    """Decompress on demand. Plain (unpacked) values pass straight through."""
    if not is_packed(blob):
        return blob
    if len(blob) - len(_MAGIC) > _MAX_BASE64_BYTES:
        raise ValueError("compressed payload exceeds size limit")
    try:
        encoded_blob = blob.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("invalid packed payload encoding") from exc
    key = hashlib.blake2b(encoded_blob, digest_size=16).hexdigest()
    with _LOCK:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            _STATS["cache_hits"] += 1
            return _CACHE[key]
        _STATS["cache_misses"] += 1
    raw = _decode_packed_payload(blob)
    obj = json.loads(raw)
    with _LOCK:
        _CACHE[key] = obj
        _CACHE.move_to_end(key)
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)
        _STATS["unpacked"] += 1
    return obj


# ── transparent doc-field compression (Mongo) ────────────────────────────────
def compress_field(doc: dict, field: str, min_bytes: int = 600) -> dict:
    """Pack a large dict/list field in-place IF it is worth it. Idempotent."""
    if not doc or field not in doc:
        return doc
    val = doc[field]
    if is_packed(val):
        return doc
    try:
        approx = len(json.dumps(val, default=str))
    except Exception:
        return doc
    if approx >= min_bytes:
        doc[field] = pack(val)
    return doc


def decompress_field(doc: dict, field: str) -> dict:
    """Unpack a field on read (no-op if it was never packed)."""
    if doc and field in doc and is_packed(doc.get(field)):
        doc[field] = unpack(doc[field])
    return doc


def decompress_doc(doc: dict, fields: list[str] | None = None) -> dict:
    if not doc:
        return doc
    for f in (fields or list(doc.keys())):
        if is_packed(doc.get(f)):
            doc[f] = unpack(doc[f])
    return doc


# ── on-disk build-manifest gzip (transparent, decompress-on-demand) ──────────
_BACKEND = Path(__file__).resolve().parent.parent
_BUILDS_VAULT = _BACKEND / "data" / "builds_vault"


def read_manifest_json(path: str | Path) -> Any:
    """Read a manifest, preferring a .gz sibling. Decompress on demand."""
    p = Path(path)
    gz = p.with_suffix(p.suffix + ".gz")
    if gz.exists():
        return json.loads(_read_bounded_gzip_file(gz))
    if p.exists():
        return json.loads(p.read_text())
    return {}


def _gzip_file(p: Path) -> tuple[int, int]:
    """gzip a json file → .json.gz, remove original. Returns (raw, packed)."""
    if p.stat().st_size > MAX_UNPACKED_BYTES:
        raise ValueError("manifest exceeds uncompressed size limit")
    raw = p.read_bytes()
    if len(raw) > MAX_UNPACKED_BYTES:
        raise ValueError("manifest exceeds uncompressed size limit")
    compressed = gzip.compress(raw, compresslevel=6)
    if len(compressed) > MAX_PACKED_BYTES:
        raise ValueError("manifest exceeds compressed size limit")
    gz = p.with_suffix(p.suffix + ".gz")
    gz.write_bytes(compressed)
    packed = len(compressed)
    p.unlink(missing_ok=True)
    return len(raw), packed


def _manifest_disk_stats() -> dict:
    raw_plain = comp = n_plain = n_gz = 0
    if _BUILDS_VAULT.exists():
        for d in _BUILDS_VAULT.iterdir():
            mp = d / "manifest.json"
            gz = d / "manifest.json.gz"
            if mp.exists():
                raw_plain += mp.stat().st_size
                n_plain += 1
            if gz.exists():
                comp += gz.stat().st_size
                n_gz += 1
    return {"uncompressed_files": n_plain, "uncompressed_bytes": raw_plain,
            "compressed_files": n_gz, "compressed_bytes": comp}


# ── source-module inventory ("src partials for all modules") ─────────────────
# Heuristic: large pure-data modules under seeds/ are import-deferred already
# (loaded inside background kicks), so flag them as lazy-eligible bulk.
def module_inventory(top: int = 25) -> dict:
    mods: list[dict] = []
    total_bytes = total_lines = 0
    for root in ("core", "routes", "seeds"):
        d = _BACKEND / root
        if not d.exists():
            continue
        for f in d.rglob("*.py"):
            if "__pycache__" in str(f):
                continue
            b = f.stat().st_size
            try:
                lines = sum(1 for _ in f.open("r", encoding="utf-8", errors="ignore"))
            except Exception:
                lines = 0
            total_bytes += b
            total_lines += lines
            mods.append({
                "module": str(f.relative_to(_BACKEND)),
                "bytes": b, "lines": lines,
                "lazy_eligible": root == "seeds" and b > 100_000,
            })
    mods.sort(key=lambda m: m["bytes"], reverse=True)
    lazy_bytes = sum(m["bytes"] for m in mods if m["lazy_eligible"])
    return {
        "module_count": len(mods),
        "total_bytes": total_bytes,
        "total_lines": total_lines,
        "lazy_eligible_bytes": lazy_bytes,
        "biggest": mods[:top],
    }


# ── unified "Saved Data" report ──────────────────────────────────────────────
def _safe(fn):
    try:
        return fn()
    except Exception:  # never let one source break the whole report
        return {"error": "source_unavailable"}


def savings() -> dict:
    namespaces: list[dict] = []
    total_raw = total_stored = 0

    # 1) zstd knowledge vault (compressed_vault)
    cv = _safe(lambda: __import__("core.compressed_vault", fromlist=["vault_stats"]).vault_stats())
    if isinstance(cv, dict) and "error" not in cv:
        raw = int(cv.get("total_raw_bytes") or 0)
        stored = int(cv.get("total_compressed_bytes") or 0)
        total_raw += raw
        total_stored += stored
        namespaces.append({"namespace": "knowledge_vault (zstd)", "raw_bytes": raw,
                           "stored_bytes": stored, "ratio": cv.get("avg_compression_ratio"),
                           "shards": cv.get("shard_count"), "rows": cv.get("total_rows")})

    # 2) cold-storage frozen collections
    cs = _safe(lambda: __import__("core.cold_storage", fromlist=["stats"]).stats())
    if isinstance(cs, dict) and "error" not in cs:
        raw = int(float(cs.get("cold_raw_mb") or 0) * 1024 * 1024)
        stored = int(float(cs.get("cold_compressed_mb") or 0) * 1024 * 1024)
        total_raw += raw
        total_stored += stored
        namespaces.append({"namespace": "cold_storage (frozen collections)",
                           "raw_bytes": raw, "stored_bytes": stored,
                           "ratio": round(raw / max(1, stored), 2),
                           "frozen": cs.get("frozen"), "shards": cs.get("cold_shards"),
                           "rows": cs.get("cold_rows")})

    # 3) on-disk build manifests (gzip)
    md = _manifest_disk_stats()
    if md["compressed_files"]:
        # estimate raw from compressed using a conservative 6× text ratio when
        # the originals are already gone
        est_raw = md["compressed_bytes"] * 6
        total_raw += est_raw
        total_stored += md["compressed_bytes"]
        namespaces.append({"namespace": "build_manifests (gzip)",
                           "raw_bytes_est": est_raw,
                           "stored_bytes": md["compressed_bytes"],
                           "compressed_files": md["compressed_files"],
                           "uncompressed_remaining": md["uncompressed_files"]})

    # 4) live codec (doc-field compression since boot)
    with _LOCK:
        st = dict(_STATS)
    if st["raw_bytes_in"]:
        total_raw += st["raw_bytes_in"]
        total_stored += st["packed_bytes_out"]
        namespaces.append({"namespace": "doc_fields (gzip codec)",
                           "raw_bytes": st["raw_bytes_in"],
                           "stored_bytes": st["packed_bytes_out"],
                           "ratio": round(st["raw_bytes_in"] / max(1, st["packed_bytes_out"]), 2),
                           "packed": st["packed"]})

    saved = max(0, total_raw - total_stored)
    return {
        "total_raw_bytes": total_raw,
        "total_stored_bytes": total_stored,
        "bytes_saved": saved,
        "saved_pct": round(100 * saved / max(1, total_raw), 1),
        "overall_ratio": round(total_raw / max(1, total_stored), 2),
        "human": {
            "raw": _human(total_raw), "stored": _human(total_stored),
            "saved": _human(saved),
        },
        "namespaces": namespaces,
        "codec": st,
        "cache": {"size": len(_CACHE), "max": _CACHE_MAX,
                  "hits": st["cache_hits"], "misses": st["cache_misses"]},
        "api_response_gzip": True,  # GZipMiddleware active (minimum_size=1000)
    }


def _human(n: int) -> str:
    f = float(n)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if f < 1024 or u == "TB":
            return f"{f:.1f}{u}"
        f /= 1024
    return f"{f:.1f}TB"


# ── transparent batch compaction ("unbulk") ──────────────────────────────────
def sweep(manifest_min_bytes: int = 50_000, freeze_cold: bool = True,
          max_manifests: int = 500) -> dict:
    """Compress oversized build manifests on disk + freeze cold collections.
    Everything stays readable on demand (read_manifest_json / cold_query)."""
    reclaimed = 0
    gz_count = 0
    scanned = 0
    if _BUILDS_VAULT.exists():
        for d in _BUILDS_VAULT.iterdir():
            if gz_count >= max_manifests:
                break
            mp = d / "manifest.json"
            if mp.exists() and mp.stat().st_size >= manifest_min_bytes:
                scanned += 1
                raw, packed = _gzip_file(mp)
                reclaimed += max(0, raw - packed)
                gz_count += 1

    frozen = None
    if freeze_cold:
        frozen = _safe(lambda: __import__("core.cold_storage", fromlist=["freeze_all"]).freeze_all())

    return {"ok": True, "manifests_compressed": gz_count,
            "manifests_scanned": scanned, "bytes_reclaimed": reclaimed,
            "bytes_reclaimed_human": _human(reclaimed), "cold_freeze": frozen}


def purge_cache() -> int:
    with _LOCK:
        n = len(_CACHE)
        _CACHE.clear()
    return n
