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
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StringConstraints, model_validator

from routes.gameforge_auth import get_current_user
from skeleton.ai.webcrawler.dragon_practice_lab import DragonPracticeLab
from skeleton.ai.webcrawler.dragon_family_custody_bridge import DragonFamilyCustodyBridge
from skeleton.ai.webcrawler.dragon_family_glean_matrix import DragonGleanMatrix
from skeleton.ai.webcrawler.dragon_family_almanakk import DragonAlmanakkLane
from skeleton.ai.webcrawler.dragon_family_idle_coordinator import read_idle_family_health
from skeleton.ai.webcrawler.dragon_family_idle_host import read_idle_host_projection
from skeleton.ai.webcrawler.dragon_practice_cycles import DragonPracticeCycles
from skeleton.ai.webcrawler.dragon_session_projection import DragonSessionProjection
from skeleton.ai.webcrawler.dragon_native_practice import DragonNativePracticeLab
from skeleton.ai.webcrawler.dragon_build_evidence import DragonBuildEvidence
from skeleton.ai.webcrawler.dragon_native_curriculum import (
    DragonNativeCurriculum,
    curriculum_report,
)
from skeleton.ai.webcrawler.dragon_native_targets import target_catalog, practice_matrix, STYLES
from skeleton.ai.webcrawler.dragon_platform_readiness import coverage_report
from core.dragon_crawler import CrawlerError, crawler_application
from pymongo.errors import PyMongoError

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
    native_target: str = Field(default="game_boy", min_length=2, max_length=64)
    native_style: str = Field(default="arcade_score_attack", min_length=2, max_length=64)


def _principal(user: dict | None = Depends(get_current_user)) -> str:
    """No anonymous/development bypass, even when the general app has dev auth off."""
    if not isinstance(user, dict) or user.get("disabled") or user.get("dev_mode"):
        raise HTTPException(status_code=401, detail="Sign in to use Dragon Academy")
    email = user.get("email")
    if not isinstance(email, str) or not 3 <= len(email.strip()) <= 200:
        raise HTTPException(status_code=403, detail="Account identity unavailable")
    if user.get("role") not in ("viewer", "editor", "admin"):
        raise HTTPException(status_code=403, detail="Account permission unavailable")
    tenant = user.get("tenant_id") or email
    if not isinstance(tenant, str) or not 1 <= len(tenant.strip()) <= 128:
        raise HTTPException(status_code=403, detail="Tenant identity unavailable")
    # Exactly one opaque owner ID per tenant/principal pair, independent of
    # user-supplied parameters; avoid exposing the email in SQLite keys.
    return sha256((tenant.strip() + "\x00" + email.strip().lower()).encode()).hexdigest()


def _database_path() -> Path:
    raw = os.environ.get("SKL_DRAGON_PRACTICE_DB_PATH", "").strip()
    if not raw:
        raise HTTPException(status_code=503, detail="Dragon Academy storage not configured")
    path = Path(raw).expanduser()
    if not path.is_absolute() or path.name in ("", ".", "..") or not path.parent.is_dir():
        raise HTTPException(status_code=503, detail="Dragon Academy durable storage unavailable")
    return path


@contextmanager
def _lab() -> Iterator[tuple[DragonPracticeLab, DragonPracticeCycles]]:
    path = _database_path()
    try:
        db = sqlite3.connect(str(path), timeout=5)
        try:
            db.execute("PRAGMA busy_timeout=5000")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA foreign_keys=ON")
            lab = DragonPracticeLab(db)
            yield lab, DragonPracticeCycles(db, lab)
        finally:
            db.close()
    except (sqlite3.DatabaseError, sqlite3.OperationalError) as exc:
        raise HTTPException(status_code=503, detail="Dragon Academy storage unavailable") from None


def _snapshot(lab: DragonPracticeLab, cycles: DragonPracticeCycles, owner: str) -> dict:
    # The public route never owns insight-review callbacks. It projects only
    # canonical reviewed evidence under the authenticated user's owner scope.
    custody = DragonFamilyCustodyBridge(lab.db, owner)
    family = custody.family()
    return {
        "ok": True,
        "progress": asdict(lab.progress(owner, authorized=True)),
        "family": {
            **family.snapshot(owner, authorized=True, limit=25),
            "glean": DragonGleanMatrix(family).projection(owner, authorized=True, limit=12),
            "almanakk": DragonAlmanakkLane(lab.db).projection(owner, authorized=True, limit=15),
            "idle_work": read_idle_family_health(lab.db, owner, authorized=True),
            "idle_host": read_idle_host_projection(lab.db, owner, at=time.time(), authorized=True),
        },
        "attempts": [asdict(a) for a in lab.attempts(owner, authorized=True, limit=50)],
        "native_attempts": [
            asdict(a) for a in DragonNativePracticeLab(lab.db, lab).list(owner, authorized=True)
        ],
        "subscription": asdict(cycles.status(owner, authorized=True)),
    }


@router.get("/status")
def academy_status(owner: str = Depends(_principal)) -> dict:
    with _lab() as (lab, cycles):
        return _snapshot(lab, cycles, owner)


@router.get("/crawler/feed")
async def crawler_feed(
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=250),
    last_event_digest: str | None = Query(default=None, max_length=64),
    user: dict | None = Depends(get_current_user),
) -> dict:
    """Prefer the account's canonical crawl checkpoint, then the practice journal.

    A digest cursor that does not match the checkpoint is a conflict. Storage
    or checkpoint failures leave the practice-lab journal available.
    """
    owner = _principal(user)
    scope = _crawler_scope(user)
    canonical = None
    try:
        canonical = await crawler_application.companion_feed(
            scope, after_sequence=after_sequence, limit=limit, expected_digest=last_event_digest,
        )
    except ValueError:
        raise HTTPException(status_code=409, detail="Crawler journal replay unavailable") from None
    except (PyMongoError, CrawlerError):
        canonical = None
    if canonical and canonical.get("active"):
        return {"ok": True, **canonical}
    with _lab() as (lab, _):
        try:
            feed = DragonSessionProjection(lab.db).read(
                owner, authorized=True, after_sequence=after_sequence, limit=limit,
                expected_digest=last_event_digest,
            )
        except ValueError:
            raise HTTPException(status_code=409, detail="Crawler journal replay unavailable") from None
        return {"ok": True, **asdict(feed)}


@router.get("/native/targets")
def native_targets(owner: str = Depends(_principal)) -> dict:
    # Catalog metadata does not imply working native compilation.
    return {
        "ok": True,
        "targets": target_catalog(),
        "styles": STYLES,
        "supported_matrix": practice_matrix(),
        "coverage": coverage_report(),
    }


class NativeProductionPixelArtPreview(BaseModel):
    """Strictly original 8x8 source sprite preview, no external images or ROMs."""

    model_config = ConfigDict(extra="forbid")
    hero: str = Field(default="hatchling", max_length=32)
    quest_theme: str = Field(default="ancient_ruins", max_length=32)
    palette: str = Field(default="dmg_green", max_length=30)
    seed: StrictInt = Field(default=1, ge=0, le=0xFFFFFFFF)
    target: str = Field(default="game_boy", max_length=32)


@router.post("/native/production/art-preview")
def native_production_art_preview(
    body: NativeProductionPixelArtPreview,
    owner: str = Depends(_principal),
) -> dict:
    """Pixel-perfect intended original 2bpp source tiles, NOT device rendering."""
    from skeleton.ai.webcrawler.dragon_native_artforge import (
        TARGETS,
        make_art,
    )

    if body.target not in TARGETS:
        raise HTTPException(status_code=422, detail="Original sprite tile preview adapter unavailable")
    # Cartridge video asset palette classes are intentionally bounded: other
    # UI themes map into a compatible handheld 2bpp tone class.
    actual_palette = body.palette if body.palette in ("dmg_green", "handheld", "vga_dusk") else "handheld"
    try:
        art, tiles = make_art(
            hero=body.hero,
            theme=body.quest_theme,
            palette=actual_palette,
            seed=body.seed,
            target=body.target,
        )
    except ValueError:
        raise HTTPException(status_code=422, detail="Unsupported original sprite design") from None
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
NativeOriginalGrid = Annotated[list[NativeOriginalGridRow], Field(min_length=10, max_length=10)]


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
    seed: StrictInt = Field(default=1, ge=0, le=0xFFFFFFFF)
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
        PortableGameDesign,
        ProductionRequest,
    )

    return ProductionRequest(
        title=body.title,
        style=body.style,
        targets=tuple(body.targets),
        original_work_attested=body.original_work_attested,
        rights_basis=body.rights_basis,
        rights_reference=body.rights_reference,
        seed=body.seed,
        max_portfolio_bytes=3_000_000,
        portable_design=(
            PortableGameDesign(**body.portable_design.model_dump())
            if body.portable_design is not None
            else None
        ),
        authored_puzzles=(
            tuple(tuple(row for row in board) for board in body.authored_puzzles)
            if body.authored_puzzles is not None
            else None
        ),
    )


class NativeRouteWorldRequest(BaseModel):
    """Only deterministic original homebrew world scenarios are admitted."""

    model_config = ConfigDict(extra="forbid")
    seed: StrictInt = Field(default=1, ge=0, le=0xFFFFFFFF)
    weather: str = Field(default="clear", pattern=r"^(clear|rain|windy|storm|snow|high_tide)$")
    hour: StrictInt = Field(default=8, ge=0, le=23)


class NativeRoutePreviewRequest(NativeRouteWorldRequest):
    max_routes: StrictInt = Field(default=7, ge=1, le=12)
    search_budget: StrictInt = Field(default=1700, ge=100, le=3000)
    include_long: StrictBool = Field(default=True)


class NativeRoutePlayRequest(NativeRouteWorldRequest):
    moves: list[str] = Field(default_factory=list, max_length=80)


class NativeRouteSourceRequest(NativeRouteWorldRequest):
    original_work_attested: StrictBool = Field(default=False)
    approved: StrictBool = Field(default=False)


@router.get("/native/production/routes/taxonomy")
def native_world_route_taxonomy(
    owner: str = Depends(_principal),
) -> dict:
    from skeleton.ai.webcrawler.dragon_route_taxonomy import capabilities

    return {"ok": True, **capabilities()}


