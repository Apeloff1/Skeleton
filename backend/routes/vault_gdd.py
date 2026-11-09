"""
Vault GDD + Mount API.

Compiles a vault-grounded Game Design Document straight from the Item-Foundry
gamefiles for a build and MOUNTS the build (persists GDD + coverage + item
stats). Lives under the Galaxy-Studio namespace.
"""
from __future__ import annotations

import io
import json
import zipfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from core import asset_forge
from core import snowball_forge
from core import vault_gdd

router = APIRouter(prefix="/api/galaxy-studio/vault-gdd", tags=["vault-gdd"])


class MountReq(BaseModel):
    build_id: str = Field(..., min_length=1)
    seed: int = 0
    forge_if_empty: bool = True
    use_llm: bool = False
    persist: bool = True


@router.post("/mount")
def mount(req: MountReq) -> dict:
    """Generate the vault-grounded GDD from the gamefiles and mount the build."""
    return vault_gdd.mount(
        build_id=req.build_id, seed=req.seed, forge_if_empty=req.forge_if_empty,
        use_llm=req.use_llm, persist=req.persist,
    )


@router.get("/stats/{build_id}")
def stats(build_id: str) -> dict:
    data = vault_gdd.read_gamefiles(build_id)
    return {"build_id": build_id, "stats": vault_gdd.foundry_stats(data["items"])}


@router.get("/{build_id}")
def get_mount(build_id: str) -> dict:
    m = vault_gdd.get_mount(build_id)
    if not m:
        raise HTTPException(404, "build not mounted yet")
    return m


@router.get("/{build_id}/gdd.md")
def export_gdd(build_id: str) -> PlainTextResponse:
    m = vault_gdd.get_mount(build_id)
    if not m:
        data = vault_gdd.read_gamefiles(build_id)
        gdd = vault_gdd.compile_gdd(data["build"], data["items"], data["manifest"])
    else:
        gdd = m.get("gdd", "")
    fname = (m or {}).get("title", "build") if m else "build"
    fname = str(fname).replace(" ", "_")[:40] + "_GDD.md"
    return PlainTextResponse(
        gdd, media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ── Escalating snowball build: parity-locked, quality-gated, 10× assets ───
class EscalateReq(BaseModel):
    build_id: str = Field(..., min_length=1)
    genre: str = "rpg"
    seed: int = 0
    platoon_size: int = 4
    base_grade: int = 2
    era: str | None = None
    config: dict | None = None
    persist: bool = True


@router.post("/escalate")
def escalate(req: EscalateReq) -> dict:
    """Run the escalating snowball: each stage parses all prior GDD + gamefiles,
    builds on top, clears escalating quality gates, forges era-appropriate
    assets, escalates the GDD and keeps GDD↔gamefile parity locked on every
    step. Era-sensitive + every choice logged to the per-game ledger."""
    return snowball_forge.escalate(
        build_id=req.build_id, genre=req.genre, seed=req.seed,
        platoon_size=req.platoon_size, base_grade=req.base_grade,
        era=req.era, config=req.config, persist=req.persist,
    )


@router.get("/choices/{build_id}")
def choices(build_id: str) -> dict:
    """The per-game choice ledger + the parsed awareness agents read each step."""
    from core import game_choices
    return {"build_id": build_id,
            "awareness": game_choices.parse_context(build_id),
            "ledger": game_choices.get_choices(build_id)}


@router.get("/era-ladder/{build_id}")
def era_ladder(build_id: str, era_a: str = "8bit", era_b: str = "modern",
               genre: str = "rpg", seed: int = 0) -> dict:
    """Re-forge the same game across two eras and diff asset counts / storage /
    capacity — visualises the asset-growth story across eras."""
    return snowball_forge.era_ladder(build_id, era_a, era_b, genre, seed)


@router.post("/phase-gates")
def phase_gates(req: EscalateReq) -> dict:
    """Advanced mode — map the snowball onto the 100-phase gate ladder. The
    build is escalated (era-sensitive) and every phase band is gated by a
    checkpoint derived from the result."""
    from core import phase_gates as pg
    from core import construct_forge as cf
    m = snowball_forge.escalate(
        build_id=req.build_id, genre=req.genre, seed=req.seed,
        platoon_size=req.platoon_size, base_grade=req.base_grade,
        era=req.era, config=req.config, persist=req.persist)
    # The 100 phases run AFTER assets and FACTOR THEM IN — pull the build's
    # combined forged-asset inventory (constructs + materials + universal).
    combined = cf.build_assets(req.build_id)
    fams = sorted({(a.get("family") or a.get("kind")) for a in combined if (a.get("family") or a.get("kind"))})
    out = pg.build(m, assets={"forged": len(combined), "families": fams})
    out["build_id"] = req.build_id
    out["era"] = m["era"]
    return out


@router.post("/questionnaire")
def questionnaire(req: EscalateReq) -> dict:
    """Conformance questionnaire — proves every snowball step corresponds to
    the locked choices (era/genre/parity/escalation/assets/storage)."""
    from core import snowball_questionnaire as sq
    m = snowball_forge.escalate(
        build_id=req.build_id, genre=req.genre, seed=req.seed,
        platoon_size=req.platoon_size, base_grade=req.base_grade,
        era=req.era, config=req.config, persist=req.persist)
    return sq.build(m)


@router.get("/parity/{build_id}")
def parity(build_id: str) -> dict:
    m = vault_gdd.get_mount(build_id)
    esc = (m or {}).get("escalation") if m else None
    if not esc:
        raise HTTPException(404, "build not escalated yet")
    return {
        "build_id": build_id,
        "parity_locked": esc.get("parity_locked"),
        "parity_pct": esc.get("parity_pct"),
        "grade_escalating": esc.get("grade_escalating"),
        "ladder": esc.get("ladder"),
    }


@router.get("/{build_id}/gamefiles.zip")
def export_gamefiles(build_id: str) -> StreamingResponse:
    """Bundle the behaviour code + GDD + asset manifest into a downloadable zip."""
    data = vault_gdd.read_gamefiles(build_id)
    items = data["items"]
    if not items:
        raise HTTPException(404, "no gamefiles to bundle")
    m = vault_gdd.get_mount(build_id)
    gdd = (m or {}).get("gdd") or vault_gdd.compile_gdd(
        data["build"], items, data["manifest"])
    assets = asset_forge.list_assets(build_id)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("GDD.md", gdd)
        zf.writestr("manifest.json", json.dumps(
            {"build_id": build_id, "items": len(items), "assets": len(assets)}, indent=2))
        for it in items:
            zf.writestr(f"gamefiles/{it['stage']}/{it['item_id']}.js", it.get("code", ""))
            zf.writestr(f"gamefiles/{it['stage']}/{it['item_id']}.json",
                        json.dumps({k: v for k, v in it.items()
                                    if k not in ("_id",)}, default=str, indent=2))
        if assets:
            zf.writestr("assets/asset_manifest.json", json.dumps(assets, default=str, indent=2))
    buf.seek(0)
    fname = str((m or {}).get("title", "build")).replace(" ", "_")[:40] + "_gamefiles.zip"
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
