"""routes/storage.py — the UNBULK / "Saved Data" report API.

GET  /api/storage/savings  → unified compression savings (raw vs stored, % saved)
GET  /api/storage/modules  → source-module inventory ("src partials for all modules")
POST /api/storage/sweep    → transparent batch compaction (gzip manifests + freeze cold)
POST /api/storage/cache/purge → drop the decompress-on-demand cache
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from core import unbulk

router = APIRouter(prefix="/api/storage", tags=["storage-unbulk"])


@router.get("/savings")
def savings():
    return unbulk.savings()


@router.get("/modules")
def modules(top: int = 25):
    from core import lazy_registry as L
    inv = unbulk.module_inventory(top=top)
    inv["lazy"] = L.full_status()          # companion: loaded vs deferred
    return inv


@router.get("/lazy")
def lazy_status():
    """Loaded-vs-deferred picture for core + non-core(seeds) + flagged modules."""
    from core import lazy_registry as L
    return L.full_status()


@router.post("/lazy/wrap")
def lazy_wrap():
    """Wrap all core + non-core + flagged modules as lazy proxies; report status."""
    from core import lazy_registry as L
    core = L.wrap_all()
    noncore = L.wrap_noncore()
    flagged = L.wrap_flagged()
    return {"wrapped_core": len(core), "wrapped_noncore": len(noncore),
            "wrapped_flagged": len(flagged), "status": L.full_status()}


class SweepReq(BaseModel):
    manifest_min_bytes: int = 50_000
    freeze_cold: bool = True
    max_manifests: int = 500


@router.post("/sweep")
def sweep(req: SweepReq):
    return unbulk.sweep(manifest_min_bytes=req.manifest_min_bytes,
                        freeze_cold=req.freeze_cold,
                        max_manifests=req.max_manifests)


@router.post("/cache/purge")
def purge_cache():
    return {"purged": unbulk.purge_cache()}
