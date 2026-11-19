"""Scoped original successor synthesis, measured comparison and native export."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import Field, StrictFloat, StrictInt, model_validator

from core import game_successor as successor
from core.game_learning import workspace
from routes.game_learning import Request, WriteRequest, _call, _scope
from routes.gameforge_auth import get_current_user

router = APIRouter(prefix="/game-successor", tags=["Original successor"])
successor.register_handlers()


class OwnedSource(Request):
    kind: Literal["owned_source"]
    project_id: str = Field(min_length=1, max_length=128)
    project_version: int = Field(ge=1, strict=True)
    source_id: str = Field(min_length=1, max_length=128)
    source_digest: str = Field(pattern="^[a-f0-9]{64}$")
    family: Literal["adventure", "fishing", "farming", "platformer", "arena"] = "adventure"
    authored_mechanics: dict[str, StrictFloat | StrictInt] | None = Field(default=None, max_length=64)


class AuthoredSource(Request):
    kind: Literal["authored_profile"]
    profile_id: str = Field(min_length=1, max_length=128)


class SynthesisRequest(WriteRequest):
    title: str = Field(default="Riverlight: The Threefold Valley", min_length=1, max_length=120)
    sources: list[Annotated[OwnedSource | AuthoredSource, Field(discriminator="kind")]] = Field(
        min_length=1, max_length=3
    )
    seed: int = Field(default=1, ge=0, le=2**32 - 1, strict=True)
    weights: dict[str, float] | None = None
    mechanic_priorities: dict[str, str] | None = None
    style_priorities: dict[str, float] | None = None

    @model_validator(mode="after")
    def origin_count(self):
        if len(self.sources) not in (1, 3):
            raise ValueError("select exactly one or three origins")
        if any(
            value is not None and len(value) > 32
            for value in (self.weights, self.mechanic_priorities, self.style_priorities)
        ):
            raise ValueError("priority maps exceed capacity")
        return self


class CompareRequest(WriteRequest):
    target_metrics: dict[str, float] = Field(min_length=1, max_length=16)
    candidates: int = Field(default=4, ge=1, le=16, strict=True)
    episodes: int = Field(default=2, ge=1, le=8, strict=True)
    max_steps: int = Field(default=256, ge=1, le=4096, strict=True)
    seed: int = Field(default=7, ge=0, le=2**32 - 1, strict=True)
    policy_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def cumulative_budget(self):
        if (self.candidates + 2) * self.episodes * self.max_steps > 131072:
            raise ValueError("comparison cumulative simulation budget exceeds 131072")
        return self


class DesktopRequest(WriteRequest):
    target_id: Literal["windows-amd64", "linux-amd64", "linux-arm64", "darwin-amd64", "darwin-arm64"]
    timeout_seconds: int = Field(default=180, ge=10, le=300, strict=True)


class WorldRequest(WriteRequest):
    expected_spec_digest: str = Field(pattern="^[a-f0-9]{64}$")
    changes: dict[str, Any] = Field(min_length=1, max_length=8)


@router.get("/sources")
async def get_sources(user=Depends(get_current_user)):
    return await _call(successor.sources(_scope(user)))


@router.post("/projects/{project_id}/synthesize")
async def synthesize(project_id: str, body: SynthesisRequest, user=Depends(get_current_user)):
    return {"job": await _call(workspace.start_job(_scope(user), project_id, "successor", body.model_dump()))}


@router.get("/projects/{project_id}/candidates")
async def get_candidates(project_id: str, user=Depends(get_current_user)):
    return await _call(successor.candidates(_scope(user), project_id))


@router.get("/candidates/{candidate_id}")
async def get_candidate(candidate_id: str, user=Depends(get_current_user)):
    return {"candidate": await _call(successor.candidate(_scope(user), candidate_id))}


@router.post("/candidates/{candidate_id}/adopt")
async def adopt(candidate_id: str, body: WriteRequest, user=Depends(get_current_user)):
    return await _call(successor.adopt(_scope(user), candidate_id, body.model_dump()))


@router.post("/candidates/{candidate_id}/compare")
async def compare(candidate_id: str, body: CompareRequest, user=Depends(get_current_user)):
    scope = _scope(user)
    value = await _call(successor.candidate(scope, candidate_id))
    return {
        "job": await _call(
            workspace.start_job(
                scope,
                value["project_id"],
                "successor_compare",
                {**body.model_dump(), "candidate_id": candidate_id},
            )
        )
    }


@router.get("/candidates/{candidate_id}/export")
async def export(candidate_id: str, user=Depends(get_current_user)):
    return await _call(successor.export_candidate(_scope(user), candidate_id))


@router.get("/desktop-catalog")
async def get_desktop_catalog(user=Depends(get_current_user)):
    _scope(user)
    return await _call(successor.desktop_catalog())


@router.post("/candidates/{candidate_id}/desktop")
async def build_desktop(candidate_id: str, body: DesktopRequest, user=Depends(get_current_user)):
    scope = _scope(user)
    value = await _call(successor.candidate(scope, candidate_id))
    return {
        "job": await _call(
            workspace.start_job(
                scope, value["project_id"], "desktop", {**body.model_dump(), "candidate_id": candidate_id}
            )
        )
    }


@router.post("/projects/{project_id}/desktop")
async def build_current_desktop(project_id: str, body: DesktopRequest, user=Depends(get_current_user)):
    return {"job": await _call(workspace.start_job(_scope(user), project_id, "desktop", body.model_dump()))}


@router.get("/projects/{project_id}/world")
async def get_world(project_id: str, user=Depends(get_current_user)):
    return await _call(successor.world(_scope(user), project_id))


@router.patch("/projects/{project_id}/world")
async def edit_world(project_id: str, body: WorldRequest, user=Depends(get_current_user)):
    return await _call(successor.edit_world(_scope(user), project_id, body.model_dump()))
