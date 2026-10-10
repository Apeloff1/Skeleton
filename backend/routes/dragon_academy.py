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

from fastapi import APIRouter, Depends, HTTPException, Path as URLPath, Query, Response, Request
from pydantic import BaseModel, Field

from routes.gameforge_auth import get_current_user
from skeleton.ai.game_builder.dragon_review_store import DragonReviewStore
from skeleton.ai.webcrawler.dragon_execution_pool import DragonExecutionPool, DragonPoolCapacityError
from skeleton.ai.game_builder.reviewed_knowledge import ReviewedKnowledgeStore, KnowledgeError
from skeleton.ai.game_builder.dragon_wisdom_pyramid import DragonWisdomPyramid
from skeleton.ai.game_builder.dragon_wisdom_custody import DragonCustodyAnchor
from skeleton.ai.game_builder.dragon_wisdom_memory import DragonWisdomMemory
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
    return DragonExecutionPool.owner_key(tenant, email)

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
        "wisdom_review": _wisdom_snapshot(lab.db, owner),
    }

def _wisdom_snapshot(db: sqlite3.Connection, owner: str) -> dict | None:
    raw = os.environ.get("SKL_DRAGON_REVIEW_SIGNING_KEY_HEX", "")
    if not raw:
        return None
    try:
        key = bytes.fromhex(raw)
        store = DragonReviewStore(db, signing_key=key)
        return store.latest(owner, now=int(time.time()), authorized=True)
    except (ValueError, KeyError, TypeError):
        raise HTTPException(status_code=409, detail="Dragon advisory snapshot unavailable") from None

@router.get("/status")
def academy_status(owner: str = Depends(_principal)) -> dict:
    with _lab() as (lab,cycles):
        return _snapshot(lab,cycles,owner)

@router.get("/wisdom")
def academy_wisdom(owner: str = Depends(_principal)) -> dict:
    with _lab() as (lab,_):
        return {"ok": True, "snapshot": _wisdom_snapshot(lab.db, owner)}

@contextmanager
def _wisdom_library() -> Iterator[ReviewedKnowledgeStore]:
    # The reviewed source ledger is separately configured and authoritative.
    # Never silently create an empty substitute knowledgebase on a GET request.
    raw = os.environ.get("SKL_DRAGON_KNOWLEDGE_DB_PATH", "").strip()
    if not raw:
        raise HTTPException(status_code=503, detail="Dragon knowledge library not configured")
    path = Path(raw).expanduser()
    if not path.is_absolute() or not path.is_file():
        raise HTTPException(status_code=503, detail="Dragon knowledge library unavailable")
    try:
        with ReviewedKnowledgeStore(path) as library:
            yield library
    except (sqlite3.DatabaseError, KnowledgeError, ValueError, TypeError):
        raise HTTPException(status_code=409, detail="Dragon knowledge verification unavailable") from None


def _verify_wisdom_custody(library: ReviewedKnowledgeStore, owner: str) -> None:
    # Production setting is opt-in during migration: once enabled, no
    # unanchored, rolled-back or unverifiable snapshot may reach HOAG.
    if os.environ.get("SKL_DRAGON_WISDOM_CUSTODY_REQUIRED") != "1":
        return
    raw = os.environ.get("SKL_DRAGON_WISDOM_ANCHOR_KEY_HEX", "")
    directory = os.environ.get("SKL_DRAGON_WISDOM_ANCHOR_DIR", "")
    try:
        key = bytes.fromhex(raw)
    except ValueError:
        key = b""
    if len(key) < 32 or not directory:
        raise HTTPException(status_code=503, detail="Dragon independent custody signer unavailable")
    try:
        verified = DragonCustodyAnchor(directory, signing_key=key).verify(
            DragonWisdomPyramid(library), owner,
            authorized=True, require_current=True,
        )
        if not verified["anchored"]:
            raise ValueError("unanchored source review")
    except (ValueError, OSError, sqlite3.DatabaseError):
        raise HTTPException(status_code=409, detail="Dragon signed custody verification failed") from None


