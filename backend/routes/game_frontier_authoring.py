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
    action: str = Field(min_length=1, max_length=512)
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


@router.get("/epic-handbooks")
async def search_epic_handbooks(
    domain: str = "", treatment: str = "", director: str = "",
    worldline: str = "", phase: str = "", campaign: str = "",
    chronicle: str = "", epoch: str = "", saga: str = "", epic: str = "",
    offset: int = 0, limit: int = 32, user=Depends(get_current_user),
):
    """Authenticated indexed discovery of nine billion bounded virtual manuals."""
    _scope(user)
    from skeleton.forge.game_frontier_studio_epic_handbooks import list_books
    from skeleton.forge.game_frontier_studio import StudioError
    try:
        return list_books(domain=domain, treatment=treatment, director=director,
                          worldline=worldline, phase=phase, campaign=campaign,
                          chronicle=chronicle, epoch=epoch, saga=saga, epic=epic,
                          offset=offset, limit=limit)
    except StudioError as exc:
        raise HTTPException(422, detail={"code": "invalid_epic_manual_search",
                                         "message": str(exc)}) from exc


@router.get("/epic-handbooks/rank/{domain}/{treatment}/{director}/{worldline}/{phase}/{campaign}/{chronicle}/{epoch}/{saga}")
async def rank_epic_handbooks(
    domain: str, treatment: str, director: str, worldline: str, phase: str,
    campaign: str, chronicle: str, epoch: str, saga: str,
    sort: str = "quality", user=Depends(get_current_user),
):
    """Rank ten actually rendered longform worlds on source evidence and length."""
    _scope(user)
    from skeleton.forge.game_frontier_studio_epic_handbooks import rank_variants
    from skeleton.forge.game_frontier_studio import StudioError
    try:
        return rank_variants(domain, treatment, director, worldline, phase,
                             campaign, chronicle, epoch, saga, sort=sort)
    except StudioError as exc:
        raise HTTPException(422, detail={"code": "invalid_epic_manual_ranking",
                                         "message": str(exc)}) from exc


@router.get("/epic-handbooks/{domain}/{treatment}/{director}/{worldline}/{phase}/{campaign}/{chronicle}/{epoch}/{saga}/{epic}")
async def read_epic_handbook(
    domain: str, treatment: str, director: str, worldline: str, phase: str,
    campaign: str, chronicle: str, epoch: str, saga: str, epic: str,
    user=Depends(get_current_user),
):
    """Return source-grounded Markdown and SHA receipt; no creation side effect."""
    _scope(user)
    from skeleton.forge.game_frontier_studio_epic_handbooks import receipt
    from skeleton.forge.game_frontier_studio import StudioError
    try:
        return receipt(domain, treatment, director, worldline, phase,
                       campaign, chronicle, epoch, saga, epic)
    except StudioError as exc:
        raise HTTPException(404, detail={"code": "unknown_epic_manual",
                                         "message": str(exc)}) from exc


@router.get("/saga-handbooks")
async def search_saga_handbooks(
    domain: str = "", treatment: str = "", director: str = "",
    worldline: str = "", phase: str = "", campaign: str = "",
    chronicle: str = "", epoch: str = "", saga: str = "",
    offset: int = 0, limit: int = 32, user=Depends(get_current_user),
):
    """Authenticated bounded 900M-document virtual index; no materialization."""
    _scope(user)
    from skeleton.forge.game_frontier_studio_saga_handbooks import list_books
    from skeleton.forge.game_frontier_studio import StudioError
    try:
        return list_books(domain=domain, treatment=treatment,
                          director=director, worldline=worldline,
                          phase=phase, campaign=campaign, chronicle=chronicle,
                          epoch=epoch, saga=saga, offset=offset, limit=limit)
    except StudioError as exc:
        raise HTTPException(422, detail={"code": "invalid_saga_document_search",
                                         "message": str(exc)}) from exc


@router.get("/saga-handbooks/rank/{domain}/{treatment}/{director}/{worldline}/{phase}/{campaign}/{chronicle}/{epoch}")
async def rank_saga_handbooks(
    domain: str, treatment: str, director: str, worldline: str, phase: str,
    campaign: str, chronicle: str, epoch: str, sort: str = "quality",
    user=Depends(get_current_user),
):
    """Compare ten actually rendered variants with shared source context."""
    _scope(user)
    from skeleton.forge.game_frontier_studio_saga_handbooks import rank_variants
    from skeleton.forge.game_frontier_studio import StudioError
    try:
        return rank_variants(domain, treatment, director, worldline, phase,
                             campaign, chronicle, epoch, sort=sort)
    except StudioError as exc:
        raise HTTPException(422, detail={"code": "invalid_saga_document_ranking",
                                         "message": str(exc)}) from exc