@router.post("/native/production/routes/preview")
def native_world_route_preview(
    body: NativeRoutePreviewRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_route_world_factory import (
        make_frontier,
        scenario_digest,
        structural_report,
    )
    from skeleton.ai.webcrawler.dragon_route_world import (
        portfolio,
        route_dictionary,
        experience,
    )
    from skeleton.ai.webcrawler.dragon_route_world_assurance import demand_viable_world

    try:
        world, traveller = make_frontier(seed=body.seed, weather=body.weather, hour=body.hour)
        routes = portfolio(
            world,
            traveller,
            max_routes=body.max_routes,
            expansion_cap=body.search_budget,
            include_circuitous=body.include_long,
        )
        summary = structural_report(world)
        quality = demand_viable_world(world, traveller)
        current = experience(world, traveller)
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original game route world could not be evaluated within bounded limits"
        ) from None
    return {
        "ok": True,
        "schema": "skeleton.ai.dragon.route_world_preview.v1",
        "world_digest": scenario_digest(world),
        "world": summary,
        "assurance": quality,
        "routes": route_dictionary(routes),
        "player": current,
        "source_only": True,
        "claim": "generic original graph travel mechanics, not native vehicle-specific simulation",
    }


@router.post("/native/production/routes/play")
def native_world_route_play(
    body: NativeRoutePlayRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_route_world_factory import make_frontier
    from skeleton.ai.webcrawler.dragon_route_world import experience

    try:
        world, traveller = make_frontier(seed=body.seed, weather=body.weather, hour=body.hour)
        state = experience(world, traveller, path=tuple(body.moves))
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original game route is unavailable, undiscovered or exceeds resources"
        ) from None
    return {"ok": True, **state}


def _native_world_zip(files: dict[str, str], *, filename: str) -> Response:
    """Shared bounded reproducible ZIP for genuinely playable original C99 game."""
    from io import BytesIO
    from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

    allow = {
        "src/main.c",
        "include/dragon_route_world.h",
        "dragon-original-route-proof.json",
        "Makefile",
        "CMakeLists.txt",
        "README.md",
    }
    if set(files) != allow or any(type(value) is not str for value in files.values()):
        raise ValueError("native original game source must use exact vetted archive names")
    if sum(len(body.encode("utf-8")) for body in files.values()) > 1_500_000:
        raise ValueError("native source archive exceeds size budget")
    memory = BytesIO()
    with ZipFile(memory, "w", ZIP_DEFLATED, compresslevel=9) as package:
        for name in sorted(files):
            record = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            record.compress_type = ZIP_DEFLATED
            record.external_attr = 0o100644 << 16
            package.writestr(record, files[name].encode("utf-8"))
    payload = memory.getvalue()
    if len(payload) > 1_500_000:
        raise ValueError("compressed original game archive exceeds limit")
    return Response(
        content=payload,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
            "X-Content-SHA256": sha256(payload).hexdigest(),
            "X-Dragon-Claim": "original-source-only-native-C99-not-compiled",
        },
    )


@router.post("/native/production/routes/source-bundle")
def native_world_route_source_bundle(
    body: NativeRouteSourceRequest,
    owner: str = Depends(_native_source_editor),
):
    if not body.original_work_attested or not body.approved:
        raise HTTPException(
            status_code=403, detail="Original creation rights and source export approval required"
        )
    from skeleton.ai.webcrawler.dragon_route_world_factory import make_frontier
    from skeleton.ai.webcrawler.dragon_route_native_game import emit_route_game

    try:
        world, traveller = make_frontier(seed=body.seed, weather=body.weather, hour=body.hour)
        files = emit_route_game(world, traveller, authorized=True)
        return _native_world_zip(files, filename="dragon-original-world-routes.zip")
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original route-world C99 project did not pass export checks"
        ) from None


class NativeMazeWorldRequest(BaseModel):
    """Constructive maze: guaranteed playable backbone before alternatives."""

    model_config = ConfigDict(extra="forbid")
    width: StrictInt = Field(default=6, ge=4, le=8)
    height: StrictInt = Field(default=6, ge=4, le=6)
    seed: StrictInt = Field(default=1977, ge=0, le=0xFFFFFFFF)
    scenic_density: StrictInt = Field(default=65, ge=0, le=100)
    detour_density: StrictInt = Field(default=70, ge=0, le=100)
    secret_count: StrictInt = Field(default=2, ge=0, le=4)
    challenge: str = Field(default="balanced", pattern=r"^(gentle|balanced|challenging|spicy)$")
    weather: str = Field(default="clear", pattern=r"^(clear|rain|windy|storm|snow|high_tide)$")


class NativeMazePlayRequest(NativeMazeWorldRequest):
    moves: list[str] = Field(default_factory=list, max_length=80)


class NativeMazeSourceRequest(NativeMazeWorldRequest):
    original_work_attested: StrictBool = Field(default=False)
    approved: StrictBool = Field(default=False)


def _construct_native_maze(body: NativeMazeWorldRequest):
    from skeleton.ai.webcrawler.dragon_route_maze import MazeRequest, build_maze

    return build_maze(
        MazeRequest(
            width=body.width,
            height=body.height,
            seed=body.seed,
            scenic_density=body.scenic_density,
            detour_density=body.detour_density,
            secret_count=body.secret_count,
            challenge=body.challenge,
            weather=body.weather,
        )
    )


@router.post("/native/production/routes/maze/preview")
def native_world_maze_preview(
    body: NativeMazeWorldRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from dataclasses import asdict
    from skeleton.ai.webcrawler.dragon_route_maze import verify_maze
    from skeleton.ai.webcrawler.dragon_route_world import experience

    try:
        created = _construct_native_maze(body)
        proof = verify_maze(created)
        player = experience(created.world, created.traveller)
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original multi-route maze has no valid completion certificate"
        ) from None
    return {
        "ok": True,
        "schema": "skeleton.ai.dragon.maze_route_preview.v1",
        "completion": proof,
        "certificate": asdict(created.certificate),
        "player": player,
        "source_only": True,
        "claim": "original constructive maze, playable recovery plus restart after exhausted budgets",
    }


@router.post("/native/production/routes/maze/play")
def native_world_maze_play(
    body: NativeMazePlayRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_route_world import experience

    try:
        creation = _construct_native_maze(body)
        player = experience(creation.world, creation.traveller, path=tuple(body.moves))
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original maze passage is unavailable or resource limits were exceeded"
        ) from None
    return {"ok": True, **player}


@router.post("/native/production/routes/maze/recovery")
def native_world_maze_recovery(
    body: NativeMazePlayRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_route_maze import recover_maze

    try:
        built = _construct_native_maze(body)
        report = recover_maze(built, tuple(body.moves))
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original current maze world state cannot be independently replayed"
        ) from None
    return {"ok": True, **report}


@router.post("/native/production/routes/maze/source-bundle")
def native_world_maze_source_bundle(
    body: NativeMazeSourceRequest,
    owner: str = Depends(_native_source_editor),
):
    if not body.original_work_attested or not body.approved:
        raise HTTPException(status_code=403, detail="Original maze rights and export approval required")
    from skeleton.ai.webcrawler.dragon_route_native_game import emit_route_game

    try:
        created = _construct_native_maze(body)
        project = emit_route_game(
            created.world,
            created.traveller,
            authorized=True,
            maze_creation=created,
        )
        return _native_world_zip(project, filename="dragon-original-completable-maze.zip")
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Maze source must replay every location and weather proof before export"
        ) from None


class NativeLivingWorldRequest(BaseModel):
    """Exact operator-selected original game-world style and lifecycle."""

    model_config = ConfigDict(extra="forbid")
    world_id: StrictInt = Field(default=0, ge=0, lt=1_600_000)
    variation: StrictInt = Field(default=0, ge=0, le=9)
    style: str | None = Field(default=None, pattern=r"^[a-z][a-z_]{2,47}$")
    lifecycle: str | None = Field(default=None, pattern=r"^[a-z][a-z_]{2,47}$")


class NativeLivingPlayRequest(NativeLivingWorldRequest):
    moves: list[str] = Field(default_factory=list, max_length=192)


class NativeLivingRouteRequest(NativeLivingWorldRequest):
    slot: StrictInt = Field(default=0, ge=0, le=9)


class NativeLivingJournalRequest(NativeLivingPlayRequest):
    expected_final_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


def _dragon_living_world(body: NativeLivingWorldRequest):
    from skeleton.ai.webcrawler.dragon_living_world import create_world

    return create_world(
        world_id=body.world_id,
        variant=body.variation,
        style=body.style,
        lifecycle=body.lifecycle,
    )


@router.get("/native/production/worlds/catalog")
def native_living_world_catalog(owner: str = Depends(_principal)) -> dict:
    from skeleton.ai.webcrawler.dragon_living_world import catalog
    from skeleton.ai.webcrawler.dragon_living_world_lattice import lattice_capabilities

    return {"ok": True, **catalog(), "compositional_lattice": lattice_capabilities()}


@router.post("/native/production/worlds/preview")
def native_living_world_preview(
    body: NativeLivingWorldRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from dataclasses import asdict
    from skeleton.ai.webcrawler.dragon_living_world import (
        initial_state,
        describe,
        terrain_for_state,
    )

    try:
        world = _dragon_living_world(body)
        player = initial_state(world)
        tilemap = [terrain_for_state(world, player, 0, x, y) for y in range(-2, 3) for x in range(-2, 3)]
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Selected original living-world style or lifecycle is unsupported"
        ) from None
    return {
        "ok": True,
        "schema": "skeleton.ai.dragon.living_world_preview.v1",
        "world": asdict(world),
        "player": describe(world, player),
        "tiles": tilemap,
        "render_scope": "abstract original living-world game mechanics, not a voxel or 3D engine",
        "address_scope": "16m lazily indexed possible original world-variant slots, not completed games",
    }


