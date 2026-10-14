"""Authenticated game editor, measured simulation and local-learning commands."""

from __future__ import annotations

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pymongo.errors import PyMongoError

from core.game_learning import GameLearningError, workspace
from routes.gameforge_auth import get_current_user

log = logging.getLogger(__name__)
router = APIRouter(prefix="/game-learning", tags=["Game learning"])


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WriteRequest(Request):
    expected_version: int = Field(ge=1, strict=True)
    idempotency_key: str = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def normalized_key(self):
        if self.idempotency_key != self.idempotency_key.strip():
            raise ValueError("idempotency key must be normalized")
        return self


class CreateProject(Request):
    name: str = Field(min_length=1, max_length=120)
    console_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=512)


class ProjectFile(Request):
    path: str = Field(min_length=1, max_length=256)
    content: str = Field(max_length=128000)
    language: str | None = Field(default=None, max_length=32)
    revision: int | None = Field(default=None, ge=1, strict=True)


class EditorRequest(WriteRequest):
    files: list[ProjectFile] | None = Field(default=None, max_length=96)
    program_text: str | None = Field(default=None, max_length=128000)
    path: str | None = Field(default=None, max_length=256)
    entrypoint: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def edit_payload(self):
        if (self.files is None) == (self.program_text is None):
            raise ValueError("provide either files or program_text")
        return self


class SourceRequest(WriteRequest):
    kind: Literal["text", "rom", "dragon", "project"]
    filename: str | None = Field(default=None, min_length=1, max_length=256)
    text: str | None = Field(default=None, max_length=16 * 1024 * 1024)
    content_base64: str | None = Field(default=None, max_length=23 * 1024 * 1024)
    dragon_ref: str | None = Field(default=None, min_length=1, max_length=512)
    rights_refs: list[str] = Field(min_length=1, max_length=64)
    rights_acknowledged: bool = False
    license_ref: str | None = Field(default=None, min_length=1, max_length=512)

    @model_validator(mode="after")
    def source_payload(self):
        if self.rights_acknowledged is not True or any(
            not ref or ref != ref.strip() or len(ref) > 512 for ref in self.rights_refs
        ):
            raise ValueError("explicit normalized source rights acknowledgement is required")
        values = (self.text, self.content_base64, self.dragon_ref)
        if sum(value is not None for value in values) != 1 or (self.kind == "dragon") != (
            self.dragon_ref is not None
        ):
            raise ValueError("provide exactly one payload matching source kind")
        return self


class SimulationRequest(WriteRequest):
    session_id: str | None = Field(default=None, min_length=1, max_length=128)
    expected_session_version: int | None = Field(default=None, ge=1, strict=True)
    reset: bool | None = None
    action: str | None = Field(default=None, min_length=1, max_length=64)
    actions: list[str] | None = Field(default=None, max_length=4096)
    steps: int | None = Field(default=None, ge=1, le=4096, strict=True)
    seed: int = Field(default=0, ge=0, le=2**63 - 1, strict=True)
    source_id: str | None = Field(default=None, max_length=128)
    episode_steps: int | None = Field(default=None, ge=1, le=4096, strict=True)
    max_steps: int | None = Field(default=None, ge=1, le=4096, strict=True)

    @model_validator(mode="after")
    def action_payload(self):
        if sum(value is not None for value in (self.action, self.actions, self.steps)) > 1:
            raise ValueError("provide one action, action sequence, or step count")
        if self.session_id and self.expected_session_version is None:
            raise ValueError("existing sessions require expected_session_version")
        if self.actions and any(not action or len(action) > 64 for action in self.actions):
            raise ValueError("actions must be bounded identifiers")
        return self


class TrainRequest(WriteRequest):
    algorithm: Literal["q_learning"] = "q_learning"
    epochs: int = Field(default=16, ge=1, le=256, strict=True)
    seed: int = Field(default=0, ge=0, le=2**63 - 1, strict=True)
    episode_steps: int = Field(default=256, ge=1, le=4096, strict=True)
    source_id: str | None = Field(default=None, max_length=128)
    session_ids: list[str] = Field(default_factory=list, max_length=128)
    parent_policy_id: str | None = Field(default=None, max_length=128)
    fresh_policy: bool = False


class GenerateRequest(WriteRequest):
    title: str = Field(default="Original learned game", min_length=1, max_length=120)
    genre: str = Field(default="arcade_golden_age", min_length=1, max_length=64)
    seed: int = Field(default=0, ge=0, le=2**32 - 1, strict=True)
    complexity: int = Field(default=2, ge=1, le=5, strict=True)
    policy_id: str | None = Field(default=None, max_length=128)
    source_id: str | None = Field(default=None, max_length=128)