@router.get("/saga-handbooks/{domain}/{treatment}/{director}/{worldline}/{phase}/{campaign}/{chronicle}/{epoch}/{saga}")
async def read_saga_handbook(
    domain: str, treatment: str, director: str, worldline: str, phase: str,
    campaign: str, chronicle: str, epoch: str, saga: str,
    user=Depends(get_current_user),
):
    """Source-derived SHA-addressed manual, never a production certification."""
    _scope(user)
    from skeleton.forge.game_frontier_studio_saga_handbooks import receipt
    from skeleton.forge.game_frontier_studio import StudioError
    try:
        return receipt(domain, treatment, director, worldline, phase,
                       campaign, chronicle, epoch, saga)
    except StudioError as exc:
        raise HTTPException(404, detail={"code": "unknown_saga_document",
                                         "message": str(exc)}) from exc


@router.get("/epoch-handbooks")
async def search_epoch_handbooks(
    domain: str = "", treatment: str = "", director: str = "",
    worldline: str = "", phase: str = "", campaign: str = "",
    chronicle: str = "", epoch: str = "",
    offset: int = 0, limit: int = 32, user=Depends(get_current_user),
):
    """Authorized bounded arithmetic search of 90M on-demand manuals."""
    _scope(user)
    from skeleton.forge.game_frontier_studio_epoch_handbooks import list_books
    from skeleton.forge.game_frontier_studio import StudioError
    try:
        return list_books(domain=domain, treatment=treatment, director=director,
                          worldline=worldline, phase=phase, campaign=campaign,
                          chronicle=chronicle, epoch=epoch, offset=offset, limit=limit)
    except StudioError as exc:
        raise HTTPException(422, detail={"code":"invalid_epoch_handbook_search",
                                         "message":str(exc)}) from exc


@router.get("/epoch-handbooks/rank/{domain}/{treatment}/{director}/{worldline}/{phase}/{campaign}/{chronicle}")
async def rank_epoch_handbooks(
    domain: str, treatment: str, director: str, worldline: str,
    phase: str, campaign: str, chronicle: str, sort: str = "quality",
    user=Depends(get_current_user),
):
    """Compare ten actually rendered epoch books within one exact chronicle."""
    _scope(user)
    from skeleton.forge.game_frontier_studio_epoch_handbooks import rank_variants
    from skeleton.forge.game_frontier_studio import StudioError
    try:
        return rank_variants(domain, treatment, director, worldline,
                             phase, campaign, chronicle, sort=sort)
    except StudioError as exc:
        raise HTTPException(422, detail={"code":"invalid_epoch_ranking",
                                         "message":str(exc)}) from exc


@router.get("/epoch-handbooks/{domain}/{treatment}/{director}/{worldline}/{phase}/{campaign}/{chronicle}/{epoch}")
async def read_epoch_handbook(
    domain: str, treatment: str, director: str, worldline: str,
    phase: str, campaign: str, chronicle: str, epoch: str,
    user=Depends(get_current_user),
):
    """Exact SHA-addressed temporal authoring source manual."""
    _scope(user)
    from skeleton.forge.game_frontier_studio_epoch_handbooks import receipt
    from skeleton.forge.game_frontier_studio import StudioError
    try:
        return receipt(domain, treatment, director, worldline, phase,
                       campaign, chronicle, epoch)
    except StudioError as exc:
        raise HTTPException(404, detail={"code":"unknown_epoch_handbook",
                                         "message":str(exc)}) from exc


@router.get("/chronicle-handbooks")
async def search_chronicle_handbooks(
    domain: str = "", treatment: str = "", director: str = "",
    worldline: str = "", phase: str = "", campaign: str = "",
    chronicle: str = "", offset: int = 0, limit: int = 32,
    user=Depends(get_current_user),
):
    """Read the arithmetic index of 9M source-grounded technical manuals."""
    _scope(user)
    from skeleton.forge.game_frontier_studio_chronicle_handbooks import list_books
    from skeleton.forge.game_frontier_studio import StudioError
    try:
        return list_books(domain=domain,treatment=treatment,director=director,
                          worldline=worldline,phase=phase,campaign=campaign,
                          chronicle=chronicle,offset=offset,limit=limit)
    except StudioError as exc:
        raise HTTPException(422,detail={"code":"invalid_chronicle_handbook_query",
                                        "message":str(exc)}) from exc