@router.post("/native/production/worlds/play")
def native_living_world_play(
    body: NativeLivingPlayRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_living_world import replay, describe, terrain_for_state

    try:
        world = _dragon_living_world(body)
        state = replay(world, tuple(body.moves))
        current = describe(world, state)
        surroundings = [
            terrain_for_state(world, state, state.realm, state.x + dx, state.y + dy)
            for dy in range(-2, 3)
            for dx in range(-2, 3)
        ]
    except ValueError:
        raise HTTPException(
            status_code=422, detail="World action is locked, unsupported or exceeds bounded play history"
        ) from None
    return {
        "ok": True,
        "played_moves": list(body.moves),
        "current": current,
        "surroundings": surroundings,
    }


@router.post("/native/production/worlds/alternatives")
def native_living_world_alternatives(
    body: NativeLivingWorldRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_living_world_routes import portfolio

    try:
        return {"ok": True, **portfolio(_dragon_living_world(body), limit=10)}
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original alternative paths could not be independently replayed"
        ) from None


@router.post("/native/production/worlds/route")
def native_living_world_route(
    body: NativeLivingRouteRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from dataclasses import asdict
    from skeleton.ai.webcrawler.dragon_living_world_routes import (
        materialize_route,
        verify_route,
    )

    try:
        world = _dragon_living_world(body)
        route = materialize_route(world, body.slot)
        verified = verify_route(world, route)
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Indexed route address did not produce real original gameplay"
        ) from None
    return {"ok": True, "route": asdict(route), "verification": verified}


@router.post("/native/production/worlds/journal")
def native_living_world_journal(
    body: NativeLivingJournalRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_living_world import journal

    try:
        world = _dragon_living_world(body)
        report = journal(world, tuple(body.moves))
        actual = report["final"]["player"]["history_digest"]
        if body.expected_final_digest is not None and body.expected_final_digest != actual:
            raise ValueError("replayed original-world history differs from claimed state")
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original world choice history does not match a real game replay"
        ) from None
    return {"ok": True, **report}


class NativeLivingCheckpointRequest(NativeLivingWorldRequest):
    """Stateless signed progression across sequential bounded action batches."""

    token: str | None = Field(
        default=None, strict=True, min_length=100, max_length=12000, pattern=r"^[A-Za-z0-9_.-]+$"
    )
    moves: list[str] = Field(default_factory=list, max_length=192)


class NativeLivingCheckpointInspectRequest(NativeLivingWorldRequest):
    token: str = Field(strict=True, min_length=100, max_length=12000, pattern=r"^[A-Za-z0-9_.-]+$")


@router.post("/native/production/worlds/checkpoint/advance")
def native_living_world_checkpoint_advance(
    body: NativeLivingCheckpointRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_living_world_checkpoint import continue_world
    from skeleton.ai.webcrawler.dragon_living_world import describe, terrain_for_state

    try:
        world = _dragon_living_world(body)
        signed = continue_world(
            world,
            owner,
            previous_token=body.token,
            actions=tuple(body.moves),
        )
        from skeleton.ai.webcrawler.dragon_living_world_checkpoint import open_checkpoint

        state = open_checkpoint(world, signed["new_checkpoint"], owner)
        nearby = [
            terrain_for_state(world, state, state.realm, state.x + dx, state.y + dy)
            for dy in range(-2, 3)
            for dx in range(-2, 3)
            if abs(state.x + dx) <= 1_000_000 and abs(state.y + dy) <= 1_000_000
        ]
        return {
            "ok": True,
            **signed,
            "current": describe(world, state),
            "surroundings": nearby,
        }
    except RuntimeError:
        raise HTTPException(
            status_code=503, detail="Owner-bound persistent world checkpoint signing not configured"
        ) from None
    except PermissionError:
        raise HTTPException(
            status_code=403, detail="Original living-world checkpoint is expired or belongs to another player"
        ) from None
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original living-world checkpoint or subsequent move is invalid"
        ) from None


@router.post("/native/production/worlds/checkpoint/inspect")
def native_living_world_checkpoint_inspect(
    body: NativeLivingCheckpointInspectRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_living_world_checkpoint import open_checkpoint
    from skeleton.ai.webcrawler.dragon_living_world import describe, terrain_for_state

    try:
        world = _dragon_living_world(body)
        state = open_checkpoint(world, body.token, owner)
        nearby = [
            terrain_for_state(world, state, state.realm, state.x + dx, state.y + dy)
            for dy in range(-2, 3)
            for dx in range(-2, 3)
            if abs(state.x + dx) <= 1_000_000 and abs(state.y + dy) <= 1_000_000
        ]
        return {
            "ok": True,
            "current": describe(world, state),
            "surroundings": nearby,
            "checkpoint_bound_to_authenticated_owner": True,
        }
    except RuntimeError:
        raise HTTPException(status_code=503, detail="World checkpoint signing unavailable") from None
    except PermissionError:
        raise HTTPException(
            status_code=403, detail="World checkpoint expired or not authorized for this user"
        ) from None
    except ValueError:
        raise HTTPException(status_code=422, detail="World checkpoint verification failed") from None


class NativeLivingStoreRequest(NativeLivingWorldRequest):
    token: str = Field(strict=True, min_length=100, max_length=12000, pattern=r"^[A-Za-z0-9_.-]+$")
    slot: StrictInt = Field(default=0, ge=0, le=9)
    replace_existing: StrictBool = Field(default=False)
    expected_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class NativeLivingRestoreRequest(NativeLivingWorldRequest):
    slot: StrictInt = Field(default=0, ge=0, le=9)


@router.post("/native/production/worlds/store")
def native_living_world_store(
    body: NativeLivingStoreRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_living_world_checkpoint import open_checkpoint
    from skeleton.ai.webcrawler.dragon_living_world_store import store

    world = _dragon_living_world(body)
    try:
        state = open_checkpoint(world, body.token, owner)
        with sqlite3.connect(str(_database_path()), timeout=5) as db:
            db.execute("PRAGMA busy_timeout=5000")
            return {
                "ok": True,
                **store(
                    db,
                    world,
                    state,
                    owner,
                    body.slot,
                    expected_digest=body.expected_digest,
                    replace_existing=body.replace_existing,
                ),
            }
    except RuntimeError:
        raise HTTPException(
            status_code=503, detail="Durable original world signing has not been configured"
        ) from None
    except PermissionError:
        raise HTTPException(
            status_code=403, detail="Original game checkpoint is not authorized or save was modified"
        ) from None
    except FileExistsError:
        raise HTTPException(
            status_code=409,
            detail="Durable save slot occupied or stale version; refusing to overwrite choices",
        ) from None
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original living-world state or optimistic save receipt invalid"
        ) from None
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="Durable original world database unavailable") from None


@router.post("/native/production/worlds/restore")
def native_living_world_restore(
    body: NativeLivingRestoreRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_living_world_store import restore

    world = _dragon_living_world(body)
    try:
        with sqlite3.connect(str(_database_path()), timeout=5) as db:
            db.execute("PRAGMA busy_timeout=5000")
            return {"ok": True, **restore(db, world, owner, body.slot)}
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail="No original game save exists in this user's slot"
        ) from None
    except PermissionError:
        raise HTTPException(
            status_code=403, detail="Saved world belongs to another player or has invalid integrity"
        ) from None
    except (RuntimeError, sqlite3.Error):
        raise HTTPException(
            status_code=503, detail="Original game durable save store or signing is unavailable"
        ) from None
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original game requested restore has invalid parameters"
        ) from None


@router.get("/native/production/worlds/saves")
def native_living_world_saves(
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_living_world_store import list_saves

    try:
        with sqlite3.connect(str(_database_path()), timeout=5) as db:
            db.execute("PRAGMA busy_timeout=5000")
            return {
                "ok": True,
                "schema": "skeleton.ai.dragon.durable_living_world_save.v1",
                "saves": list(list_saves(db, owner)),
            }
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="Original world save index is unavailable") from None


class NativeTemporalMazeRequest(NativeLivingWorldRequest):
    """Optional local waypoint: no fictitious mandatory victory condition."""

    model_config = ConfigDict(extra="forbid")
    moves: list[str] = Field(default_factory=list, max_length=192)
    checkpoint_token: str | None = Field(
        default=None, strict=True, min_length=100, max_length=12000, pattern=r"^[A-Za-z0-9_.-]+$"
    )
    delta_x: StrictInt = Field(default=2, ge=-4, le=4)
    delta_y: StrictInt = Field(default=2, ge=-4, le=4)
    search_budget: StrictInt = Field(default=2500, ge=100, le=4000)
    horizon: StrictInt = Field(default=32, ge=1, le=48)
    radius: StrictInt = Field(default=2, ge=1, le=3)


@router.post("/native/production/worlds/maze/analyze")
def native_living_world_temporal_maze(
    body: NativeTemporalMazeRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_living_world import (
        initial_state,
        replay,
        describe,
    )
    from skeleton.ai.webcrawler.dragon_living_maze_solvers import (
        compare_solvers,
        changing_doors,
    )

    try:
        world = _dragon_living_world(body)
        if not world.shifting_routes:
            raise ValueError("only original mutable maze topologies have temporal planning")
        if body.delta_x == 0 and body.delta_y == 0:
            raise ValueError("optional moving-maze destination must require movement")
        if body.checkpoint_token is None:
            current = replay(world, tuple(body.moves))
        else:
            if body.moves:
                raise ValueError("supply either a signed checkpoint or a replay history")
            from skeleton.ai.webcrawler.dragon_living_world_checkpoint import open_checkpoint

            current = open_checkpoint(world, body.checkpoint_token, owner)
        goal = (current.realm, current.x + body.delta_x, current.y + body.delta_y)
        if abs(goal[1]) > 1_000_000 or abs(goal[2]) > 1_000_000:
            raise ValueError("original moving-maze search exceeds coordinates")
        evidence = compare_solvers(
            world, goal, starting_state=current, budget=body.search_budget, horizon=body.horizon
        )
        geography = changing_doors(world, realm=current.realm, x=current.x, y=current.y, radius=body.radius)
    except RuntimeError:
        raise HTTPException(
            status_code=503, detail="Signed original maze continuation is not configured"
        ) from None
    except PermissionError:
        raise HTTPException(
            status_code=403, detail="Changing-maze checkpoint is not owned by this user"
        ) from None
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Temporal maze goal, replay or route solver budget is invalid"
        ) from None
    return {
        "ok": True,
        "schema": "skeleton.ai.dragon.temporal_maze_analysis.v1",
        "current": describe(world, current),
        "target": {"realm": goal[0], "x": goal[1], "y": goal[2]},
        "solvers": evidence,
        "shifting_topology": geography,
        "scope": "two real optional-waypoint path solvers, not forced whole-world victory",
    }


class NativeCodexWorldRequest(BaseModel):
    """Exact versioned world identity; decimal strings, never a JS float."""

    model_config = ConfigDict(extra="forbid")
    index: str = Field(default="0", strict=True, min_length=1, max_length=600, pattern=r"^(0|[1-9][0-9]*)$")


class NativeCodexWorldEditRequest(NativeCodexWorldRequest):
    changes: dict[str, StrictInt] = Field(default_factory=dict, max_length=192)


class NativeCodexWorldPlayRequest(NativeCodexWorldRequest):
    actions: list[str] = Field(default_factory=list, max_length=96)


class NativeCodexWorldGatewayRequest(NativeCodexWorldRequest):
    domain: str = Field(default="topology", pattern=r"^[a-z_]{2,32}$")


class NativeCodexWorldPlatformRequest(NativeCodexWorldRequest):
    target: str = Field(default="game_boy", pattern=r"^[a-z0-9_]{2,48}$")
    chunks: StrictInt = Field(default=1, ge=1, le=4)


