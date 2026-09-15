"""
routes/tool_forge.py — Tool Forge API.

Config-driven game tools modelled on the Universal Forge. Each tool is a scoped
forge with its own catalog, applicable style axes and a shared 7-step pipeline
that mounts a forged batch to a build's Vault.
"""
from __future__ import annotations

import json as _json

from fastapi import APIRouter
from pydantic import BaseModel, Field

from core import tool_forge as tf

router = APIRouter(prefix="/api/galaxy-studio/tools", tags=["tool-forge"])


def _parse_axes(axes: str | None) -> dict:
    if not axes:
        return {}
    try:
        d = _json.loads(axes)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


@router.get("")
def tools():
    """List every game tool + the shared pipeline definition."""
    return tf.list_tools()


@router.get("/{tool}/catalog")
def catalog(tool: str):
    """Scoped categories (with thumb palettes) + applicable axes for a tool."""
    return tf.tool_catalog(tool)


@router.get("/{tool}/asset")
def asset(tool: str, id: str, era: str | None = None, seed: int | None = None,
          axes: str | None = None, full: bool = False):
    """Targeted single-asset fetch — light by default, full=1 for the 3D mesh."""
    return tf.tool_asset(tool, id, era=era, seed=seed,
                         axes=_parse_axes(axes), full=full)


class PipelineReq(BaseModel):
    build_id: str = Field(..., min_length=1)
    era: str | None = None
    seed: int = 0
    count: int = 12
    mount: bool = True
    axes: dict | None = None
    config: dict | None = None
    categories: list | None = None
    mode: str = "consecutive"


@router.post("/{tool}/pipeline")
def pipeline(tool: str, req: PipelineReq):
    """Run the shared 7-step pipeline for a tool and mount the batch to a build."""
    return tf.run_pipeline(tool, req.build_id, era=req.era, seed=req.seed,
                           count=req.count, mount=req.mount,
                           axes=req.axes, config=req.config,
                           categories=req.categories, mode=req.mode)
