"""
╔════════════════════════════════════════════════════════════════════════╗
║  GALAXY STUDIO — BUILD FILE VAULT                                      ║
║  ────────────────────────────────────────────────────────────────────  ║
║  Streams generated build files to zstd-compressed shards on disk       ║
║  so RAM never holds the full payload. At 90 KB/file in memory, a       ║
║  200k-file build would OOM a 31 GB container; this vault keeps the     ║
║  in-memory footprint bounded to a single shard (~2-5k files).          ║
║                                                                        ║
║  Shards live at:                                                       ║
║      {BUILDS_ROOT}/{build_id}/shard_{NNNN}.jsonl.zst                   ║
║      {BUILDS_ROOT}/{build_id}/manifest.json                            ║
║                                                                        ║
║  Public API (all synchronous — safe from any thread):                  ║
║    • append_files(build_id, files_dict)    → manifest entry            ║
║    • get_file_count(build_id)              → int                       ║
║    • list_file_paths(build_id)             → list[{path, size}]        ║
║    • get_file(build_id, path)              → str | None                ║
║    • iter_files(build_id)                  → Iterator[(path, str)]     ║
║    • package_zip(build_id, out_path)       → Path                      ║
║    • clear_build(build_id)                 → None                      ║
║    • preserve_on_failure(build_id)         → None  (no-op marker)      ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations
import os
import io
import json
import time
import zipfile
import threading
from pathlib import Path
from typing import Iterator, Tuple

import zstandard as zstd


# ── Paths ───────────────────────────────────────────────────────────────
def _resolve_writable_dir(preferred: str, fallback: str) -> Path:
    try:
        p = Path(preferred)
        p.mkdir(parents=True, exist_ok=True)
        t = p / ".w_probe"
        t.write_text("ok"); t.unlink(missing_ok=True)
        return p
    except Exception:
        fp = Path(fallback)
        fp.mkdir(parents=True, exist_ok=True)
        return fp


# ★ 2026-02 FIX: default to /tmp (overlay FS, 100+ GB free) instead of
# /app/backend/data/builds_vault (shared 10 GB volume with /data/db + /root
# + /app + /var/log). When that 10 GB volume fills, MongoDB crashes with
# ENOSPC at boot and the whole backend dies silently. The overlay has
# plenty of headroom. Override by setting GALAXY_BUILDS_VAULT_DIR in .env
# if you really want persistence across restarts.
#
# ★ 2026-05 FIX: switched default to PERSISTENT location at
# /app/backend/data/builds_vault. User explicitly wants files preserved
# across pod restarts ("Build does not find files" → root-caused to /tmp
# eviction). Compression keeps space cost low (~10:1, ~190 MB per 31k-file
# build). If disk pressure becomes a problem we can add TTL cleanup or
# move shards to S3. NEVER ship /tmp default again.
BUILDS_ROOT = _resolve_writable_dir(
    os.environ.get("GALAXY_BUILDS_VAULT_DIR", "/app/backend/data/builds_vault"),
    "/tmp/galaxy_builds_vault",
)

_ZLEVEL = int(os.environ.get("GALAXY_BUILDS_ZSTD_LEVEL", "10"))  # balance speed vs ratio
# One compressor per thread — zstd ctxs aren't thread-safe.
_TLS = threading.local()

# Per-build locks so concurrent phases don't corrupt the manifest.
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(build_id: str) -> threading.Lock:
    with _LOCKS_GUARD:
        lk = _LOCKS.get(build_id)
        if lk is None:
            lk = threading.Lock()
            _LOCKS[build_id] = lk
        return lk


def _zctx() -> zstd.ZstdCompressor:
    c = getattr(_TLS, "zc", None)
    if c is None:
        c = zstd.ZstdCompressor(level=_ZLEVEL, threads=-1, write_content_size=True)
        _TLS.zc = c
    return c


_DECOMPRESSOR = zstd.ZstdDecompressor()


# ── Helpers ─────────────────────────────────────────────────────────────
def _build_dir(build_id: str) -> Path:
    p = BUILDS_ROOT / build_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _manifest_path(build_id: str) -> Path:
    return _build_dir(build_id) / "manifest.json"


def _read_manifest(build_id: str) -> dict:
    mp = _manifest_path(build_id)
    gz = mp.with_suffix(mp.suffix + ".gz")
    if gz.exists():
        # Transparently read a swept/compressed manifest (decompress on demand).
        try:
            import gzip as _gz
            return json.loads(_gz.decompress(gz.read_bytes()))
        except Exception:
            return _rebuild_manifest(build_id)
    if not mp.exists():
        return {"build_id": build_id, "shards": [], "file_count": 0,
                "total_raw_bytes": 0, "total_compressed_bytes": 0,
                "path_index": {}, "created_at": time.time()}
    try:
        return json.loads(mp.read_text())
    except Exception:
        # Corrupt manifest — rebuild from shard files on disk.
        return _rebuild_manifest(build_id)


def _write_manifest(build_id: str, manifest: dict) -> None:
    mp = _manifest_path(build_id)
    tmp = mp.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, separators=(",", ":")))
    tmp.replace(mp)


def _rebuild_manifest(build_id: str) -> dict:
    """Walk shard files and reconstruct the manifest. Used on corruption."""
    d = _build_dir(build_id)
    shards = sorted(d.glob("shard_*.jsonl.zst"))
    manifest = {"build_id": build_id, "shards": [], "file_count": 0,
                "total_raw_bytes": 0, "total_compressed_bytes": 0,
                "path_index": {}, "created_at": time.time(),
                "rebuilt": True}
    for sp in shards:
        idx = int(sp.stem.split("_")[1])
        count = 0
        paths = []
        raw = 0
        try:
            with open(sp, "rb") as fh:
                dc = _DECOMPRESSOR.stream_reader(fh)
                buf = io.TextIOWrapper(dc, encoding="utf-8")
                for line in buf:
                    try:
                        row = json.loads(line)
                        paths.append(row["p"])
                        count += 1
                        raw += len(row.get("c", ""))
                    except Exception:
                        continue
        except Exception:
            continue
        entry = {"idx": idx, "file": sp.name, "count": count,
                 "raw_bytes": raw, "compressed_bytes": sp.stat().st_size}
        manifest["shards"].append(entry)
        manifest["file_count"] += count
        manifest["total_raw_bytes"] += raw
        manifest["total_compressed_bytes"] += sp.stat().st_size
        for p in paths:
            manifest["path_index"][p] = idx
    _write_manifest(build_id, manifest)
    return manifest


# ── Public API ──────────────────────────────────────────────────────────
def append_files(build_id: str, files: dict) -> dict:
    """Append a batch of {path: content} to a new shard, update manifest.

    Returns the updated manifest summary. Duplicate paths override the
    previous shard's index (content in the old shard is orphaned until
    clear_build but lookup will always see the newest).
    Safe to call from background threads (per-build lock).
    """
    if not files:
        return {"file_count": get_file_count(build_id), "appended": 0}

    lk = _lock_for(build_id)
    with lk:
        manifest = _read_manifest(build_id)
        next_idx = (manifest["shards"][-1]["idx"] + 1) if manifest["shards"] else 0
        shard_name = f"shard_{next_idx:05d}.jsonl.zst"
        shard_path = _build_dir(build_id) / shard_name

        count = 0
        raw = 0
        zc = _zctx()
        with open(shard_path, "wb") as fh:
            with zc.stream_writer(fh) as zw:
                for path, content in files.items():
                    if content is None:
                        continue
                    if not isinstance(content, str):
                        try:
                            content = str(content)
                        except Exception:
                            continue
                    line = json.dumps({"p": path, "c": content},
                                      separators=(",", ":"),
                                      ensure_ascii=False).encode("utf-8") + b"\n"
                    zw.write(line)
                    raw += len(content)
                    count += 1
                    manifest["path_index"][path] = next_idx

        if count == 0:
            try: shard_path.unlink()
            except Exception: pass
            return {"file_count": manifest["file_count"], "appended": 0}

        compressed = shard_path.stat().st_size
        entry = {"idx": next_idx, "file": shard_name, "count": count,
                 "raw_bytes": raw, "compressed_bytes": compressed,
                 "created_at": time.time()}
        manifest["shards"].append(entry)
        manifest["file_count"] += count
        manifest["total_raw_bytes"] += raw
        manifest["total_compressed_bytes"] += compressed
        _write_manifest(build_id, manifest)
        return {
            "file_count": manifest["file_count"],
            "appended": count,
            "shard": shard_name,
            "compressed_bytes": compressed,
            "compression_ratio": round(raw / max(compressed, 1), 2),
        }


def get_file_count(build_id: str) -> int:
    return _read_manifest(build_id).get("file_count", 0)


def get_stats(build_id: str) -> dict:
    m = _read_manifest(build_id)
    return {
        "build_id": build_id,
        "file_count": m.get("file_count", 0),
        "shards": len(m.get("shards", [])),
        "total_raw_bytes": m.get("total_raw_bytes", 0),
        "total_compressed_bytes": m.get("total_compressed_bytes", 0),
        "compression_ratio": round(m.get("total_raw_bytes", 0) /
                                   max(m.get("total_compressed_bytes", 1), 1), 2),
    }


def _iter_shard(build_id: str, shard_file: str) -> Iterator[Tuple[str, str]]:
    sp = _build_dir(build_id) / shard_file
    if not sp.exists():
        return
    try:
        with open(sp, "rb") as fh:
            dc = _DECOMPRESSOR.stream_reader(fh)
            buf = io.TextIOWrapper(dc, encoding="utf-8")
            while True:
                try:
                    line = next(buf)
                except StopIteration:
                    break
                except Exception:
                    # A shard still being flushed by a live runner (or a
                    # truncated/corrupt frame) raises mid-stream zstd/UTF-8
                    # errors. Stop reading THIS shard gracefully instead of
                    # crashing the whole vault read (e.g. /vault/zip during a
                    # force-completed-but-still-writing build).
                    break
                try:
                    row = json.loads(line)
                    yield row["p"], row.get("c", "")
                except Exception:
                    continue
    except Exception:
        # Couldn't even open/decompress the shard — skip it entirely.
        return


def list_file_paths(build_id: str, limit: int = 0) -> list[dict]:
    """List all paths with size. Streams through shards without loading
    content into RAM — we need full content only to measure size, so we
    do it shard-by-shard and discard."""
    out = []
    m = _read_manifest(build_id)
    for shard in m.get("shards", []):
        for p, c in _iter_shard(build_id, shard["file"]):
            out.append({"path": p, "size": len(c),
                        "lines": c.count("\n") + 1,
                        "type": p.split(".")[-1] if "." in p else "txt"})
            if limit and len(out) >= limit:
                return out
    # De-dup by path keeping the LAST occurrence (most recent shard wins)
    dedup: dict[str, dict] = {}
    for entry in out:
        dedup[entry["path"]] = entry
    return list(dedup.values())


def get_file(build_id: str, file_path: str) -> str | None:
    m = _read_manifest(build_id)
    idx = m.get("path_index", {}).get(file_path)
    if idx is None:
        # Fallback — scan all shards in reverse (newest first)
        for shard in reversed(m.get("shards", [])):
            for p, c in _iter_shard(build_id, shard["file"]):
                if p == file_path:
                    return c
        return None
    # Find the shard entry for that idx
    target = next((s for s in m["shards"] if s["idx"] == idx), None)
    if not target:
        return None
    # Scan only that shard (single-file lookup inside a shard is linear
    # but shards are ~2k files so it's fast).
    latest = None
    for p, c in _iter_shard(build_id, target["file"]):
        if p == file_path:
            latest = c
    return latest


def iter_files(build_id: str) -> Iterator[Tuple[str, str]]:
    """Stream all (path, content) pairs, newest wins on duplicates.
    Memory-bounded: only one shard's content passes through at a time."""
    m = _read_manifest(build_id)
    seen: set[str] = set()
    # Walk newest → oldest, emit first occurrence only
    for shard in reversed(m.get("shards", [])):
        for p, c in _iter_shard(build_id, shard["file"]):
            if p in seen:
                continue
            seen.add(p)
            yield p, c


