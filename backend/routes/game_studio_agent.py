"""Authenticated request-driven Jeeves studio assistant goals."""

from typing import Literal
from fastapi import APIRouter, Depends, Query
from pydantic import Field, model_validator
from core import game_studio_agent as agent
from routes.game_learning import Request, WriteRequest, _call, _scope
from routes.gameforge_auth import get_current_user

router = APIRouter(prefix="/game-studio-agent", tags=["Jeeves studio assistant"])


class GoalCreate(WriteRequest):
    goal: str = Field(min_length=1, max_length=8000)
    max_steps: int = Field(default=8, ge=1, le=16, strict=True)
    execution_mode: Literal["plan", "run"] = "plan"
    allow_edits: bool = Field(default=False, strict=True)
    authorization_seconds: int = Field(default=600, ge=60, le=3600, strict=True)
    max_model_calls: int = Field(default=4, ge=1, le=8, strict=True)
    max_output_tokens: int = Field(default=1024, ge=256, le=4096, strict=True)
    max_jobs: int = Field(default=2, ge=0, le=4, strict=True)
    completion_requirements: list[Literal["edit", "build", "preview", "export"]] | None = Field(
        default=None, max_length=4
    )

    @model_validator(mode="after")
    def normalized_goal(self):
        if not self.goal.strip():
            raise ValueError("describe a concrete studio goal")
        if self.completion_requirements is not None:
            if len(set(self.completion_requirements)) != len(self.completion_requirements):
                raise ValueError("select each completion requirement once")
            if self.completion_requirements and self.execution_mode != "run":
                raise ValueError("verified workflow requirements need run mode")
            if "edit" in self.completion_requirements and not self.allow_edits:
                raise ValueError("the edit requirement needs explicit edit authorization")
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
    target: Literal["planner", "action", "job", "play", "reconcile"]
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
    return {"goal": await _call(agent.create(_scope(user), project_id, payload))}


@router.get("/projects/{project_id}/goals")
async def list_goals(project_id: str, user=Depends(get_current_user)):
    return {"goals": await _call(agent.list_goals(_scope(user), project_id))}


@router.get("/goals/{goal_id}")
async def get_goal(goal_id: str, user=Depends(get_current_user)):
    return {"goal": await _call(agent.inspect(_scope(user), goal_id))}


@router.post("/goals/{goal_id}/advance")
async def advance_goal(goal_id: str, body: GoalAdvance, user=Depends(get_current_user)):
    return {"goal": await _call(agent.advance(_scope(user), goal_id, body.model_dump()))}


@router.post("/goals/{goal_id}/control")
async def control_goal(goal_id: str, body: GoalControl, user=Depends(get_current_user)):
    return {"goal": await _call(agent.control(_scope(user), goal_id, body.model_dump()))}
