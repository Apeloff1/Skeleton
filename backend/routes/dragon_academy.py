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
from typing import Iterator

from fastapi import APIRouter, Depends, HTTPException, Path as URLPath, Query, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

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
    )


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
