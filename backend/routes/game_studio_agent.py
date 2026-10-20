"""Authenticated request-driven Jeeves studio assistant goals."""

from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field, model_validator
from core import game_studio_agent as agent
from routes.game_learning import Request, WriteRequest, _call, _scope
from routes.gameforge_auth import get_current_user

router = APIRouter(prefix="/game-studio-agent", tags=["Jeeves studio assistant"])


class StudioQualityGate(Request):
    """Operator-selected measured acceptance, never a subjective quality score."""

    schema_version: Literal["skeleton.game.studio_quality_policy.v1"] = (
        "skeleton.game.studio_quality_policy.v1"
    )
    baseline_review_job_id: str | None = Field(default=None, min_length=1, max_length=128)
    max_refinement_rounds: int = Field(default=2, ge=1, le=4, strict=True)
    min_available_frames: int = Field(default=2, ge=1, le=25, strict=True)
    min_executed_steps: int = Field(default=1, ge=1, le=512, strict=True)
    max_error_findings: int = Field(default=0, ge=0, le=128, strict=True)
    max_warning_findings: int = Field(default=128, ge=0, le=128, strict=True)
    require_no_regression: bool = Field(default=True, strict=True)
    restore_on_regression: bool = Field(default=True, strict=True)
    adaptive_ranking: bool = Field(default=False, strict=True)
    numeric_memory_policy: Literal["goal_only", "reuse_compatible", "reset"] = "goal_only"

    @model_validator(mode="after")
    def numeric_memory_grant(self):
        if self.numeric_memory_policy != "goal_only" and not self.adaptive_ranking:
            raise ValueError("shared numeric memory requires the explicit adaptive-ranking grant")
        return self


class GoalCreate(WriteRequest):
    goal: str = Field(min_length=1, max_length=8000)
    max_steps: int = Field(default=8, ge=1, le=16, strict=True)
    execution_mode: Literal["plan", "run"] = "plan"
    allow_edits: bool = Field(default=False, strict=True)
    authorization_seconds: int = Field(default=600, ge=60, le=3600, strict=True)
    max_model_calls: int = Field(default=4, ge=1, le=16, strict=True)
    max_output_tokens: int = Field(default=1024, ge=256, le=4096, strict=True)
    max_jobs: int = Field(default=2, ge=0, le=8, strict=True)
    completion_mode: Literal["native", "original"] = "native"
    completion_requirements: (
        list[Literal["edit", "build", "preview", "export", "simulate", "review", "package"]] | None
    ) = Field(default=None, max_length=5)
    quality_gate: StudioQualityGate | None = None

    @model_validator(mode="after")
    def normalized_goal(self):
        if not self.goal.strip():
            raise ValueError("describe a concrete studio goal")
        if self.completion_requirements is not None:
            supported = (
                {"edit", "simulate", "review", "package", "export"}
                if self.completion_mode == "original"
                else {"edit", "build", "preview", "export"}
            )
            if set(self.completion_requirements) - supported:
                raise ValueError("select completion requirements supported by this workflow mode")
            if len(set(self.completion_requirements)) != len(self.completion_requirements):
                raise ValueError("select each completion requirement once")
            if self.completion_requirements and self.execution_mode != "run":
                raise ValueError("verified workflow requirements need run mode")
            if "edit" in self.completion_requirements and not self.allow_edits:
                raise ValueError("the edit requirement needs explicit edit authorization")
        if self.quality_gate is not None:
            if (
                self.completion_mode != "original"
                or self.execution_mode != "run"
                or not {"simulate", "review"}.issubset(self.completion_requirements or [])
            ):
                raise ValueError("measured quality requires an original run with simulation and review")
            if self.quality_gate.restore_on_regression and not self.allow_edits:
                raise ValueError("incumbent restoration requires explicit edit authorization")
        return self


class GoalAdvance(Request):
    expected_goal_version: int = Field(ge=1, strict=True)
    idempotency_key: str = Field(min_length=1, max_length=512)
    steps: int = Field(default=1, ge=1, le=4, strict=True)


class GoalControl(Request):
    expected_goal_version: int = Field(ge=1, strict=True)
    idempotency_key: str = Field(min_length=1, max_length=512)
    action: Literal["pause", "resume", "cancel"]