def package_zip(build_id: str, out_path: Path | None = None) -> Path:
    """Stream vault contents into a ZIP file on disk (no full in-RAM copy)."""
    d = _build_dir(build_id)
    if out_path is None:
        out_path = d / f"{build_id}.zip"
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6, allowZip64=True) as zf:
        for p, c in iter_files(build_id):
            try:
                zf.writestr(p, c)
            except Exception:
                continue
    return out_path


def clear_build(build_id: str) -> None:
    """Delete all shards and manifest for a build. Called on explicit user
    deletion. NOT called on failure — failure preserves shards so user can
    still download or resume."""
    d = _build_dir(build_id)
    if not d.exists():
        return
    try:
        for f in d.iterdir():
            try: f.unlink()
            except Exception: pass
        d.rmdir()
    except Exception:
        pass


def preserve_on_failure(build_id: str) -> dict:
    """Mark a build's vault as preserved so later resume / download still
    works. Writes a FAILED marker file and returns stats. Does NOT delete."""
    m = _read_manifest(build_id)
    marker = _build_dir(build_id) / "FAILED.marker"
    marker.write_text(json.dumps({
        "build_id": build_id,
        "preserved_at": time.time(),
        "file_count": m.get("file_count", 0),
        "shards": len(m.get("shards", [])),
    }))
    return get_stats(build_id)


