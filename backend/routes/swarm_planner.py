"""
Hierarchical Swarm Planner API — Backlog I.3.

Prefixed /api/galaxy-studio/swarm/planner/* to live under the existing swarm hub.
Builds a director→leads→platoons→workers task DAG with provable 100% coverage,
dependency ordering (topological waves) and deterministic seeds.
"""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core import swarm_planner as planner
from core import swarm_scheduler as scheduler

router = APIRouter(prefix="/api/galaxy-studio/swarm/planner", tags=["swarm-planner"])


class PlanReq(BaseModel):
    build_id: str = Field(..., min_length=1)
    phases: list[str] | None = None
    objectives: list[str] | None = None
    deps: dict[str, list[str]] | None = None
    seed: int = 0
    platoon_size: int = 5
    game_ctx: dict[str, Any] = Field(default_factory=dict)


@router.post("/plan")
def make_plan(req: PlanReq) -> dict:
    try:
        return planner.plan_build(
            build_id=req.build_id,
            phases=req.phases,
            objectives=req.objectives,
            deps=req.deps,
            seed=req.seed,
            platoon_size=req.platoon_size,
            game_ctx=req.game_ctx,
        )
    except ValueError:
        raise HTTPException(400, "invalid swarm planning request")


class VerifyReq(BaseModel):
    plan: dict[str, Any]


@router.post("/verify")
def verify(req: VerifyReq) -> dict:
    nodes = req.plan.get("nodes")
    edges = req.plan.get("edges")
    waves = req.plan.get("waves")
    if (
        not isinstance(nodes, list) or not 1 <= len(nodes) <= 2_048
        or not isinstance(edges, list) or len(edges) > 10_000
        or not isinstance(waves, list) or len(waves) > planner.MAX_PHASES
        or any(not isinstance(node, dict) for node in nodes)
        or any(not isinstance(edge, dict) for edge in edges)
        or any(not isinstance(wave, dict) for wave in waves)
    ):
        raise HTTPException(422, "invalid bounded swarm plan structure")
    try:
        return planner.verify_plan(req.plan)
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise HTTPException(422, "invalid swarm plan structure") from exc


class ExecuteReq(BaseModel):
    build_id: str = Field(..., min_length=1)
    phases: list[str] | None = None
    objectives: list[str] | None = None
    deps: dict[str, list[str]] | None = None
    seed: int = 0
    platoon_size: int = 5
    rounds: int = 2
    game_ctx: dict[str, Any] = Field(default_factory=dict)
    persist: bool = True


@router.post("/execute")
def execute(req: ExecuteReq) -> dict:
    """Plan + run the DAG LIVE: walk the topological waves and run the real
    per-phase platoons, passing each phase its upstream handoffs."""
    try:
        return scheduler.execute_schedule(
            build_id=req.build_id, phases=req.phases, objectives=req.objectives,
            deps=req.deps, seed=req.seed, platoon_size=req.platoon_size,
            game_ctx=req.game_ctx, rounds=req.rounds, persist=req.persist,
        )
    except ValueError:
        raise HTTPException(400, "invalid swarm execution request")
    except RuntimeError as exc:
        raise HTTPException(503, "swarm execution custody unavailable") from exc


@router.get("/runs/{build_id}")
def runs(build_id: str, limit: int = 10) -> dict:
    try:
        return {"build_id": build_id, "runs": scheduler.get_runs(build_id, limit)}
    except ValueError as exc:
        raise HTTPException(422, "invalid swarm schedule history query") from exc
    except RuntimeError as exc:
        raise HTTPException(503, "swarm schedule history unavailable") from exc


@router.get("/diff/{build_id}")
def diff(build_id: str, hash_a: str | None = None, hash_b: str | None = None) -> dict:
    """Compare only the requested durable plan receipts, never substituted runs."""
    try:
        return scheduler.diff_runs(build_id, hash_a, hash_b)
    except ValueError as exc:
        raise HTTPException(422, "invalid swarm schedule diff query") from exc
    except RuntimeError as exc:
        raise HTTPException(503, "swarm schedule history unavailable") from exc


