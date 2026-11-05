"""
routes/agent_swarm.py — Graph-Engineering swarm DAG (/api/swarm-dag).

A scoped directive fans out into bounded parallel sub-agent workers. Each
worker reads only account-owned prior graph findings, publishes its finding to
the account-owned graph, and contributes to an acknowledged merge receipt.
The shared LAFS and Delta-KDA memories have no tenant authorization contract
and are deliberately not read here. Event-bus notifications carry only
opaque run and owner-scope references, not private finding contents.
"""
from __future__ import annotations

import asyncio
import hashlib
import threading
import time
import uuid
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from routes.gameforge_auth import require_authenticated_identity

router = APIRouter(prefix="/api/swarm-dag", tags=["swarm-dag"])

_STOP = {"the", "a", "an", "and", "or", "of", "to", "for", "with", "build", "make",
         "create", "add", "game", "please", "then", "into", "that"}



def _project_id(project: str) -> str:
    if (
        not isinstance(project, str)
        or not 1 <= len(project.strip()) <= 200
        or project != project.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in project)
    ):
        raise ValueError("project must be bounded printable non-empty text")
    return project


def _owner_scope(identity: dict) -> tuple[dict[str, str], str]:
    """Require a normalized account/tenant principal before any graph access.

    A hash is used only for collision-resistant storage keys; database
    authorization always matches both original owner and tenant fields.
    """
    if not isinstance(identity, dict) or identity.get("dev_mode"):
        raise HTTPException(401, "Authentication required for private swarm work")
    tenant, owner = identity.get("tenant_id"), identity.get("owner_id")
    if any(
        not isinstance(value, str)
        or not 1 <= len(value) <= 256
        or value != value.strip()
        or value == "anonymous"
        or any(ord(ch) < 32 or 0xD800 <= ord(ch) <= 0xDFFF for ch in value)
        for value in (tenant, owner)
    ):
        raise HTTPException(403, "Swarm graph identity is unavailable")
    key = hashlib.sha256((tenant + "\x00" + owner).encode("utf-8")).hexdigest()
    return {"tenant_id": tenant, "owner_id": owner}, key




class SwarmReq(BaseModel):
    directive: str = Field(..., min_length=3, max_length=10000)
    workers: int = Field(4, ge=1, le=32)              # parallel sub-agents (fan-out)
    project: str = Field("swarm", min_length=1, max_length=200)

    @field_validator("project")
    @classmethod
    def valid_project(cls, value: str) -> str:
        return _project_id(value)


def _subtasks(directive: str, n: int) -> List[str]:
    """Honor every admitted worker seat without creating hidden fan-out."""
    if not isinstance(directive, str) or not 3 <= len(directive) <= 10000:
        raise ValueError("directive must be 3 to 10000 characters")
    if type(n) is not int or not 1 <= n <= 32:
        raise ValueError("worker count must be an integer in [1, 32]")
    tokens = [
        token for token in "".join(
            char.lower() if char.isalnum() else " " for char in directive
        ).split()
        if token not in _STOP and len(token) > 2
    ]
    unique = list(dict.fromkeys(tokens)) or ["core"]
    return [unique[i % len(unique)][:128] for i in range(n)]


async def _worker(worker_id: int, focus: str, project: str, run_id: str, identity: dict) -> Dict:
    """Generate one account-bound finding and require acknowledged graph custody."""
    scope, owner_key = _owner_scope(identity)
    # Legacy LAFS and Delta-KDA are shared process-wide and do not expose an
    # owner/tenant filter. Never consult them for a private user's graph.
    # Reuse only already-owned graph findings, with a fixed 3-row read bound.
    recalled: list[str] = []
    recall_available = False
    try:
        from core.databases import core_db
        cursor = core_db["swarm_graph"].find(
            {"project": project, "type": "Finding", **scope},
            {"_id": 0, "focus": 1},
        ).sort("ts", -1)
        rows = await cursor.to_list(3)
        recalled = [
            row["focus"][:128] for row in rows
            if isinstance(row, dict) and isinstance(row.get("focus"), str)
        ][:3]
        recall_available = True
    except Exception:
        # The durable finding still proceeds without optional context. A read
        # outage is flagged in the result; it never grants cross-tenant reads.
        pass
    finding = {
        "type": "Finding",
        "worker": worker_id,
        "focus": focus,
        "recalled": recalled,
        "kda_recall_strength": None,
        "summary": f"Sub-agent {worker_id} prepared '{focus}' with {len(recalled)} private graph finding(s).",
        "recall_available": recall_available,
        "memory_mode": "owner_scoped_graph",
        "run_id": run_id,
    }
    node_id = f"{owner_key}:{project}:{run_id}:worker:{worker_id}"
    try:
        from core.databases import core_db
        outcome = await core_db["swarm_graph"].update_one(
            {"_id": node_id, **scope},
            {"$set": {**finding, "project": project, **scope, "ts": time.time()}},
            upsert=True,
        )
        if getattr(outcome, "acknowledged", False) is not True:
            raise RuntimeError("graph write was not acknowledged")
    except Exception as exc:
        raise RuntimeError("swarm finding was not durably stored") from exc

    try:
        from gameforge.prood import event_bus as _bus
        await _bus.publish("swarm.finding", {
            "worker": worker_id, "run_id": run_id, "owner_scope": owner_key,
        })
    except Exception:  # telemetry not a source of durable graph authority
        pass
    return {**finding, "node_id": node_id, "persisted": True}


