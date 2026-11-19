"""Authenticated cockpit for fictional minimap, survey approval, and event commit."""
from __future__ import annotations

import re
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from core.frontier_cockpit import DEMO_WORLD, CockpitError, get_service
from routes.gameforge_auth import require_role

router = APIRouter(prefix="/game-frontier-cockpit", tags=["Game Frontier cockpit"])
_WORLD = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_ACTOR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .@_+\-]{1,63}$")


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ActorBody(Body):
    actor: str | None = Field(default=None, max_length=64)


class PanBody(ActorBody):
    dx: int = Field(ge=-1, le=1)
    dy: int = Field(ge=-1, le=1)


class ZoomBody(ActorBody):
    direction: int = Field(ge=-1, le=1)


class LayerBody(ActorBody):
    layer_id: str = Field(min_length=1, max_length=64)


class PortalBody(ActorBody):
    portal_id: str = Field(min_length=1, max_length=64)


class StationBody(Body):
    control_id: str = Field(min_length=1, max_length=64)
    x: float
    y: float
    z: float


class BaselineBody(ActorBody):
    baseline_id: str = Field(min_length=1, max_length=64)
    epoch: str = Field(min_length=1, max_length=64)
    instrument: str = Field(min_length=1, max_length=80)
    surveyor: str = Field(min_length=1, max_length=80)
    notes: str = Field(default="", max_length=500)
    stations: list[StationBody] = Field(min_length=1, max_length=64)


class SightingBody(ActorBody):
    sighting_id: str = Field(min_length=1, max_length=64)
    baseline_id: str = Field(min_length=1, max_length=64)
    control_id: str = Field(min_length=1, max_length=64)
    bearing_deg: float
    distance_m: float
    uncertainty_m: float


class FixBody(ActorBody):
    sighting_ids: list[str] = Field(min_length=1, max_length=32)


class ProposeBody(ActorBody):
    preset: str | None = Field(default=None, max_length=64)
    signal: str = Field(min_length=1, max_length=64)
    current_value: float
    page_id: str | None = Field(default=None, max_length=128)
    priority: int | None = Field(default=None, ge=-100, le=100)
    comparison: str | None = Field(default=None, max_length=32)
    threshold: float | None = None
    action_kind: str | None = Field(default=None, max_length=64)
    action_channel: str | None = Field(default=None, max_length=32)
    action_target: str | None = Field(default=None, max_length=128)
    action_value: str | None = Field(default=None, max_length=1024)
    cooldown_ms: int | None = Field(default=None, ge=0, le=86_400_000)


class CommitBody(ActorBody):
    expected_canon_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


def _world(world_id: str) -> str:
    if _WORLD.fullmatch(world_id) is None:
        raise HTTPException(422, detail={"code": "invalid_world", "message": "Unknown fictional world id."})
    return world_id


def _actor(user: dict, stated: str | None, *, write: bool) -> str:
    if isinstance(user, dict) and not user.get("dev_mode"):
        email = str(user.get("email") or "").strip()
        role = user.get("role")
        if write and role not in {"editor", "admin"}:
            raise HTTPException(403, detail={
                "code": "operator_role_required",
                "message": "An editor must approve this fictional survey or event.",
            })
        if not email or email.lower() == "anonymous":
            raise HTTPException(401, detail={
                "code": "operator_identity_required",
                "message": "Sign in so the approval records your operator identity.",
            })
        if stated and stated.strip() != email:
            raise HTTPException(403, detail={
                "code": "operator_mismatch",
                "message": "Operator identity must match the signed-in account.",
            })
        return email
    if not write:
        return "viewer"
    name = (stated or "").strip()
    if _ACTOR.fullmatch(name) is None or name.lower() == "anonymous":
        raise HTTPException(422, detail={
            "code": "operator_name_required",
            "message": "Enter the operator name that will be recorded on this approval.",
        })
    return name


def _call(fn):
    try:
        return fn()
    except CockpitError as exc:
        code = "cockpit_rejected" if exc.status == 409 else "cockpit_invalid"
        if exc.status == 404:
            code = "unknown_world"
        raise HTTPException(exc.status, detail={"code": code, "message": str(exc)}) from exc


def _now() -> int:
    return time.time_ns() // 1_000_000


