"""
Item Foundry API — Agent Item Creation Workflow.

Every agent in the active platoon for an item-bearing stage forges a COMPLETE
item (definition + skin + behaviour code + world placement), graded above the
base gamefiles, validated/reflected, then folded into the gamefiles and Vault.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from core import item_foundry as foundry

router = APIRouter(prefix="/api/galaxy-studio/items", tags=["item-foundry"])


class ForgeBuildReq(BaseModel):
    build_id: str = Field(..., min_length=1)
    genre: str | None = None
    base_grade: int = 2
    seed: int = 0
    platoon_size: int = 5
    use_llm: bool = False
    persist: bool = True


def _vault_ctx(req: ForgeBuildReq) -> dict:
    ctx = {"genre": req.genre or "rpg", "base_grade": req.base_grade}
    try:
        from core.databases import get_sync_db
        doc = get_sync_db()["galaxy_builds"].find_one({"build_id": req.build_id}, {"_id": 0})
        if doc:
            ctx["genre"] = doc.get("genre") or ctx["genre"]
            ctx["title"] = doc.get("title") or doc.get("name") or ""
    except Exception:
        pass
    return ctx


@router.post("/forge-build")
def forge_build(req: ForgeBuildReq) -> dict:
    return foundry.forge_build(
        build_id=req.build_id, vault_ctx=_vault_ctx(req), seed=req.seed,
        platoon_size=req.platoon_size, persist=req.persist, use_llm=req.use_llm,
    )


@router.get("/build/{build_id}")
def list_build(build_id: str, stage: str | None = None) -> dict:
    return {"build_id": build_id, "items": foundry.list_items(build_id, stage)}
