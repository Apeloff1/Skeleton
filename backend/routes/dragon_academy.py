"""Authenticated Dragon Academy product adapter.

All identities derive from verified GameForge principals, NEVER request JSON.
The canonical crawler owns promotion and human-review receipts; there is no
public endpoint that can mint XP or fabricate ApprovedLesson/PromotionDecision.
Demo HTML is returned as data only; the client renders in an isolated WebView.
Requires an operator-configured durable SQLite path; no in-memory fallback.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from hashlib import sha256
import os
from pathlib import Path
import sqlite3
import time
from typing import Annotated, Iterator

from fastapi import APIRouter, Depends, HTTPException, Path as URLPath, Query, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StringConstraints

from routes.gameforge_auth import get_current_user
from skeleton.ai.webcrawler.dragon_practice_lab import DragonPracticeLab
from skeleton.ai.webcrawler.dragon_practice_cycles import DragonPracticeCycles
from skeleton.ai.webcrawler.dragon_session_projection import DragonSessionProjection
from skeleton.ai.webcrawler.dragon_native_practice import DragonNativePracticeLab
from skeleton.ai.webcrawler.dragon_build_evidence import DragonBuildEvidence
from skeleton.ai.webcrawler.dragon_native_curriculum import (
    DragonNativeCurriculum,curriculum_report,
)
from skeleton.ai.webcrawler.dragon_native_targets import target_catalog, practice_matrix, STYLES

router = APIRouter(prefix="/api/dragon-academy", tags=["Dragon Academy"])

class CurriculumGenerateRequest(BaseModel):
    approved: bool = Field(default=False)

class NativeGenerateRequest(BaseModel):
    target_id: str = Field(default="game_boy", min_length=2, max_length=64)
    style: str = Field(default="arcade_score_attack", min_length=2, max_length=64)

class RunPracticeRequest(BaseModel):
    max_demos: int = Field(default=2, ge=1, le=4)

class SubscribeRequest(BaseModel):
    hours: int = Field(default=24, ge=1, le=168)
    interval_seconds: int = Field(default=3600, ge=300, le=86400)
    max_ticks: int = Field(default=24, ge=1, le=168)
    demos_per_tick: int = Field(default=2, ge=1, le=4)
    approved: bool = Field(default=False)
    adaptive: bool = Field(default=False)
    native_target: str = Field(default='game_boy', min_length=2, max_length=64)
    native_style: str = Field(default='arcade_score_attack', min_length=2, max_length=64)

def _principal(user: dict | None = Depends(get_current_user)) -> str:
    """No anonymous/development bypass, even when the general app has dev auth off."""
    if not isinstance(user, dict) or user.get("disabled") or user.get("dev_mode"):
        raise HTTPException(status_code=401, detail="Sign in to use Dragon Academy")
    email = user.get("email")
    if not isinstance(email,str) or not 3 <= len(email.strip()) <= 200:
        raise HTTPException(status_code=403, detail="Account identity unavailable")
    if user.get("role") not in ("viewer","editor","admin"):
        raise HTTPException(status_code=403, detail="Account permission unavailable")
    tenant=user.get("tenant_id") or email
    if not isinstance(tenant,str) or not 1 <= len(tenant.strip()) <= 128:
        raise HTTPException(status_code=403, detail="Tenant identity unavailable")
    # Exactly one opaque owner ID per tenant/principal pair, independent of
    # user-supplied parameters; avoid exposing the email in SQLite keys.
    return sha256((tenant.strip()+"\x00"+email.strip().lower()).encode()).hexdigest()

def _database_path() -> Path:
    raw=os.environ.get("SKL_DRAGON_PRACTICE_DB_PATH","").strip()
    if not raw:
        raise HTTPException(status_code=503, detail="Dragon Academy storage not configured")
    path=Path(raw).expanduser()
    if not path.is_absolute() or path.name in ("",".","..") or not path.parent.is_dir():
        raise HTTPException(status_code=503, detail="Dragon Academy durable storage unavailable")
    return path

@contextmanager
def _lab() -> Iterator[tuple[DragonPracticeLab,DragonPracticeCycles]]:
    path=_database_path()
    try:
        db=sqlite3.connect(str(path),timeout=5)
        try:
            db.execute("PRAGMA busy_timeout=5000")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA foreign_keys=ON")
            lab=DragonPracticeLab(db)
            yield lab,DragonPracticeCycles(db,lab)
        finally:
            db.close()
    except (sqlite3.DatabaseError,sqlite3.OperationalError) as exc:
        raise HTTPException(status_code=503,detail="Dragon Academy storage unavailable") from None

def _snapshot(lab: DragonPracticeLab, cycles: DragonPracticeCycles,
              owner: str) -> dict:
    return {
        "ok": True,
        "progress": asdict(lab.progress(owner,authorized=True)),
        "attempts": [asdict(a) for a in lab.attempts(owner,authorized=True,limit=50)],
        "native_attempts": [asdict(a) for a in DragonNativePracticeLab(lab.db,lab).list(owner,authorized=True)],
        "subscription": asdict(cycles.status(owner,authorized=True)),
    }

@router.get("/status")
def academy_status(owner: str = Depends(_principal)) -> dict:
    with _lab() as (lab,cycles):
        return _snapshot(lab,cycles,owner)

@router.get("/crawler/feed")
def crawler_feed(
    after_sequence: int = Query(default=0,ge=0),
    limit: int = Query(default=100,ge=1,le=250),
    owner: str = Depends(_principal),
) -> dict:
    with _lab() as (lab,_):
        try:
            feed=DragonSessionProjection(lab.db).read(
                owner,authorized=True,after_sequence=after_sequence,limit=limit)
        except ValueError:
            raise HTTPException(status_code=409,detail="Crawler journal replay unavailable") from None
        return {"ok": True,**asdict(feed)}

@router.get("/native/targets")
def native_targets(owner: str = Depends(_principal)) -> dict:
    # Catalog metadata does not imply working native compilation.
    return {"ok":True,"targets":target_catalog(),"styles":STYLES,
            "supported_matrix":practice_matrix()}


class NativeProductionPixelArtPreview(BaseModel):
    """Strictly original 8x8 source sprite preview, no external images or ROMs."""
    model_config = ConfigDict(extra="forbid")
    hero: str = Field(default="hatchling", max_length=32)
    quest_theme: str = Field(default="ancient_ruins", max_length=32)
    palette: str = Field(default="dmg_green", max_length=30)
    seed: StrictInt = Field(default=1, ge=0, le=0xffffffff)
    target: str = Field(default="game_boy", max_length=32)


@router.post("/native/production/art-preview")
def native_production_art_preview(
    body: NativeProductionPixelArtPreview,
    owner: str = Depends(_principal),
) -> dict:
    """Pixel-perfect intended original 2bpp source tiles, NOT device rendering."""
    from skeleton.ai.webcrawler.dragon_native_artforge import (
        TARGETS, make_art,
    )
    if body.target not in TARGETS:
        raise HTTPException(status_code=422,
                            detail="Original sprite tile preview adapter unavailable")
    # Cartridge video asset palette classes are intentionally bounded: other
    # UI themes map into a compatible handheld 2bpp tone class.
    actual_palette = (body.palette if body.palette in
                      ("dmg_green", "handheld", "vga_dusk") else "handheld")
    try:
        art, tiles = make_art(
            hero=body.hero, theme=body.quest_theme,
            palette=actual_palette, seed=body.seed, target=body.target,
        )
    except ValueError:
        raise HTTPException(status_code=422,
                            detail="Unsupported original sprite design") from None
    return {
        "ok": True,
        "schema": art.schema,
        "target": body.target,
        "requested_palette": body.palette,
        "applied_palette": actual_palette,
        "hero": body.hero,
        "quest_theme": body.quest_theme,
        "frames": {
            "hero": tiles["dragon"],
            "hero_blink": tiles["dragon_blink"],
            "collectible": tiles["star"],
            "enemy": tiles["enemy"],
        },
        "gb_tiles_sha256": art.gb_source_digest,
        "nes_tiles_sha256": art.nes_source_digest,
        "claim_boundary": (
            "actual original 2bpp sprite source values only; "
            "screen colors and hardware rendering not certified"
        ),
    }


NativeOriginalGridRow = Annotated[
    str, StringConstraints(min_length=12, max_length=12, pattern=r"^[#.@$o]{12}$")
]
NativeOriginalGrid = Annotated[
    list[NativeOriginalGridRow], Field(min_length=10, max_length=10)
]


class NativeProductionDesignBody(BaseModel):
    """Optional original game controls; never interpreted as executable source."""
    model_config = ConfigDict(extra="forbid")
    palette: str = Field(default="vga_dusk", max_length=30)
    hero: str = Field(default="hatchling", max_length=32)
    quest_theme: str = Field(default="ancient_ruins", max_length=32)
    difficulty: StrictInt = Field(default=4, ge=1, le=10)
    stages: StrictInt = Field(default=4, ge=1, le=8)
    candidates: StrictInt = Field(default=8, ge=1, le=24)
    project_notes: str = Field(default="Original native homebrew; platform-scaled design", max_length=200)
    procedural_levels: StrictBool = Field(default=False)
    campaign_pathing: str = Field(default="branching", pattern=r"^(linear|branching)$")
    challenge_profile: str = Field(default="balanced", pattern=r"^(gentle|balanced|challenging|spicy)$")


class NativeProductionSourceRequest(BaseModel):
    """Strict browser-only original source export, never privileged ROM compilation."""
    model_config = ConfigDict(extra="forbid")
    title: str = Field(..., min_length=2, max_length=80)
    style: str = Field(..., min_length=2, max_length=64)
    targets: list[str] = Field(..., min_length=1, max_length=3)
    seed: StrictInt = Field(default=1, ge=0, le=0xffffffff)
    original_work_attested: StrictBool = Field(default=False)
    rights_basis: str = Field(default="original_homebrew", max_length=40)
    rights_reference: str = Field(default="", max_length=240)
    approved: StrictBool = Field(default=False)
    portable_design: NativeProductionDesignBody | None = Field(default=None)
    authored_puzzles: list[NativeOriginalGrid] | None = Field(default=None, max_length=8)


def _native_source_editor(user: dict | None = Depends(get_current_user)) -> str:
    # The native product endpoint is not anonymous, development-mode enabled,
    # or accessible to viewer principals. Source bundles are consequential
    # creator artifacts even when they do not execute compilers.
    principal = _principal(user)
    if not isinstance(user, dict) or user.get("role") not in ("editor", "admin"):
        raise HTTPException(status_code=403, detail="Creator edit permission required")
    return principal


@router.get("/native/production/capabilities")
def native_production_capabilities(owner: str = Depends(_principal)) -> dict:
    from skeleton.ai.webcrawler.dragon_native_production import capability_matrix
    return {
        "ok": True,
        "targets": capability_matrix(),
        "claim_boundary": "source emitters and optional local ROM adapters; not device certification",
    }


def _make_native_production_request(body: NativeProductionSourceRequest):
    from skeleton.ai.webcrawler.dragon_native_production import (
        PortableGameDesign, ProductionRequest,
    )
    return ProductionRequest(
        title=body.title, style=body.style, targets=tuple(body.targets),
        original_work_attested=body.original_work_attested,
        rights_basis=body.rights_basis, rights_reference=body.rights_reference,
        seed=body.seed, max_portfolio_bytes=3_000_000,
        portable_design=(PortableGameDesign(**body.portable_design.model_dump())
                         if body.portable_design is not None else None),
        authored_puzzles=(tuple(tuple(row for row in board)
                                for board in body.authored_puzzles)
                          if body.authored_puzzles is not None else None),
    )


class NativeRouteWorldRequest(BaseModel):
    """Only deterministic original homebrew world scenarios are admitted."""
    model_config=ConfigDict(extra="forbid")
    seed: StrictInt=Field(default=1,ge=0,le=0xffffffff)
    weather: str=Field(default="clear",
        pattern=r"^(clear|rain|windy|storm|snow|high_tide)$")
    hour: StrictInt=Field(default=8,ge=0,le=23)


class NativeRoutePreviewRequest(NativeRouteWorldRequest):
    max_routes: StrictInt=Field(default=7,ge=1,le=12)
    search_budget: StrictInt=Field(default=1700,ge=100,le=3000)
    include_long: StrictBool=Field(default=True)


class NativeRoutePlayRequest(NativeRouteWorldRequest):
    moves: list[str]=Field(default_factory=list,max_length=80)


class NativeRouteSourceRequest(NativeRouteWorldRequest):
    original_work_attested: StrictBool=Field(default=False)
    approved: StrictBool=Field(default=False)


@router.get("/native/production/routes/taxonomy")
def native_world_route_taxonomy(
    owner: str=Depends(_principal),
) -> dict:
    from skeleton.ai.webcrawler.dragon_route_taxonomy import capabilities
    return {"ok":True,**capabilities()}


@router.post("/native/production/routes/preview")
def native_world_route_preview(
    body: NativeRoutePreviewRequest,
    owner: str=Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_route_world_factory import (
        make_frontier,scenario_digest,structural_report,
    )
    from skeleton.ai.webcrawler.dragon_route_world import (
        portfolio,route_dictionary,experience,
    )
    from skeleton.ai.webcrawler.dragon_route_world_assurance import demand_viable_world
    try:
        world,traveller=make_frontier(
            seed=body.seed,weather=body.weather,hour=body.hour)
        routes=portfolio(world,traveller,max_routes=body.max_routes,
                         expansion_cap=body.search_budget,
                         include_circuitous=body.include_long)
        summary=structural_report(world)
        quality=demand_viable_world(world,traveller)
        current=experience(world,traveller)
    except ValueError:
        raise HTTPException(status_code=422,
            detail="Original game route world could not be evaluated within bounded limits") from None
    return {
        "ok":True,
        "schema":"skeleton.ai.dragon.route_world_preview.v1",
        "world_digest":scenario_digest(world),
        "world":summary,
        "assurance":quality,
        "routes":route_dictionary(routes),
        "player":current,
        "source_only":True,
        "claim":"generic original graph travel mechanics, not native vehicle-specific simulation",
    }


@router.post("/native/production/routes/play")
def native_world_route_play(
    body: NativeRoutePlayRequest,
    owner: str=Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_route_world_factory import make_frontier
    from skeleton.ai.webcrawler.dragon_route_world import experience
    try:
        world,traveller=make_frontier(
            seed=body.seed,weather=body.weather,hour=body.hour)
        state=experience(world,traveller,path=tuple(body.moves))
    except ValueError:
        raise HTTPException(status_code=422,
            detail="Original game route is unavailable, undiscovered or exceeds resources") from None
    return {"ok":True,**state}


def _native_world_zip(files: dict[str,str], *,filename:str) -> Response:
    """Shared bounded reproducible ZIP for genuinely playable original C99 game."""
    from io import BytesIO
    from zipfile import ZipFile,ZipInfo,ZIP_DEFLATED
    allow={
        "src/main.c","include/dragon_route_world.h",
        "dragon-original-route-proof.json","Makefile",
        "CMakeLists.txt","README.md",
    }
    if (set(files)!=allow or
            any(type(value) is not str for value in files.values())):
        raise ValueError("native original game source must use exact vetted archive names")
    if sum(len(body.encode("utf-8")) for body in files.values())>1_500_000:
        raise ValueError("native source archive exceeds size budget")
    memory=BytesIO()
    with ZipFile(memory,"w",ZIP_DEFLATED,compresslevel=9) as package:
        for name in sorted(files):
            record=ZipInfo(name,date_time=(1980,1,1,0,0,0))
            record.compress_type=ZIP_DEFLATED
            record.external_attr=0o100644<<16
            package.writestr(record,files[name].encode("utf-8"))
    payload=memory.getvalue()
    if len(payload)>1_500_000:
        raise ValueError("compressed original game archive exceeds limit")
    return Response(content=payload,media_type="application/zip",headers={
        "Content-Disposition":f'attachment; filename="{filename}"',
        "X-Content-Type-Options":"nosniff",
        "Cache-Control":"private, no-store",
        "X-Content-SHA256":sha256(payload).hexdigest(),
        "X-Dragon-Claim":"original-source-only-native-C99-not-compiled",
    })


@router.post("/native/production/routes/source-bundle")
def native_world_route_source_bundle(
    body: NativeRouteSourceRequest,
    owner: str=Depends(_native_source_editor),
):
    if not body.original_work_attested or not body.approved:
        raise HTTPException(status_code=403,
            detail="Original creation rights and source export approval required")
    from skeleton.ai.webcrawler.dragon_route_world_factory import make_frontier
    from skeleton.ai.webcrawler.dragon_route_native_game import emit_route_game
    try:
        world,traveller=make_frontier(
            seed=body.seed,weather=body.weather,hour=body.hour)
        files=emit_route_game(world,traveller,authorized=True)
        return _native_world_zip(files,filename="dragon-original-world-routes.zip")
    except ValueError:
        raise HTTPException(status_code=422,
            detail="Original route-world C99 project did not pass export checks") from None


class NativeMazeWorldRequest(BaseModel):
    """Constructive maze: guaranteed playable backbone before alternatives."""
    model_config=ConfigDict(extra="forbid")
    width: StrictInt=Field(default=6,ge=4,le=8)
    height: StrictInt=Field(default=6,ge=4,le=6)
    seed: StrictInt=Field(default=1977,ge=0,le=0xffffffff)
    scenic_density: StrictInt=Field(default=65,ge=0,le=100)
    detour_density: StrictInt=Field(default=70,ge=0,le=100)
    secret_count: StrictInt=Field(default=2,ge=0,le=4)
    challenge: str=Field(default="balanced",
        pattern=r"^(gentle|balanced|challenging|spicy)$")
    weather: str=Field(default="clear",
        pattern=r"^(clear|rain|windy|storm|snow|high_tide)$")


class NativeMazePlayRequest(NativeMazeWorldRequest):
    moves: list[str]=Field(default_factory=list,max_length=80)


class NativeMazeSourceRequest(NativeMazeWorldRequest):
    original_work_attested: StrictBool=Field(default=False)
    approved: StrictBool=Field(default=False)


def _construct_native_maze(body:NativeMazeWorldRequest):
    from skeleton.ai.webcrawler.dragon_route_maze import MazeRequest,build_maze
    return build_maze(MazeRequest(
        width=body.width,height=body.height,seed=body.seed,
        scenic_density=body.scenic_density,
        detour_density=body.detour_density,
        secret_count=body.secret_count,
        challenge=body.challenge,weather=body.weather,
    ))


@router.post("/native/production/routes/maze/preview")
def native_world_maze_preview(
    body: NativeMazeWorldRequest,
    owner: str=Depends(_native_source_editor),
) -> dict:
    from dataclasses import asdict
    from skeleton.ai.webcrawler.dragon_route_maze import verify_maze
    from skeleton.ai.webcrawler.dragon_route_world import experience
    try:
        created=_construct_native_maze(body)
        proof=verify_maze(created)
        player=experience(created.world,created.traveller)
    except ValueError:
        raise HTTPException(status_code=422,
            detail="Original multi-route maze has no valid completion certificate") from None
    return {
        "ok":True,
        "schema":"skeleton.ai.dragon.maze_route_preview.v1",
        "completion":proof,
        "certificate":asdict(created.certificate),
        "player":player,
        "source_only":True,
        "claim":"original constructive maze, playable recovery plus restart after exhausted budgets",
    }


@router.post("/native/production/routes/maze/play")
def native_world_maze_play(
    body: NativeMazePlayRequest,
    owner: str=Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_route_world import experience
    try:
        creation=_construct_native_maze(body)
        player=experience(
            creation.world,creation.traveller,path=tuple(body.moves))
    except ValueError:
        raise HTTPException(status_code=422,
            detail="Original maze passage is unavailable or resource limits were exceeded") from None
    return {"ok":True,**player}


@router.post("/native/production/routes/maze/recovery")
def native_world_maze_recovery(
    body:NativeMazePlayRequest,
    owner:str=Depends(_native_source_editor),
)->dict:
    from skeleton.ai.webcrawler.dragon_route_maze import recover_maze
    try:
        built=_construct_native_maze(body)
        report=recover_maze(built,tuple(body.moves))
    except ValueError:
        raise HTTPException(status_code=422,
            detail="Original current maze world state cannot be independently replayed") from None
    return {"ok":True,**report}


@router.post("/native/production/routes/maze/source-bundle")
def native_world_maze_source_bundle(
    body: NativeMazeSourceRequest,
    owner: str=Depends(_native_source_editor),
):
    if not body.original_work_attested or not body.approved:
        raise HTTPException(status_code=403,
            detail="Original maze rights and export approval required")
    from skeleton.ai.webcrawler.dragon_route_native_game import emit_route_game
    try:
        created=_construct_native_maze(body)
        project=emit_route_game(
            created.world,created.traveller,authorized=True,
            maze_creation=created,
        )
        return _native_world_zip(
            project,filename="dragon-original-completable-maze.zip")
    except ValueError:
        raise HTTPException(status_code=422,
            detail="Maze source must replay every location and weather proof before export") from None


class NativeLivingWorldRequest(BaseModel):
    """Exact operator-selected original game-world style and lifecycle."""
    model_config=ConfigDict(extra="forbid")
    world_id:StrictInt=Field(default=0,ge=0,lt=1_600_000)
    variation:StrictInt=Field(default=0,ge=0,le=9)
    style:str|None=Field(default=None,
        pattern=r"^[a-z][a-z_]{2,47}$")
    lifecycle:str|None=Field(default=None,
        pattern=r"^[a-z][a-z_]{2,47}$")


class NativeLivingPlayRequest(NativeLivingWorldRequest):
    moves:list[str]=Field(default_factory=list,max_length=192)


class NativeLivingRouteRequest(NativeLivingWorldRequest):
    slot:StrictInt=Field(default=0,ge=0,le=9)


class NativeLivingJournalRequest(NativeLivingPlayRequest):
    expected_final_digest:str|None=Field(
        default=None,pattern=r"^[a-f0-9]{64}$")


def _dragon_living_world(body:NativeLivingWorldRequest):
    from skeleton.ai.webcrawler.dragon_living_world import create_world
    return create_world(
        world_id=body.world_id,variant=body.variation,
        style=body.style,lifecycle=body.lifecycle,
    )


@router.get("/native/production/worlds/catalog")
def native_living_world_catalog(owner:str=Depends(_principal))->dict:
    from skeleton.ai.webcrawler.dragon_living_world import catalog
    return {"ok":True,**catalog()}


@router.post("/native/production/worlds/preview")
def native_living_world_preview(
    body:NativeLivingWorldRequest,
    owner:str=Depends(_native_source_editor),
)->dict:
    from dataclasses import asdict
    from skeleton.ai.webcrawler.dragon_living_world import (
        initial_state,describe,terrain,
    )
    try:
        world=_dragon_living_world(body)
        player=initial_state(world)
        tilemap=[
            terrain(world,0,x,y)
            for y in range(-2,3) for x in range(-2,3)
        ]
    except ValueError:
        raise HTTPException(status_code=422,
            detail="Selected original living-world style or lifecycle is unsupported") from None
    return {
        "ok":True,
        "schema":"skeleton.ai.dragon.living_world_preview.v1",
        "world":asdict(world),
        "player":describe(world,player),
        "tiles":tilemap,
        "render_scope":"abstract original living-world game mechanics, not a voxel or 3D engine",
        "address_scope":"16m lazily indexed possible original world-variant slots, not completed games",
    }


@router.post("/native/production/worlds/play")
def native_living_world_play(
    body:NativeLivingPlayRequest,
    owner:str=Depends(_native_source_editor),
)->dict:
    from skeleton.ai.webcrawler.dragon_living_world import replay,describe,terrain
    try:
        world=_dragon_living_world(body)
        state=replay(world,tuple(body.moves))
        current=describe(world,state)
        surroundings=[
            terrain(world,state.realm,state.x+dx,state.y+dy)
            for dy in range(-2,3) for dx in range(-2,3)
        ]
    except ValueError:
        raise HTTPException(status_code=422,
            detail="World action is locked, unsupported or exceeds bounded play history") from None
    return {
        "ok":True,"played_moves":list(body.moves),
        "current":current,"surroundings":surroundings,
    }


@router.post("/native/production/worlds/alternatives")
def native_living_world_alternatives(
    body:NativeLivingWorldRequest,
    owner:str=Depends(_native_source_editor),
)->dict:
    from skeleton.ai.webcrawler.dragon_living_world_routes import portfolio
    try:
        return {"ok":True,**portfolio(_dragon_living_world(body),limit=10)}
    except ValueError:
        raise HTTPException(status_code=422,
            detail="Original alternative paths could not be independently replayed") from None


@router.post("/native/production/worlds/route")
def native_living_world_route(
    body:NativeLivingRouteRequest,
    owner:str=Depends(_native_source_editor),
)->dict:
    from dataclasses import asdict
    from skeleton.ai.webcrawler.dragon_living_world_routes import (
        materialize_route,verify_route,
    )
    try:
        world=_dragon_living_world(body)
        route=materialize_route(world,body.slot)
        verified=verify_route(world,route)
    except ValueError:
        raise HTTPException(status_code=422,
            detail="Indexed route address did not produce real original gameplay") from None
    return {"ok":True,"route":asdict(route),"verification":verified}


@router.post("/native/production/worlds/journal")
def native_living_world_journal(
    body:NativeLivingJournalRequest,
    owner:str=Depends(_native_source_editor),
)->dict:
    from skeleton.ai.webcrawler.dragon_living_world import journal
    try:
        world=_dragon_living_world(body)
        report=journal(world,tuple(body.moves))
        actual=report["final"]["player"]["history_digest"]
        if (body.expected_final_digest is not None and
                body.expected_final_digest!=actual):
            raise ValueError("replayed original-world history differs from claimed state")
    except ValueError:
        raise HTTPException(status_code=422,
            detail="Original world choice history does not match a real game replay") from None
    return {"ok":True,**report}


class NativeLivingCheckpointRequest(NativeLivingWorldRequest):
    """Stateless signed progression across sequential bounded action batches."""
    token:str|None=Field(
        default=None,strict=True,min_length=100,max_length=12000,
        pattern=r"^[A-Za-z0-9_.-]+$")
    moves:list[str]=Field(default_factory=list,max_length=192)


class NativeLivingCheckpointInspectRequest(NativeLivingWorldRequest):
    token:str=Field(strict=True,min_length=100,max_length=12000,
                    pattern=r"^[A-Za-z0-9_.-]+$")


@router.post("/native/production/worlds/checkpoint/advance")
def native_living_world_checkpoint_advance(
    body:NativeLivingCheckpointRequest,
    owner:str=Depends(_native_source_editor),
)->dict:
    from skeleton.ai.webcrawler.dragon_living_world_checkpoint import continue_world
    from skeleton.ai.webcrawler.dragon_living_world import describe,terrain
    try:
        world=_dragon_living_world(body)
        signed=continue_world(
            world,owner,previous_token=body.token,
            actions=tuple(body.moves),
        )
        from skeleton.ai.webcrawler.dragon_living_world_checkpoint import open_checkpoint
        state=open_checkpoint(world,signed["new_checkpoint"],owner)
        nearby=[
            terrain(world,state.realm,state.x+dx,state.y+dy)
            for dy in range(-2,3) for dx in range(-2,3)
            if abs(state.x+dx)<=1_000_000 and abs(state.y+dy)<=1_000_000
        ]
        return {
            "ok":True,**signed,"current":describe(world,state),
            "surroundings":nearby,
        }
    except RuntimeError:
        raise HTTPException(status_code=503,
            detail="Owner-bound persistent world checkpoint signing not configured") from None
    except PermissionError:
        raise HTTPException(status_code=403,
            detail="Original living-world checkpoint is expired or belongs to another player") from None
    except ValueError:
        raise HTTPException(status_code=422,
            detail="Original living-world checkpoint or subsequent move is invalid") from None


@router.post("/native/production/worlds/checkpoint/inspect")
def native_living_world_checkpoint_inspect(
    body:NativeLivingCheckpointInspectRequest,
    owner:str=Depends(_native_source_editor),
)->dict:
    from skeleton.ai.webcrawler.dragon_living_world_checkpoint import open_checkpoint
    from skeleton.ai.webcrawler.dragon_living_world import describe,terrain
    try:
        world=_dragon_living_world(body)
        state=open_checkpoint(world,body.token,owner)
        nearby=[
            terrain(world,state.realm,state.x+dx,state.y+dy)
            for dy in range(-2,3) for dx in range(-2,3)
            if abs(state.x+dx)<=1_000_000 and abs(state.y+dy)<=1_000_000
        ]
        return {
            "ok":True,"current":describe(world,state),
            "surroundings":nearby,"checkpoint_bound_to_authenticated_owner":True,
        }
    except RuntimeError:
        raise HTTPException(status_code=503,
            detail="World checkpoint signing unavailable") from None
    except PermissionError:
        raise HTTPException(status_code=403,
            detail="World checkpoint expired or not authorized for this user") from None
    except ValueError:
        raise HTTPException(status_code=422,
            detail="World checkpoint verification failed") from None


class NativeAtlasWorldRequest(BaseModel):
    """Multi-region original world: bounded multi-maze compositional gameplay."""
    model_config=ConfigDict(extra="forbid")
    seed:StrictInt=Field(default=1977,ge=0,le=0xffffffff)
    regions:StrictInt=Field(default=4,ge=2,le=12)
    width:StrictInt=Field(default=6,ge=4,le=8)
    height:StrictInt=Field(default=6,ge=4,le=6)
    climate:str=Field(default="clear",
        pattern=r"^(clear|rain|windy|storm|snow|high_tide)$")
    challenge:str=Field(default="balanced",
        pattern=r"^(gentle|balanced|challenging|spicy)$")
    scenic_density:StrictInt=Field(default=60,ge=0,le=100)
    detour_density:StrictInt=Field(default=70,ge=0,le=100)
    secret_count:StrictInt=Field(default=2,ge=0,le=4)


class NativeAtlasPlayRequest(NativeAtlasWorldRequest):
    commands:list[str]=Field(default_factory=list,max_length=512)


def _original_route_atlas(body:NativeAtlasWorldRequest):
    from skeleton.ai.webcrawler.dragon_route_atlas import AtlasRequest,build_atlas
    return build_atlas(AtlasRequest(
        seed=body.seed,regions=body.regions,
        width=body.width,height=body.height,
        climate=body.climate,challenge=body.challenge,
        scenic_density=body.scenic_density,
        detour_density=body.detour_density,
        secret_count=body.secret_count,
    ))


@router.post("/native/production/routes/atlas/preview")
def native_world_atlas_preview(
    body:NativeAtlasWorldRequest,
    owner:str=Depends(_native_source_editor),
)->dict:
    from skeleton.ai.webcrawler.dragon_route_atlas import (
        verify_atlas,atlas_report,play_atlas,
    )
    try:
        atlas=_original_route_atlas(body)
        result=verify_atlas(atlas)
        if not result["status"]=="hierarchical_completion_verified":
            raise ValueError("one original region failed world-scale game certification")
        current=play_atlas(atlas)
    except ValueError:
        raise HTTPException(status_code=422,
            detail="World-scale original route maze failed constructive completion") from None
    return {
        "ok":True,
        "schema":"skeleton.ai.dragon.original_world_atlas_preview.v1",
        "review":result,
        "atlas":atlas_report(atlas),
        "player":current,
        "native_claim":"independently native-source-capable regions, Python portal runtime",
        "physical_claim":"no finished single-binary multi-region console runtime",
    }


@router.post("/native/production/routes/atlas/play")
def native_world_atlas_play(
    body:NativeAtlasPlayRequest,
    owner:str=Depends(_native_source_editor),
)->dict:
    from skeleton.ai.webcrawler.dragon_route_atlas import play_atlas
    try:
        atlas=_original_route_atlas(body)
        player=play_atlas(atlas,tuple(body.commands))
    except ValueError:
        raise HTTPException(status_code=422,
            detail="Original multi-region route action is invalid, locked or unfinishable") from None
    return {"ok":True,**player}


class NativePuzzleGridValidationRequest(BaseModel):
    """Small bounded original authored-grid validation; never compiles source."""
    model_config = ConfigDict(extra="forbid")
    levels: list[NativeOriginalGrid] = Field(min_length=1, max_length=8)


@router.post("/native/production/puzzle/validate")
def native_production_validate_puzzle(
    body: NativePuzzleGridValidationRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_native_puzzle_authoring import preview_authored_levels
    try:
        games = tuple(tuple(row for row in level) for level in body.levels)
        return preview_authored_levels(games)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422,
                            detail="Original authored grid must be 12x10, safe and solver-proven") from None


@router.get("/native/production/puzzle/starter")
def native_production_puzzle_starter(
    stages: int = 1, owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_native_puzzle_authoring import starter_authored_levels
    try:
        return {"ok": True, **starter_authored_levels(stages)}
    except ValueError:
        raise HTTPException(status_code=422, detail="Unsupported starter game stage count") from None


class NativeOriginalCampaignAnalysisRequest(BaseModel):
    """Pure original-game topology/challenge research, not a deployed game."""
    model_config=ConfigDict(extra="forbid")
    levels: list[NativeOriginalGrid]=Field(min_length=1,max_length=8)
    mode: str=Field(default="branching",pattern=r"^(linear|branching)$")
    challenge_profile: str=Field(
        default="balanced",pattern=r"^(gentle|balanced|challenging|spicy)$")
    route_budget: StrictInt=Field(default=2500,ge=500,le=8000)


@router.post("/native/production/puzzle/campaign/analyze")
def native_production_analyze_campaign(
    body: NativeOriginalCampaignAnalysisRequest,
    owner: str=Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_native_puzzle_authoring import validate_authored_levels
    from skeleton.ai.webcrawler.dragon_native_multipath import analyse_routes,route_report
    from skeleton.ai.webcrawler.dragon_native_campaign_paths import design_campaign,graph_report
    from skeleton.ai.webcrawler.dragon_native_challenge_director import (
        make_challenge_plan,challenge_report,
    )
    try:
        campaign=validate_authored_levels(
            tuple(tuple(line for line in board) for board in body.levels))
        reports=tuple(route_report(analyse_routes(
            original.rows,max_routes=4,expansion_cap=body.route_budget,
        )) for original in campaign.levels)
        chapters=design_campaign(
            len(campaign.levels),mode=body.mode,
            intensity=body.challenge_profile,
            stage_difficulty=tuple(x["difficulty_estimate"] for x in reports),
        )
        director=make_challenge_plan(
            reports,profile=body.challenge_profile,
            branching=body.mode=="branching" and len(campaign.levels)>=3,
        )
    except ValueError:
        raise HTTPException(status_code=422,
            detail="Original campaign routes, stages or challenge goals could not be proven") from None
    return {
        "ok":True,
        "schema":"skeleton.ai.dragon.native_campaign_design_preview.v1",
        "original_campaign_digest":campaign.digest,
        "chapter_paths":graph_report(chapters),
        "challenge":challenge_report(director),
        "stages":[{"stage":index+1,"routes":document}
                  for index,document in enumerate(reports)],
        "claim":"solver-derived challenge and branching; no human player enjoyment certified",
    }


class NativePuzzleCurrentHintRequest(BaseModel):
    """Editor-only exact live hints: symbolic board data, never executable source."""
    model_config = ConfigDict(extra="forbid")
    rows: NativeOriginalGrid
    player: StrictInt = Field(ge=0, lt=120)
    crates: list[StrictInt] = Field(min_length=1, max_length=3)


class NativeRouteAnalysisRequest(BaseModel):
    """Small symbolic original game board; no third-party game extraction."""
    model_config=ConfigDict(extra="forbid")
    rows: NativeOriginalGrid
    max_routes: StrictInt=Field(default=4,ge=1,le=8)
    search_budget: StrictInt=Field(default=4000,ge=500,le=20000)


@router.post("/native/production/puzzle/multiple-routes")
def native_production_multiple_routes(
    body: NativeRouteAnalysisRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_native_multipath import analyse_routes,route_report
    try:
        routes=analyse_routes(
            tuple(body.rows),
            max_routes=body.max_routes,
            expansion_cap=body.search_budget,
        )
    except ValueError:
        raise HTTPException(status_code=422,
            detail="Original puzzle board could not produce bounded proven route analysis") from None
    return {"ok":True,**route_report(routes)}


@router.post("/native/production/puzzle/current-hint")
def native_production_current_puzzle_hint(
    body: NativePuzzleCurrentHintRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_native_puzzle import solve_grid
    original = tuple(body.rows)
    try:
        moves,visited = solve_grid(
            original,
            current_player=body.player,
            current_crates=tuple(body.crates),
        )
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="Original current game board state has no bounded proven route",
        ) from None
    return {
        "ok": True,
        "schema": "skeleton.ai.dragon.original_puzzle_current_hint.v1",
        "next_move": moves[0] if moves else None,
        "remaining_moves": len(moves),
        "shortest_route": moves,
        "search_states": visited,
        "solved": len(moves) == 0,
        "proof_scope": "bounded exact abstract Sokoban grid only; no compiled hardware claim",
    }


@router.post("/native/production/preview")
def native_production_preview(
    body: NativeProductionSourceRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    """No build, rights approval, storage mutation, compiler or knowledge promotion."""
    if not body.original_work_attested:
        raise HTTPException(status_code=403, detail="Original rights declaration required")
    from skeleton.ai.webcrawler.dragon_native_production import preview_native_portfolio
    try:
        return {"ok": True, **preview_native_portfolio(_make_native_production_request(body))}
    except (ValueError, PermissionError):
        raise HTTPException(status_code=422,
                            detail="Unsupported target, genre or portable game controls") from None


@router.post("/native/production/source-bundle")
def native_production_source_bundle(
    body: NativeProductionSourceRequest,
    owner: str = Depends(_native_source_editor),
):
    """Authenticated, size-limited original game-source export; entirely in memory."""
    if not body.approved or not body.original_work_attested:
        raise HTTPException(status_code=403,
                            detail="Explicit publication and original rights attestation required")
    from skeleton.ai.webcrawler.dragon_native_production import build_source_bundle
    try:
        request = _make_native_production_request(body)
        payload, index = build_source_bundle(request, authorized=True)
    except (ValueError, PermissionError):
        raise HTTPException(status_code=422,
                            detail="Unsupported source target, rights evidence or resource budget") from None
    return Response(
        content=payload, media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="dragon-original-native-sources.zip"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
            "X-Content-SHA256": sha256(payload).hexdigest(),
            "X-Dragon-Request-Id": index["request_id"],
            "X-Dragon-Claim": "source-only-not-a-compiled-game",
        },
    )

def _build_signing_key() -> bytes:
    value=os.environ.get("SKL_DRAGON_BUILD_SIGNING_KEY_HEX","")
    try:
        key=bytes.fromhex(value)
    except ValueError:
        key=b""
    if len(key)<32:
        raise HTTPException(status_code=503,
             detail="Dragon native build evidence signer unavailable")
    return key

@router.get("/native/evidence")
def native_build_evidence(owner: str = Depends(_principal)) -> dict:
    # Read-only product endpoint. A browser cannot mint compiler evidence,
    # submit invented ROM bytes, approve its own game or award progression XP.
    key=_build_signing_key()
    with _lab() as (lab,_):
        native=DragonNativePracticeLab(lab.db,lab)
        receipts=DragonBuildEvidence(lab.db,native,
                     private_signing_key=key).history(owner,authorized=True)
        return {"ok":True,"receipts":[asdict(r) for r in receipts[-50:]],
                "claim_boundary":"ROM structural proof, not executed gameplay"}

def _curriculum(lab: DragonPracticeLab) -> DragonNativeCurriculum:
    native=DragonNativePracticeLab(lab.db,lab)
    configured=os.environ.get("SKL_DRAGON_BUILD_SIGNING_KEY_HEX","").strip()
    evidence=(DragonBuildEvidence(lab.db,native,
             private_signing_key=_build_signing_key()) if configured else None)
    return DragonNativeCurriculum(native,evidence)

@router.get("/native/curriculum")
def native_curriculum(owner: str = Depends(_principal)) -> dict:
    with _lab() as (lab,_):
        result=_curriculum(lab).evaluate(owner,authorized=True)
        return {"ok":True,**curriculum_report(result)}

@router.post("/native/curriculum/generate")
def native_curriculum_generate(
    body: CurriculumGenerateRequest,
    owner: str = Depends(_principal),
) -> dict:
    if not body.approved:
        raise HTTPException(status_code=403,
                            detail="Explicit native practice approval required")
    with _lab() as (lab,cycles):
        try:
            next_state,attempt=_curriculum(lab).generate_next(
                owner,authorized=True,consent=True,now=time.time())
        except PermissionError:
            raise HTTPException(status_code=403,
                                detail="Approved native lesson required") from None
        except ValueError:
            raise HTTPException(status_code=422,
                                detail="No unlocked native exercise or resource budget") from None
        return {"ok":True,"created_native":asdict(attempt),
                "curriculum":curriculum_report(next_state),
                **{k:v for k,v in _snapshot(lab,cycles,owner).items() if k!="ok"}}

@router.post("/native/generate")
def generate_native(body: NativeGenerateRequest,
                    owner: str = Depends(_principal)) -> dict:
    with _lab() as (lab,cycles):
        native=DragonNativePracticeLab(lab.db,lab)
        try:
            item=native.generate(owner,target_id=body.target_id,style=body.style,
                                 now=time.time(),authorized=True,consent=True)
        except PermissionError:
            raise HTTPException(status_code=403,detail="Approved lessons or licensed SDK unavailable") from None
        except ValueError:
            raise HTTPException(status_code=422,detail="Native target or exercise not available") from None
        result=_snapshot(lab,cycles,owner)
        result["created_native"]=asdict(item)
        return result

@router.get("/native/{attempt_id}/archive")
def native_archive(
    attempt_id: str = URLPath(pattern=r"^[a-f0-9]{64}$"),
    owner: str = Depends(_principal),
):
    with _lab() as (lab,_):
        native=DragonNativePracticeLab(lab.db,lab)
        try:
            content,digest=native.archive(owner,attempt_id,authorized=True)
        except (LookupError,ValueError):
            raise HTTPException(status_code=404,detail="Native project unavailable") from None
        return Response(content=content,media_type="application/zip",
                        headers={"Content-Disposition":
                          'attachment; filename="dragon-native-'+attempt_id[:12]+'.zip"',
                          "X-Content-Type-Options":"nosniff",
                          "Cache-Control":"private, no-store",
                          "X-Content-SHA256":digest})

@router.post("/practice/run")
def run_practice(body: RunPracticeRequest, owner: str = Depends(_principal)) -> dict:
    with _lab() as (lab,cycles):
        # An authenticated click is *not* permission to mint practice lessons.
        # The canonical crawler must have deposited review-approved lessons.
        attempts=lab.run_batch(owner,authorized=True,consent=True,
                               now=time.time(),max_demos=body.max_demos)
        result=_snapshot(lab,cycles,owner)
        result["created"]=[asdict(a) for a in attempts]
        return result

@router.post("/practice/subscribe")
def subscribe_practice(body: SubscribeRequest, owner: str = Depends(_principal)) -> dict:
    if not body.approved:
        raise HTTPException(status_code=403,detail="Explicit practice approval is required")
    now=time.time()
    with _lab() as (lab,cycles):
        cycles.enable(owner,authorized=True,human_approved=True,now=now,
                      expires_at=now+body.hours*3600,
                      interval_seconds=body.interval_seconds,
                      max_ticks=body.max_ticks,
                      demos_per_tick=body.demos_per_tick,
                      generation_mode='curriculum' if body.adaptive else 'native',
                      native_target=body.native_target,
                      native_style=body.native_style)
        return _snapshot(lab,cycles,owner)

@router.post("/practice/stop")
def stop_practice(owner: str = Depends(_principal)) -> dict:
    with _lab() as (lab,cycles):
        cycles.disable(owner,authorized=True)
        return _snapshot(lab,cycles,owner)

@router.post("/practice/revoke")
def revoke_practice(owner: str = Depends(_principal)) -> dict:
    with _lab() as (lab,cycles):
        cycles.disable(owner,authorized=True)
        lab.revoke(owner,authorized=True)
        return _snapshot(lab,cycles,owner)

@router.get("/practice/{attempt_id}/artifact")
def practice_artifact(
    attempt_id: str = URLPath(pattern=r"^[a-f0-9]{64}$"),
    owner: str = Depends(_principal),
) -> dict:
    with _lab() as (lab,_):
        try:
            html=lab.artifact(owner,attempt_id,authorized=True)
        except (LookupError,ValueError):
            raise HTTPException(status_code=404,detail="Demo unavailable") from None
        # Never serve playable HTML with an application origin/cookie context.
        return {
            "ok": True,
            "attempt_id": attempt_id,
            "html": html,
            "sha256": sha256(html.encode("utf-8")).hexdigest(),
            "sandbox_required": True,
        }
