"""Authenticated durable studio campaign controls and bounded evidence pages."""

from fastapi import APIRouter, Depends, Query
from pydantic import Field, model_validator

from core import game_studio_learning as learning
from routes.game_learning import Request, WriteRequest, _call, _scope
from routes.gameforge_auth import get_current_user

router = APIRouter(prefix="/game-studio-learning", tags=["Studio learning"])


class CampaignCreate(WriteRequest):
    round_limit: int = Field(default=100000, ge=1, le=100000, strict=True)
    slice_rounds: int = Field(default=4, ge=1, le=8, strict=True)
    episodes: int = Field(default=1, ge=1, le=4, strict=True)
    max_steps: int = Field(default=256, ge=1, le=4096, strict=True)
    seed: int = Field(default=0, ge=0, le=2**63 - 1, strict=True)
    policy_id: str | None = Field(default=None, min_length=1, max_length=128)
    auto_continue: bool = Field(default=False, strict=True)
    authorization_seconds: int = Field(default=3600, ge=60, le=86400, strict=True)

    @model_validator(mode="after")
    def slice_budget(self):
        if self.slice_rounds * (self.episodes + 4) * self.max_steps > 131072:
            raise ValueError("all training/play/adversarial slice transitions must fit131072steps")
        return self


class CampaignControl(Request):
    expected_campaign_version: int = Field(ge=1, strict=True)
    idempotency_key: str = Field(min_length=1, max_length=512)


learning.register_handler()


@router.post("/projects/{project_id}/campaigns")
async def create_campaign(project_id: str, body: CampaignCreate, user=Depends(get_current_user)):
    return {"campaign": await _call(learning.create(_scope(user), project_id, body.model_dump()))}


@router.get("/projects/{project_id}/campaigns")
async def list_campaigns(project_id: str, user=Depends(get_current_user)):
    scope = _scope(user)
    await _call(learning.workspace._project(project_id, scope))
    rows = (
        await learning.campaigns.find({**scope, "project_id": project_id})
        .sort("created_at", -1)
        .limit(64)
        .to_list(length=64)
    )
    return {"campaigns": [await _call(learning.inspect(scope, row["campaign_id"])) for row in rows]}


@router.get("/campaigns/{campaign_id}")
async def inspect_campaign(campaign_id: str, user=Depends(get_current_user)):
    return {"campaign": await _call(learning.inspect(_scope(user), campaign_id))}


@router.post("/campaigns/{campaign_id}/pulse")
async def pulse(campaign_id: str, body: CampaignControl, user=Depends(get_current_user)):
    return await _call(learning.pulse(_scope(user), campaign_id, body.model_dump()))


@router.post("/campaigns/{campaign_id}/{action}")
async def control(campaign_id: str, action: str, body: CampaignControl, user=Depends(get_current_user)):
    if action not in {"pause", "resume", "cancel"}:
        from fastapi import HTTPException

        raise HTTPException(404)
    return {"campaign": await _call(learning.control(_scope(user), campaign_id, action, body.model_dump()))}


@router.get("/campaigns/{campaign_id}/rounds")
async def get_rounds(
    campaign_id: str,
    after: int = Query(default=0, ge=0, le=100000),
    limit: int = Query(default=32, ge=1, le=32),
    user=Depends(get_current_user),
):
    return await _call(learning.rounds(_scope(user), campaign_id, after, limit))


@router.get("/projects/{project_id}/lessons")
async def get_lessons(
    project_id: str,
    q: str = Query(default="", max_length=256),
    limit: int = Query(default=32, ge=1, le=32),
    user=Depends(get_current_user),
):
    return await _call(learning.lessons(_scope(user), project_id, q, limit))
