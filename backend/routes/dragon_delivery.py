"""Authenticated, fail-closed Dragon knowledge-to-design delivery projections.

Uses the canonical reviewed source/Almanakk store. These endpoints do not
execute a compiler, grant training rights, mutate review status, or claim a
native build. Source generation requires a separately admitted resource lane.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Iterator
import os
import re
import sqlite3
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from routes.dragon_academy import _principal, _native_source_editor
from skeleton.ai.game_builder.dragon_almanacs import DragonAlmanacs
from skeleton.ai.game_builder.dragon_delivery import DragonDelivery
from skeleton.ai.game_builder.reviewed_knowledge import ReviewedKnowledgeStore
from skeleton.ai.webcrawler.dragon_game_design import parse_design
from skeleton.ai.webcrawler.dragon_execution_pool import DragonExecutionPool

router = APIRouter(prefix="/api/dragon-academy/delivery", tags=["Dragon Delivery"])
_TOPIC = re.compile(r"[a-f0-9]{64}\Z")
_MAX_CLOCK = 4_102_444_800


class DeliveryBriefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    design: dict[str, object]
    query: str = Field(min_length=1, max_length=300)


def _clock() -> int:
    now = int(time.time())
    if not 0 <= now <= _MAX_CLOCK:
        raise HTTPException(status_code=503, detail="Current knowledge clock unavailable")
    return now


def _knowledge_path() -> Path:
    raw = os.environ.get("SKL_DRAGON_KNOWLEDGE_DB_PATH", "").strip()
    if not raw:
        raise HTTPException(status_code=503, detail="Dragon knowledge database not configured")
    path = Path(raw).expanduser()
    if (not path.is_absolute() or path.is_symlink() or not path.is_file()
            or not path.parent.is_dir()):
        raise HTTPException(status_code=503, detail="Dragon knowledge database unavailable")
    return path


@contextmanager
def _delivery() -> Iterator[DragonDelivery]:
    """Open knowledge storage without misclassifying failures in the caller.

    Exception handling must cover only acquiring the reviewed-knowledge
    connection. The caller may use a separate native-practice SQLite database,
    whose errors must be handled by that plane rather than relabeled as a
    reviewed-knowledge outage.
    """
    path = _knowledge_path()
    with ExitStack() as stack:
        try:
            library = stack.enter_context(ReviewedKnowledgeStore(path))
        except (sqlite3.DatabaseError, OSError):
            raise HTTPException(
                status_code=503,
                detail="Dragon knowledge storage unavailable",
            ) from None
        yield DragonDelivery(DragonAlmanacs(library))


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Vary"] = "Authorization"


def _project(work) -> dict:
    try:
        return {"ok": True, **work()}
    except HTTPException:
        raise
    except (ValueError, TypeError, LookupError, PermissionError):
        raise HTTPException(status_code=422, detail="Canonical delivery evidence or request is invalid") from None


@router.get("/overview")
def delivery_overview(request: Request, response: Response,
                      owner: str = Depends(_principal)) -> dict:
    _private(response)
    with _delivery() as delivery:
        result = _project(lambda: delivery.overview(owner, now=_clock(), authorized=True))
    pool = getattr(request.app.state, "dragon_execution_pool", None)
    raw = os.environ.get("SKL_DRAGON_PRACTICE_DB_PATH", "").strip()
    path = Path(raw).expanduser() if raw else None
    result["practice_storage_ready"] = bool(
        path and path.is_absolute() and not path.is_symlink() and path.is_file()
    )
    # Native source emission is gated by the existing shared resource pool;
    # this is not a claim of a compiled artifact or authorized release.
    result["resource_runtime_ready"] = isinstance(pool, DragonExecutionPool)
    result["resource_runtime_configured"] = isinstance(pool, DragonExecutionPool)
    result["generation_available"] = isinstance(pool, DragonExecutionPool)
    return result


@router.get("/knowledge")
def delivery_knowledge(response: Response, query: str = Query(min_length=1, max_length=300),
                       owner: str = Depends(_principal)) -> dict:
    _private(response)
    with _delivery() as delivery:
        return _project(lambda: delivery.search(owner, query, now=_clock(),
                                                 authorized=True, limit=12))


@router.get("/almanacs")
def delivery_almanacs(response: Response, offset: int = Query(default=0, ge=0, le=100000),
                      owner: str = Depends(_principal)) -> dict:
    _private(response)
    with _delivery() as delivery:
        return _project(lambda: delivery.almanacs.report(
            owner, authorized=True, limit=32, offset=offset
        ))


@router.get("/almanacs/{topic}/learning")
def delivery_learning(topic: str, response: Response,
                      owner: str = Depends(_principal)) -> dict:
    _private(response)
    if not _TOPIC.fullmatch(topic):
        raise HTTPException(status_code=422, detail="Invalid Almanakk topic identity")
    with _delivery() as delivery:
        return _project(lambda: delivery.almanacs.learning_view(
            owner, topic, authorized=True, limit=100
        ))


@router.post("/brief")
def delivery_brief(body: DeliveryBriefRequest, response: Response,
                   owner: str = Depends(_principal)) -> dict:
    _private(response)
    try:
        design = parse_design(body.design)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Unsupported native design controls") from None
    with _delivery() as delivery:
        return _project(lambda: delivery.brief(
            owner, design, body.query, now=_clock(), authorized=True
        ))


class DeliveryGenerateRequest(DeliveryBriefRequest):
    approved: bool
    plan_digest: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    prepared_at: int = Field(ge=0, le=4_102_444_800)
    request_id: str = Field(min_length=16, max_length=80, pattern=r"^[A-Za-z0-9_-]{16,80}$")


def _canonical_brief(delivery: DragonDelivery, owner: str,
                     body: DeliveryGenerateRequest) -> tuple[object, dict]:
    try:
        design = parse_design(body.design)
        brief = delivery.brief(owner, design, body.query, now=_clock(),
                               authorized=True, prepared_at=body.prepared_at)
    except (ValueError, TypeError, LookupError, StopIteration):
        raise HTTPException(status_code=409,
                            detail="Delivery evidence or design has changed") from None
    if (brief["plan_digest"] != body.plan_digest
            or not brief["ready_for_source_generation"]):
        raise HTTPException(status_code=409,
                            detail="Delivery brief is stale or cannot be admitted")
    return design, brief


def _existing_delivery(native, owner: str, request_id: str):
    from skeleton.ai.webcrawler.dragon_native_projects import digest
    attempt_id = digest([owner, "delivery", request_id])
    try:
        native.project(owner, attempt_id, authorized=True)
    except LookupError:
        return None
    return attempt_id


@router.post("/generate")
def delivery_generate(body: DeliveryGenerateRequest, request: Request,
                      response: Response,
                      owner: str = Depends(_native_source_editor)) -> dict:
    """Generate an original SOURCE project only after fresh reviewed evidence.

    A shared owner scheduler reserves resources before durable generation;
    retries read the prior artifact without another resource charge.
    """
    from dataclasses import asdict
    from routes.dragon_academy import _lab
    from skeleton.ai.game_builder.resource_governor import ResourceDelta, ResourceLimitError
    from skeleton.ai.webcrawler.dragon_chunk_executor import ChunkResult
    from skeleton.ai.webcrawler.dragon_execution_pool import DragonPoolCapacityError
    from skeleton.ai.webcrawler.dragon_resource_session import SessionTask
    from skeleton.ai.webcrawler.dragon_native_practice import DragonNativePracticeLab

    _private(response)
    if body.approved is not True:
        raise HTTPException(status_code=403, detail="Explicit native-source consent required")
    pool = getattr(request.app.state, "dragon_execution_pool", None)
    if not isinstance(pool, DragonExecutionPool):
        raise HTTPException(status_code=503,
                            detail="Shared Dragon resource runtime not configured")
    with _delivery() as delivery:
        design, brief = _canonical_brief(delivery, owner, body)
        with _lab() as (practice, _):
            native = DragonNativePracticeLab(practice.db, practice)
            stable = _existing_delivery(native, owner, body.request_id)
            try:
                if stable is not None:
                    # Re-check the exact stored owner-bound brief on every replay.
                    attempt = native.generate(
                        owner, target_id=design.target, style=design.genre,
                        now=time.time(), authorized=True, consent=True,
                        design=design, source_context=brief,
                        request_id=body.request_id,
                    )
                    execution = {"done": True, "reason": "durable_replay",
                                 "completed_chunks": 0}
                else:
                    worker = pool.executor(owner)
                    task = SessionTask(
                        task_id="delivery-" + body.request_id, lane="user",
                        memory_bytes=8 * 1024 * 1024, cpu_units=1, io_tokens=1,
                    )
                    reserved = ResourceDelta(artifact_bytes=250000)

                    def generate_source(plan, should_stop):
                        if should_stop():
                            raise ValueError("Native source generation stopped before admission")
                        generated = native.generate(
                            owner, target_id=design.target, style=design.genre,
                            now=time.time(), authorized=True, consent=True,
                            design=design, source_context=brief,
                            request_id=body.request_id,
                        )
                        project = native.project(owner, generated.attempt_id,
                                                 authorized=True)
                        from json import dumps
                        usage = len(dumps(project, sort_keys=True).encode("utf-8"))
                        return ChunkResult(True, generated.attempt_id,
                                           ResourceDelta(artifact_bytes=usage))

                    run = worker.run(task, generate_source, authorized=True,
                                     consent=True, max_chunks=1,
                                     reserved_usage=reserved)
                    if not run.done:
                        return {"ok": True, "delivery_state": "deferred",
                                "plan_digest": brief["plan_digest"],
                                "created_native": None,
                                "resource_execution": asdict(run),
                                "compiled": False, "gameplay_verified": False,
                                "release_authorized": False,
                                "training_authorized": False}
                    attempt_id = run.checkpoints[-1]
                    attempt = next((item for item in native.list(owner, authorized=True)
                                    if item.attempt_id == attempt_id), None)
                    if attempt is None:
                        raise HTTPException(status_code=503,
                                            detail="Native source receipt not recoverable")
                    execution = asdict(run)
            except PermissionError:
                raise HTTPException(status_code=403,
                                    detail="Approved native practice lesson required") from None
            except ValueError:
                raise HTTPException(status_code=409,
                                    detail="Native source request conflicts with durable evidence or quota") from None
            except (sqlite3.DatabaseError, OSError):
                raise HTTPException(status_code=503, detail="Native practice storage unavailable") from None
            except (ResourceLimitError, DragonPoolCapacityError):
                raise HTTPException(status_code=503, detail="Dragon source generation capacity exhausted") from None

            learning = None
            recovery = False
            try:
                learning = delivery.record_project_learning(
                    owner, native, attempt.attempt_id, authorized=True)
            except (ValueError, LookupError, OSError, sqlite3.DatabaseError):
                recovery = True
            return {"ok": True, "delivery_state": "source_generated",
                    "created_native": asdict(attempt),
                    "resource_execution": execution,
                    "plan_digest": brief["plan_digest"],
                    "project_learning": learning,
                    "learning_recovery_required": recovery,
                    "compiled": False, "gameplay_verified": False,
                    "release_authorized": False, "training_authorized": False}


@router.post("/{attempt_id}/learning")
def recover_delivery_learning(attempt_id: str, response: Response,
                              owner: str = Depends(_native_source_editor)) -> dict:
    """Re-project a committed source artifact, never generate a second one."""
    from routes.dragon_academy import _lab
    from skeleton.ai.webcrawler.dragon_native_practice import DragonNativePracticeLab
    _private(response)
    if not _TOPIC.fullmatch(attempt_id):
        raise HTTPException(status_code=422, detail="Invalid artifact identity")
    with _delivery() as delivery:
        with _lab() as (practice, _):
            native = DragonNativePracticeLab(practice.db, practice)
            try:
                result = delivery.record_project_learning(owner, native,
                                                          attempt_id, authorized=True)
            except LookupError:
                raise HTTPException(status_code=404, detail="Native source not found") from None
            except (ValueError, sqlite3.DatabaseError, OSError):
                raise HTTPException(status_code=409,
                                    detail="Source lineage cannot be reconciled") from None
    return {"ok": True, "new_source_generated": False,
            "project_learning": result,
            "training_authorized": False, "release_authorized": False}
