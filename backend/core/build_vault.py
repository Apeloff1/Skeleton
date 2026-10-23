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
import json
import time
import zipfile
import threading
import logging
import tempfile
from pathlib import Path, PurePosixPath
from typing import Iterable, Iterator, Tuple

import zstandard as zstd

_log = logging.getLogger(__name__)


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
# ★ 2026-10 FIX: durable default matches backend_data:/app/data mount.
# /app/backend/data was on the read-only image filesystem and silently
# redirected the vault to the 64 MiB /tmp tmpfs. Admission required 64 MiB
# free and could therefore never start a real build.
# Switched default to PERSISTENT location at
# /app/data/builds_vault. User explicitly wants files preserved
# across pod restarts ("Build does not find files" → root-caused to /tmp
# eviction). Compression keeps space cost low (~10:1, ~190 MB per 31k-file
# build). If disk pressure becomes a problem we can add TTL cleanup or
# move shards to S3. NEVER ship /tmp default again.
BUILDS_ROOT = _resolve_writable_dir(
    os.environ.get("GALAXY_BUILDS_VAULT_DIR", "/app/data/builds_vault"),
    "/tmp/galaxy_builds_vault",
)

_ZLEVEL = int(os.environ.get("GALAXY_BUILDS_ZSTD_LEVEL", "10"))  # balance speed vs ratio
# One compressor per thread — zstd ctxs aren't thread-safe.
_TLS = threading.local()

# Per-build locks so concurrent phases don't corrupt the manifest.
_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()
_MAX_BUILD_ID_LENGTH = 128
_MAX_ARCHIVE_MEMBER_LENGTH = 4096


def _validate_build_id(build_id: str) -> str:
    """Accept only a bounded single safe path component for build directories."""
    if not isinstance(build_id, str) or not build_id or len(build_id) > _MAX_BUILD_ID_LENGTH:
        raise ValueError("build_id must be a non-empty bounded identifier")
    if build_id != build_id.strip() or build_id in {".", ".."}:
        raise ValueError("build_id must be a canonical identifier")
    if Path(build_id).name != build_id:
        raise ValueError("build_id must be a single path component")
    allowed = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    if any(ch not in allowed for ch in build_id):
        raise ValueError("build_id contains unsupported path characters")
    return build_id


def _safe_archive_member(path: str) -> str:
    """Reject archive member names that could escape a later extraction root."""
    value = str(path)
    if not value or len(value) > _MAX_ARCHIVE_MEMBER_LENGTH or "\x00" in value or "\\" in value:
        raise ValueError("unsafe archive member path")
    member = PurePosixPath(value)
    if member.is_absolute() or any(part in {"", ".", ".."} for part in member.parts):
        raise ValueError("unsafe archive member path")
    return member.as_posix()


def _lock_for(build_id: str) -> threading.RLock:
    build_id = _validate_build_id(build_id)
    with _LOCKS_GUARD:
        lk = _LOCKS.get(build_id)
        if lk is None:
            lk = threading.RLock()
            _LOCKS[build_id] = lk
        return lk


def _zctx() -> zstd.ZstdCompressor:
    c = getattr(_TLS, "zc", None)
    if c is None:
        # The artifact owner already admits physical workers. A compressor
        # per worker must not create another pool spanning every host CPU.
        c = zstd.ZstdCompressor(level=_ZLEVEL, threads=0, write_content_size=True)
        _TLS.zc = c
    return c


# ── Helpers ─────────────────────────────────────────────────────────────
def _build_dir(build_id: str) -> Path:
    build_id = _validate_build_id(build_id)
    root = os.path.realpath(os.fspath(BUILDS_ROOT))
    candidate = os.path.realpath(os.path.normpath(os.path.join(root, build_id)))
    root_prefix = root + os.sep
    if not candidate.startswith(root_prefix):
        raise ValueError("build_id resolves outside the build vault root")
    path = Path(candidate)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _manifest_path(build_id: str) -> Path:
    return _build_dir(build_id) / "manifest.json"