class GoalRetry(Request):
    expected_goal_version: int = Field(ge=1, strict=True)
    idempotency_key: str = Field(min_length=1, max_length=512)
    target: Literal["planner", "action", "job", "play", "reconcile", "restore_incumbent"]
    new_planner_attempt: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def new_attempt_scope(self):
        if self.new_planner_attempt and self.target != "planner":
            raise ValueError("only planner recovery can request a fresh bounded model attempt")
        return self


class GoalAuthorization(Request):
    expected_goal_version: int = Field(ge=1, strict=True)
    idempotency_key: str = Field(min_length=1, max_length=512)
    authorization_seconds: int = Field(ge=60, le=3600, strict=True)


@router.get("/catalog")
async def catalog(user=Depends(get_current_user)):
    return await _call(agent.catalog(_scope(user)))


@router.post("/goals/{goal_id}/retry")
async def retry(goal_id: str, body: GoalRetry, user=Depends(get_current_user)):
    return {"goal": await _call(agent.retry(_scope(user), goal_id, body.model_dump()))}


@router.post("/goals/{goal_id}/authorization")
async def authorize(goal_id: str, body: GoalAuthorization, user=Depends(get_current_user)):
    return {"goal": await _call(agent.authorize_goal(_scope(user), goal_id, body.model_dump()))}


@router.get("/goals/{goal_id}/history")
async def history(
    goal_id: str,
    after: int = Query(default=0, ge=0, le=16),
    limit: int = Query(default=8, ge=1, le=8),
    user=Depends(get_current_user),
):
    return await _call(agent.history(_scope(user), goal_id, after, limit))


@router.post("/projects/{project_id}/goals")
async def create_goal(project_id: str, body: GoalCreate, user=Depends(get_current_user)):
    payload = body.model_dump()
    if "max_output_tokens" not in body.model_fields_set:
        payload.pop("max_output_tokens")
    if "completion_requirements" not in body.model_fields_set:
        payload.pop("completion_requirements")
    if "completion_mode" not in body.model_fields_set:
        payload.pop("completion_mode")
    if "quality_gate" not in body.model_fields_set:
        payload.pop("quality_gate")
    return {"goal": await _call(agent.create(_scope(user), project_id, payload))}


@router.get("/projects/{project_id}/goals")
async def list_goals(project_id: str, user=Depends(get_current_user)):
    return {"goals": await _call(agent.list_goals(_scope(user), project_id))}


@router.get("/goals/{goal_id}")
async def get_goal(goal_id: str, user=Depends(get_current_user)):
    return {"goal": await _call(agent.inspect(_scope(user), goal_id))}


@router.get("/goals/{goal_id}/dragon-observation")
async def dragon_observation(
    goal_id: str,
    after: int = Query(default=0, ge=0, le=16),
    limit: int = Query(default=8, ge=1, le=16),
    user=Depends(get_current_user),
):
    """Owner-scoped verified journal projection, not screen recording or learning.

    Keep scope, source permissions and history integrity in the canonical
    application owner. No untrusted client may submit Dragon observations.
    """
    from skeleton.ai.game_builder.studio_e2e_observation import (
        StudioObservationError,
        observe_goal,
    )

    scope = _scope(user)
    # The history owner also rechecks live source/Dragon evidence dependencies.
    # Inspect alone authenticates the goal but not every revoked source pin.
    await _call(agent.history(scope, goal_id, after=0, limit=1))
    goal = await _call(agent.inspect(scope, goal_id))
    try:
        return observe_goal(goal, after=after, limit=limit)
    except StudioObservationError as exc:
        raise HTTPException(status_code=503, detail="Studio observation evidence unavailable") from exc


@router.post("/goals/{goal_id}/advance")
async def advance_goal(goal_id: str, body: GoalAdvance, user=Depends(get_current_user)):
    return {"goal": await _call(agent.advance(_scope(user), goal_id, body.model_dump()))}


@router.post("/goals/{goal_id}/control")
async def control_goal(goal_id: str, body: GoalControl, user=Depends(get_current_user)):
    return {"goal": await _call(agent.control(_scope(user), goal_id, body.model_dump()))}