def prune_old_builds(keep: int = 12, protect: set | None = None) -> dict:
    """Keep only the `keep` most-recent build dirs; delete the rest to bound
    disk usage. Builds marked FAILED (preserved) and any in `protect` are
    never deleted. Safe to call after every completion. Returns a report."""
    protect = protect or set()
    try:
        keep = max(1, int(os.environ.get("GALAXY_VAULT_KEEP", keep)))
    except Exception:
        keep = 12
    if not BUILDS_ROOT.exists():
        return {"pruned": 0, "kept": 0, "protected": 0}
    entries = []
    for d in BUILDS_ROOT.iterdir():
        if not d.is_dir():
            continue
        try:
            mtime = d.stat().st_mtime
        except Exception:
            mtime = 0.0
        preserved = (d / "FAILED.marker").exists()
        entries.append((d.name, mtime, preserved))
    # newest first
    entries.sort(key=lambda e: e[1], reverse=True)
    kept = 0
    pruned = 0
    protected = 0
    for idx, (name, _mt, preserved) in enumerate(entries):
        if name in protect or preserved:
            protected += 1
            continue
        if kept < keep:
            kept += 1
            continue
        try:
            clear_build(name)
            pruned += 1
        except Exception:
            pass
    return {"pruned": pruned, "kept": kept, "protected": protected, "total_before": len(entries)}


def global_stats() -> dict:
    """Summary of all builds currently in the vault, incl. compression savings."""
    if not BUILDS_ROOT.exists():
        return {"builds": 0, "total_files": 0, "disk_bytes": 0,
                "raw_bytes": 0, "compression_ratio": 1.0, "saved_bytes": 0}
    total_files = 0
    disk = 0
    raw = 0
    builds = 0
    newest_id = None
    newest_mtime = -1.0
    for d in BUILDS_ROOT.iterdir():
        if not d.is_dir():
            continue
        builds += 1
        try:
            mt = d.stat().st_mtime
            if mt > newest_mtime:
                newest_mtime = mt
                newest_id = d.name
        except Exception:
            pass
        m = _read_manifest(d.name)
        total_files += m.get("file_count", 0)
        disk += m.get("total_compressed_bytes", 0)
        raw += m.get("total_raw_bytes", 0)
    return {
        "builds": builds,
        "total_files": total_files,
        "disk_bytes": disk,
        "raw_bytes": raw,
        "compression_ratio": round(raw / max(disk, 1), 2),
        "saved_bytes": max(0, raw - disk),
        "zstd_level": _ZLEVEL,
        "newest_build_id": newest_id,
    }