@router.get("/native/production/worlds/codex/capabilities")
def native_world_codex_capabilities(
    owner: str = Depends(_principal),
) -> dict:
    from skeleton.ai.webcrawler.dragon_world_codex import summary
    from skeleton.ai.webcrawler.dragon_native_targets import CATALOG

    return {
        "ok": True,
        "codex": summary(),
        "registered_native_targets": len(CATALOG),
        "claim": "1024-bit reversible world configuration capacity, "
        "not 128 finished simulation/physics engines or hardware ports",
    }


@router.post("/native/production/worlds/codex/inspect")
def native_world_codex_inspect(
    body: NativeCodexWorldRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from dataclasses import asdict
    from skeleton.ai.webcrawler.dragon_world_codex import unrank
    from skeleton.ai.webcrawler.dragon_world_codex_runtime import start, report

    try:
        source = unrank(body.index)
        return {"ok": True, "design": asdict(source), "game": report(source, start(source), detail=True)}
    except ValueError:
        raise HTTPException(status_code=422, detail="World Codex address is invalid or unsupported") from None


@router.post("/native/production/worlds/codex/edit")
def native_world_codex_edit(
    body: NativeCodexWorldEditRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from dataclasses import asdict
    from skeleton.ai.webcrawler.dragon_world_codex import edit

    try:
        edited = edit(body.index, body.changes)
        return {
            "ok": True,
            "new_decimal_index": edited.decimal_index,
            "updated": asdict(edited),
            "changed_axes": sorted(body.changes),
        }
    except ValueError:
        raise HTTPException(status_code=422, detail="Original Codex axis or level unsupported") from None


@router.post("/native/production/worlds/codex/impact")
def native_world_codex_impact(
    body: NativeCodexWorldEditRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    """Show observed design consequences before accepting an edited world ID.

    Only compares deterministic source-generated gameplay and native tile bytes;
    it does not pretend to have rendered a commercial 3D level or ROM binary.
    """
    from skeleton.ai.webcrawler.dragon_world_codex import (
        unrank, edit, DOMAIN_AXIS, EXTENSION_DOMAIN_AXIS,
    )
    from skeleton.ai.webcrawler.dragon_world_codex_runtime import (
        start, codex_cell, gate_catalog,
    )
    from skeleton.ai.webcrawler.dragon_codex_tiles import tile_pack

    try:
        old=unrank(body.index)
        new=edit(body.index, body.changes)
        old_state=start(old)
        new_state=start(new)
        before=codex_cell(old, old_state)
        after=codex_cell(new, new_state)
        old_gates=gate_catalog(old, old_state)
        new_gates=gate_catalog(new, new_state)
        original_tiles=tile_pack(old, "nes")
        edited_tiles=tile_pack(new, "nes")
        domains={**DOMAIN_AXIS,**EXTENSION_DOMAIN_AXIS}
        return {
            "ok": True,
            "source_index":old.decimal_index,
            "edited_index":new.decimal_index,
            "version":new.schema,
            "changed_axes":sorted(
                axis for axis,level in body.changes.items()
                if (old.values+old.extension_values)[
                    tuple(axis for names in domains.values() for axis in names).index(axis)
                ]!=level
            ),
            "affected_domains":[name for name,axes in domains.items()
                                if any(axis in body.changes for axis in axes)],
            "terrain": {
                "before":before["codex_terrain"],
                "after":after["codex_terrain"],
                "aerial_before":before.get("aerial_topology"),
                "aerial_after":after.get("aerial_topology"),
                "changed":before["codex_cell_digest"]!=after["codex_cell_digest"],
            },
            "traversal":{
                "before":old_gates,"after":new_gates,
                "additional_route_names":[
                    row["name"] for row in new_gates
                    if row["name"] not in {gate["name"] for gate in old_gates}
                ],
            },
            "tiles":{
                "target":"nes",
                "before_count":len(original_tiles.named_tiles),
                "after_count":len(edited_tiles.named_tiles),
                "changed":[name for name,h in zip(
                    edited_tiles.named_tiles,edited_tiles.artwork_hashes)
                    if name not in original_tiles.named_tiles or
                    original_tiles.artwork_hashes[
                        original_tiles.named_tiles.index(name)
                    ]!=h],
                "verified_roundtrip":edited_tiles.all_tile_roundtrips_verified,
                "hardware_binary_compiled":False,
            },
        }
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="World axis change or indexed gameplay design is unsupported",
        ) from None


@router.post("/native/production/worlds/codex/play")
def native_world_codex_play(
    body: NativeCodexWorldPlayRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_world_codex import unrank
    from skeleton.ai.webcrawler.dragon_world_codex_runtime import replay, report

    try:
        source = unrank(body.index)
        game = replay(source, tuple(body.actions))
        return {"ok": True, "replayed_actions": list(body.actions), "game": report(source, game)}
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Codex world choice is unavailable or blocked by an actual gate"
        ) from None


@router.post("/native/production/worlds/codex/unlock-witness")
def native_world_codex_unlock_witness(
    body: NativeCodexWorldGatewayRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_world_codex import unrank
    from skeleton.ai.webcrawler.dragon_world_codex_runtime import proof_of_access

    try:
        return {"ok": True, **proof_of_access(unrank(body.index), body.domain)}
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original world passage has no replayed access witness"
        ) from None


@router.post("/native/production/worlds/codex/compile-target")
def native_world_codex_compile_target(
    body: NativeCodexWorldPlatformRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_world_codex import unrank
    from skeleton.ai.webcrawler.dragon_codex_platforms import (
        content_pack,
        verify_content_pack,
    )

    try:
        source = unrank(body.index)
        package = content_pack(source, body.target, chunks=body.chunks)
        evidence = verify_content_pack(source, package)
        return {"ok": True, "package": package, "independent_verification": evidence}
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original world content could not fit registered platform profile"
        ) from None


@router.post("/native/production/worlds/codex/platforms")
def native_world_codex_platforms(
    body: NativeCodexWorldRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_world_codex import unrank
    from skeleton.ai.webcrawler.dragon_codex_platforms import target_preview

    try:
        return {"ok": True, **target_preview(unrank(body.index), limit=60)}
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original world codex platform discovery failed"
        ) from None


class NativeCodexStoryRequest(NativeCodexWorldRequest):
    decisions: list[str] = Field(default_factory=list, max_length=96)


@router.post("/native/production/worlds/codex/story")
def native_world_codex_story(
    body: NativeCodexStoryRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_world_codex import unrank
    from skeleton.ai.webcrawler.dragon_world_story_grammar import (
        replay_story,
        story_report,
    )

    try:
        source = unrank(body.index)
        narrative = replay_story(source, tuple(body.decisions))
        return {
            "ok": True,
            "actual_decisions": list(body.decisions),
            "original_story_world": jsonable_encoder(story_report(source, narrative)),
        }
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original narrative option locked by history, discovery or world time"
        ) from None


@router.post("/native/production/worlds/codex/native-desktop-source")
def native_world_codex_desktop_source(
    body: NativeCodexWorldRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from dataclasses import asdict
    from skeleton.ai.webcrawler.dragon_world_codex import unrank
    from skeleton.ai.webcrawler.dragon_codex_desktop import (
        emit_codex_c99,
        inspect_c99_source,
    )

    try:
        source = unrank(body.index)
        game = emit_codex_c99(source)
        return {
            "ok": True,
            "project": asdict(game),
            "independent_source_verification": inspect_c99_source(source, game),
            "execution_claim": "C99 host-platform playable source. "
            "No compiled binary, hardware run or third-party SDK claim.",
        }
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original source world cannot emit native C99 game safely"
        ) from None


class NativeCodexAccessRequest(NativeCodexWorldRequest):
    domain: str = Field(default="geology", pattern=r"^[a-z_]{2,32}$")
    actions: list[str] = Field(default_factory=list, max_length=96)


class NativeCodexAccessUnlockRequest(NativeCodexWorldRequest):
    gate_id: str = Field(default="access_elevation_tectonics", pattern=r"^access_[a-z_]{2,56}$")
    horizon: StrictInt = Field(default=96, ge=8, le=96)


@router.post("/native/production/worlds/codex/access-matrix")
def native_world_codex_access_matrix(
    body: NativeCodexAccessRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from dataclasses import asdict
    from skeleton.ai.webcrawler.dragon_world_codex import unrank
    from skeleton.ai.webcrawler.dragon_codex_access_matrix import (
        replay_access,
        available_gates,
    )

    try:
        source = unrank(body.index)
        current = replay_access(source, tuple(body.actions))
        statuses = available_gates(source, current, domain=body.domain)
        return {
            "ok": True,
            "schema": "skeleton.ai.dragon.access_matrix_preview.v1",
            "actually_played_actions": list(body.actions),
            "source_digest": source.codex_digest,
            "player_world_turn": current.world.player.base.turn,
            "player_position": [
                current.world.player.base.realm,
                current.world.player.base.x,
                current.world.player.base.y,
            ],
            "historical_era": current.world.era,
            "access_digest": current.access_digest,
            "optional_paths": [asdict(x) for x in statuses],
            "world_must_have_an_ending": False,
            "claim": "actual optional routes, not unconditional game solvability",
        }
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original seasonal/era route history or domain cannot replay"
        ) from None


@router.post("/native/production/worlds/codex/access-proof")
def native_world_codex_access_proof(
    body: NativeCodexAccessUnlockRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_world_codex import unrank
    from skeleton.ai.webcrawler.dragon_codex_access_matrix import attempt_unlock

    try:
        source = unrank(body.index)
        result = attempt_unlock(source, body.gate_id, horizon=body.horizon)
        return {"ok": True, **result}
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original optional game-world gate is not implemented"
        ) from None


class NativeCodexTileRequest(NativeCodexWorldRequest):
    target: str = Field(default="game_boy", pattern=r"^[a-z0-9_]{2,48}$")


@router.post("/native/production/worlds/codex/tiles")
def native_world_codex_tiles(
    body: NativeCodexTileRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from dataclasses import asdict
    from skeleton.ai.webcrawler.dragon_world_codex import unrank
    from skeleton.ai.webcrawler.dragon_codex_tiles import (
        tile_pack,
        verify_tile_pack,
    )

    try:
        source = unrank(body.index)
        art = tile_pack(source, body.target)
        verified = verify_tile_pack(source, art)
        return {
            "ok": True,
            "source": asdict(art),
            "independent_format_verification": verified,
            "visual_claim": "actual original 8x8 tile pixels and native "
            "GB/NES/SNES bitplanes where supported; not a compiled ROM",
        }
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original source world or native graphics format unsupported"
        ) from None


class NativeCodexBundleRequest(NativeCodexWorldRequest):
    target: str = Field(default="game_boy", pattern=r"^[a-z0-9_]{2,48}$")
    chunks: StrictInt = Field(default=1, ge=1, le=4)
    rights_attested: StrictBool = Field(default=False)


@router.post("/native/production/worlds/codex/source-bundle")
def native_world_codex_source_bundle(
    body: NativeCodexBundleRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from base64 import b64encode
    from dataclasses import asdict
    from skeleton.ai.webcrawler.dragon_world_codex import unrank
    from skeleton.ai.webcrawler.dragon_codex_bundle import (
        publish_codex_source,
        verify_codex_source,
    )

    try:
        source = unrank(body.index)
        product = publish_codex_source(
            source, body.target, chunks=body.chunks, rights_attested=body.rights_attested
        )
        independently = verify_codex_source(source, product, chunks=body.chunks)
    except PermissionError:
        raise HTTPException(
            status_code=403, detail="Source-game owner must explicitly attest original content rights"
        ) from None
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original game source bundle violates format or source integrity"
        ) from None
    metadata = asdict(product)
    metadata.pop("zip_bytes")
    filename = "dragon-original-codex-" + source.codex_digest[:12] + "-" + body.target + ".zip"
    return {
        "ok": True,
        "filename": filename,
        "source_bundle": metadata,
        "archive_base64": b64encode(product.zip_bytes).decode("ascii"),
        "independent_source_verification": independently,
        "scope": "reproducible original source art/gameplay, "
        "no precompiled console ROM or third-party SDK license",
    }


class NativeGenomicWorldRequest(BaseModel):
    """Arbitrary-precision design address is a DECIMAL STRING, never a float."""

    model_config = ConfigDict(extra="forbid")
    index: str = Field(default="0", strict=True, min_length=1, max_length=80, pattern=r"^(0|[1-9][0-9]*)$")


class NativeGenomicWorldPlayRequest(NativeGenomicWorldRequest):
    actions: list[str] = Field(default_factory=list, max_length=128)


class NativeGenomicWorldEditRequest(NativeGenomicWorldRequest):
    changes: dict[str, StrictInt] = Field(default_factory=dict, max_length=24)


class NativeGenomicPathRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path_index: str = Field(
        default="0", strict=True, min_length=1, max_length=100, pattern=r"^(0|[1-9][0-9]*)$"
    )


class NativeGenomicPathComposeRequest(NativeGenomicWorldRequest):
    """Compose sixteen actual in-world action choices without bigint JS math."""

    word: list[StrictInt] = Field(default_factory=lambda: [0] * 16, min_length=16, max_length=16)


@router.post("/native/production/worlds/genome/compose-path")
def native_genomic_world_compose_path(
    body: NativeGenomicPathComposeRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from dataclasses import asdict
    from skeleton.ai.webcrawler.dragon_genomic_paths import (
        rank_path,
        materialize_path,
        verify_path,
    )

    try:
        path_id = rank_path(body.index, tuple(body.word))
        program = materialize_path(path_id)
        checked = verify_path(program)
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original indexed game path contains invalid or non-playable actions"
        ) from None
    return {
        "ok": True,
        "exact_decimal_path_address": path_id,
        "playable_route": asdict(program),
        "verification": checked,
        "claim": "sixteen real independently replayed user-selected original actions",
    }


class NativeGenomicPathSampleRequest(NativeGenomicWorldRequest):
    limit: StrictInt = Field(default=4, ge=1, le=6)


@router.get("/native/production/worlds/genome/capabilities")
def native_genomic_world_capabilities(
    owner: str = Depends(_principal),
) -> dict:
    from skeleton.ai.webcrawler.dragon_world_genome import lattice_summary
    from skeleton.ai.webcrawler.dragon_genomic_paths import pathspace_summary

    return {
        "ok": True,
        "genomic_world_space": lattice_summary(),
        "real_choice_path_space": pathspace_summary(),
        "claim": "exact compositional address space; not a count of completed "
        "games, unique artistic expressions or reviewed game releases",
    }


@router.post("/native/production/worlds/genome/inspect")
def native_genomic_world_inspect(
    body: NativeGenomicWorldRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from dataclasses import asdict
    from skeleton.ai.webcrawler.dragon_world_genome import (
        unrank_genome_address,
    )
    from skeleton.ai.webcrawler.dragon_genomic_world import (
        initial_genomic_state,
        report,
    )

    try:
        addr = unrank_genome_address(body.index)
        now = initial_genomic_state(addr)
        snapshot = report(addr, now, radius=2)
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Unknown original world genome or noncanonical huge address"
        ) from None
    return {
        "ok": True,
        "source_address": asdict(addr),
        "actual_game_state": snapshot,
        "materialized_cells": len(snapshot["local_terrain"]),
        "goal_required": snapshot["has_mandatory_win"],
    }


@router.post("/native/production/worlds/genome/play")
def native_genomic_world_play(
    body: NativeGenomicWorldPlayRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_world_genome import unrank_genome_address
    from skeleton.ai.webcrawler.dragon_genomic_world import replay_genomic, report

    try:
        addr = unrank_genome_address(body.index)
        current = replay_genomic(addr, tuple(body.actions))
        actual = report(addr, current, radius=2)
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Real original world action history cannot be replayed"
        ) from None
    return {
        "ok": True,
        "replayed_actions": list(body.actions),
        "actual_game_state": actual,
        "final_history_digest": current.history_digest,
        "source_fingerprint": addr.genome_digest,
        "claim": "each action changes real original world mechanics; "
        "no mandatory win condition for endless worlds",
    }


@router.post("/native/production/worlds/genome/edit")
def native_genomic_world_edit(
    body: NativeGenomicWorldEditRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from dataclasses import asdict
    from skeleton.ai.webcrawler.dragon_world_genome import (
        edit_genome,
    )

    try:
        next_address = edit_genome(body.index, body.changes)
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Unknown world genome axis or out-of-range physical level"
        ) from None
    return {
        "ok": True,
        "updated_source": asdict(next_address),
        "reversible_decimal_address": next_address.decimal_index,
        "modified_actual_simulation_controls": sorted(body.changes),
    }


@router.post("/native/production/worlds/genome/path")
def native_genomic_world_path(
    body: NativeGenomicPathRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from dataclasses import asdict
    from skeleton.ai.webcrawler.dragon_genomic_paths import (
        materialize_path,
        verify_path,
    )

    try:
        action_program = materialize_path(body.path_index)
        verdict = verify_path(action_program)
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original large-address path has no verified physical gameplay"
        ) from None
    return {
        "ok": True,
        "source_path": asdict(action_program),
        "independent_verification": verdict,
    }


@router.post("/native/production/worlds/genome/sample-paths")
def native_genomic_world_sample_paths(
    body: NativeGenomicPathSampleRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_genomic_paths import sample_paths

    try:
        return {"ok": True, **sample_paths(body.index, limit=body.limit)}
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original world path sample is not validly replayable"
        ) from None


class NativeOriginalMechanicRequest(BaseModel):
    """Typed executable original game program: exact decimal, never float."""

    model_config = ConfigDict(extra="forbid")
    program_index: str = Field(default="0", min_length=1, max_length=20, pattern=r"^(0|[1-9][0-9]*)$")
    levels: list[StrictInt] | None = Field(default=None, min_length=32, max_length=32)
    parent_codex_index: str | None = Field(
        default=None, min_length=1, max_length=900, pattern=r"^(0|[1-9][0-9]*)$"
    )


class NativeOriginalMechanicPlayRequest(NativeOriginalMechanicRequest):
    moves: list[str] = Field(default_factory=list, max_length=128)


class NativeOriginalMechanicFusionRequest(NativeOriginalMechanicPlayRequest):
    """One bounded original-gameplay interaction page, at real current state."""

    offset: StrictInt = Field(default=0, ge=0, lt=1024)
    limit: StrictInt = Field(default=32, ge=1, le=64)


@router.post("/native/production/worlds/originals/interactions")
def native_original_mechanics_interactions(
    body: NativeOriginalMechanicFusionRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_original_mechanic_forge import (
        replay,
        interaction_catalog,
    )

    try:
        program = _original_mechanic_program(body)
        state = replay(program, tuple(body.moves))
        result = interaction_catalog(program, state, offset=body.offset, limit=body.limit)
        return {"ok": True, **result, "current_gameplay_digest": state.history_digest}
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original cross-mechanic synthesis needs earned, valid game-state actions"
        ) from None


class NativeOriginalMechanicCompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    first: str = Field(min_length=1, max_length=20, pattern=r"^(0|[1-9][0-9]*)$")
    second: str = Field(min_length=1, max_length=20, pattern=r"^(0|[1-9][0-9]*)$")


class NativeOriginalMechanicNucleusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    original_nucleus: StrictInt = Field(ge=0, lt=16_777_216)


class NativeOriginalCampaignRequest(NativeOriginalMechanicRequest):
    route_intent: StrictInt = Field(default=0, ge=0, le=15)
    branch_seed: StrictInt = Field(default=0, ge=0, le=0xFFFFFFFF)
    steps: StrictInt = Field(default=24, ge=1, le=128)


class NativeOriginalCampaignPortfolioRequest(NativeOriginalMechanicRequest):
    branch_seed: StrictInt = Field(default=0, ge=0, le=0xFFFFFFFF)
    count: StrictInt = Field(default=8, ge=1, le=16)
    steps: StrictInt = Field(default=24, ge=1, le=128)


def _original_mechanic_program(body: NativeOriginalMechanicRequest):
    from skeleton.ai.webcrawler.dragon_original_mechanic_forge import (
        make_program,
        program_from_levels,
    )

    if body.levels is not None:
        if body.program_index != "0":
            raise ValueError("exact numeric index cannot contradict 32 selected rule levels")
        return program_from_levels(tuple(body.levels), parent_codex_index=body.parent_codex_index)
    return make_program(body.program_index, parent_codex_index=body.parent_codex_index)


@router.get("/native/production/worlds/originals/catalog")
def native_original_mechanics_catalog(
    owner: str = Depends(_principal),
) -> dict:
    from skeleton.ai.webcrawler.dragon_original_mechanic_forge import (
        capabilities,
        MECHANICS,
    )
    from skeleton.ai.webcrawler.dragon_original_campaign_forge import ROUTE_INTENTS
    from skeleton.ai.webcrawler.dragon_original_prototype_factory import (
        structurally_qualified_capacity,
    )

    return {
        "ok": True,
        **capabilities(),
        "prototype_viability_capacity": structurally_qualified_capacity(),
        "mechanics": [
            {
                "id": row[0],
                "domain": row[1],
                "cost_resource": row[2],
                "reward_resource": row[3],
                "levels": [0, 1, 2, 3],
            }
            for row in MECHANICS
        ],
        "playable_route_intents": list(ROUTE_INTENTS),
    }


@router.post("/native/production/worlds/originals/preview")
def native_original_mechanics_preview(
    body: NativeOriginalMechanicRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from dataclasses import asdict
    from skeleton.ai.webcrawler.dragon_original_mechanic_forge import (
        initial,
        choices,
    )
    from skeleton.ai.webcrawler.dragon_original_campaign_forge import (
        demonstrate_mechanics,
    )

    try:
        program = _original_mechanic_program(body)
        state = initial(program)
        return {
            "ok": True,
            "program": asdict(program),
            "initial_game_state": jsonable_encoder(asdict(state)),
            "playable_actions": choices(program, state),
            "causal_gameplay_proofs": demonstrate_mechanics(program),
            "fixed_win_required": False,
            "prebuilt_finished_games": 0,
        }
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original game program or indexed codex configuration is invalid"
        ) from None


@router.post("/native/production/worlds/originals/play")
def native_original_mechanics_play(
    body: NativeOriginalMechanicPlayRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from dataclasses import asdict
    from skeleton.ai.webcrawler.dragon_original_mechanic_forge import (
        replay,
        choices,
    )

    try:
        program = _original_mechanic_program(body)
        state = replay(program, tuple(body.moves))
        return {
            "ok": True,
            "program_index": program.decimal_index,
            "source_digest": program.source_digest,
            "played_actions": list(body.moves),
            "current_game_state": jsonable_encoder(asdict(state)),
            "available_actions": choices(program, state),
            "playable_after_endings": True,
            "claim": "real original game-state choices, no mandatory world victory",
        }
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original game action is unavailable or has invalid replay evidence"
        ) from None


@router.post("/native/production/worlds/originals/compare")
def native_original_mechanics_difference(
    body: NativeOriginalMechanicCompareRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_original_mechanic_forge import (
        make_program,
        distinguish,
    )

    try:
        return {"ok": True, **distinguish(make_program(body.first), make_program(body.second))}
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Mechanically distinct original game programs were not verified"
        ) from None


@router.post("/native/production/worlds/originals/nucleus")
def native_original_mechanics_nucleus(
    body: NativeOriginalMechanicNucleusRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from dataclasses import asdict
    from skeleton.ai.webcrawler.dragon_original_mechanic_forge import (
        binary_nucleus,
        initial,
        choices,
    )

    program = binary_nucleus(body.original_nucleus)
    return {
        "ok": True,
        "original_nucleus": body.original_nucleus,
        "program": asdict(program),
        "real_initial_actions": choices(program, initial(program)),
        "number_of_finished_games_claimed": 0,
        "claim": "exact mechanically separable gameplay rules, not completed authored titles",
    }


@router.post("/native/production/worlds/originals/campaign")
def native_original_campaign_playthrough(
    body: NativeOriginalCampaignRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from dataclasses import asdict
    from skeleton.ai.webcrawler.dragon_original_campaign_forge import (
        compose_journey,
        verify_journey,
    )

    try:
        program = _original_mechanic_program(body)
        journey = compose_journey(
            program, route_intent=body.route_intent, branch_seed=body.branch_seed, steps=body.steps
        )
        return {
            "ok": True,
            "journey": asdict(journey),
            "verification": verify_journey(program, journey),
        }
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Selected original gameplay journey could not be executed"
        ) from None


@router.post("/native/production/worlds/originals/campaigns")
def native_original_campaign_portfolio(
    body: NativeOriginalCampaignPortfolioRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_original_campaign_forge import (
        sample_experiences,
    )

    try:
        return {
            "ok": True,
            **sample_experiences(
                _original_mechanic_program(body),
                seed=body.branch_seed,
                limit=body.count,
                steps=body.steps,
            ),
        }
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original alternative journeys lack replayed gameplay evidence"
        ) from None


class NativeOriginalPrototypeRequest(BaseModel):
    """Exact 32-mechanic original game candidate, never counted as publication."""

    model_config = ConfigDict(extra="forbid")
    original_nucleus: StrictInt = Field(default=0, ge=0, lt=4_294_967_296)
    branch_seed: StrictInt = Field(default=0, ge=0, le=0xFFFFFFFF)
    routes: StrictInt = Field(default=4, ge=1, le=12)
    steps: StrictInt = Field(default=16, ge=4, le=64)


class NativeOriginalPrototypeBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: StrictInt = Field(default=0, ge=0, lt=4_294_967_296)
    count: StrictInt = Field(default=4, ge=1, le=12)
    branch_seed: StrictInt = Field(default=0, ge=0, le=0xFFFFFFFF)
    routes: StrictInt = Field(default=2, ge=1, le=8)
    steps: StrictInt = Field(default=12, ge=4, le=48)


class NativeOriginalPrototypeCompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    first: StrictInt = Field(ge=0, lt=4_294_967_296)
    second: StrictInt = Field(ge=0, lt=4_294_967_296)


@router.post("/native/production/worlds/originals/prototype")
def native_original_game_prototype(
    body: NativeOriginalPrototypeRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from dataclasses import asdict
    from skeleton.ai.webcrawler.dragon_original_prototype_factory import (
        materialize,
        verify_prototype,
    )

    try:
        proposed = materialize(
            body.original_nucleus, branch_seed=body.branch_seed, routes=body.routes, steps=body.steps
        )
        verified = verify_prototype(proposed, branch_seed=body.branch_seed)
        return {"ok": True, "original_prototype": asdict(proposed), "verification": verified}
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original game prototype could not execute both real gameplay layers"
        ) from None


@router.post("/native/production/worlds/originals/prototypes")
def native_original_game_prototype_batch(
    body: NativeOriginalPrototypeBatchRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_original_prototype_factory import (
        sample_prototypes,
    )

    try:
        return {
            "ok": True,
            **sample_prototypes(
                start=body.start,
                count=body.count,
                branch_seed=body.branch_seed,
                routes=body.routes,
                steps=body.steps,
            ),
        }
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original prototype batch contains out-of-range or unplayable games"
        ) from None


@router.post("/native/production/worlds/originals/prototypes/compare")
def native_original_game_prototypes_difference(
    body: NativeOriginalPrototypeCompareRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_original_prototype_factory import (
        distinguish_prototypes,
    )

    try:
        return {"ok": True, **distinguish_prototypes(body.first, body.second)}
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Two original candidate game rulebooks need distinct valid indexes"
        ) from None


class NativeIndexedLivingDesignRequest(BaseModel):
    """One actual generated design and a replayable route, never bulk minting."""

    model_config = ConfigDict(extra="forbid")
    design_index: StrictInt = Field(default=0, ge=0, lt=5_000_000_000)
    route_slot: StrictInt = Field(default=0, ge=0, le=9)


@router.post("/native/production/worlds/indexed-design")
def native_living_world_indexed_design(
    body: NativeIndexedLivingDesignRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_living_world_lattice import (
        DESIGN_ADDRESS_COUNT,
        route_at_design_index,
    )

    if body.design_index >= DESIGN_ADDRESS_COUNT:
        raise HTTPException(
            status_code=422, detail="Original generator design index outside valid compositional lattice"
        )
    try:
        report = route_at_design_index(body.design_index, path_slot=body.route_slot)
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Requested original game address has no valid replayable route"
        ) from None
    return {"ok": True, **jsonable_encoder(report)}


class NativeAtlasWorldRequest(BaseModel):
    """Multi-region original world: bounded multi-maze compositional gameplay."""

    model_config = ConfigDict(extra="forbid")
    seed: StrictInt = Field(default=1977, ge=0, le=0xFFFFFFFF)
    regions: StrictInt = Field(default=4, ge=2, le=12)
    width: StrictInt = Field(default=6, ge=4, le=8)
    height: StrictInt = Field(default=6, ge=4, le=6)
    climate: str = Field(default="clear", pattern=r"^(clear|rain|windy|storm|snow|high_tide)$")
    challenge: str = Field(default="balanced", pattern=r"^(gentle|balanced|challenging|spicy)$")
    scenic_density: StrictInt = Field(default=60, ge=0, le=100)
    detour_density: StrictInt = Field(default=70, ge=0, le=100)
    secret_count: StrictInt = Field(default=2, ge=0, le=4)


class NativeAtlasPlayRequest(NativeAtlasWorldRequest):
    commands: list[str] = Field(default_factory=list, max_length=512)


def _original_route_atlas(body: NativeAtlasWorldRequest):
    from skeleton.ai.webcrawler.dragon_route_atlas import AtlasRequest, build_atlas

    return build_atlas(
        AtlasRequest(
            seed=body.seed,
            regions=body.regions,
            width=body.width,
            height=body.height,
            climate=body.climate,
            challenge=body.challenge,
            scenic_density=body.scenic_density,
            detour_density=body.detour_density,
            secret_count=body.secret_count,
        )
    )


@router.post("/native/production/routes/atlas/preview")
def native_world_atlas_preview(
    body: NativeAtlasWorldRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_route_atlas import (
        verify_atlas,
        atlas_report,
        play_atlas,
    )

    try:
        atlas = _original_route_atlas(body)
        result = verify_atlas(atlas)
        if not result["status"] == "hierarchical_completion_verified":
            raise ValueError("one original region failed world-scale game certification")
        current = play_atlas(atlas)
    except ValueError:
        raise HTTPException(
            status_code=422, detail="World-scale original route maze failed constructive completion"
        ) from None
    return {
        "ok": True,
        "schema": "skeleton.ai.dragon.original_world_atlas_preview.v1",
        "review": result,
        "atlas": atlas_report(atlas),
        "player": current,
        "native_claim": "independently native-source-capable regions, Python portal runtime",
        "physical_claim": "no finished single-binary multi-region console runtime",
    }


@router.post("/native/production/routes/atlas/play")
def native_world_atlas_play(
    body: NativeAtlasPlayRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_route_atlas import play_atlas

    try:
        atlas = _original_route_atlas(body)
        player = play_atlas(atlas, tuple(body.commands))
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original multi-region route action is invalid, locked or unfinishable"
        ) from None
    return {"ok": True, **player}


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
        raise HTTPException(
            status_code=422, detail="Original authored grid must be 12x10, safe and solver-proven"
        ) from None


@router.get("/native/production/puzzle/starter")
def native_production_puzzle_starter(
    stages: int = 1,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_native_puzzle_authoring import starter_authored_levels

    try:
        return {"ok": True, **starter_authored_levels(stages)}
    except ValueError:
        raise HTTPException(status_code=422, detail="Unsupported starter game stage count") from None


class NativeOriginalCampaignAnalysisRequest(BaseModel):
    """Pure original-game topology/challenge research, not a deployed game."""

    model_config = ConfigDict(extra="forbid")
    levels: list[NativeOriginalGrid] = Field(min_length=1, max_length=8)
    mode: str = Field(default="branching", pattern=r"^(linear|branching)$")
    challenge_profile: str = Field(default="balanced", pattern=r"^(gentle|balanced|challenging|spicy)$")
    route_budget: StrictInt = Field(default=2500, ge=500, le=8000)


@router.post("/native/production/puzzle/campaign/analyze")
def native_production_analyze_campaign(
    body: NativeOriginalCampaignAnalysisRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_native_puzzle_authoring import validate_authored_levels
    from skeleton.ai.webcrawler.dragon_native_multipath import analyse_routes, route_report
    from skeleton.ai.webcrawler.dragon_native_campaign_paths import design_campaign, graph_report
    from skeleton.ai.webcrawler.dragon_native_challenge_director import (
        make_challenge_plan,
        challenge_report,
    )

    try:
        campaign = validate_authored_levels(tuple(tuple(line for line in board) for board in body.levels))
        reports = tuple(
            route_report(
                analyse_routes(
                    original.rows,
                    max_routes=4,
                    expansion_cap=body.route_budget,
                )
            )
            for original in campaign.levels
        )
        chapters = design_campaign(
            len(campaign.levels),
            mode=body.mode,
            intensity=body.challenge_profile,
            stage_difficulty=tuple(x["difficulty_estimate"] for x in reports),
        )
        director = make_challenge_plan(
            reports,
            profile=body.challenge_profile,
            branching=body.mode == "branching" and len(campaign.levels) >= 3,
        )
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original campaign routes, stages or challenge goals could not be proven"
        ) from None
    return {
        "ok": True,
        "schema": "skeleton.ai.dragon.native_campaign_design_preview.v1",
        "original_campaign_digest": campaign.digest,
        "chapter_paths": jsonable_encoder(graph_report(chapters)),
        "challenge": challenge_report(director),
        "stages": [{"stage": index + 1, "routes": document} for index, document in enumerate(reports)],
        "claim": "solver-derived challenge and branching; no human player enjoyment certified",
    }


class NativePuzzleCurrentHintRequest(BaseModel):
    """Editor-only exact live hints: symbolic board data, never executable source."""

    model_config = ConfigDict(extra="forbid")
    rows: NativeOriginalGrid
    player: StrictInt = Field(ge=0, lt=120)
    crates: list[StrictInt] = Field(min_length=1, max_length=3)


class NativeRouteAnalysisRequest(BaseModel):
    """Small symbolic original game board; no third-party game extraction."""

    model_config = ConfigDict(extra="forbid")
    rows: NativeOriginalGrid
    max_routes: StrictInt = Field(default=4, ge=1, le=8)
    search_budget: StrictInt = Field(default=4000, ge=500, le=20000)


@router.post("/native/production/puzzle/multiple-routes")
def native_production_multiple_routes(
    body: NativeRouteAnalysisRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_native_multipath import analyse_routes, route_report

    try:
        routes = analyse_routes(
            tuple(body.rows),
            max_routes=body.max_routes,
            expansion_cap=body.search_budget,
        )
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Original puzzle board could not produce bounded proven route analysis"
        ) from None
    return {"ok": True, **route_report(routes)}


@router.post("/native/production/puzzle/current-hint")
def native_production_current_puzzle_hint(
    body: NativePuzzleCurrentHintRequest,
    owner: str = Depends(_native_source_editor),
) -> dict:
    from skeleton.ai.webcrawler.dragon_native_puzzle import solve_grid

    original = tuple(body.rows)
    try:
        moves, visited = solve_grid(
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
        raise HTTPException(
            status_code=422, detail="Unsupported target, genre or portable game controls"
        ) from None


@router.post("/native/production/source-bundle")
def native_production_source_bundle(
    body: NativeProductionSourceRequest,
    owner: str = Depends(_native_source_editor),
):
    """Authenticated, size-limited original game-source export; entirely in memory."""
    if not body.approved or not body.original_work_attested:
        raise HTTPException(
            status_code=403, detail="Explicit publication and original rights attestation required"
        )
    from skeleton.ai.webcrawler.dragon_native_production import build_source_bundle

    try:
        request = _make_native_production_request(body)
        payload, index = build_source_bundle(request, authorized=True)
    except (ValueError, PermissionError):
        raise HTTPException(
            status_code=422, detail="Unsupported source target, rights evidence or resource budget"
        ) from None
    return Response(
        content=payload,
        media_type="application/zip",
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
    value = os.environ.get("SKL_DRAGON_BUILD_SIGNING_KEY_HEX", "")
    try:
        key = bytes.fromhex(value)
    except ValueError:
        key = b""
    if len(key) < 32:
        raise HTTPException(status_code=503, detail="Dragon native build evidence signer unavailable")
    return key


@router.get("/native/evidence")
def native_build_evidence(owner: str = Depends(_principal)) -> dict:
    # Read-only product endpoint. A browser cannot mint compiler evidence,
    # submit invented ROM bytes, approve its own game or award progression XP.
    key = _build_signing_key()
    with _lab() as (lab, _):
        native = DragonNativePracticeLab(lab.db, lab)
        receipts = DragonBuildEvidence(lab.db, native, private_signing_key=key).history(
            owner, authorized=True
        )
        return {
            "ok": True,
            "receipts": [asdict(r) for r in receipts[-50:]],
            "claim_boundary": "ROM structural proof, not executed gameplay",
        }


def _curriculum(lab: DragonPracticeLab) -> DragonNativeCurriculum:
    native = DragonNativePracticeLab(lab.db, lab)
    configured = os.environ.get("SKL_DRAGON_BUILD_SIGNING_KEY_HEX", "").strip()
    evidence = (
        DragonBuildEvidence(lab.db, native, private_signing_key=_build_signing_key()) if configured else None
    )
    return DragonNativeCurriculum(native, evidence)


@router.get("/native/curriculum")
def native_curriculum(owner: str = Depends(_principal)) -> dict:
    with _lab() as (lab, _):
        result = _curriculum(lab).evaluate(owner, authorized=True)
        return {"ok": True, **curriculum_report(result)}


@router.post("/native/curriculum/generate")
def native_curriculum_generate(
    body: CurriculumGenerateRequest,
    owner: str = Depends(_principal),
) -> dict:
    if not body.approved:
        raise HTTPException(status_code=403, detail="Explicit native practice approval required")
    with _lab() as (lab, cycles):
        try:
            next_state, attempt = _curriculum(lab).generate_next(
                owner, authorized=True, consent=True, now=time.time()
            )
        except PermissionError:
            raise HTTPException(status_code=403, detail="Approved native lesson required") from None
        except ValueError:
            raise HTTPException(
                status_code=422, detail="No unlocked native exercise or resource budget"
            ) from None
        return {
            "ok": True,
            "created_native": asdict(attempt),
            "curriculum": curriculum_report(next_state),
            **{k: v for k, v in _snapshot(lab, cycles, owner).items() if k != "ok"},
        }


@router.post("/native/generate")
def generate_native(body: NativeGenerateRequest, owner: str = Depends(_principal)) -> dict:
    with _lab() as (lab, cycles):
        native = DragonNativePracticeLab(lab.db, lab)
        try:
            item = native.generate(
                owner,
                target_id=body.target_id,
                style=body.style,
                now=time.time(),
                authorized=True,
                consent=True,
            )
        except PermissionError:
            raise HTTPException(
                status_code=403, detail="Approved lessons or licensed SDK unavailable"
            ) from None
        except ValueError:
            raise HTTPException(status_code=422, detail="Native target or exercise not available") from None
        result = _snapshot(lab, cycles, owner)
        result["created_native"] = asdict(item)
        return result


@router.get("/native/{attempt_id}/archive")
def native_archive(
    attempt_id: str = URLPath(pattern=r"^[a-f0-9]{64}$"),
    owner: str = Depends(_principal),
):
    with _lab() as (lab, _):
        native = DragonNativePracticeLab(lab.db, lab)
        try:
            content, digest = native.archive(owner, attempt_id, authorized=True)
        except (LookupError, ValueError):
            raise HTTPException(status_code=404, detail="Native project unavailable") from None
        return Response(
            content=content,
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="dragon-native-' + attempt_id[:12] + '.zip"',
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "private, no-store",
                "X-Content-SHA256": digest,
            },
        )


@router.post("/practice/run")
def run_practice(body: RunPracticeRequest, owner: str = Depends(_principal)) -> dict:
    with _lab() as (lab, cycles):
        # An authenticated click is *not* permission to mint practice lessons.
        # The canonical crawler must have deposited review-approved lessons.
        attempts = lab.run_batch(
            owner, authorized=True, consent=True, now=time.time(), max_demos=body.max_demos
        )
        result = _snapshot(lab, cycles, owner)
        result["created"] = [asdict(a) for a in attempts]
        return result


@router.post("/practice/subscribe")
def subscribe_practice(body: SubscribeRequest, owner: str = Depends(_principal)) -> dict:
    if not body.approved:
        raise HTTPException(status_code=403, detail="Explicit practice approval is required")
    now = time.time()
    with _lab() as (lab, cycles):
        cycles.enable(
            owner,
            authorized=True,
            human_approved=True,
            now=now,
            expires_at=now + body.hours * 3600,
            interval_seconds=body.interval_seconds,
            max_ticks=body.max_ticks,
            demos_per_tick=body.demos_per_tick,
            generation_mode="curriculum" if body.adaptive else "native",
            native_target=body.native_target,
            native_style=body.native_style,
        )
        return _snapshot(lab, cycles, owner)


@router.post("/practice/stop")
def stop_practice(owner: str = Depends(_principal)) -> dict:
    with _lab() as (lab, cycles):
        cycles.disable(owner, authorized=True)
        return _snapshot(lab, cycles, owner)


@router.post("/practice/revoke")
def revoke_practice(owner: str = Depends(_principal)) -> dict:
    with _lab() as (lab, cycles):
        cycles.disable(owner, authorized=True)
        lab.revoke(owner, authorized=True)
        return _snapshot(lab, cycles, owner)


@router.get("/practice/{attempt_id}/artifact")
def practice_artifact(
    attempt_id: str = URLPath(pattern=r"^[a-f0-9]{64}$"),
    owner: str = Depends(_principal),
) -> dict:
    with _lab() as (lab, _):
        try:
            html = lab.artifact(owner, attempt_id, authorized=True)
        except (LookupError, ValueError):
            raise HTTPException(status_code=404, detail="Demo unavailable") from None
        # Never serve playable HTML with an application origin/cookie context.
        return {
            "ok": True,
            "attempt_id": attempt_id,
            "html": html,
            "sha256": sha256(html.encode("utf-8")).hexdigest(),
            "sandbox_required": True,
        }


# Compose Dragon delivery with the existing authenticated Academy authorities.
# Source creation is strictly opt-in; the library and resource ledger remain canonical.
from core.dragon_delivery_routes import register_delivery_routes as _register_delivery_routes

_register_delivery_routes(router, _principal, _lab, lambda: time.time())

# Reuse this authenticated Academy surface for consent-bound reference review.
from routes.dragon_knowledge import register_knowledge_routes as _register_knowledge_routes

_register_knowledge_routes(router)


class CrawlerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CrawlerCreateRequest(CrawlerRequest):
    idempotency_key: str = Field(min_length=1, max_length=128)
    seeds: list[str] = Field(min_length=1, max_length=16)
    title: str | None = Field(default=None, min_length=1, max_length=160)
    topics: list[str] = Field(default_factory=list, max_length=16)
    max_requests: int = Field(default=24, ge=1, le=128, strict=True)
    max_documents: int = Field(default=16, ge=1, le=64, strict=True)
    max_bytes: int = Field(default=8 * 1024 * 1024, ge=1024, le=32 * 1024 * 1024, strict=True)
    max_depth: int = Field(default=1, ge=0, le=3, strict=True)
    consent: bool = Field(strict=True)
    rights_acknowledged: bool = Field(strict=True)

    @model_validator(mode="after")
    def capture_authority(self):
        if self.consent is not True or self.rights_acknowledged is not True:
            raise ValueError("explicit capture consent and source-rights acknowledgement are required")
        if self.idempotency_key != self.idempotency_key.strip():
            raise ValueError("idempotency key must be normalized")
        if any(
            not isinstance(url, str) or not 1 <= len(url) <= 2048 or url != url.strip()
            for url in self.seeds
        ):
            raise ValueError("seed URLs must be bounded normalized strings")
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError("seed URLs must be distinct")
        if any(not topic or len(topic) > 80 or topic != topic.strip() for topic in self.topics):
            raise ValueError("topics must be bounded normalized strings")
        return self


class CrawlerWriteRequest(CrawlerRequest):
    idempotency_key: str = Field(min_length=1, max_length=128)
    expected_version: int = Field(ge=1, strict=True)

    @model_validator(mode="after")
    def normalized_operation(self):
        if self.idempotency_key != self.idempotency_key.strip():
            raise ValueError("idempotency key must be normalized")
        return self


class CrawlerRunRequest(CrawlerWriteRequest):
    max_steps: int = Field(default=4, ge=1, le=4, strict=True)


class CrawlerControlRequest(CrawlerWriteRequest):
    action: str = Field(pattern=r"^(pause|resume|cancel)$")


class CrawlerAutomationRequest(CrawlerWriteRequest):
    enabled: bool = Field(strict=True)
    max_slices: int = Field(default=16, ge=1, le=64, strict=True)
    max_seconds: int = Field(default=900, ge=15, le=3600, strict=True)


def _crawler_scope(user: dict | None = Depends(get_current_user)) -> dict[str, str]:
    owner = _principal(user)
    return {"tenant_id": (user.get("tenant_id") or user["email"]).strip(), "owner_id": owner}


def _crawler_write_scope(user: dict | None = Depends(get_current_user)) -> dict[str, str]:
    scope = _crawler_scope(user)
    if user.get("role") not in {"editor", "admin"}:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "crawler_write_denied",
                "message": "Editor permission is required to run crawler commands.",
            },
        )
    return scope


async def _crawler_result(operation):
    try:
        return await operation
    except CrawlerError as exc:
        raise HTTPException(
            status_code=exc.status, detail={"code": exc.code, "message": exc.message}
        ) from None
    except PermissionError:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "crawler_authority_denied",
                "message": "Crawler consent or source policy no longer permits this operation.",
            },
        ) from None
    except LookupError:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "crawler_not_found",
                "message": "Crawler session or captured source not found.",
            },
        ) from None
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "crawler_request_rejected",
                "message": "The canonical crawler rejected this request or runtime identity. Reload current state and check the source policy.",
            },
        ) from None
    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "crawler_storage_unavailable",
                "message": "Crawler storage is unavailable; retry the same operation key.",
            },
        ) from None


