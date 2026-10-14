"""Authenticated game editor, measured simulation and local-learning commands."""

from __future__ import annotations

import logging
import asyncio
import json
from datetime import datetime, timezone
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
    workers: int = Field(default=1, ge=1, le=8, strict=True)
    resource_profile: Literal["cpu"] = "cpu"
    demonstration_ids: list[str] = Field(default_factory=list, max_length=16)
    frame_stride: int = Field(default=8, ge=1, le=256, strict=True)


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


class PlayRequest(WriteRequest):
    source_id: str | None = Field(default=None, max_length=128)
    seed: int = Field(default=0, ge=0, le=2**63 - 1, strict=True)
    max_steps: int = Field(default=4096, ge=1, le=4096, strict=True)
    fps: int = Field(default=15, ge=1, le=30, strict=True)
    controller: Literal["human", "ai"] = "human"
    policy_id: str | None = Field(default=None, max_length=128)


class PlayInput(Request):
    control_token: str = Field(min_length=20, max_length=256)
    expected_control_version: int = Field(ge=1, strict=True)
    input_sequence: int = Field(ge=1, strict=True)
    action: str = Field(min_length=1, max_length=64)
    held: bool = Field(default=True, strict=True)


class PlayControl(Request):
    expected_control_version: int = Field(ge=1, strict=True)
    action: Literal["pause", "resume", "stop", "takeover", "reset"]
    controller: Literal["human", "ai"] | None = None
    policy_id: str | None = Field(default=None, max_length=128)


class RecordingRequest(Request):
    expected_control_version: int = Field(ge=1, strict=True)
    consent: bool = Field(strict=True)
    label: str | None = Field(default=None, max_length=120)
    idempotency_key: str = Field(min_length=1, max_length=512)


class RecordingFeedback(Request):
    rating: int = Field(ge=1, le=5, strict=True)
    note: str | None = Field(default=None, max_length=2000)


class RecordingStop(Request):
    consent: bool = Field(strict=True)
    feedback: RecordingFeedback | None = None


class RecordingReplay(WriteRequest):
    fps: int = Field(default=15, ge=1, le=30, strict=True)


def _plays():
    from core.game_play import GamePlayAuthority

    if not hasattr(workspace, "_play_authority"):
        workspace._play_authority = GamePlayAuthority(workspace)
    return workspace._play_authority


@router.get("/resources")
async def game_resources(user: User):
    from core.game_play import resource_profiles

    _scope(user)
    return resource_profiles()


@router.post("/projects/{project_id}/play")
async def create_play(project_id: str, body: PlayRequest, user: User):
    return {
        "play": await _call(_plays().create(_scope(user), project_id, body.model_dump(exclude_none=True)))
    }


@router.get("/projects/{project_id}/play")
async def list_play(project_id: str, user: User):
    scope = _scope(user)
    project = await _call(workspace._project(project_id, scope))
    rows = (
        await _plays()
        .plays.find({**scope, "project_id": project_id, "play_id": {"$in": project.get("play_ids", [])}})
        .sort("updated_at", -1)
        .limit(32)
        .to_list(length=32)
    )
    return {"plays": [_plays().public(row) for row in rows]}


@router.get("/play/{play_id}")
async def get_play(play_id: str, user: User):
    return {"play": await _call(_plays().get(_scope(user), play_id))}


@router.post("/play/{play_id}/input")
async def play_input(play_id: str, body: PlayInput, user: User):
    return {"play": await _call(_plays().input(_scope(user), play_id, body.model_dump()))}


@router.post("/play/{play_id}/control")
async def play_control(play_id: str, body: PlayControl, user: User):
    return {"play": await _call(_plays().control(_scope(user), play_id, body.model_dump(exclude_none=True)))}


@router.post("/play/{play_id}/recordings")
async def start_recording(play_id: str, body: RecordingRequest, user: User):
    return {
        "recording": await _call(
            _plays().start_recording(_scope(user), play_id, body.model_dump(exclude_none=True))
        )
    }


@router.get("/projects/{project_id}/recordings")
async def list_recordings(project_id: str, user: User):
    scope = _scope(user)
    await _call(workspace._project(project_id, scope))
    rows = (
        await _plays()
        .recordings.find({**scope, "project_id": project_id})
        .sort("created_at", -1)
        .limit(128)
        .to_list(length=128)
    )
    return {"recordings": [_plays().recording_public(row) for row in rows]}


@router.get("/recordings/{recording_id}")
async def get_recording(recording_id: str, user: User):
    row = await _call(_plays().recording(_scope(user), recording_id))
    return {"recording": _plays().recording_public(row)}


@router.post("/recordings/{recording_id}/stop")
async def stop_recording(recording_id: str, body: RecordingStop, user: User):
    return {
        "recording": await _call(
            _plays().stop_recording(_scope(user), recording_id, body.model_dump(exclude_none=True))
        )
    }


