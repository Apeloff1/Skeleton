"""
routes/galaxy_studio_files.py — Files & download sub-router.

Extracted from routes/galaxy_studio.py (Phase-6 decomposition, Feb 2026).
Hosts the 4 file-listing / single-file / ZIP-download / APK-download
endpoints:

  GET /files/{build_id}
  GET /file/{build_id}/{file_path:path}
  GET /download/{build_id}
  GET /download-apk/{build_id}

The APK pipeline (binary_builder) is wired through a lazy import; the
ZIP-packaging helper (_package_build) and binary-prefix sentinel
(_BINARY_PREFIX) come via galaxy_studio_state lazy proxies.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from routes.galaxy_studio_state import (
    load_build,
    get_package_build,
    get_binary_prefix,
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


def _resolve_under_dir(root: str, *parts: str) -> str:
    """Join under root; 400 if result escapes root."""
    root_r = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(root_r, *parts))
    if candidate != root_r and not candidate.startswith(root_r + os.sep):
        raise HTTPException(400, "path escapes download sandbox")
    return candidate




@router.get("/files/{build_id}")
async def get_files(build_id: str):
    """Get all generated files for a build.

    Checks the in-memory build dict first, then falls through to the on-disk
    compressed vault. Returns a paginated-friendly file listing — never 400s
    just because the build was already compressed.
    """
    build = await load_build(build_id)
    if not build:
        raise HTTPException(404, "Build not found")

    files = build.get("files") or {}

    # ── UNION vault + memory (2026-06-18 fix) ──────────────────────────
    # Previously the vault was only consulted when in-memory `files` was
    # empty. After a full build the in-memory dict often retains a few
    # residual docs from the last batch while the on-disk vault holds the
    # full ~25k generated files (including the mutation permutation
    # modules). Short-circuiting on memory therefore hid almost everything.
    # We now union BOTH sources, deduping by path (vault wins on conflict).
    vault_meta: list[dict] = []
    try:
        from core import build_vault as _bv
        vault_meta = _bv.list_file_paths(build_id, limit=300000) or []
    except Exception:
        vault_meta = []

    by_path: dict[str, dict] = {}

    for path, content in files.items():
        if isinstance(content, str):
            size  = len(content)
            lines = content.count("\n") + 1
        elif isinstance(content, dict):
            size  = content.get("size", 0)
            lines = content.get("lines", 0)
        else:
            try: size = int(content)
            except Exception: size = 0
            lines = 0
        by_path[path] = {
            "path":  path,
            "size":  size,
            "lines": lines,
            "type":  path.split(".")[-1] if "." in path else "txt",
        }

    # Vault entries override/extend memory (vault is the source of truth).
    for entry in vault_meta:
        path = entry.get("path", "")
        if not path:
            continue
        by_path[path] = {
            "path":  path,
            "size":  entry.get("size", 0),
            "lines": entry.get("lines", 0),
            "type":  path.split(".")[-1] if "." in path else "txt",
        }

    if not by_path:
        return {
            "build_id":    build_id,
            "title":       build.get("title", ""),
            "total_files": 0,
            "total_lines": 0,
            "total_bytes": 0,
            "files":       [],
            "source":      "empty",
        }

    file_list = list(by_path.values())
    if vault_meta and files:
        source = "vault+memory"
    elif vault_meta:
        source = "vault"
    else:
        source = "memory"

    return {
        "build_id":    build_id,
        "title":       build.get("title", ""),
        "total_files": len(file_list),
        "total_lines": sum(f["lines"] for f in file_list),
        "total_bytes": sum(f["size"]  for f in file_list),
        "files":       sorted(file_list, key=lambda f: f["path"]),
        "source":      source,
    }


@router.get("/file/{build_id}/{file_path:path}")
async def get_file(build_id: str, file_path: str):
    """Get content of a single generated file. Checks in-memory first,
    then the on-disk vault."""
    build = await load_build(build_id)
    if not build:
        raise HTTPException(404, "Build not found")

    mem     = build.get("files") or {}
    content = mem.get(file_path)
    if content is None:
        try:
            from core import build_vault as _bv
            content = _bv.get_file(build_id, file_path)
        except Exception:
            content = None
    if content is None:
        raise HTTPException(404, f"File '{file_path}' not found")
    return {
        "path":    file_path,
        "content": content,
        "lines":   content.count("\n") + 1,
        "size":    len(content),
    }


@router.get("/download/{build_id}")
async def download_build(build_id: str):
    """Download build as ZIP. Streams from the on-disk vault so massive
    builds (250k+ files) download without OOM."""
    build = await load_build(build_id)
    if not build:
        raise HTTPException(404, "Build not found")

    if build.get("download_url"):
        return {"redirect": build["download_url"], "type": "apk"}

    from core import build_vault as _bv
    vault_count = _bv.get_file_count(build_id)
    mem_count   = len(build.get("files") or {})
    if vault_count == 0 and mem_count == 0:
        raise HTTPException(400, "No files. Complete build first.")

    safe_id = _safe_segment(build_id, what="build_id")
    zip_path = await get_package_build(safe_id)
    # Same-file sanitizer for FileResponse (CodeQL path-injection).
    zip_path = _resolve_under_dir("/tmp/galaxy_studio", safe_id, os.path.basename(zip_path))
    if not os.path.isfile(zip_path):
        raise HTTPException(404, "ZIP not ready")
    filename = f"{(build.get('title') or 'game').lower().replace(' ', '-')[:20]}-galaxy-studio.zip"
    return FileResponse(zip_path, media_type="application/zip", filename=filename)


@router.get("/download-apk/{build_id}")
async def download_build_apk(build_id: str):
    """Download build as a REAL signed Android APK (sideload-able on
    Android 7+). Wires the galaxy_studio build into the new binary_builder
    APK pipeline (javac → d8 → aapt2 → apksigner v2+v3)."""
    build = await load_build(build_id)
    if not build:
        raise HTTPException(404, "Build not found")

    from core import build_vault as _bv
    from services import binary_builder
    vault_count = _bv.get_file_count(build_id)
    mem_files   = build.get("files") or {}
    if vault_count == 0 and not mem_files:
        raise HTTPException(400, "No files. Complete build first.")

    _BIN_PREFIX = get_binary_prefix()

    files_list: list[dict] = []
    seen: set[str] = set()
    for path, content in _bv.iter_files(build_id):
        if path in seen: continue
        seen.add(path)
        if isinstance(content, str) and content.startswith(_BIN_PREFIX):
            import base64
            content = base64.b64decode(content[len(_BIN_PREFIX):])
        files_list.append({"path": path, "content": content})
    for path, content in mem_files.items():
        if path in seen: continue
        seen.add(path)
        if isinstance(content, str) and content.startswith(_BIN_PREFIX):
            import base64
            content = base64.b64decode(content[len(_BIN_PREFIX):])
        files_list.append({"path": path, "content": content})

    apk_build = {
        "build_id": build_id,
        "title":    build.get("title") or "Galaxy Game",
        "files":    files_list,
    }
    import asyncio as _a
    art = await _a.get_event_loop().run_in_executor(None, binary_builder.build_apk, apk_build)
    if not art.get("is_installable"):
        raise HTTPException(503, f"APK toolchain unavailable or build failed: {art.get('signature_info','')[:200]}")
    filename = f"{(build.get('title') or 'game').lower().replace(' ', '-')[:20]}-galaxy.apk"
    return FileResponse(
        art["path"],
        media_type="application/vnd.android.package-archive",
        filename=filename,
    )