@router.get("/crawler/readiness")
async def crawler_readiness(owner: str = Depends(_principal)) -> dict:
    return await _crawler_result(crawler_application.readiness())


@router.get("/crawler/sessions")
async def crawler_sessions(
    cursor: str | None = Query(default=None, min_length=1, max_length=128),
    limit: int = Query(default=16, ge=1, le=32),
    scope: dict = Depends(_crawler_scope),
) -> dict:
    return await _crawler_result(crawler_application.list(scope, cursor=cursor, limit=limit))


@router.post("/crawler/sessions")
async def crawler_create(
    body: CrawlerCreateRequest, scope: dict = Depends(_crawler_write_scope)
) -> dict:
    return {
        "ok": True,
        "session": await _crawler_result(crawler_application.create(scope, body.model_dump())),
    }


@router.get("/crawler/sessions/{session_id}")
async def crawler_session(
    session_id: str = URLPath(min_length=1, max_length=128),
    scope: dict = Depends(_crawler_scope),
) -> dict:
    return {"ok": True, "session": await _crawler_result(crawler_application.get(scope, session_id))}


@router.post("/crawler/sessions/{session_id}/run")
async def crawler_run(
    body: CrawlerRunRequest,
    session_id: str = URLPath(min_length=1, max_length=128),
    scope: dict = Depends(_crawler_write_scope),
) -> dict:
    return await _crawler_result(crawler_application.run(scope, session_id, body.model_dump()))