@router.get("/recordings/{recording_id}/export")
async def export_recording(recording_id: str, user: User):
    return await _call(_plays().export_recording(_scope(user), recording_id))


@router.post("/recordings/{recording_id}/replay")
async def replay_recording(recording_id: str, body: RecordingReplay, user: User):
    return {
        "play": await _call(_plays().replay(_scope(user), recording_id, body.model_dump(exclude_none=True)))
    }


@router.get("/play/{play_id}/events")
async def play_events(
    play_id: str,
    user: User,
    after: int = Query(default=0, ge=0),
    stream_id: str | None = Query(default=None, max_length=128),
):
    from fastapi.responses import StreamingResponse
    from core.game_learning_events import frame_hub, FrameCursorError
    import asyncio
    import json

    scope = _scope(user)
    current = await _call(_plays()._read(scope, play_id))
    incarnation = stream_id or current["stream_id"]
    if incarnation != current["stream_id"]:
        raise HTTPException(
            409, detail={"code": "stream_replaced", "message": "Reload the actual current play stream."}
        )

    async def stream():
        cursor = after
        for _ in range(900):
            row = await _plays()._read(scope, play_id)
            if row["stream_id"] != incarnation:
                yield 'event: resync\ndata: {"reason":"stream_replaced"}\n\n'
                return
            try:
                events = frame_hub.read("play:" + play_id, incarnation, cursor)
            except FrameCursorError:
                projection = await _plays().frames.find_one(
                    {
                        "_id": "play:" + play_id,
                        **scope,
                        "stream_id": incarnation,
                        "expires_at": {"$gt": datetime.now(timezone.utc)},
                    }
                )
                events = (
                    [projection["event"]] if projection and projection["event"]["sequence"] > cursor else []
                )
            for event in events:
                cursor = event["sequence"]
                yield f'id: {incarnation}:{cursor}\nevent: {event["event"]}\ndata: {json.dumps(event, separators=(",", ":"))}\n\n'
            if row["status"] in {"stopped", "failed", "interrupted"}:
                yield "event: terminal\ndata: " + json.dumps(
                    {"play_id": play_id, "status": row["status"]}
                ) + "\n\n"
                return
            if not events:
                yield ": keepalive\n\n"
            await asyncio.sleep(0.1)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.get("/jobs/{job_id}/instances")
async def job_instances(job_id: str, user: User):
    return await _call(workspace.job_instances(_scope(user), job_id))


@router.get("/jobs/{job_id}/events")
async def job_events(
    job_id: str,
    user: User,
    after: int = Query(default=0, ge=0),
    stream_id: str | None = Query(default=None, max_length=128),
):
    from fastapi.responses import StreamingResponse
    from core.game_learning_events import frame_hub, FrameCursorError

    scope = _scope(user)
    await _call(workspace.get_job(scope, job_id))
    raw = await workspace.jobs.find_one({"_id": job_id, **scope})
    incarnation = stream_id or raw.get("frame_stream_id")
    if not incarnation:
        raise HTTPException(
            409,
            detail={
                "code": "actors_not_started",
                "message": "Wait for actual actor admission before opening the frame stream.",
            },
        )
    if incarnation != raw.get("frame_stream_id"):
        raise HTTPException(
            409, detail={"code": "stream_replaced", "message": "Reload the current actor stream."}
        )

    async def stream():
        cursor = after
        for _ in range(3000):
            state = await workspace.jobs.find_one({"_id": job_id, **scope})
            if state is None:
                return
            await workspace._authority(scope, state["input"])
            if state.get("frame_stream_id") != incarnation:
                yield 'event: resync\ndata: {"reason":"stream_replaced"}\n\n'
                return
            try:
                events = frame_hub.read("job:" + job_id, incarnation, cursor)
            except FrameCursorError:
                rows = (
                    await workspace.database["game_learning_live_frames"]
                    .find(
                        {
                            **scope,
                            "job_id": job_id,
                            "stream_id": incarnation,
                            "event.sequence": {"$gt": cursor},
                            "expires_at": {"$gt": datetime.now(timezone.utc)},
                        }
                    )
                    .sort("event.sequence", 1)
                    .limit(8)
                    .to_list(length=8)
                )
                events = [row["event"] for row in rows]
            for event in events:
                cursor = event["sequence"]
                yield f'id: {incarnation}:{cursor}\nevent: {event["event"]}\ndata: {json.dumps(event,separators=(",", ":"))}\n\n'
            if state["status"] in {"completed", "failed", "cancelled", "interrupted"}:
                yield "event: terminal\ndata: " + json.dumps(
                    {"job_id": job_id, "status": state["status"]}
                ) + "\n\n"
                return
            if not events:
                yield ": keepalive\n\n"
            await asyncio.sleep(0.1)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
