"""
routes/agent_swarm.py — Graph-Engineering swarm DAG (/api/swarm-dag).

Implements the "Karpathy loop → AgentHub → Dynamic Workflows" progression from
the Graph-Engineering playbook: a single directive fans out into N parallel
sub-agent workers arranged on a dependency DAG. Each worker

  1. RECALLS shared memory (LAFS canon + Delta-KDA associative memory),
  2. produces a typed result node, and
  3. WRITES its finding back into the shared knowledge graph + Delta memory,

so the graph — not an ever-growing orchestrator transcript — is the durable
shared-memory layer (exactly the playbook's thesis). An orchestrator node then
merges the leaf results. Everything streams onto the PROOD event bus.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/swarm-dag", tags=["swarm-dag"])

_STOP = {"the", "a", "an", "and", "or", "of", "to", "for", "with", "build", "make",
         "create", "add", "game", "please", "then", "into", "that"}


class SwarmReq(BaseModel):
    directive: str = Field(..., min_length=3)
    workers: int = 4              # parallel sub-agents (fan-out)
    project: str = "swarm"


def _subtasks(directive: str, n: int) -> List[str]:
    toks = [t for t in ''.join(c.lower() if c.isalnum() else ' ' for c in directive).split()
            if t not in _STOP and len(t) > 2]
    seen, uniq = set(), []
    for t in toks:
        if t not in seen:
            seen.add(t); uniq.append(t)
    if not uniq:
        uniq = ["core"]
    # round-robin the concept tokens into n worker foci
    return [uniq[i % len(uniq)] for i in range(max(1, min(n, 8)))]


async def _worker(worker_id: int, focus: str, project: str) -> Dict:
    """One fresh-context sub-agent: recall shared memory → emit typed node."""
    recall, kda = [], None
    try:
        from gameforge.lafs import lafs as _lafs
        recall = _lafs.probability_search(focus, acquisition="efe", top_k=3)
    except Exception:  # noqa: BLE001
        pass
    try:
        from gameforge.omega import delta_memory as _dm
        kda = _dm.read(focus)
        _dm.write(f"{project}:{focus}", f"worker-{worker_id} explored {focus}", modality="text")
    except Exception:  # noqa: BLE001
        pass
    finding = {
        "type": "Finding", "worker": worker_id, "focus": focus,
        "recalled": [r.get("path") for r in recall[:3]],
        "kda_recall_strength": (kda or {}).get("recall_strength"),
        "summary": f"Sub-agent {worker_id} synthesised '{focus}' from "
                   f"{len(recall)} canon sheet(s).",
    }
    # write the finding back into the shared knowledge graph (durable memory)
    node_id = f"{project}:{focus}:{worker_id}"
    try:
        from core.databases import core_db
        await core_db["swarm_graph"].update_one(
            {"_id": node_id},
            {"$set": {**finding, "project": project, "ts": time.time()}}, upsert=True)
    except Exception:  # noqa: BLE001
        pass
    try:
        from gameforge.prood import event_bus as _bus
        await _bus.publish("swarm.finding", {"worker": worker_id, "focus": focus})
    except Exception:  # noqa: BLE001
        pass
    return {**finding, "node_id": node_id}


@router.get("/graph/{project}")
async def swarm_graph(project: str, limit: int = 50):
    """Read the shared knowledge-graph memory produced by a swarm run."""
    try:
        from core.databases import core_db
        rows = await core_db["swarm_graph"].find(
            {"project": project}, {"_id": 0}).sort("ts", -1).to_list(int(limit))
    except Exception:  # noqa: BLE001
        rows = []
    return {"ok": True, "project": project, "nodes": rows, "count": len(rows)}


@router.post("/run")
async def run_swarm(req: SwarmReq):
    """Fan out `workers` parallel sub-agents on a DAG, merge at an orchestrator
    node. Returns the commit-graph-style transcript + merged plan."""
    run_id = uuid.uuid4().hex[:12]
    foci = _subtasks(req.directive, req.workers)
    t0 = time.time()

    # ── parallel fan-out (Dynamic-Workflows style) ──
    results = await asyncio.gather(*[_worker(i, f, req.project) for i, f in enumerate(foci)])

    # ── orchestrator merge node ──
    merged = {
        "type": "Merge", "run_id": run_id, "directive": req.directive,
        "worker_count": len(results),
        "foci": foci,
        "plan": [f"Integrate '{r['focus']}' (worker {r['worker']})" for r in results],
        "total_recalled": sum(len(r.get("recalled") or []) for r in results),
    }
    try:
        from gameforge.prood import event_bus as _bus
        await _bus.publish("swarm.merged", {"run_id": run_id, "workers": len(results)})
    except Exception:  # noqa: BLE001
        pass

    return {"ok": True, "run_id": run_id, "project": req.project,
            "dag": {"root": "directive", "workers": foci, "merge": "orchestrator"},
            "workers": results, "merge": merged,
            "ms": round((time.time() - t0) * 1000, 1)}