@router.post("/crawler/sessions/{session_id}/control")
async def crawler_control(
    body: CrawlerControlRequest,
    session_id: str = URLPath(min_length=1, max_length=128),
    scope: dict = Depends(_crawler_scope),
    user: dict = Depends(get_current_user),
) -> dict:
    if body.action == "resume" and user.get("role") not in {"editor", "admin"}:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "crawler_write_denied",
                "message": "Editor permission is required to resume capture.",
            },
        )
    return {
        "ok": True,
        "session": await _crawler_result(
            crawler_application.control(scope, session_id, body.model_dump())
        ),
    }


@router.post("/crawler/sessions/{session_id}/automation")
async def crawler_automation(
    session_id: str,
    body: CrawlerAutomationRequest,
    scope: dict = Depends(_crawler_scope),
    user: dict = Depends(get_current_user),
) -> dict:
    return {
        "ok": True,
        "session": await _crawler_result(
            crawler_application.automation(scope, session_id, body.model_dump(), principal=user)
        ),
    }


@router.get("/crawler/sessions/{session_id}/search")
async def crawler_search(
    session_id: str,
    query: str = Query(min_length=1, max_length=512),
    limit: int = Query(default=8, ge=1, le=8),
    scope: dict = Depends(_crawler_scope),
) -> dict:
    return await _crawler_result(crawler_application.search(scope, session_id, query, limit=limit))