@router.get("/plan-diff")
def plan_diff(phases: int = 12, platoon_size: int = 5,
              seed_a: int = 0, seed_b: int = 1, build_id: str = "diff") -> dict:
    """Deterministic replay/diff: plan the SAME phases under two seeds and show
    how the platoon worker assignments shuffle — no live run required."""
    if type(phases) is not int or not 1 <= phases <= 100:
        raise HTTPException(422, "phase count must be between 1 and 100")
    ph = [f"p{i:02d}" for i in range(1, phases + 1)]

    def _workers(seed: int) -> tuple[str, dict[str, list[str]]]:
        plan = planner.plan_build(build_id=build_id, phases=ph, seed=seed,
                                  platoon_size=platoon_size)
        wm = {n["phase_id"]: sorted(w.get("code") for w in (n.get("workers") or []))
              for n in plan["nodes"] if n["tier"] == "platoon"}
        return plan["plan_hash"], wm

    ha, wa = _workers(seed_a)
    hb, wb = _workers(seed_b)
    rows, stable = [], 0
    total = retained = 0
    for p in ph:
        sa, sb = set(wa.get(p, [])), set(wb.get(p, []))
        added, removed = sorted(sb - sa), sorted(sa - sb)
        union = len(sa | sb) or 1
        if not added and not removed:
            stable += 1
        total += len(sa | sb)
        retained += len(sa & sb)
        rows.append({
            "phase_id": p, "similarity": round(len(sa & sb) / union, 3),
            "kept": sorted(sa & sb), "added": added, "removed": removed,
            "unchanged": not added and not removed,
        })
    return {
        "seed_a": seed_a, "seed_b": seed_b, "plan_hash_a": ha, "plan_hash_b": hb,
        "same_seed": seed_a == seed_b, "phase_count": len(ph),
        "stable_phases": stable,
        "stability_pct": round(100 * retained / total, 1) if total else 0.0,
        "rows": rows,
    }


class BuildReq(BaseModel):
    build_id: str = Field(..., min_length=1)
    seed: int = 0
    platoon_size: int = 5
    rounds: int = 2


@router.post("/execute-build")
def execute_build(req: BuildReq) -> dict:
    """Run the live DAG for a REAL build: phases come from the canonical build
    ladder, genre/context from the galaxy_builds record."""
    try:
        return scheduler.execute_build(
            build_id=req.build_id, seed=req.seed,
            platoon_size=req.platoon_size, rounds=req.rounds,
        )
    except ValueError:
        raise HTTPException(400, "invalid swarm build request")
    except LookupError as exc:
        raise HTTPException(404, "canonical Galaxy build not found") from exc
    except RuntimeError as exc:
        raise HTTPException(503, "canonical Galaxy build authority unavailable") from exc


@router.post("/execute/async")
def execute_async(req: ExecuteReq) -> dict:
    """Async free-form execution (lifts the live phase cap)."""
    try:
        job_id = scheduler.start_async(
            "execute", build_id=req.build_id, phases=req.phases, objectives=req.objectives,
            deps=req.deps, seed=req.seed, platoon_size=req.platoon_size,
            game_ctx=req.game_ctx, rounds=req.rounds, persist=req.persist,
        )
    except ValueError as exc:
        raise HTTPException(422, "invalid swarm asynchronous job request") from exc
    except RuntimeError as exc:
        raise HTTPException(503, "swarm asynchronous admission unavailable") from exc
    return {"job_id": job_id, "status": "running"}


@router.post("/execute-build/async")
def execute_build_async(req: BuildReq) -> dict:
    """Async real-build execution — runs the full ladder without the online cap."""
    try:
        job_id = scheduler.start_async(
            "build", build_id=req.build_id, seed=req.seed,
            platoon_size=req.platoon_size, rounds=req.rounds,
        )
    except ValueError as exc:
        raise HTTPException(422, "invalid asynchronous real-build request") from exc
    except RuntimeError as exc:
        raise HTTPException(503, "asynchronous real-build admission unavailable") from exc
    return {"job_id": job_id, "status": "running"}


@router.get("/job/{job_id}")
async def job(job_id: str) -> dict:
    from routes.galaxy_studio_state import load_build

    try:
        j = scheduler.get_job(job_id)
    except RuntimeError as exc:
        raise HTTPException(503, "swarm job history unavailable") from exc
    if not j or await load_build(j.get("build_id", "")) is None:
        raise HTTPException(404, "unknown job")
    return j


@router.get("/preview")
def preview(build_id: str = "demo", phases: int = 12, seed: int = 0, platoon_size: int = 5) -> dict:
    """A compact ready-to-render plan for the UI (default 12 phases)."""
    phases = max(1, min(phases, 100))
    ph = [f"p{i:02d}" for i in range(1, phases + 1)]
    plan = planner.plan_build(build_id=build_id, phases=ph, seed=seed, platoon_size=platoon_size)
    plan["verification"] = planner.verify_plan(plan)
    return plan