def _read_manifest(build_id: str) -> dict:
    with _lock_for(build_id):
        return _read_manifest_locked(build_id)


def _read_manifest_locked(build_id: str) -> dict:
    mp = _manifest_path(build_id)
    gz = mp.with_suffix(mp.suffix + ".gz")
    if mp.exists():
        try:
            manifest = json.loads(mp.read_text())
            return _normalize_manifest(build_id, manifest)
        except (OSError, TypeError, ValueError, KeyError, RecursionError, OverflowError):
            return _rebuild_manifest(build_id)
    if gz.exists():
        # Transparently read a swept/compressed manifest (decompress on demand).
        try:
            import gzip as _gz
            return _normalize_manifest(build_id, json.loads(_gz.decompress(gz.read_bytes())))
        except Exception:
            return _rebuild_manifest(build_id)
    if any(mp.parent.glob("shard_*.jsonl.zst")):
        return _rebuild_manifest(build_id)
    return {
        "build_id": build_id,
        "shards": [],
        "file_count": 0,
        "total_raw_bytes": 0,
        "total_compressed_bytes": 0,
        "path_index": {},
        "created_at": time.time(),
    }


def _normalize_manifest(build_id: str, manifest: object) -> dict:
    if not isinstance(manifest, dict) or manifest.get("build_id") != build_id:
        raise ValueError("invalid build manifest identity")
    shards = manifest.get("shards")
    paths = manifest.get("path_index")
    if not isinstance(shards, list) or not isinstance(paths, dict):
        raise ValueError("invalid build manifest indexes")
    indices = set()
    previous = -1
    for shard in shards:
        if not isinstance(shard, dict):
            raise ValueError("invalid shard entry")
        idx = shard.get("idx")
        if isinstance(idx, bool) or not isinstance(idx, int) or idx <= previous:
            raise ValueError("invalid shard sequence")
        if shard.get("file") != f"shard_{idx:05d}.jsonl.zst":
            raise ValueError("invalid shard identity")
        for field in ("count", "raw_bytes", "compressed_bytes"):
            value = shard.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("invalid shard counters")
        previous = idx
        indices.add(idx)
    if any(
        not isinstance(path, str) or isinstance(idx, bool) or not isinstance(idx, int) or idx not in indices
        for path, idx in paths.items()
    ):
        raise ValueError("invalid live path index")
    for field in ("total_raw_bytes", "total_compressed_bytes"):
        value = manifest.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("invalid manifest counters")
    # Earlier manifests counted overwritten physical records as live files.
    manifest["file_count"] = len(paths)
    return manifest


