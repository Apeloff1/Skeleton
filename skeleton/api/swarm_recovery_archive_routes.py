"""Portable recovery archive endpoints for cold-restart swarm operations."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field

from skeleton.agents.swarm_recovery import SwarmRecoveryManager
from skeleton.api.swarm_recovery_service import activate_recovery

router = APIRouter(prefix="/swarm/recovery", tags=["swarm-recovery"])

MAX_ARCHIVE_BYTES = 8 * 1024 * 1024


class RecoveryArchiveImport(BaseModel):
    archive: dict[str, Any]
    max_bytes: int = Field(default=MAX_ARCHIVE_BYTES, ge=1024, le=MAX_ARCHIVE_BYTES)


def _state():
    from skeleton.api.server import get_state

    return get_state()


def _recovery() -> SwarmRecoveryManager:
    state = _state()
    with state._swarm_bind_lock:
        if state.swarm_recovery is None:
            state.swarm_recovery = SwarmRecoveryManager(max_checkpoints=16)
        return state.swarm_recovery


def _publish_recovery(staged: SwarmRecoveryManager) -> SwarmRecoveryManager:
    """Publish a fully verified recovery manager atomically with health readers."""
    state = _state()
    with state._swarm_bind_lock:
        state.swarm_recovery = staged
        return staged


def _encoded_size(archive: dict[str, Any]) -> int:
    try:
        return len(json.dumps(archive, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"archive is not JSON serializable: {exc}") from exc


@router.get("/archive")
def export_recovery_archive() -> dict[str, Any]:
    recovery = _recovery()
    archive = recovery.export_archive()
    size = _encoded_size(archive)
    if size > MAX_ARCHIVE_BYTES:
        raise HTTPException(status_code=413, detail="recovery archive exceeds export size limit")
    return {
        "archive": archive,
        "bytes": size,
        "status": asdict(recovery.status()),
    }


@router.post("/archive")
def import_recovery_archive(body: RecoveryArchiveImport) -> dict[str, Any]:
    size = _encoded_size(body.archive)
    if size > body.max_bytes:
        raise HTTPException(status_code=413, detail="recovery archive exceeds import size limit")

    try:
        staged = SwarmRecoveryManager.from_archive(body.archive)
    except (TypeError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=f"invalid recovery archive: {exc}") from exc

    staged = _publish_recovery(staged)
    return {
        "imported": True,
        "bytes": size,
        "status": asdict(staged.status()),
    }


@router.get("/catalog")
def recovery_catalog() -> dict[str, Any]:
    recovery = _recovery()
    runtime = [
        {"sequence": item.sequence, "created_at": item.created_at, "checksum": item.checksum}
        for item in recovery.store.history()
    ]
    tenant = [
        {"sequence": item.sequence, "created_at": item.created_at, "checksum": item.checksum}
        for item in recovery.tenant_store.history()
    ]
    return {"runtime": runtime, "tenant": tenant, "status": asdict(recovery.status())}


@router.post("/activate/{sequence}")
def activate_recovery_checkpoint(sequence: int = Path(ge=1)) -> dict[str, Any]:
    recovery = _recovery()
    try:
        result = activate_recovery(_state(), recovery, sequence)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=f"recovery activation rejected: {exc}") from exc
    return {
        "activated": True,
        "sequence": result.sequence,
        "tenant_source": result.tenant_source,
        "tenant_repair": result.tenant_repair,
        "status": asdict(recovery.status()),
    }