class RevokeRequest(Request):
    expected_version: int = Field(ge=1, strict=True)


def _scope(user):
    if not user or user.get("disabled") or user.get("dev_mode"):
        raise HTTPException(
            401,
            detail={
                "code": "authentication_required",
                "message": "Sign in to use a game-learning workspace.",
            },
        )
    owner = str(user.get("email") or user.get("user_id") or "").strip()
    tenant = str(user.get("tenant_id") or owner).strip()
    if not owner or not tenant or user.get("role") not in {"viewer", "editor", "admin"}:
        raise HTTPException(
            403,
            detail={
                "code": "account_identity_unavailable",
                "message": "An active authenticated account is required.",
            },
        )
    return workspace._scope(tenant, owner)


async def _call(awaitable):
    try:
        return await awaitable
    except GameLearningError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code, "message": exc.message}) from exc
    except PyMongoError as exc:
        raise HTTPException(
            503,
            detail={"code": "workspace_storage_unavailable", "message": "Workspace storage is unavailable."},
        ) from exc
    except (ValueError, TypeError, KeyError) as exc:
        log.warning("Game workspace request rejected by %s", type(exc).__name__)
        raise HTTPException(
            422,
            detail={
                "code": "workspace_input_rejected",
                "message": "The source, program or execution parameters were rejected.",
            },
        ) from exc


User = Annotated[dict | None, Depends(get_current_user)]


@router.get("/catalog")
async def catalog(user: User):
    _scope(user)
    return await _call(workspace.catalog())


@router.get("/dragon-sources")
async def dragon_sources(user: User, limit: int = Query(default=32, ge=1, le=64)):
    return {"sources": await _call(workspace.dragon_sources(_scope(user), limit))}


@router.get("/projects")
async def list_projects(user: User, limit: int = Query(default=50, ge=1, le=64)):
    return {"projects": await _call(workspace.list_projects(_scope(user), limit))}


@router.post("/projects")
async def create_project(body: CreateProject, user: User):
    return {
        "project": await _call(workspace.create_project(_scope(user), body.model_dump(exclude_none=True)))
    }


@router.get("/projects/{project_id}")
async def get_project(project_id: str, user: User):
    return {"project": await _call(workspace.get_project(_scope(user), project_id))}


@router.patch("/projects/{project_id}/editor")
async def edit_project(project_id: str, body: EditorRequest, user: User):
    return {
        "project": await _call(
            workspace.save_editor(_scope(user), project_id, body.model_dump(exclude_none=True))
        )
    }


@router.post("/projects/{project_id}/sources")
async def add_source(project_id: str, body: SourceRequest, user: User):
    project, source = await _call(
        workspace.ingest_source(_scope(user), project_id, body.model_dump(exclude_none=True))
    )
    return {"project": project, "source": source}


@router.delete("/projects/{project_id}/sources/{source_id}")
async def revoke_source(project_id: str, source_id: str, body: RevokeRequest, user: User):
    return {
        "project": await _call(
            workspace.revoke_source(_scope(user), project_id, source_id, body.expected_version)
        )
    }


@router.post("/projects/{project_id}/simulate")
async def simulate(project_id: str, body: SimulationRequest, user: User):
    project, session = await _call(
        workspace.simulate(_scope(user), project_id, body.model_dump(exclude_none=True))
    )
    return {"project": project, "session": session}


@router.post("/projects/{project_id}/train")
async def train(project_id: str, body: TrainRequest, user: User):
    return {
        "job": await _call(
            workspace.start_job(_scope(user), project_id, "train", body.model_dump(exclude_none=True))
        )
    }


@router.post("/projects/{project_id}/generate")
async def generate(project_id: str, body: GenerateRequest, user: User):
    return {
        "job": await _call(
            workspace.start_job(_scope(user), project_id, "generate", body.model_dump(exclude_none=True))
        )
    }


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, user: User):
    return {"job": await _call(workspace.get_job(_scope(user), job_id))}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, user: User):
    return {"job": await _call(workspace.cancel_job(_scope(user), job_id))}


@router.post("/jobs/{job_id}/resume")
async def resume_job(job_id: str, user: User):
    return {"job": await _call(workspace.resume_job(_scope(user), job_id))}


@router.get("/projects/{project_id}/export")
async def export_project(
    project_id: str,
    user: User,
    format: Literal["json"] = "json",
    expected_version: int | None = Query(default=None, ge=1),
    generated_job_id: str | None = Query(default=None, max_length=128),
):
    return await _call(
        workspace.export_project(
            _scope(user), project_id, expected_version=expected_version, generated_job_id=generated_job_id
        )
    )
