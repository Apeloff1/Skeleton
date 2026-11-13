"""
Galaxy Studio — Vault Admin sub-router.

Extracted from routes/galaxy_studio.py (Jun 2026, decomposition continuation).
On-demand disk reclaim + live builds-vault usage stats.

Uses the existing Galaxy physical admission slot to prevent maintenance
from racing a build writer or artifact reader. Disk scans and explicit
pruning execute off the API event loop; no automatic pruning is introduced.

Mounted from routes/galaxy_studio.py via ``router.include_router(...)`` WITHOUT
an additional prefix so the public paths stay identical
(``/api/galaxy-studio/admin/vault/stats`` and ``.../admin/vault/prune``).
"""

from __future__ import annotations
import os

from fastapi import APIRouter, HTTPException
from core.http_errors import internal_http_error

# Sub-router — NO prefix so the parent's "/api/galaxy-studio" prefix applies.
router = APIRouter(tags=["galaxy-studio"])


@router.get("/admin/vault/stats")
async def admin_vault_stats():
    """Live builds-vault usage: build count, total files, compressed bytes."""
    try:
        from core import build_vault as _bv
        from routes.galaxy_studio import _run_vault_admin_operation

        st = await _run_vault_admin_operation(_bv.global_stats)
        disk_bytes = int(st.get("disk_bytes", 0))
        raw_bytes = int(st.get("raw_bytes", 0))
        saved_bytes = int(st.get("saved_bytes", 0))
        return {
            "ok": True,
            "builds": st.get("builds", 0),
            "total_files": st.get("total_files", 0),
            "disk_bytes": disk_bytes,
            "disk_mb": round(disk_bytes / (1024 * 1024), 1),
            "raw_mb": round(raw_bytes / (1024 * 1024), 1),
            "saved_mb": round(saved_bytes / (1024 * 1024), 1),
            "compression_ratio": st.get("compression_ratio", 1.0),
            "zstd_level": st.get("zstd_level", 10),
            "newest_build_id": st.get("newest_build_id"),
            "keep_target": int(os.environ.get("GALAXY_VAULT_KEEP", 12)),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise internal_http_error("vault stats unavailable", e) from None


@router.post("/admin/vault/prune")
async def admin_vault_prune(keep: int = 12):
    """Reclaim disk by keeping only the `keep` most-recent builds.
    Preserved (FAILED) builds are never deleted."""
    try:
        from core import build_vault as _bv
        from routes.galaxy_studio import _run_vault_admin_operation

        def reclaim():
            before = _bv.global_stats()
            result = _bv.prune_old_builds(keep=max(1, int(keep)))
            after = _bv.global_stats()
            reclaimed = int(before.get("disk_bytes", 0)) - int(after.get("disk_bytes", 0))
            return {
                "ok": True,
                "prune": result,
                "builds_before": before.get("builds", 0),
                "builds_after": after.get("builds", 0),
                "reclaimed_bytes": reclaimed,
                "reclaimed_mb": round(reclaimed / (1024 * 1024), 1),
            }

        return await _run_vault_admin_operation(reclaim)
    except HTTPException:
        raise
    except Exception as e:
        raise internal_http_error("vault prune failed", e) from None



__all__ = ["router", "admin_vault_stats", "admin_vault_prune"]
