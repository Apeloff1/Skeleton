"""Authenticated REST controls for fifty real Forge Studio authoring actions.

Reuses the existing canonical game-learning workspace, scoped owner identity,
versioned project revisions and native game compiler; no second project store.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from core import game_frontier_authoring as studio
from routes.game_learning import Request, WriteRequest, _call, _scope
from routes.gameforge_auth import get_current_user

router = APIRouter(prefix="/game-frontier-authoring", tags=["Game Studio authoring"])


class EditorStep(Request):
    action: str = Field(min_length=1, max_length=192)
    parameters: dict[str, Any] = Field(default_factory=dict, max_length=32)


class EditorMutation(WriteRequest):
    expected_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    steps: list[EditorStep] = Field(min_length=1, max_length=64)


class NativeExport(WriteRequest):
    expected_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    seed: int = Field(default=42, ge=0, le=2**63 - 1, strict=True)
    islands: int = Field(default=12, ge=3, le=64, strict=True)


class TileSelection(Request):
    layer: str = Field(min_length=1, max_length=128)
    x: int = Field(ge=0, le=255, strict=True)
    y: int = Field(ge=0, le=255, strict=True)
    width: int = Field(ge=1, le=256, strict=True)
    height: int = Field(ge=1, le=256, strict=True)


class GameplayProbe(Request):
    position_xyz_m: list[float] = Field(min_length=3, max_length=3)
    mass_kg: float = Field(default=75.0, gt=0, le=100000)
    now_ms: int = Field(default=0, ge=0, le=2**63 - 1, strict=True)
    current_signals: dict[str, float] = Field(default_factory=dict, max_length=128)
    previous_signals: dict[str, float] = Field(default_factory=dict, max_length=128)
    flags: dict[str, bool] = Field(default_factory=dict, max_length=512)


class NativeBuild(Request):
    seed: int = Field(default=42, ge=0, le=2**63 - 1, strict=True)
    islands: int = Field(default=12, ge=3, le=64, strict=True)
    include_godot: bool = False


def _write_scope(user):
    scope = _scope(user)
    if user.get("role") not in {"editor", "admin"}:
        raise HTTPException(403, detail={
            "code": "game_studio_write_denied",
            "message": "Project editor role required for source modification.",
        })
    return scope


@router.get("/handbooks")
async def search_original_world_handbooks(
    domain: str = "", treatment: str = "", director: str = "",
    worldline: str = "", offset: int = 0, limit: int = 32,
    user=Depends(get_current_user),
):
    """Browse 9,000 real source-linked game design books without huge responses."""
    _scope(user)
    from skeleton.forge.game_frontier_studio_worldline_handbooks import list_volumes
    from skeleton.forge.game_frontier_studio import StudioError
    try:
        return list_volumes(domain=domain,treatment=treatment,
                            director=director,worldline=worldline,
                            offset=offset,limit=limit)
    except StudioError as exc:
        raise HTTPException(422,detail={
            "code":"invalid_game_studio_handbook_search","message":str(exc),
        }) from exc


@router.get("/handbooks/{domain}/{treatment}/{director}/{worldline}")
async def read_original_world_handbook(
    domain: str,treatment: str,director: str,worldline: str,
    user=Depends(get_current_user),
):
    """Render one source-verified full game-production manual plus SHA receipt."""
    _scope(user)
    from skeleton.forge.game_frontier_studio_worldline_handbooks import handbook_receipt
    from skeleton.forge.game_frontier_studio import StudioError
    try:
        return handbook_receipt(domain,treatment,director,worldline)
    except StudioError as exc:
        raise HTTPException(404,detail={
            "code":"unknown_game_studio_handbook","message":str(exc),
        }) from exc


@router.get("/recipes")
async def search_production_recipes(
    query: str = "", domain: str = "", offset: int = 0, limit: int = 32,
    generation: str = "classic", system_layer: str = "",
    director: str = "", finish: str = "", worldline: str = "", phase: str = "",
    user=Depends(get_current_user),
):
    """Discover bounded 4,500, 45,000, 450,000 or 4,500,000 executable source transformations."""
    _scope(user)
    from skeleton.forge.game_frontier_studio_production_recipes import search_recipes
    from skeleton.forge.game_frontier_studio_system_expansions import search_expansions
    from skeleton.forge.game_frontier_studio_directed_production import search_directions
    from skeleton.forge.game_frontier_studio_final_production import search_final_actions
    from skeleton.forge.game_frontier_studio_worldline_production import search_worldlines
    from skeleton.forge.game_frontier_studio_phase_production import search_phases
    from skeleton.forge.game_frontier_studio import StudioError
    try:
        if generation == "phase":
            return search_phases(query=query,domain=domain,system_layer=system_layer,
                                 director=director,finish=finish,worldline=worldline,
                                 phase=phase,offset=offset,limit=limit)
        if phase:
            raise StudioError("phase filtering requires phase generation")
        if generation == "worldline":
            return search_worldlines(query=query,domain=domain,
                                     system_layer=system_layer,director=director,
                                     finish=finish,worldline=worldline,
                                     offset=offset,limit=limit)
        if worldline:
            raise StudioError("worldline filtering requires worldline generation")
        if generation == "final":
            return search_final_actions(query=query, domain=domain,
                                        system_layer=system_layer,
                                        director=director, finish=finish,
                                        offset=offset, limit=limit)
        if finish:
            raise StudioError("finish filtering requires final generation")
        if generation == "directed":
            return search_directions(query=query, domain=domain,
                                     system_layer=system_layer, director=director,
                                     offset=offset, limit=limit)
        if director:
            raise StudioError("director filtering requires directed generation")
        if generation == "expanded":
            return search_expansions(query=query, domain=domain,
                                     system_layer=system_layer,
                                     offset=offset, limit=limit)
        if generation != "classic" or system_layer:
            raise StudioError("unknown producer generation or layer")
        return search_recipes(query=query, domain=domain,
                              offset=offset, limit=limit)
    except StudioError as exc:
        raise HTTPException(422, detail={
            "code": "invalid_forge_recipe_search",
            "message": str(exc),
        }) from exc


@router.get("/actions")
async def actions(user=Depends(get_current_user)):
    _scope(user)
    return studio.catalog()


@router.get("/projects/{project_id}")
async def inspect(project_id: str, user=Depends(get_current_user)):
    return await _call(studio.document(_scope(user), project_id))


@router.post("/projects/{project_id}/tiles/copy")
async def copy_tile_region(project_id: str, body: TileSelection,
                           user=Depends(get_current_user)):
    return await _call(studio.copy_tiles(
        _scope(user), project_id, **body.model_dump()))


@router.post("/projects/{project_id}/edits/preview")
async def preview(project_id: str, body: EditorMutation,
                  user=Depends(get_current_user)):
    return await _call(studio.edit(
        _scope(user), project_id, body.model_dump(), preview=True))


@router.patch("/projects/{project_id}/edits")
async def edit(project_id: str, body: EditorMutation,
               user=Depends(get_current_user)):
    return await _call(studio.edit(
        _write_scope(user), project_id, body.model_dump(), preview=False))


@router.post("/projects/{project_id}/build")
async def build_playable_game(project_id: str, body: NativeBuild,
                              user=Depends(get_current_user)):
    return await _call(studio.compile_game(
        _scope(user), project_id, **body.model_dump()))



@router.post("/projects/{project_id}/build/export")
async def export_game_to_project(project_id: str, body: NativeExport,
                                 user=Depends(get_current_user)):
    return await _call(studio.export_native_project(
        _write_scope(user), project_id, body.model_dump()))



@router.post("/projects/{project_id}/gameplay/simulate")
async def simulate_authored_gameplay(project_id: str, body: GameplayProbe,
                                                 user=Depends(get_current_user)):
    return await _call(studio.simulate_gameplay(
        _scope(user), project_id, body.model_dump()))