@router.get("/graph/{project}")
async def swarm_graph(
    project: str,
    limit: int = 50,
    identity: dict = Depends(require_authenticated_identity),
):
    """Query only this account's graph, denying unowned legacy records."""
    scope, _owner_key = _owner_scope(identity)
    try:
        _project_id(project)
    except ValueError as exc:
        raise HTTPException(422, "invalid project identity") from exc
    if type(limit) is not int or not 1 <= limit <= 100:
        raise HTTPException(422, "graph limit must be an integer in [1, 100]")
    try:
        from core.databases import core_db
        rows = await core_db["swarm_graph"].find(
            {"project": project, **scope}, {"_id": 0},
        ).sort("ts", -1).to_list(limit)
    except Exception as exc:
        raise HTTPException(503, "swarm graph storage unavailable") from exc
    return {"ok": True, "project": project, "nodes": rows, "count": len(rows)}


MAX_CONCURRENT_SWARM_RUNS = 8
# Thread-backed, nonblocking admission avoids sharing asyncio semaphores
# across ASGI workers and prevents unbounded 32-worker fanout per request.
_RUN_ADMISSION = threading.BoundedSemaphore(MAX_CONCURRENT_SWARM_RUNS)


@router.post("/run")
async def run_swarm(
    req: SwarmReq,
    identity: dict = Depends(require_authenticated_identity),
):
    """Admit bounded private swarm work; always release capacity."""
    scope, owner_key = _owner_scope(identity)
    try:
        _project_id(req.project)
    except ValueError as exc:
        raise HTTPException(422, "invalid project identity") from exc
    if not _RUN_ADMISSION.acquire(blocking=False):
        raise HTTPException(503, "swarm worker admission at capacity")
    try:
        return await _run_swarm_scoped(req, scope, owner_key)
    finally:
        _RUN_ADMISSION.release()


async def _run_swarm_scoped(req: SwarmReq, scope: dict[str, str], owner_key: str):
    """Only account-owned, acknowledged graph writes make a run successful."""
    run_id = uuid.uuid4().hex
    foci = _subtasks(req.directive, req.workers)
    start = time.monotonic()
    attempts = await asyncio.gather(*[
        _worker(index, focus, req.project, run_id, scope)
        for index, focus in enumerate(foci)
    ], return_exceptions=True)
    def _bound_receipt(index, result):
        return (
            isinstance(result, dict)
            and result.get("persisted") is True
            and result.get("run_id") == run_id
            and result.get("node_id") == f"{owner_key}:{req.project}:{run_id}:worker:{index}"
        )

    successful = [
        result for index, result in enumerate(attempts)
        if _bound_receipt(index, result)
    ]
    failed_workers = [
        index for index, result in enumerate(attempts)
        if not _bound_receipt(index, result)
    ]
    if failed_workers:
        return {
            "ok": False, "status": "partial_failure", "run_id": run_id,
            "project": req.project, "requested_workers": req.workers,
            "persisted_workers": len(successful), "failed_workers": failed_workers,
            "workers": successful, "merge": None,
        }

    merged = {
        "type": "Merge", "run_id": run_id, "directive": req.directive,
        "worker_count": len(successful), "foci": foci,
        "plan": [
            f"Integrate '{row['focus']}' (worker {row['worker']})"
            for row in successful
        ],
        "total_recalled": sum(len(row.get("recalled") or []) for row in successful),
    }
    try:
        from core.databases import core_db
        outcome = await core_db["swarm_graph"].update_one(
            {"_id": f"{owner_key}:{req.project}:{run_id}:merge", **scope},
            {"$set": {**merged, "project": req.project, **scope, "ts": time.time()}},
            upsert=True,
        )
        if getattr(outcome, "acknowledged", False) is not True:
            raise RuntimeError("merge was not acknowledged")
    except Exception:
        return {
            "ok": False, "status": "merge_not_durable", "run_id": run_id,
            "project": req.project, "requested_workers": req.workers,
            "persisted_workers": len(successful), "workers": successful,
            "merge": None,
        }
    try:
        from gameforge.prood import event_bus as _bus
        await _bus.publish("swarm.merged", {
            "run_id": run_id, "workers": len(successful), "owner_scope": owner_key,
        })
    except Exception:
        pass
    return {
        "ok": True, "status": "durable", "run_id": run_id, "project": req.project,
        "dag": {"root": "directive", "workers": foci, "merge": "orchestrator"},
        "workers": successful, "merge": {**merged, "persisted": True},
        "ms": round((time.monotonic() - start) * 1000, 1),
    }
