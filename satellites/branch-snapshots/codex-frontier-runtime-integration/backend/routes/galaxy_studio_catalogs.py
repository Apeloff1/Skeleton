"""
Galaxy Studio — Catalog delegators sub-router.

Extracted from routes/galaxy_studio.py (Jun 2026, decomposition continuation).
These three read-only endpoints simply delegate to their owning subsystem
modules (capabilities / gamedev-pipeline / datasets) and hold NO state of their
own — making them a clean, side-effect-free extraction.

Mounted from routes/galaxy_studio.py via ``router.include_router(...)`` WITHOUT
an additional prefix so the public paths stay identical:
  - /api/galaxy-studio/capabilities/catalog
  - /api/galaxy-studio/pipeline/catalog
  - /api/galaxy-studio/datasets/catalog
"""

from __future__ import annotations
from fastapi import APIRouter, HTTPException

# Sub-router — NO prefix so the parent's "/api/galaxy-studio" prefix applies.
router = APIRouter(tags=["galaxy-studio"])


@router.get("/capabilities/catalog")
async def get_capabilities_catalog():
    """Catalog of the 40 generated capability systems (engine + per-capability
    mutation permutation engine). Used by the frontend Capabilities screen."""
    try:
        from routes import galaxy_studio_capabilities as _caps
        return _caps.get_capability_catalog()
    except Exception as e:
        raise HTTPException(500, f"capability catalog unavailable: {e}")


@router.get("/pipeline/catalog")
async def get_pipeline_catalog_route():
    """Catalog of the 8-stage AAA Game Development Pipeline."""
    try:
        from routes import galaxy_studio_gamedev_pipeline as _gdp
        return _gdp.get_pipeline_catalog()
    except Exception as e:
        raise HTTPException(500, f"pipeline catalog unavailable: {e}")


@router.get("/datasets/catalog")
async def get_datasets_catalog_route():
    """Catalog of the local agent self-sufficiency datasets."""
    try:
        from routes import galaxy_studio_datasets as _ds
        return _ds.get_dataset_catalog()
    except Exception as e:
        raise HTTPException(500, f"dataset catalog unavailable: {e}")


__all__ = [
    "router",
    "get_capabilities_catalog",
    "get_pipeline_catalog_route",
    "get_datasets_catalog_route",
]