@router.get("/chronicle-handbooks/rank/{domain}/{treatment}/{director}/{worldline}/{phase}/{campaign}")
async def rank_chronicle_handbooks(
    domain: str, treatment: str, director: str, worldline: str,
    phase: str, campaign: str, sort: str = "quality",
    user=Depends(get_current_user),
):
    """Compare only ten actually rendered variants of one common campaign."""
    _scope(user)
    from skeleton.forge.game_frontier_studio_chronicle_handbooks import rank_variants
    from skeleton.forge.game_frontier_studio import StudioError
    try:
        return rank_variants(domain,treatment,director,worldline,phase,campaign,sort=sort)
    except StudioError as exc:
        raise HTTPException(422,detail={"code":"invalid_chronicle_ranking",
                                        "message":str(exc)}) from exc


@router.get("/chronicle-handbooks/{domain}/{treatment}/{director}/{worldline}/{phase}/{campaign}/{chronicle}")
async def read_chronicle_handbook(
    domain: str, treatment: str, director: str, worldline: str,
    phase: str, campaign: str, chronicle: str, user=Depends(get_current_user),
):
    """Render exactly one SHA-addressed source-derived chronicle document."""
    _scope(user)
    from skeleton.forge.game_frontier_studio_chronicle_handbooks import receipt
    from skeleton.forge.game_frontier_studio import StudioError
    try:
        return receipt(domain,treatment,director,worldline,phase,campaign,chronicle)
    except StudioError as exc:
        raise HTTPException(404,detail={"code":"unknown_chronicle_handbook",
                                        "message":str(exc)}) from exc


@router.get("/campaign-handbooks")
async def search_campaign_handbooks(
    domain: str = "", treatment: str = "", director: str = "",
    worldline: str = "", phase: str = "", campaign: str = "",
    offset: int = 0, limit: int = 32, user=Depends(get_current_user),
):
    """Bounded source-grounded discovery over 900K generated real game manuals."""
    _scope(user)
    from skeleton.forge.game_frontier_studio_campaign_handbooks import list_books
    from skeleton.forge.game_frontier_studio import StudioError
    try:
        return list_books(domain=domain,treatment=treatment,director=director,
                          worldline=worldline,phase=phase,campaign=campaign,
                          offset=offset,limit=limit)
    except StudioError as exc:
        raise HTTPException(422,detail={
            "code":"invalid_campaign_handbook_search","message":str(exc)}) from exc


@router.get("/campaign-handbooks/rank/{domain}/{treatment}/{director}/{worldline}/{phase}")
async def rank_campaign_handbooks(
    domain: str,treatment: str,director: str,worldline: str,phase: str,
    sort: str = "quality", user=Depends(get_current_user),
):
    """Rank ten actual rendered alternatives by objective quality or word length.

    This comparison is scoped to one chosen game context; not a global top 900K.
    """
    _scope(user)
    from skeleton.forge.game_frontier_studio_campaign_handbooks import rank_variants
    from skeleton.forge.game_frontier_studio import StudioError
    try:
        return rank_variants(domain,treatment,director,worldline,phase,sort=sort)
    except StudioError as exc:
        raise HTTPException(422,detail={
            "code":"invalid_campaign_handbook_ranking","message":str(exc)}) from exc


@router.get("/campaign-handbooks/{domain}/{treatment}/{director}/{worldline}/{phase}/{campaign}")
async def read_campaign_handbook(
    domain: str,treatment: str,director: str,worldline: str,phase: str,
    campaign: str,user=Depends(get_current_user),
):
    """Reconstruct one source-owned manual with deterministic score and SHA."""
    _scope(user)
    from skeleton.forge.game_frontier_studio_campaign_handbooks import receipt
    from skeleton.forge.game_frontier_studio import StudioError
    try:
        return receipt(domain,treatment,director,worldline,phase,campaign)
    except StudioError as exc:
        raise HTTPException(404,detail={
            "code":"unknown_campaign_handbook","message":str(exc)}) from exc


