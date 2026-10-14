"""Authenticated read-only project review jobs and inspectable numerical evidence."""

from fastapi import APIRouter, Depends
from pydantic import Field, model_validator

from core.game_learning import workspace
from core.game_studio_review import read_review, register_review_handler
from routes.game_learning import WriteRequest, _call, _scope
from routes.gameforge_auth import get_current_user

router = APIRouter(prefix="/game-learning", tags=["Studio review"])


class StudioReviewBody(WriteRequest):
    seed: int = Field(default=0, ge=0, le=2**32 - 1, strict=True)
    episode_steps: int = Field(default=128, ge=1, le=512, strict=True)
    capture_every: int = Field(default=4, ge=1, le=32, strict=True)
    actions: list[str] | None = Field(default=None, min_length=1, max_length=512)
    policy_id: str | None = Field(default=None, min_length=1, max_length=128)
    source_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def bounded_controller(self):
        if self.actions is not None:
            if self.policy_id is not None or len(self.actions) > self.episode_steps:
                raise ValueError("choose bounded explicit actions or one frozen policy")
            if any(not action or len(action) > 64 or action != action.strip() for action in self.actions):
                raise ValueError("actions must be normalized registered runtime names")
        return self


register_review_handler()


@router.post("/projects/{project_id}/review")
async def start_review(project_id: str, body: StudioReviewBody, user=Depends(get_current_user)):
    return {
        "job": await _call(
            workspace.start_job(_scope(user), project_id, "review", body.model_dump(exclude_none=True))
        )
    }


@router.get("/projects/{project_id}/reviews/{job_id}")
async def inspect_review(project_id: str, job_id: str, user=Depends(get_current_user)):
    return await _call(read_review(_scope(user), project_id, job_id))
