"""
routes/galaxy_studio_vault.py — Vault read + ZIP-write sub-router.

Extracted from routes/galaxy_studio.py:
  • Phase-5 (Feb 2026) — read endpoints (/vault, /vault/download/{id}).
  • Phase-6 (Feb 2026) — ZIP-write endpoint (/vault/zip/{id}).

The remaining /vault/zip-to-apk/{id} endpoint stays in the parent module
because it carries deep coupling to ``_disk_write_file``, EAS subprocess
wiring, and Expo app.json templating.

Cycle-break: every parent helper that this sub-router needs is reached
via a lazy proxy in ``galaxy_studio_state`` — ``_vault_entries``,
``get_all_vault_entries()``, ``load_build()``, ``get_vault_dir()``,
``get_zip_write_file()``, ``get_vault_save()``, ``save_vault_entry()``.
"""
from __future__ import annotations

import os
import zipfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from routes.galaxy_studio_state import (
    _vault_entries,
    get_all_vault_entries,
    load_build,
    get_vault_dir,
    get_zip_write_file,
    get_vault_save,
    save_vault_entry,
)

router = APIRouter(tags=["galaxy-studio"])


def _safe_segment(value: str, *, what: str = "path") -> str:
    """Reject path traversal / absolute segments in user-supplied ids."""
    s = str(value or "").strip()
    if (
        not s
        or s in {".", ".."}
        or ".." in s
        or "/" in s
        or "\\" in s
        or s.startswith(("~", "/", "\\"))
    ):
        raise HTTPException(400, f"invalid {what}")
    return s


def _safe_slug(title: str, *, fallback: str = "build") -> str:
    raw = (title or fallback).lower().replace(" ", "-")
    cleaned = "".join(c if (c.isalnum() or c in "-_") else "-" for c in raw)
    cleaned = cleaned.strip("-_")[:20] or fallback
    return _safe_segment(cleaned, what="slug")


def _resolve_under_dir(root: str, *parts: str) -> str:
    """Join under root; 400 if result escapes root."""
    root_r = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(root_r, *parts))
    if candidate != root_r and not candidate.startswith(root_r + os.sep):
        raise HTTPException(400, "path escapes vault sandbox")
    return candidate




@router.post("/vault/zip/{build_id}")
async def vault_create_zip(build_id: str) -> dict:
    """Generate ZIP from a completed build and save it to the vault.

    Streams from the on-disk build-vault shards (memory-safe for massive
    builds) so we never blow RAM packaging a 30 000+ file build.
    """
    build = await load_build(build_id)
    if not build:
        raise HTTPException(404, "Build not found")

    from core import build_vault as _bv
    vault_count = _bv.get_file_count(build_id)
    mem_files = build.get("files") or {}
    if vault_count == 0 and not mem_files:
        raise HTTPException(400, "No files to package. Complete build first.")

    safe_id = _safe_segment(build_id, what="build_id")
    slug = _safe_slug(build.get("title") or "build", fallback="build")
    zip_filename = f"{slug}-{safe_id[:8]}.zip"
    zip_path = _resolve_under_dir(get_vault_dir(), "zips", zip_filename)
    os.makedirs(os.path.dirname(zip_path), exist_ok=True)

    zip_write_file = get_zip_write_file()
    written: set[str] = set()
    total_files = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        # 1) Stream vault shards (memory-bounded).
        for path, content in _bv.iter_files(build_id):
            if path in written:
                continue
            try:
                zip_write_file(zf, f"{slug}/{path}", content)
                written.add(path)
                total_files += 1
            except Exception:
                continue
        # 2) Top up with any unflushed in-memory files.
        for path, content in mem_files.items():
            if path in written:
                continue
            try:
                zip_write_file(zf, f"{slug}/{path}", content)
                written.add(path)
                total_files += 1
            except Exception:
                continue

    entry = get_vault_save()(
        safe_id,
        "zip",
        build.get("title", "game"),
        zip_path,
        {"file_count": total_files, "genre": build.get("genre", "unknown")},
    )
    try:
        await save_vault_entry(entry)
    except Exception:
        pass

    return {
        "vault_id": entry["vault_id"],
        "filename": zip_filename,
        "size": entry["size_human"],
        "size_bytes": entry["size_bytes"],
        "file_count": total_files,
        "download_url": f"/api/galaxy-studio/vault/download/{entry['vault_id']}",
        "message": f"ZIP saved to vault: {zip_filename} ({entry['size_human']})",
    }


@router.get("/vault")
async def vault_list() -> dict:
    """List all vault entries (ZIPs and APKs).

    Refreshes the in-memory ``_vault_entries`` cache from Mongo on every
    call (cheap — single ``find()``) so we never serve stale entries to
    the operator.
    """
    await get_all_vault_entries()
    entries = sorted(_vault_entries.values(), key=lambda e: e["created_at"], reverse=True)
    zips = [e for e in entries if e["type"] == "zip"]
    apks = [e for e in entries if e["type"] == "apk"]
    return {
        "total_entries": len(entries),
        "zips": [{
            "vault_id": e["vault_id"],
            "title": e["title"],
            "filename": e["filename"],
            "size": e["size_human"],
            "size_bytes": e["size_bytes"],
            "file_count": e.get("file_count", 0),
            "genre": e.get("genre", ""),
            "created_at": e["created_at"],
            "download_url": f"/api/galaxy-studio/vault/download/{e['vault_id']}",
        } for e in zips],
        "apks": [{
            "vault_id": e["vault_id"],
            "title": e["title"],
            "filename": e["filename"],
            "size": e["size_human"],
            "size_bytes": e["size_bytes"],
            "eas_build_id": e.get("eas_build_id", ""),
            "status": e.get("status", ""),
            "created_at": e["created_at"],
            "download_url": f"/api/galaxy-studio/vault/download/{e['vault_id']}",
        } for e in apks],
    }


@router.get("/vault/download/{vault_id}")
async def vault_download(vault_id: str):
    """Stream a vault entry (ZIP or APK) back to the client.

    404s in two distinct cases that operators care about:
      1. ``Vault entry not found`` — Mongo + cache both lack this id.
      2. ``File no longer exists on disk`` — entry was logged but the
         underlying file got swept (eviction, dev-box cleanup, …).
    """
    await get_all_vault_entries()
    safe_vid = _safe_segment(vault_id, what="vault_id")
    entry = _vault_entries.get(safe_vid) or _vault_entries.get(vault_id)
    if not entry:
        raise HTTPException(404, "Vault entry not found")
    root = os.path.realpath(get_vault_dir())
    real = os.path.realpath(entry["path"])
    if real != root and not real.startswith(root + os.sep):
        raise HTTPException(400, "path escapes vault sandbox")
    file_path = real
    if not os.path.exists(file_path):
        raise HTTPException(404, "File no longer exists on disk")
    media_type = (
        "application/zip"
        if entry["type"] == "zip"
        else "application/vnd.android.package-archive"
    )
    return FileResponse(file_path, media_type=media_type, filename=entry["filename"])


__all__ = ["router"]