@router.get("/phase-handbooks")
async def list_phase_game_handbooks(
    domain: str = "", treatment: str = "", director: str = "",
    worldline: str = "", phase: str = "", offset: int = 0,
    limit: int = 32, user=Depends(get_current_user),
):
    """Discover 90,000 source-owned technical books with bounded pages."""
    _scope(user)
    from skeleton.forge.game_frontier_studio_phase_handbooks import list_books
    from skeleton.forge.game_frontier_studio import StudioError
    try:
        return list_books(domain=domain, treatment=treatment, director=director,
                          worldline=worldline, phase=phase,
                          offset=offset, limit=limit)
    except StudioError as exc:
        raise HTTPException(422,detail={
            "code":"invalid_phase_handbook_search","message":str(exc)}) from exc


@router.get("/phase-handbooks/{domain}/{treatment}/{director}/{worldline}/{phase}")
async def read_phase_game_handbook(
    domain: str,treatment: str,director: str,worldline: str,phase: str,
    user=Depends(get_current_user),
):
    """One complete source-verified world-building manual and SHA receipt."""
    _scope(user)
    from skeleton.forge.game_frontier_studio_phase_handbooks import receipt
    from skeleton.forge.game_frontier_studio import StudioError
    try:
        return receipt(domain,treatment,director,worldline,phase)
    except StudioError as exc:
        raise HTTPException(404,detail={
            "code":"unknown_phase_handbook","message":str(exc)}) from exc


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
    director: str = "", finish: str = "", worldline: str = "", phase: str = "", campaign: str = "", chronicle: str = "", epoch: str = "", saga: str = "", epic: str = "",
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
    from skeleton.forge.game_frontier_studio_campaign_production import search_campaigns
    from skeleton.forge.game_frontier_studio_chronicle_production import search_chronicles
    from skeleton.forge.game_frontier_studio_epoch_production import search_epochs
    from skeleton.forge.game_frontier_studio_saga_production import search_sagas
    from skeleton.forge.game_frontier_studio_epic_variations import search_epics
    from skeleton.forge.game_frontier_studio import StudioError
    try:
        if generation == "epic":
            if query:
                raise StudioError("Epic source search requires exact indexed filters")
            return search_epics(domain=domain,system_layer=system_layer,
                                director=director,finish=finish,worldline=worldline,
                                phase=phase,campaign=campaign,chronicle=chronicle,
                                epoch=epoch,saga=saga,epic=epic,
                                offset=offset,limit=limit)
        if epic:
            raise StudioError("Epic filtering requires Epic generation")
        if generation == "saga":
            if query:
                raise StudioError("saga search only accepts indexed exact filters")
            return search_sagas(domain=domain,system_layer=system_layer,
                                director=director,finish=finish,worldline=worldline,
                                phase=phase,campaign=campaign,chronicle=chronicle,
                                epoch=epoch,saga=saga,offset=offset,limit=limit)
        if saga:
            raise StudioError("saga filtering requires saga generation")
        if generation == "epoch":
            if query:
                raise StudioError("epoch discovery uses exact filters, not scans")
            return search_epochs(domain=domain,system_layer=system_layer,
                                 director=director,finish=finish,worldline=worldline,
                                 phase=phase,campaign=campaign,chronicle=chronicle,
                                 epoch=epoch,offset=offset,limit=limit)
        if epoch:
            raise StudioError("epoch filtering requires epoch generation")
        if generation == "chronicle":
            if query:
                raise StudioError("chronicle discovery requires exact indexed filters")
            return search_chronicles(domain=domain,system_layer=system_layer,
                                     director=director,finish=finish,worldline=worldline,
                                     phase=phase,campaign=campaign,chronicle=chronicle,
                                     offset=offset,limit=limit)
        if chronicle:
            raise StudioError("chronicle filtering requires chronicle generation")
        if generation == "campaign":
            if query:
                raise StudioError("campaign discovery uses exact filters, not unbounded text scanning")
            return search_campaigns(domain=domain,system_layer=system_layer,
                                    director=director,finish=finish,worldline=worldline,
                                    phase=phase,campaign=campaign,
                                    offset=offset,limit=limit)
        if campaign:
            raise StudioError("campaign filtering requires campaign generation")
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


class RouteInspection(Request):
    scenarios: list[dict[str, Any]] = Field(min_length=1, max_length=100)


@router.post("/projects/{project_id}/routes/audit")
async def audit_authored_walkable_routes(
    project_id: str, body: RouteInspection,
    user=Depends(get_current_user),
):
    """Authenticated read-only source replay, not a native-game certification."""
    return await _call(studio.audit_walkable_routes(
        _scope(user), project_id, body.model_dump()))
