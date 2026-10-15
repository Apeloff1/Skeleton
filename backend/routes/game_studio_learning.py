"""Authenticated durable studio campaign controls and bounded evidence pages."""

from typing import Literal

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
    source_id: str | None = Field(default=None, min_length=1, max_length=128)
    auto_continue: bool = Field(default=False, strict=True)
    authorization_seconds: int = Field(default=3600, ge=60, le=86400, strict=True)

    evaluation_seeds: int = Field(default=3, ge=1, le=8, strict=True)
    curriculum: Literal["fresh", "mixed", "counterexample"] = "mixed"
    objective_weights: dict[str, float] = Field(
        max_length=5,
        default_factory=lambda: {
            "return": 1,
            "completion": 0.5,
            "survival": 0.5,
            "coverage": 0.2,
            "diversity": 0.1,
        },
    )
    max_mean_step_ms: float | None = Field(default=None, gt=0, le=60000, strict=True, allow_inf_nan=False)
    max_death_regression: float = Field(default=0, ge=0, le=1, strict=True, allow_inf_nan=False)
    max_worst_seed_regression: float = Field(default=0, ge=0, le=1e9, strict=True, allow_inf_nan=False)

    @model_validator(mode="before")
    @classmethod
    def numeric_types(cls, value):
        if isinstance(value, dict):
            weights = value.get("objective_weights")
            if weights is not None and (
                not isinstance(weights, dict) or any(type(v) not in (int, float) for v in weights.values())
            ):
                raise ValueError("objective weights must be actual numeric values")
        return value

    @model_validator(mode="after")
    def slice_budget(self):
        if self.slice_rounds * (self.episodes + 4 * self.evaluation_seeds) * self.max_steps > 131072:
            raise ValueError("all training/play/adversarial slice transitions must fit131072steps")
        from skeleton.jeeves.game_studio_learning import CampaignConfig

        CampaignConfig(
            objective_weights=self.objective_weights,
            evaluation_seeds=self.evaluation_seeds,
            curriculum=self.curriculum,
            max_mean_step_ms=self.max_mean_step_ms,
            max_death_regression=self.max_death_regression,
            max_worst_seed_regression=self.max_worst_seed_regression,
        )
        return self


class CampaignControl(Request):
    expected_campaign_version: int = Field(ge=1, strict=True)
    idempotency_key: str = Field(min_length=1, max_length=512)


class CampaignAuthorization(CampaignControl):
    auto_continue: bool = Field(strict=True)
    authorization_seconds: int = Field(ge=60, le=86400, strict=True)


class ChampionAdopt(CampaignControl):
    expected_version: int = Field(ge=1, strict=True)
    champion_round_digest: str = Field(pattern="^[a-f0-9]{64}$")


learning.register_handler()


@router.get("/catalog")
async def campaign_catalog(user=Depends(get_current_user)):
    from skeleton.jeeves.game_studio_learning import campaign_catalog

    _scope(user)
    return campaign_catalog()


@router.post("/campaigns/{campaign_id}/authorization")
async def authorize(campaign_id: str, body: CampaignAuthorization, user=Depends(get_current_user)):
    return {
        "campaign": await _call(learning.authorize_campaign(_scope(user), campaign_id, body.model_dump()))
    }


@router.get("/campaigns/{campaign_id}/champion")
async def champion(campaign_id: str, user=Depends(get_current_user)):
    return await _call(learning.champion(_scope(user), campaign_id))


@router.post("/campaigns/{campaign_id}/champion/adopt")
async def adopt_champion(campaign_id: str, body: ChampionAdopt, user=Depends(get_current_user)):
    return await _call(learning.adopt_champion(_scope(user), campaign_id, body.model_dump()))


@router.get("/campaigns/{campaign_id}/champion/export")
async def export_champion(campaign_id: str, user=Depends(get_current_user)):
    return await _call(learning.export_champion(_scope(user), campaign_id))


@router.get("/campaigns/{campaign_id}/attempts")
async def attempts(
    campaign_id: str,
    after_epoch: int = Query(default=0, ge=0),
    limit: int = Query(default=32, ge=1, le=32),
    user=Depends(get_current_user),
):
    return await _call(learning.attempts(_scope(user), campaign_id, after_epoch, limit))


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
    cursor: str | None = Query(default=None, min_length=1, max_length=256),
    user=Depends(get_current_user),
):
    return await _call(learning.lessons(_scope(user), project_id, q, limit, cursor))


@router.get("/campaigns/{campaign_id}/mirror-views")
async def mirror_views(
    campaign_id: str,
    lanes: int = Query(default=4,ge=1,le=6),
    steps: int = Query(default=12,ge=1,le=24),
    sample: int = Query(default=0,ge=0,le=255),
    user=Depends(get_current_user),
):
    return await _call(learning.scenario_mirror_views(
        _scope(user), campaign_id, lanes=lanes, steps=steps, sample=sample,
    ))


@router.get("/campaigns/{campaign_id}/scenario-drafts")
async def scenario_drafts(
    campaign_id: str,
    limit: int = Query(default=4,ge=1,le=5),
    user=Depends(get_current_user),
):
    return await _call(learning.scenario_drafts(_scope(user),campaign_id,limit=limit))


@router.get("/engines/{editor}/test-manifest")
async def original_engine_test_manifest(editor: str,user=Depends(get_current_user)):
    return await _call(learning.scenario_engine_test_manifest(_scope(user),editor))


@router.get("/research/sales-informed-scenarios")
async def sales_informed_design_references(user=Depends(get_current_user)):
    from skeleton.jeeves.game_studio_scenario_lab import sales_informed_catalog
    return sales_informed_catalog()