def _annotate(user: dict, payload: dict) -> dict:
    payload["viewer"] = {
        "actor": _actor(user, None, write=False) if not user.get("dev_mode") else "",
        "role": user.get("role"),
        "can_commit": user.get("role") in {"editor", "admin"} or bool(user.get("dev_mode")),
    }
    return payload


@router.get("/worlds/{world_id}")
async def read_world(world_id: str, user=Depends(require_role("viewer"))):
    world = _world(world_id)
    return _annotate(user, _call(lambda: get_service().view(world)))


@router.post("/worlds/{world_id}/camera/pan")
async def pan_camera(world_id: str, body: PanBody, user=Depends(require_role("editor"))):
    _actor(user, body.actor, write=False)
    return _annotate(user, _call(lambda: get_service().pan(_world(world_id), body.dx, body.dy)))


@router.post("/worlds/{world_id}/camera/zoom")
async def zoom_camera(world_id: str, body: ZoomBody, user=Depends(require_role("editor"))):
    _actor(user, body.actor, write=False)
    if body.direction not in (-1, 1):
        raise HTTPException(422, detail={"code": "invalid_zoom", "message": "Zoom by one level in or out."})
    return _annotate(user, _call(lambda: get_service().zoom(_world(world_id), body.direction)))


@router.post("/worlds/{world_id}/camera/layer")
async def jump_layer(world_id: str, body: LayerBody, user=Depends(require_role("editor"))):
    _actor(user, body.actor, write=False)
    return _annotate(user, _call(lambda: get_service().jump(_world(world_id), body.layer_id)))


@router.post("/worlds/{world_id}/camera/portal")
async def travel_portal(world_id: str, body: PortalBody, user=Depends(require_role("editor"))):
    _actor(user, body.actor, write=False)
    return _annotate(user, _call(lambda: get_service().portal(_world(world_id), body.portal_id)))


@router.post("/worlds/{world_id}/baseline")
async def save_baseline(world_id: str, body: BaselineBody, user=Depends(require_role("editor"))):
    _actor(user, body.actor, write=True)
    return _annotate(user, _call(lambda: get_service().save_baseline(_world(world_id), body.model_dump())))


@router.post("/worlds/{world_id}/baselines/{baseline_id}/approve")
async def approve_baseline(world_id: str, baseline_id: str, body: ActorBody,
                           user=Depends(require_role("editor"))):
    actor = _actor(user, body.actor, write=True)
    return _annotate(user, _call(lambda: get_service().approve_baseline(_world(world_id), baseline_id, actor)))


@router.post("/worlds/{world_id}/sightings")
async def save_sighting(world_id: str, body: SightingBody, user=Depends(require_role("editor"))):
    _actor(user, body.actor, write=True)
    return _annotate(user, _call(lambda: get_service().save_sighting(_world(world_id), body.model_dump())))


@router.post("/worlds/{world_id}/sightings/{sighting_id}/approve")
async def approve_sighting(world_id: str, sighting_id: str, body: ActorBody,
                           user=Depends(require_role("editor"))):
    actor = _actor(user, body.actor, write=True)
    return _annotate(user, _call(lambda: get_service().approve_sighting(_world(world_id), sighting_id, actor)))


@router.post("/worlds/{world_id}/fixes")
async def solve_fix(world_id: str, body: FixBody, user=Depends(require_role("editor"))):
    actor = _actor(user, body.actor, write=True)
    return _annotate(user, _call(lambda: get_service().solve(_world(world_id), body.sighting_ids, actor)))


@router.post("/worlds/{world_id}/events/propose")
async def propose_event(world_id: str, body: ProposeBody, user=Depends(require_role("editor"))):
    actor = _actor(user, body.actor, write=True)
    return _annotate(user, _call(lambda: get_service().propose(_world(world_id), body.model_dump(), actor, _now())))


@router.post("/worlds/{world_id}/events/{proposal_id}/commit")
async def commit_event(world_id: str, proposal_id: str, body: CommitBody,
                       user=Depends(require_role("editor"))):
    actor = _actor(user, body.actor, write=True)

    def _commit():
        service = get_service()
        world = _world(world_id)
        service.authorize_operator(world, actor)
        return service.commit(world, proposal_id, body.expected_canon_digest, actor, _now())

    return _annotate(user, _call(_commit))


@router.get("/worlds")
async def list_worlds(user=Depends(require_role("viewer"))):
    _ = user
    return {"worlds": [DEMO_WORLD], "fictional_only": True, "device_geolocation": False}
