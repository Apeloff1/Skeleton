"""Recovered GameForge polish surface with current project/source authority.

The archival API performed installation-wide writes and cleared stale markers.
This replacement never grants build, release, or native verification authority.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pymongo import ReturnDocument
from starlette.requests import ClientDisconnect

from core.forge_quality_contract import artifact_text, checked_json, compatible_rewrite, source_digest
from core.forge_validator import SIM_STAGES
from routes.game_kb import _STAGE_ART
from routes.playable import PlayableModelFailure, _db
from routes.playable_access import _GuardedPrivateProjectRoute, assert_project_access, reauthorize_project_context, project_router
from routes.quality import MIN_QUALITY
from routes.quality_polish import MAX_POLISH_PASSES, polish_pass

_MAX_WIRE_BYTES = 192 * 1024


class _BoundedPolishRoute(_GuardedPrivateProjectRoute):
    """Bound the actual HTTP body before the legacy admission reads JSON."""

    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            def reject(status: int):
                return JSONResponse(
                    {"detail": "Invalid or oversized polish request"},
                    status_code=status, headers={"Cache-Control": "private, no-store"},
                )

            length = request.headers.getlist("content-length")
            if length and (
                len(length) != 1 or not length[0].isascii() or not length[0].isdecimal()
                or len(length[0]) > 6
            ):
                return reject(400)
            if length and int(length[0]) > _MAX_WIRE_BYTES:
                return reject(413)
            coding = request.headers.get("content-encoding", "identity").lower()
            if coding != "identity":
                return reject(415)
            data = bytearray()
            try:
                async for chunk in request.stream():
                    if len(data) + len(chunk) > _MAX_WIRE_BYTES:
                        return reject(413)
                    data.extend(chunk)
            except ClientDisconnect:
                return reject(400)
            if length and int(length[0]) != len(data):
                return reject(400)
            captured = bytes(data)
            if captured:
                try:
                    checked_json(captured.decode("utf-8"), maximum=_MAX_WIRE_BYTES)
                except (UnicodeError, ValueError):
                    return reject(400)
            # Replay the admitted bytes once through the public Request contract;
            # dependency parsing and the endpoint receive the same request body.
            sent = False

            async def receive():
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": captured, "more_body": False}
                return await request.receive()

            return await original(Request(request.scope, receive=receive))

        return handler


router = project_router(
    prefix="/api/polish", tags=["polish"], route_class=_BoundedPolishRoute,
)


async def _run_polish(kind: str, content, *, simulate: bool, max_passes: int) -> dict:
    try:
        artifact_text(content)
    except ValueError:
        raise HTTPException(422, "Artifact is not complete bounded JSON") from None
    try:
        return await polish_pass(kind, content, simulate=simulate, max_passes=max_passes)
    except PlayableModelFailure as exc:
        # An uncertain engine dispatch is not a new retry authorization.
        raise exc.http_error() from None


@router.post("/artifact")
async def polish_inline(
    request: Request, simulate: bool = Query(False),
    max_passes: int = Query(MAX_POLISH_PASSES, ge=1, le=10),
):
    try:
        body = checked_json((await request.body()).decode("utf-8"), maximum=_MAX_WIRE_BYTES)
    except (UnicodeError, ValueError):
        raise HTTPException(422, "Invalid polish request") from None
    if type(body) is not dict or set(body) != {"kind", "content"}:
        raise HTTPException(422, "Expected kind and content")
    kind = body["kind"]
    if type(kind) is not str or not 1 <= len(kind) <= 128 or not kind.strip():
        raise HTTPException(422, "Invalid artifact kind")
    await reauthorize_project_context(mutate=True)
    simulation_required = any(
        label in kind.lower() for label in ("physic", "tileset", "cinematic", "camera", "procedural")
    )
    result = await _run_polish(
        kind, body["content"], simulate=simulate or simulation_required, max_passes=max_passes,
    )
    return {"kind": kind, "gate": MIN_QUALITY, **result, "persisted": False}


@router.post("/{pid}/stage/{stage}")
async def polish_game_stage(
    pid: str, stage: str, simulate: bool = Query(False),
    max_passes: int = Query(MAX_POLISH_PASSES, ge=1, le=10),
):
    key = _STAGE_ART.get(stage)
    if key is None:
        raise HTTPException(422, "Unknown forge stage")
    await assert_project_access(pid, mutate=True)
    row = await _db.game_kb.find_one({"game_id": pid}, {"_id": 0, "artifacts": 1})
    artifacts = row.get("artifacts") if row else None
    if type(artifacts) is not dict or key not in artifacts:
        raise HTTPException(404, "Forge artifact not found")
    original = artifacts[key]
    try:
        prior_text, prior_value = artifact_text(original)
    except ValueError:
        raise HTTPException(422, "Stored artifact is not complete bounded JSON") from None

    result = await _run_polish(
        stage, original, simulate=simulate or stage in SIM_STAGES, max_passes=max_passes,
    )
    response = {
        "game_id": pid, "stage": stage, "artifact": key, "gate": MIN_QUALITY,
        **{name: value for name, value in result.items() if name != "content"},
        "persisted": False,
    }
    if not (result.get("passed") is True and result.get("audit_complete") is True):
        return response

    try:
        candidate_text, candidate = artifact_text(result["content"])
        if type(original) in (dict, list):
            candidate_text, candidate = artifact_text(candidate)
    except (KeyError, ValueError):
        raise HTTPException(409, "Polish source cannot be verified") from None
    if (
        not compatible_rewrite(prior_value, candidate)
        or result.get("source_sha256") != source_digest(candidate_text)
        or candidate_text == prior_text
    ):
        return response

    await assert_project_access(pid, mutate=True)
    # Preserve the storage representation, and never erase dependency staleness
    # or promote a model observation to a ship/release decision.
    replacement = candidate_text if type(original) is str else candidate
    receipt = {
        "at": datetime.now(timezone.utc).isoformat(),
        "previous_source_sha256": source_digest(prior_text),
        "source_sha256": source_digest(candidate_text),
        "score": result["score"], "passed": True,
        "audit_complete": True, "evidence_scope": "model-review-structural-proxy",
        "improved_by": result["improved_by"], "passes": result["passes"],
    }
    updated = await _db.game_kb.find_one_and_update(
        {
            "game_id": pid,
            # Expression equality compares the whole field rather than matching
            # a value found inside an array; literal prevents operator interpretation.
            "$expr": {"$eq": [f"$artifacts.{key}", {"$literal": original}]},
            "deleted": {"$ne": True}, "revoked": {"$ne": True},
            "rights_revoked": {"$ne": True},
            "state": {"$nin": ["deleted", "revoked", "archived", "withdrawn"]},
        },
        {"$set": {f"artifacts.{key}": replacement, f"polish.{key}": receipt}},
        projection={"_id": 0, f"polish.{key}": 1},
        return_document=ReturnDocument.AFTER,
        upsert=False,
    )
    if updated is None:
        raise HTTPException(409, "Forge artifact changed or is no longer available")
    observed = (updated.get("polish") or {}).get(key)
    if not isinstance(observed, dict) or observed.get("source_sha256") != receipt["source_sha256"]:
        raise HTTPException(409, "Polish publication could not be confirmed")
    return {**response, "persisted": True}