@router.get("/crawler/sessions/{session_id}/sources")
async def crawler_sources(
    session_id: str = URLPath(min_length=1, max_length=128),
    cursor: str | None = Query(default=None, min_length=1, max_length=128),
    limit: int = Query(default=16, ge=1, le=32),
    after_sequence: int | None = Query(default=None, ge=0),
    scope: dict = Depends(_crawler_scope),
) -> dict:
    return await _crawler_result(
        crawler_application.sources(
            scope, session_id, cursor=cursor, limit=limit, after_sequence=after_sequence
        )
    )


@router.delete("/crawler/sessions/{session_id}")
async def crawler_delete(
    body: CrawlerWriteRequest,
    session_id: str = URLPath(min_length=1, max_length=128),
    scope: dict = Depends(_crawler_scope),
) -> dict:
    return await _crawler_result(crawler_application.delete(scope, session_id, body.model_dump()))


@router.get("/crawler/sessions/{session_id}/events")
async def crawler_events(
    session_id: str = URLPath(min_length=1, max_length=128),
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=32, ge=1, le=64),
    scope: dict = Depends(_crawler_scope),
) -> dict:
    return await _crawler_result(
        crawler_application.events(scope, session_id, after_sequence=after_sequence, limit=limit)
    )


@router.get("/crawler/sessions/{session_id}/sources/{source_id}")
async def crawler_source(
    session_id: str = URLPath(min_length=1, max_length=128),
    source_id: str = URLPath(min_length=1, max_length=128),
    scope: dict = Depends(_crawler_scope),
) -> dict:
    return {
        "ok": True,
        "source": await _crawler_result(crawler_application.source(scope, session_id, source_id)),
    }


