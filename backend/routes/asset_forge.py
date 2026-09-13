"""Asset Forge API — 10× asset packs per gamefile, folded into the Vault."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from core import asset_forge
from core import vault_gdd

router = APIRouter(prefix="/api/galaxy-studio/assets", tags=["asset-forge"])


class ForgeAssetsReq(BaseModel):
    build_id: str = Field(..., min_length=1, max_length=200)
    seed: int = Field(0, ge=-2147483648, le=2147483647)
    era: str | None = Field(None, max_length=100)
    persist: bool = True


@router.post("/forge")
def forge(req: ForgeAssetsReq) -> dict:
    """Forge an era-appropriate asset pack for every gamefile in the Vault."""
    items = vault_gdd.read_gamefiles(req.build_id)["items"]
    summary = asset_forge.forge_build_assets(req.build_id, items, req.seed,
                                             req.persist, era=req.era)
    summary.pop("assets", None)  # keep the response light
    return summary


@router.get("/{build_id}")
def list_build(build_id: str, item_id: str | None = None) -> dict:
    return {"build_id": build_id, "assets": asset_forge.list_assets(build_id, item_id)}