def _write_manifest(build_id: str, manifest: dict) -> None:
    with _lock_for(build_id):
        mp = _manifest_path(build_id)
        descriptor, name = tempfile.mkstemp(prefix=".manifest-", suffix=".tmp", dir=mp.parent)
        tmp = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(manifest, handle, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            tmp.replace(mp)
        finally:
            _discard_temporary(tmp)


def _discard_temporary(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        _log.warning("failed to remove attempt-owned vault temporary %s: %s", path, exc)


def _shard_records(path: Path) -> Iterator[Tuple[str, str]]:
    """Decode one complete frame with an attempt-private decoder context."""
    decoder = zstd.ZstdDecompressor().decompressobj()
    pending = bytearray()
    with path.open("rb") as handle:
        while compressed := handle.read(256):
            if decoder.eof:
                raise ValueError("trailing bytes after vault shard frame")
            pending.extend(decoder.decompress(compressed))
            if decoder.unused_data:
                raise ValueError("trailing bytes after vault shard frame")
            start = 0
            while (end := pending.find(b"\n", start)) >= 0:
                row = json.loads(pending[start:end])
                if (
                    not isinstance(row, dict)
                    or not isinstance(row.get("p"), str)
                    or not isinstance(row.get("c"), str)
                ):
                    raise ValueError("invalid vault shard record")
                yield row["p"], row["c"]
                start = end + 1
            if start:
                del pending[:start]
    if not decoder.eof or pending:
        raise ValueError("incomplete vault shard frame or record")


def _rebuild_manifest(build_id: str) -> dict:
    """Walk shard files and reconstruct the manifest. Used on corruption."""
    with _lock_for(build_id):
        return _rebuild_manifest_locked(build_id)


def _rebuild_manifest_locked(build_id: str) -> dict:
    d = _build_dir(build_id)
    shards = []
    for path in d.glob("shard_*.jsonl.zst"):
        try:
            idx = int(path.name.removeprefix("shard_").removesuffix(".jsonl.zst"))
        except ValueError:
            continue
        if idx >= 0 and path.name == f"shard_{idx:05d}.jsonl.zst":
            shards.append((idx, path))
    shards.sort(key=lambda item: item[0])
    manifest = {"build_id": build_id, "shards": [], "file_count": 0,
                "total_raw_bytes": 0, "total_compressed_bytes": 0,
                "path_index": {}, "created_at": time.time(),
                "rebuilt": True}
    for idx, sp in shards:
        count = 0
        paths = []
        raw = 0
        try:
            for path, content in _shard_records(sp):
                paths.append(path)
                count += 1
                raw += len(content.encode("utf-8"))
        except Exception:
            continue
        entry = {"idx": idx, "file": sp.name, "count": count,
                 "raw_bytes": raw, "compressed_bytes": sp.stat().st_size}
        manifest["shards"].append(entry)
        manifest["total_raw_bytes"] += raw
        manifest["total_compressed_bytes"] += sp.stat().st_size
        for p in paths:
            manifest["path_index"][p] = idx
    manifest["file_count"] = len(manifest["path_index"])
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
        directory = _build_dir(build_id)
        indices = [shard["idx"] for shard in manifest["shards"]]
        for existing in directory.glob("shard_*.jsonl.zst"):
            try:
                indices.append(int(existing.name.removeprefix("shard_").removesuffix(".jsonl.zst")))
            except ValueError:
                continue
        # A complete shard can survive an interrupted manifest publication.
        # Retained source must never be overwritten by the following attempt.
        next_idx = max(indices, default=-1) + 1
        shard_name = f"shard_{next_idx:05d}.jsonl.zst"
        shard_path = directory / shard_name
        descriptor, name = tempfile.mkstemp(prefix=".shard-", suffix=".tmp", dir=directory)
        staged = Path(name)

        count = 0
        raw = 0
        try:
            with os.fdopen(descriptor, "wb") as fh:
                zc = _zctx()
                with zc.stream_writer(fh, closefd=False) as zw:
                    for path, content in files.items():
                        if not isinstance(path, str):
                            raise ValueError("vault paths must be strings")
                        if content is None:
                            continue
                        if not isinstance(content, str):
                            try:
                                content = str(content)
                            except Exception:
                                continue
                        line = (
                            json.dumps(
                                {"p": path, "c": content}, separators=(",", ":"), ensure_ascii=False
                            ).encode("utf-8")
                            + b"\n"
                        )
                        zw.write(line)
                        raw += len(content.encode("utf-8"))
                        count += 1
                        manifest["path_index"][path] = next_idx
                fh.flush()
                os.fsync(fh.fileno())

            if count == 0:
                return {"file_count": manifest["file_count"], "appended": 0}

            compressed = staged.stat().st_size
            # Publish only after the frame footer and file data are durable.
            # A rebuild never sees an attempt's incomplete temporary frame.
            os.link(staged, shard_path)
            entry = {
                "idx": next_idx,
                "file": shard_name,
                "count": count,
                "raw_bytes": raw,
                "compressed_bytes": compressed,
                "created_at": time.time(),
            }
            manifest["shards"].append(entry)
            manifest["file_count"] = len(manifest["path_index"])
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
        finally:
            _discard_temporary(staged)


def get_file_count(build_id: str, *, pending_paths: Iterable[str] = ()) -> int:
    """Count unique live paths, including an optional bounded pending snapshot."""
    with _lock_for(build_id):
        manifest = _read_manifest(build_id)
        index = manifest["path_index"]
        pending = set(pending_paths)
        if any(not isinstance(path, str) for path in pending):
            raise ValueError("pending vault paths must be strings")
        return len(index) + sum(path not in index for path in pending)


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
    safe_build_id = _validate_build_id(build_id)
    if not shard_file or Path(shard_file).name != shard_file:
        return
    if shard_file in {".", ".."} or any(ch in shard_file for ch in "/\\\x00"):
        return
    sp = _build_dir(safe_build_id) / shard_file
    # Consumers must exhaust the frame before accepting a file or publishing
    # an archive. A missing/truncated source is a failed read, never a smaller
    # successful build assembled from the rows yielded before the failure.
    yield from _shard_records(sp)


def list_file_paths(build_id: str, limit: int = 0) -> list[dict]:
    """List all paths with size. Streams through shards without loading
    content into RAM — we need full content only to measure size, so we
    do it shard-by-shard and discard."""
    out = []
    m = _read_manifest(build_id)
    for shard in m.get("shards", []):
        for p, c in _iter_shard(build_id, shard["file"]):
            if m["path_index"].get(p) != shard["idx"]:
                continue
            if limit and len(out) >= limit:
                continue
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
            latest = None
            for p, c in _iter_shard(build_id, shard["file"]):
                if p == file_path:
                    latest = c
            if latest is not None:
                return latest
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
    with _lock_for(build_id):
        return _package_zip_locked(build_id, out_path)


def _package_zip_locked(build_id: str, out_path: Path | None = None) -> Path:
    d = _build_dir(build_id)
    if out_path is None:
        out_path = d / f"{_validate_build_id(build_id)}.zip"
    else:
        root = os.path.realpath(os.fspath(d))
        requested = os.fspath(out_path)
        candidate = os.path.realpath(os.path.normpath(
            requested if os.path.isabs(requested) else os.path.join(root, requested)
        ))
        if not candidate.startswith(root + os.sep):
            raise ValueError("out_path must stay inside the build directory")
        out_path = Path(candidate)
    descriptor, name = tempfile.mkstemp(prefix=".package-", suffix=".tmp", dir=out_path.parent)
    staged = Path(name)
    try:
        with os.fdopen(descriptor, "w+b") as handle:
            with zipfile.ZipFile(
                handle, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True
            ) as zf:
                for p, c in iter_files(build_id):
                    try:
                        zf.writestr(_safe_archive_member(p), c)
                    except (ValueError, OSError, RuntimeError, zipfile.BadZipFile):
                        continue
            handle.flush()
            os.fsync(handle.fileno())
        staged.replace(out_path)
        return out_path
    finally:
        _discard_temporary(staged)


def clear_build(build_id: str) -> None:
    """Delete all shards and manifest for a build. Called on explicit user
    deletion. NOT called on failure — failure preserves shards so user can
    still download or resume."""
    with _lock_for(build_id):
        d = _build_dir(build_id)
        if not d.exists():
            return
        try:
            for f in d.iterdir():
                try:
                    f.unlink()
                except OSError as exc:
                    _log.warning("failed to remove vault shard %s: %s", f, exc)
            d.rmdir()
        except OSError as exc:
            _log.warning("failed to clear vault directory %s: %s", d, exc)


def preserve_on_failure(build_id: str) -> dict:
    """Mark a build's vault as preserved so later resume / download still
    works. Writes a FAILED marker file and returns stats. Does NOT delete."""
    with _lock_for(build_id):
        m = _read_manifest(build_id)
        marker = _build_dir(build_id) / "FAILED.marker"
        marker.write_text(
            json.dumps(
                {
                    "build_id": build_id,
                    "preserved_at": time.time(),
                    "file_count": m.get("file_count", 0),
                    "shards": len(m.get("shards", [])),
                }
            )
        )
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