@router.get("/knowledge/hoag")
def knowledge_hoag(
    response: Response, owner: str = Depends(_principal),
) -> dict:
    # Render only currently valid, independently reviewed and human-approved
    # advisory claims. No source text or raw transcript is returned.
    response.headers["Cache-Control"] = "private, no-store"
    with _wisdom_library() as library:
        _verify_wisdom_custody(library, owner)
        return {"ok": True, **DragonWisdomPyramid(library).hoag_view(
            owner, now=int(time.time()), authorized=True,
            require_signed_approval=(
                os.environ.get("SKL_DRAGON_WISDOM_CUSTODY_REQUIRED") == "1"
            ),
        )}


@router.get("/knowledge/recrawls")
def knowledge_recrawls(
    response: Response, owner: str = Depends(_principal),
) -> dict:
    # Intents only. Browser has no research dispatch, approval or mint routes.
    response.headers["Cache-Control"] = "private, no-store"
    with _wisdom_library() as library:
        _verify_wisdom_custody(library, owner)
        orders = DragonWisdomPyramid(library).recrawl_queue(
            owner, now=int(time.time()), authorized=True, limit=32,
        )
        return {"ok": True, "orders": orders, "execution_authorized": False}


@router.get("/knowledge/memory")
def knowledge_memory(
    response: Response,
    mechanic: str | None = Query(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"),
    owner: str = Depends(_principal),
) -> dict:
    # Distilled memory index is advisory, separately synchronized by trusted
    # workers. Reads never reconcile/mint approvals or perform network I/O.
    response.headers["Cache-Control"] = "private, no-store"
    with _wisdom_library() as library:
        _verify_wisdom_custody(library, owner)
        memory = DragonWisdomMemory(DragonWisdomPyramid(library))
        return {"ok": True, **memory.read_current(
            owner, now=int(time.time()), authorized=True,
            mechanic=mechanic, limit=32,
        )}


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

@router.post("/practice/pulse")
def pulse_practice(request: Request, owner: str = Depends(_principal)) -> dict:
    """One consented scheduled slice; only the shared runtime can admit work."""
    from skeleton.ai.webcrawler.dragon_chunk_executor import DragonChunkExecutor
    factory = getattr(request.app.state, "dragon_practice_executor_factory", None)
    if not callable(factory):
        raise HTTPException(status_code=503, detail="Dragon resource runtime not configured")
    try:
        executor = factory(owner)
    except DragonPoolCapacityError:
        raise HTTPException(status_code=503, detail="Dragon resource capacity unavailable") from None
    if not isinstance(executor, DragonChunkExecutor) or executor.session.tenant != owner:
        raise HTTPException(status_code=503, detail="Dragon owner resource runtime unavailable")
    with _lab() as (lab, cycles):
        attempts, run = cycles.pulse_guarded(owner, authorized=True, executor=executor)
        result = _snapshot(lab, cycles, owner)
        result["created"] = [asdict(a) for a in attempts]
        result["resource_execution"] = asdict(run) if run is not None else {
            "completed_chunks": 0, "done": False, "reason": "subscription_not_due",
            "checkpoints": [], "effort": "defer",
        }
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


class DeliveryBriefRequest(BaseModel):
    model_config = {"extra": "forbid"}
    design: dict = Field(max_length=13)
    query: str = Field(min_length=1, max_length=300)


class DeliveryGenerateRequest(DeliveryBriefRequest):
    approved: bool = Field(default=False, strict=True)
    plan_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    prepared_at: int = Field(ge=0, le=4_102_444_800, strict=True)
    request_id: str = Field(pattern=r"^[A-Za-z0-9_-]{16,80}$")


def _delivery(library):
    from skeleton.ai.game_builder.dragon_almanacs import DragonAlmanacs
    from skeleton.ai.game_builder.dragon_delivery import DragonDelivery
    return DragonDelivery(DragonAlmanacs(library))


@router.get("/delivery/overview")
def delivery_overview(request: Request, response: Response,
                      owner: str = Depends(_principal)) -> dict:
    response.headers["Cache-Control"] = "private, no-store"
    with _wisdom_library() as library:
        delivery = _delivery(library)
        library.db.execute("BEGIN")
        try:
            _verify_wisdom_custody(library, owner)
            result = delivery.overview(owner, now=int(time.time()), authorized=True)
        finally:
            library.db.execute("ROLLBACK")
    result["resource_runtime_ready"] = isinstance(getattr(request.app.state, "dragon_execution_pool", None), DragonExecutionPool)
    try:
        _database_path()
        result["practice_storage_ready"] = True
    except HTTPException:
        result["practice_storage_ready"] = False
    return {"ok": True, **result}


@router.get("/delivery/knowledge")
def delivery_knowledge(response: Response,
                       query: str = Query(min_length=1, max_length=300),
                       owner: str = Depends(_principal)) -> dict:
    response.headers["Cache-Control"] = "private, no-store"
    with _wisdom_library() as library:
        delivery = _delivery(library)
        library.db.execute("BEGIN")
        try:
            _verify_wisdom_custody(library, owner)
            return {"ok": True, **delivery.search(owner, query, now=int(time.time()), authorized=True)}
        finally:
            library.db.execute("ROLLBACK")


@router.get("/delivery/almanacs")
def delivery_almanacs(response: Response, offset: int = Query(default=0, ge=0, le=100000),
                      owner: str = Depends(_principal)) -> dict:
    response.headers["Cache-Control"] = "private, no-store"
    with _wisdom_library() as library:
        delivery = _delivery(library)
        _verify_wisdom_custody(library, owner)
        return {"ok": True, **delivery.almanacs.report(owner, authorized=True, limit=32, offset=offset)}


@router.post("/delivery/brief")
def delivery_brief(body: DeliveryBriefRequest, response: Response,
                   owner: str = Depends(_principal)) -> dict:
    from skeleton.ai.webcrawler.dragon_game_design import parse_design
    response.headers["Cache-Control"] = "private, no-store"
    try:
        design = parse_design(body.design)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid native game design") from None
    with _wisdom_library() as library:
        delivery = _delivery(library)
        library.db.execute("BEGIN")
        try:
            _verify_wisdom_custody(library, owner)
            return {"ok": True, **delivery.brief(owner, design, body.query,
                        now=int(time.time()), authorized=True)}
        finally:
            library.db.execute("ROLLBACK")


@router.post("/delivery/generate")
def delivery_generate(body: DeliveryGenerateRequest, request: Request, response: Response,
                      owner: str = Depends(_principal)) -> dict:
    from skeleton.ai.webcrawler.dragon_game_design import parse_design
    from skeleton.ai.webcrawler.dragon_native_projects import digest
    from skeleton.ai.webcrawler.dragon_chunk_executor import DragonChunkExecutor, ChunkResult
    from skeleton.ai.webcrawler.dragon_resource_session import SessionTask
    from skeleton.ai.game_builder.resource_governor import ResourceDelta
    response.headers["Cache-Control"] = "private, no-store"
    if body.approved is not True:
        raise HTTPException(status_code=403, detail="Confirm this cited design before generating source")
    try:
        design = parse_design(body.design)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid native game design") from None
    pool = getattr(request.app.state, "dragon_execution_pool", None)
    if not isinstance(pool, DragonExecutionPool):
        raise HTTPException(status_code=503, detail="Shared Dragon resource runtime is not configured")
    try:
        executor = pool.executor(owner)
    except DragonPoolCapacityError:
        raise HTTPException(status_code=503, detail="Dragon resource capacity unavailable") from None
    if not isinstance(executor, DragonChunkExecutor) or executor.session.tenant != owner:
        raise HTTPException(status_code=503, detail="Owner-bound resource runtime unavailable")
    created = []
    learning = []
    with _wisdom_library() as library:
        delivery = _delivery(library)
        with _lab() as (lab, cycles):
            native = DragonNativePracticeLab(lab.db, lab)
            def generate(plan, stop):
                if stop():
                    return ChunkResult(False, "delivery:deferred", ResourceDelta())
                # Hold the current knowledge revision through artifact commit.
                # No source update or revocation can race this bounded operation.
                library.db.execute("BEGIN IMMEDIATE")
                try:
                    _verify_wisdom_custody(library, owner)
                    now = int(time.time())
                    brief = delivery.brief(owner, design, body.query, now=now,
                                prepared_at=body.prepared_at, authorized=True)
                    if brief["plan_digest"] != body.plan_digest or not brief["ready_for_source_generation"]:
                        raise HTTPException(status_code=409, detail="Knowledge or design changed; prepare a fresh brief")
                    previous = lab.db.execute("SELECT 1 FROM dragon_native_game_attempts WHERE owner=? AND attempt_id=?",
                        (owner, digest([owner, "delivery", body.request_id]))).fetchone()
                    item = native.generate(owner, target_id=design.target, style=design.genre,
                        now=now, authorized=True, consent=True, design=design,
                        source_context=brief, request_id=body.request_id)
                    created.append(item)
                    # Artifact commit is authoritative. A projection failure
                    # cannot turn a committed source project into a failed build.
                    try:
                        learning.append(delivery.record_project_learning(owner, native, item.attempt_id, authorized=True))
                        library.db.execute("COMMIT")
                    except (ValueError, LookupError, sqlite3.DatabaseError):
                        if library.db.in_transaction:
                            library.db.execute("ROLLBACK")
                    return ChunkResult(True, "delivery:" + item.attempt_id,
                        ResourceDelta(artifact_bytes=0 if previous else lab.policy.max_artifact_bytes))
                finally:
                    if library.db.in_transaction:
                        library.db.execute("ROLLBACK")
            try:
                run = executor.run(SessionTask("delivery:" + body.request_id, "user", 8 * 1024**2, 1, io_tokens=1),
                    generate, authorized=True, consent=True,
                    reserved_usage=ResourceDelta(artifact_bytes=lab.policy.max_artifact_bytes))
            except PermissionError:
                raise HTTPException(status_code=403, detail="Current approved practice lesson required") from None
            except ValueError:
                raise HTTPException(status_code=409, detail="Delivery context expired, changed, or exceeded its practice budget") from None
            if not created:
                return {"ok": True, "created_native": None, "resource_execution": asdict(run),
                        "retryable": True, "delivery_state": "deferred"}
            return {**_snapshot(lab, cycles, owner), "created_native": asdict(created[0]),
                    "resource_execution": asdict(run), "delivery_state": "source_generated",
                    "plan_digest": body.plan_digest, "compiled": False, "gameplay_verified": False,
                    "project_learning": learning[0] if learning else None,
                    "learning_recovery_required": not bool(learning)}


@router.get("/delivery/almanacs/{topic_id}/learning")
def delivery_learning(response: Response,
                      topic_id: str = URLPath(pattern=r"^topic-[a-f0-9]{64}$"),
                      owner: str = Depends(_principal)) -> dict:
    response.headers["Cache-Control"] = "private, no-store"
    with _wisdom_library() as library:
        delivery = _delivery(library)
        _verify_wisdom_custody(library, owner)
        return {"ok": True, **delivery.almanacs.learning_view(owner, topic_id, authorized=True, limit=32)}


@router.post("/delivery/{attempt_id}/learning")
def recover_delivery_learning(response: Response,
                              attempt_id: str = URLPath(pattern=r"^[a-f0-9]{64}$"),
                              owner: str = Depends(_principal)) -> dict:
    # Reconcile a committed artifact after a crash between the two existing
    # stores; this cannot generate source or grant memory/training authority.
    response.headers["Cache-Control"] = "private, no-store"
    with _wisdom_library() as library:
        delivery = _delivery(library)
        with _lab() as (lab, _):
            native = DragonNativePracticeLab(lab.db, lab)
            library.db.execute("BEGIN IMMEDIATE")
            try:
                _verify_wisdom_custody(library, owner)
                result = delivery.record_project_learning(owner, native, attempt_id, authorized=True)
                library.db.execute("COMMIT")
                return {"ok": True, "project_learning": result, "new_source_generated": False}
            except LookupError:
                raise HTTPException(status_code=404, detail="Native project unavailable") from None
            finally:
                if library.db.in_transaction:
                    library.db.execute("ROLLBACK")
