"""Typed knowledge/review operations mounted on the existing Academy router."""

from __future__ import annotations

from typing import Literal

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from core import dragon_runtime as runtime
from core.dragon_crawler import authenticated_scope
from core.game_learning import GameLearningError
from routes.gameforge_auth import get_current_user


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CandidateRequest(Request):
    session_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    start: int = Field(ge=0, le=1_000_000, strict=True)
    end: int = Field(ge=1, le=1_000_000, strict=True)
    statement: str = Field(min_length=1, max_length=2048)
    mechanic: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=128)


class ReviewRequest(Request):
    expected_version: int = Field(ge=1, le=3, strict=True)
    decision: Literal["approve_design_reference", "reject"]
    rationale: str = Field(min_length=1, max_length=2048)
    rights_reference: str | None = Field(default=None, min_length=1, max_length=128)
    rights_acknowledged: StrictBool = False
    idempotency_key: str = Field(min_length=1, max_length=128)


class ResumeReviewRequest(Request):
    review_id: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class PracticeRequest(Request):
    expected_version: int = Field(ge=1, le=3, strict=True)
    seed: int = Field(default=0, ge=0, le=2**31 - 1, strict=True)
    max_steps: int = Field(default=128, ge=16, le=512, strict=True)
    practice_consent: StrictBool
    idempotency_key: str = Field(min_length=1, max_length=128)


def register_knowledge_routes(router):
    def scope(user):
        try:
            return authenticated_scope(user)
        except Exception as exc:
            raise HTTPException(
                getattr(exc, "status", 403),
                detail={
                    "code": getattr(exc, "code", "dragon_scope_invalid"),
                    "message": "Sign in to use Dragon knowledge.",
                },
            ) from exc

    def editor(user):
        value = scope(user)
        if user.get("role") not in {"editor", "admin"}:
            raise HTTPException(
                403,
                detail={
                    "code": "dragon_review_role_required",
                    "message": "Editor or administrator review is required.",
                },
            )
        return value

    async def call(operation):
        try:
            return await operation
        except GameLearningError as exc:
            raise HTTPException(exc.status, detail={"code": exc.code, "message": exc.message}) from exc
        except (runtime.KnowledgeError, runtime.sqlite3.Error, LookupError) as exc:
            safe = runtime._error(exc)
            raise HTTPException(safe.status, detail={"code": safe.code, "message": safe.message}) from exc

    @router.get("/runtime/readiness")
    async def readiness(user: dict = Depends(get_current_user)):
        scope(user)
        return await call(runtime.runtime_readiness())

    @router.post("/knowledge/candidates")
    async def create(body: CandidateRequest, user: dict = Depends(get_current_user)):
        return await call(runtime.create_candidate(scope(user), body.model_dump()))

    @router.get("/knowledge/candidates")
    async def candidates(
        state: Literal["pending_review", "approved", "rejected"] | None = None,
        cursor: str | None = Query(None, max_length=64),
        limit: int = Query(20, ge=1, le=20),
        user: dict = Depends(get_current_user),
    ):
        return await call(runtime.list_candidates(scope(user), state=state, cursor=cursor, limit=limit))

    @router.get("/knowledge/candidates/{candidate_id}")
    async def candidate(candidate_id: str, user: dict = Depends(get_current_user)):
        return await call(runtime.get_candidate(scope(user), candidate_id))

    @router.post("/knowledge/candidates/{candidate_id}/review")
    async def review(candidate_id: str, body: ReviewRequest, user: dict = Depends(get_current_user)):
        return await call(runtime.review_candidate(editor(user), candidate_id, body.model_dump()))

    @router.get("/knowledge/search")
    async def search(
        q: str = Query(min_length=1, max_length=300),
        limit: int = Query(8, ge=1, le=8),
        user: dict = Depends(get_current_user),
    ):
        return await call(runtime.search_reviewed_references(scope(user), q, limit))

    @router.post("/knowledge/candidates/{candidate_id}/practice")
    async def practice(candidate_id: str, body: PracticeRequest, user: dict = Depends(get_current_user)):
        return await call(runtime.practice_candidate(scope(user), candidate_id, body.model_dump()))

    @router.get("/knowledge/candidates/{candidate_id}/practice")
    async def practices(
        candidate_id: str, limit: int = Query(20, ge=1, le=20), user: dict = Depends(get_current_user)
    ):
        return await call(runtime.practice_history(scope(user), candidate_id, limit))

    @router.get("/knowledge/candidates/{candidate_id}/practice/{practice_id}")
    async def practice_receipt(candidate_id: str, practice_id: str, user: dict = Depends(get_current_user)):
        return await call(runtime.inspect_reference_practice(scope(user), candidate_id, practice_id))

    @router.post("/knowledge/candidates/{candidate_id}/review/resume")
    async def resume_review(
        candidate_id: str, body: ResumeReviewRequest, user: dict = Depends(get_current_user)
    ):
        return await call(runtime.resume_review(editor(user), candidate_id, body.review_id))