@router.get("/crawler/sessions/{session_id}/sources/{source_id}/text")
async def crawler_source_text(
    session_id: str = URLPath(min_length=1, max_length=128),
    source_id: str = URLPath(min_length=1, max_length=128),
    offset: int = Query(default=0, ge=0, le=24000),
    max_chars: int = Query(default=8000, ge=1, le=16000),
    expected_content_digest: str | None = Query(default=None, pattern=r"^[a-f0-9]{64}$"),
    scope: dict = Depends(_crawler_scope),
) -> dict:
    return await _crawler_result(
        crawler_application.source_chunk(
            scope,
            session_id,
            source_id,
            offset=offset,
            max_chars=max_chars,
            expected_content_digest=expected_content_digest,
        )
    )


@router.get("/crawler/sessions/{session_id}/sources/{source_id}/export")
async def crawler_source_export(
    session_id: str = URLPath(min_length=1, max_length=128),
    source_id: str = URLPath(min_length=1, max_length=128),
    format: str = Query(default="json", pattern=r"^(json|markdown)$"),
    scope: dict = Depends(_crawler_scope),
) -> dict:
    import json

    source = await _crawler_result(crawler_application.source(scope, session_id, source_id))
    if format == "json":
        content = json.dumps(source, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False)
        media_type, extension = "application/json", "json"
    else:
        # This is downloaded text, never application-origin rendered HTML.
        content = (
            "# Captured source\n\n"
            + source.get("title", "")
            + "\n\n"
            + str(source.get("canonical_url", ""))
            + "\n\nUnreviewed external material.\n\n"
            + source.get("text", "")
            + "\n"
        )
        media_type, extension = "text/markdown; charset=utf-8", "md"
    raw = content.encode("utf-8")
    if len(raw) > 2 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "crawler_export_limit",
                "message": "Captured source exceeds the export bound.",
            },
        )
    return {
        "ok": True,
        "session_id": session_id,
        "source_id": source_id,
        "filename": "captured-source-" + sha256(source_id.encode()).hexdigest()[:16] + "." + extension,
        "media_type": media_type,
        "content": content,
        "content_digest": sha256(raw).hexdigest(),
        "review_state": "unreviewed",
        "source_classification": "untrusted_external_material",
    }
