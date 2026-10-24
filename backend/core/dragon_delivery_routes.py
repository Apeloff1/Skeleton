"""Governed owner-bound Dragon knowledge-to-native HTTP composition.

No independent knowledge database, provider, rights decision, scheduler, or
binary compiler is created. Only the configured canonical authorities are used.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import asdict
import json
import os
from pathlib import Path
import sqlite3
from typing import Callable, Iterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from skeleton.ai.game_builder.dragon_almanacs import DragonAlmanacs
from skeleton.ai.game_builder.dragon_delivery import DragonDelivery
from skeleton.ai.game_builder.reviewed_knowledge import ReviewedKnowledgeStore
from skeleton.ai.game_builder.resource_governor import ResourceDelta, ResourceLimitError
from skeleton.ai.webcrawler.dragon_chunk_executor import ChunkResult
from skeleton.ai.webcrawler.dragon_execution_pool import DragonExecutionPool, DragonPoolCapacityError
from skeleton.ai.webcrawler.dragon_game_design import parse_design
from skeleton.ai.webcrawler.dragon_native_practice import DragonNativePracticeLab
from skeleton.ai.webcrawler.dragon_native_projects import digest
from skeleton.ai.webcrawler.dragon_resource_session import SessionTask


class DeliveryBriefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    design: dict[str, object]
    query: str = Field(min_length=1, max_length=300)


class DeliveryGenerateRequest(DeliveryBriefRequest):
    approved: StrictBool
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    prepared_at: StrictInt = Field(ge=0, le=4_102_444_800)
    request_id: str = Field(pattern=r"^[A-Za-z0-9_-]{16,80}$")


@contextmanager
def _reviewed_delivery() -> Iterator[DragonDelivery]:
    configured = os.environ.get("SKL_DRAGON_KNOWLEDGE_DB_PATH", "").strip()
    if not configured:
        raise HTTPException(status_code=503, detail="Reviewed knowledge storage not configured")
    path = Path(configured).expanduser()
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise HTTPException(status_code=503, detail="Reviewed knowledge storage unavailable")
    # Database acquisition is the only operation whose failure belongs to the
    # reviewed-knowledge store. Do not catch native practice/worker errors
    # raised by the caller through the yielded context.
    with ExitStack() as stack:
        try:
            library = stack.enter_context(ReviewedKnowledgeStore(path))
        except (sqlite3.DatabaseError, OSError):
            raise HTTPException(
                status_code=503, detail="Reviewed knowledge storage unavailable"
            ) from None
        yield DragonDelivery(DragonAlmanacs(library))


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail="Owner approval or reviewed practice unavailable")
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail="Native source record not found")
    if isinstance(exc, (sqlite3.DatabaseError, OSError)):
        return HTTPException(status_code=503, detail="Durable native source storage unavailable")
    if isinstance(exc, (TypeError, ValueError)):
        return HTTPException(status_code=422, detail="Invalid native design or evidence")
    return HTTPException(status_code=503, detail="Dragon delivery unavailable")


def register_delivery_routes(
    router: APIRouter,
    principal_dependency: Callable,
    lab_factory: Callable,
    clock: Callable[[], float],
) -> None:
    """Attach only to the existing Dragon Academy owner-authenticated router."""

    def _now() -> int:
        return int(clock())

    @router.get("/delivery/overview")
    def delivery_overview(
        request: Request, response: Response,
        owner: str = Depends(principal_dependency),
    ) -> dict:
        with _reviewed_delivery() as delivery:
            try:
                result = delivery.overview(owner, now=_now(), authorized=True)
            except (ValueError, PermissionError) as exc:
                raise _error(exc) from None
        response.headers["Cache-Control"] = "private, no-store"
        practice = os.environ.get("SKL_DRAGON_PRACTICE_DB_PATH", "").strip()
        path = Path(practice).expanduser() if practice else None
        return {
            "ok": True, **result,
            "resource_runtime_ready": isinstance(
                getattr(request.app.state, "dragon_execution_pool", None),
                DragonExecutionPool,
            ),
            "practice_storage_ready": bool(
                path is not None and path.is_absolute() and
                not path.is_symlink() and path.is_file()
            ),
        }

    @router.get("/delivery/knowledge")
    def delivery_knowledge(
        query: str = Query(min_length=1, max_length=300),
        owner: str = Depends(principal_dependency),
    ) -> dict:
        with _reviewed_delivery() as delivery:
            try:
                return {"ok": True, **delivery.search(
                    owner, query, now=_now(), authorized=True
                )}
            except (ValueError, PermissionError) as exc:
                raise _error(exc) from None

    @router.get("/delivery/almanacs")
    def delivery_almanacs(
        offset: int = Query(default=0, ge=0, le=100_000),
        owner: str = Depends(principal_dependency),
    ) -> dict:
        with _reviewed_delivery() as delivery:
            try:
                return {"ok": True, **delivery.almanacs.report(
                    owner, authorized=True, offset=offset, limit=32
                )}
            except (ValueError, PermissionError) as exc:
                raise _error(exc) from None

    @router.get("/delivery/almanacs/{topic}/learning")
    def delivery_learning_view(
        topic: str, owner: str = Depends(principal_dependency),
    ) -> dict:
        with _reviewed_delivery() as delivery:
            try:
                result = delivery.almanacs.learning_view(
                    owner, topic, authorized=True, limit=32
                )
                # This is a read-only advisory projection. Native source
                # synthesis does not constitute measured gameplay evidence,
                # an independent review, or permission to promote model memory.
                findings = [
                    {
                        **finding,
                        "epistemic_state": "unreviewed",
                        "empirical_truth_established": False,
                        "memory_promotion_authorized": False,
                        "training_authorized": False,
                    }
                    for finding in result["findings"]
                ]
                return {"ok": True, **result, "findings": findings}
            except (ValueError, PermissionError) as exc:
                raise _error(exc) from None

    @router.post("/delivery/brief")
    def delivery_brief(
        body: DeliveryBriefRequest, owner: str = Depends(principal_dependency),
    ) -> dict:
        try:
            design = parse_design(body.design)
            with _reviewed_delivery() as delivery:
                return {"ok": True, **delivery.brief(
                    owner, design, body.query, now=_now(), authorized=True
                )}
        except (ValueError, PermissionError, TypeError) as exc:
            raise _error(exc) from None

    @router.post("/delivery/generate")
    def delivery_generate(
        body: DeliveryGenerateRequest,
        request: Request,
        owner: str = Depends(principal_dependency),
    ) -> dict:
        if body.approved is not True:
            raise HTTPException(status_code=403, detail="Explicit source approval required")
        now = _now()
        try:
            design = parse_design(body.design)
            with _reviewed_delivery() as delivery:
                # Rebuild all source revisions and both independent approvals
                # at execution time. Never trust the posted brief or its digest.
                try:
                    brief = delivery.brief(
                        owner, design, body.query, now=now, authorized=True,
                        prepared_at=body.prepared_at,
                    )
                except (ValueError, LookupError):
                    raise HTTPException(status_code=409, detail="Delivery brief is expired or invalid") from None
                if (
                    brief["plan_digest"] != body.plan_digest or
                    not brief["ready_for_source_generation"]
                ):
                    raise HTTPException(status_code=409, detail="Reviewed delivery evidence changed")
                pool = getattr(request.app.state, "dragon_execution_pool", None)
                if not isinstance(pool, DragonExecutionPool):
                    raise HTTPException(status_code=503, detail="Shared Dragon resource runtime unavailable")
                with lab_factory() as (lab, _cycles):
                    native = DragonNativePracticeLab(lab.db, lab)
                    expected_attempt = digest([owner, "delivery", body.request_id])
                    seen = lab.db.execute(
                        "SELECT 1 FROM dragon_native_game_attempts WHERE owner=? AND attempt_id=?",
                        (owner, expected_attempt),
                    ).fetchone()
                    if seen:
                        # Native owner store checks archived brief byte-for-byte;
                        # a replay cannot change the design or mint a second work item.
                        item = native.generate(
                            owner, target_id=design.target, style=design.genre,
                            now=now, authorized=True, consent=True, design=design,
                            source_context=brief, request_id=body.request_id,
                        )
                        run = {"done": True, "reason": "idempotent_replay"}
                    else:
                        try:
                            executor = pool.executor(owner)
                        except DragonPoolCapacityError:
                            raise HTTPException(status_code=503, detail="Dragon owner capacity unavailable") from None
                        generated = []

                        def chunk(_plan, stop) -> ChunkResult:
                            if stop():
                                return ChunkResult(False, "delivery_deferred", ResourceDelta())
                            created = native.generate(
                                owner, target_id=design.target, style=design.genre,
                                now=now, authorized=True, consent=True,
                                design=design, source_context=brief,
                                request_id=body.request_id,
                            )
                            archive, _hash = native.archive(
                                owner, created.attempt_id, authorized=True
                            )
                            generated.append(created)
                            return ChunkResult(
                                True, created.attempt_id,
                                ResourceDelta(artifact_bytes=len(archive)),
                            )

                        outcome = executor.run(
                            SessionTask(
                                "dragon-delivery-" + body.request_id, "user",
                                131072, 1, provider_tokens=0,
                            ),
                            chunk, authorized=True, consent=True, max_chunks=1,
                            reserved_usage=ResourceDelta(artifact_bytes=250000),
                        )
                        run = asdict(outcome)
                        if not outcome.done:
                            return {
                                "ok": True, "delivery_state": "deferred",
                                "created_native": None, "compiled": False,
                                "resource_execution": run,
                                "learning_recovery_required": False,
                            }
                        if not generated:
                            raise HTTPException(status_code=503, detail="Delivery generated no artifact")
                        item = generated[0]
                    learning = None
                    needs_recovery = False
                    try:
                        learning = delivery.record_project_learning(
                            owner, native, item.attempt_id, authorized=True
                        )
                    except (sqlite3.DatabaseError, OSError):
                        # Native artifact is already committed and must remain
                        # recoverable without a duplicate build or resource charge.
                        needs_recovery = True
                    return {
                        "ok": True,
                        "delivery_state": "source_generated",
                        "plan_digest": brief["plan_digest"],
                        "gameplay_verified": False,
                        "created_native": asdict(item),
                        "resource_execution": run,
                        "compiled": False,
                        "learning_recovery_required": needs_recovery,
                        "project_learning": learning,
                        "release_authorized": False,
                    }
        except HTTPException:
            raise
        except (
            PermissionError, LookupError, ValueError, TypeError,
            ResourceLimitError, DragonPoolCapacityError,
            sqlite3.DatabaseError, OSError,
        ) as exc:
            raise _error(exc) from None

    @router.post("/delivery/{attempt_id}/learning")
    def delivery_recover_learning(
        attempt_id: str,
        owner: str = Depends(principal_dependency),
    ) -> dict:
        if len(attempt_id) != 64 or any(ch not in "0123456789abcdef" for ch in attempt_id):
            raise HTTPException(status_code=422, detail="Invalid native attempt identity")
        try:
            with _reviewed_delivery() as delivery:
                with lab_factory() as (lab, _cycles):
                    native = DragonNativePracticeLab(lab.db, lab)
                    learning = delivery.record_project_learning(
                        owner, native, attempt_id, authorized=True
                    )
                    return {
                        "ok": True, "attempt_id": attempt_id,
                        "new_source_generated": False, "project_learning": learning,
                    }
        except (PermissionError, LookupError, ValueError, TypeError, sqlite3.DatabaseError) as exc:
            raise _error(exc) from None
