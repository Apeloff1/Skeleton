"""routes/systems_forge.py — Systems Forge API (non-3D game systems, SOTA)."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from core import systems_forge as sf

router = APIRouter(prefix="/api/galaxy-studio/systems", tags=["systems-forge"])


@router.get("")
def systems():
    return sf.list_systems()


@router.get("/big-wins")
def big_wins():
    return sf.list_big_wins()


class BigWinReq(BaseModel):
    build_id: str = Field(..., min_length=1)
    seed: int = 0
    mount: bool = True
    enrich: bool = False


@router.post("/big-wins/{bw}/apply")
def apply_big_win(bw: str, req: BigWinReq):
    return sf.apply_big_win(bw, req.build_id, seed=req.seed, mount=req.mount, enrich=req.enrich)


@router.get("/build/{build_id}")
def build_systems(build_id: str):
    return sf.list_build_systems(build_id)


@router.get("/build/{build_id}/export.md")
def export_build_md(build_id: str):
    md = sf.build_systems_markdown(build_id) or f"# No systems mounted on build {build_id}"
    return PlainTextResponse(md, media_type="text/markdown",
                             headers={"Content-Disposition": f'attachment; filename="{build_id}_systems.md"'})


@router.get("/{system}")
def detail(system: str):
    return sf.system_detail(system)


@router.get("/{system}/blueprint")
def blueprint(system: str, seed: int = 0):
    return sf.blueprint(system, seed=seed)


@router.get("/{system}/export.md")
def export_system_md(system: str, build_id: str = ""):
    md = sf.system_markdown(build_id, system)
    return PlainTextResponse(md, media_type="text/markdown",
                             headers={"Content-Disposition": f'attachment; filename="{system}_brief.md"'})


class SystemRunReq(BaseModel):
    build_id: str = Field(..., min_length=1)
    knobs: dict | None = None
    seed: int = 0
    mount: bool = True
    enrich: bool = False
    contexts: dict | None = None


@router.post("/{system}/generate")
def generate(system: str, req: SystemRunReq):
    res = sf.run_pipeline(system, req.build_id, knobs=req.knobs, seed=req.seed,
                          mount=req.mount, enrich=req.enrich, contexts=req.contexts)
    if req.build_id and not res.get("error"):
        try:
            from core import build_ledger as bl
            bl.log(req.build_id, "system_generated",
                   {"system": system, "mounted": req.mount,
                    "llm_enriched": res.get("llm_enriched", False),
                    "knobs": res.get("knobs", {})})
        except Exception:
            pass
    return res


class ContextReq(BaseModel):
    build_id: str = Field(..., min_length=1)
    vision: str = ""
    implementation: str = ""
    quality: str = ""


@router.get("/{system}/context")
def get_context(system: str, build_id: str = ""):
    return sf.get_system_context(build_id, system)


@router.post("/{system}/context")
def save_context(system: str, req: ContextReq):
    return sf.save_system_context(req.build_id, system,
                                  {"vision": req.vision, "implementation": req.implementation,
                                   "quality": req.quality})
