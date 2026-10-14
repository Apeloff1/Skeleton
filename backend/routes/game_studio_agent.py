"""Authenticated request-driven Jeeves studio assistant goals."""

from typing import Literal
from fastapi import APIRouter, Depends
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
    max_jobs: int = Field(default=2, ge=0, le=4, strict=True)

    @model_validator(mode="after")
    def normalized_goal(self):
        if not self.goal.strip():
            raise ValueError("describe a concrete studio goal")
        return self


class GoalAdvance(Request):
    expected_goal_version: int = Field(ge=1, strict=True)
    idempotency_key: str = Field(min_length=1, max_length=512)
    steps: int = Field(default=1, ge=1, le=4, strict=True)


class GoalControl(Request):
    expected_goal_version: int = Field(ge=1, strict=True)
    idempotency_key: str = Field(min_length=1, max_length=512)
    action: Literal["pause", "resume", "cancel"]


@router.post("/projects/{project_id}/goals")
async def create_goal(project_id: str, body: GoalCreate, user=Depends(get_current_user)):
    return {"goal": await _call(agent.create(_scope(user), project_id, body.model_dump()))}


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
