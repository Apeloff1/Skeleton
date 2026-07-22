"""
╔════════════════════════════════════════════════════════════════════════╗
║  SWARM SCHEDULER — turns a planner DAG into a LIVE execution schedule.  ║
║  ────────────────────────────────────────────────────────────────────  ║
║  Walks the Hierarchical Swarm Planner's topological waves and runs the  ║
║  real per-phase platoons (core.platoons.run_platoon) wave-by-wave:      ║
║                                                                        ║
║    • dependency ordering  — a phase only runs after ALL its upstream   ║
║      phases; it receives their merged handoffs as context.             ║
║    • parallel waves       — phases with no unmet deps share a wave.     ║
║    • deterministic        — same (seed, phases, deps) ⇒ same schedule. ║
║                                                                        ║
║  The pure ``run_with_executor`` core is DB-free and unit-testable; the ║
║  ``execute_schedule`` wrapper injects the real platoon executor and    ║
║  persists a run record.                                                 ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Callable

from core import swarm_planner as planner
from core.swarm_agents import SWARM_DOMAINS

# Online safety cap — bigger builds should go through an async pipeline.
MAX_LIVE_PHASES = 30

# Canonical Galaxy-Studio build stages (mirrors routes/snowball.py _LADDER order).
# These are the REAL phases a production build moves through, in dependency order.
BUILD_STAGES: list[str] = [
    "questionnaire", "spec", "world", "narrative", "mechanics", "physics",
    "procedural", "tileset", "assets", "qa", "build", "cinematics", "launch",
]

# agent_code → {legion_id, legion_name, category}
_CODE_META: dict[str, dict] = {}


def _code_meta() -> dict[str, dict]:
    if not _CODE_META:
        for a in SWARM_DOMAINS:
            code = a.get("agent_code")
            if code:
                _CODE_META[code] = {
                    "legion_id": a.get("legion_id"),
                    "legion_name": a.get("legion_name"),
                    "category": a.get("category"),
                    "agent": a.get("agent"),
                }
    return _CODE_META


def deps_from_plan(plan: dict) -> dict[str, list[str]]:
    """Reconstruct phase→upstream-deps from the plan's 'depends-on' edges."""
    deps: dict[str, list[str]] = {
        n["phase_id"]: [] for n in plan["nodes"] if n["tier"] == "platoon"
    }
    for e in plan.get("edges", []):
        if e.get("kind") == "depends-on":
            frm = e["from"].replace("platoon::", "")
            to = e["to"].replace("platoon::", "")
            if to in deps:
                deps[to].append(frm)
    return deps


# Executor signature: (phase_id, prev_handoff, rotation_idx, wave) -> result dict.
Executor = Callable[[str, str | None, int, int], dict]


def run_with_executor(plan: dict, executor: Executor) -> dict:
    """Walk the plan's waves in order, invoking ``executor`` per phase.

    Pure orchestration: no DB, no platoon internals — fully testable.
    Returns an execution summary with per-phase handoffs in wave order.
    """
    deps = deps_from_plan(plan)
    handoffs: dict[str, str] = {}
    phase_order: list[str] = []
    wave_summaries: list[dict] = []
    rotation = 0

    for wave in plan.get("waves", []):
        w_idx = wave["wave"]
        wave_phases = wave["phases"]
        wave_rows = []
        for phase in wave_phases:
            # merge upstream handoffs → this phase's incoming context
            up = [handoffs[d] for d in deps.get(phase, []) if handoffs.get(d)]
            prev_handoff = " || ".join(up)[:600] if up else None

            result = executor(phase, prev_handoff, rotation, w_idx) or {}
            rotation += 1
            handoffs[phase] = result.get("handoff", "") or ""
            phase_order.append(phase)
            wave_rows.append({
                "phase_id": phase,
                "wave": w_idx,
                "depends_on": deps.get(phase, []),
                "member_codes": [m.get("code") for m in result.get("members", [])],
                "member_count": len(result.get("members", [])),
                "whisper_count": result.get("whisper_count", 0),
                "utterances": len(result.get("transcript", [])),
                "handoff": handoffs[phase],
            })
        wave_summaries.append({
            "wave": w_idx,
            "phase_count": len(wave_phases),
            "phases": list(wave_phases),
            "rows": wave_rows,
        })

    executed = set(phase_order)
    planned = {n["phase_id"] for n in plan["nodes"] if n["tier"] == "platoon"}
    final = phase_order[-1] if phase_order else None
    return {
        "phases_executed": len(phase_order),
        "phases_planned": len(planned),
        "execution_complete": executed == planned,
        "missing": sorted(planned - executed),
        "wave_count": len(wave_summaries),
        "waves": wave_summaries,
        "final_handoff": handoffs.get(final, "") if final else "",
        "execution_order": phase_order,
    }


def execute_schedule(
    build_id: str,
    phases: list[str] | None = None,
    objectives: list[str] | None = None,
    deps: dict[str, list[str]] | None = None,
    seed: int = 0,
    platoon_size: int = 5,
    game_ctx: dict[str, Any] | None = None,
    rounds: int = 2,
    persist: bool = True,
) -> dict:
    """Plan + run the full DAG live via real platoons, persisting a run record."""
    game_ctx = dict(game_ctx or {})
    game_ctx.setdefault("seed", seed)

    plan = planner.plan_build(
        build_id=build_id, phases=phases, objectives=objectives,
        deps=deps, seed=seed, platoon_size=platoon_size, game_ctx=game_ctx,
    )
    if plan["phase_count"] > MAX_LIVE_PHASES:
        raise ValueError(
            f"{plan['phase_count']} phases exceeds the live cap of {MAX_LIVE_PHASES}; "
            "use a smaller slice or the async build pipeline"
        )

    verification = planner.verify_plan(plan)

    # Lazy import — keeps core.swarm_planner pure and avoids a DB import at module load.
    from core import platoons as platoons_mod

    def _executor(phase_id: str, prev_handoff: str | None, rotation_idx: int, _wave: int) -> dict:
        return platoons_mod.run_platoon(
            build_id=build_id, phase_id=phase_id, game_ctx=game_ctx,
            rotation_idx=rotation_idx, prev_handoff=prev_handoff,
            rounds=rounds, size=platoon_size, persist=persist,
        )

    execution = run_with_executor(plan, _executor)

    run = {
        "build_id": build_id,
        "seed": seed,
        "plan_hash": plan["plan_hash"],
        "coverage": plan["coverage"],
        "verification": verification,
        "critical_path_len": plan["critical_path_len"],
        "lead_count": plan["lead_count"],
        "rounds": rounds,
        "platoon_size": platoon_size,
        "created_at": time.time(),
        "execution": execution,
        "participation": participation_stats(execution),
    }

    if persist:
        try:
            from core.databases import get_sync_db
            col = get_sync_db()["swarm_schedule_runs"]
            col.create_index([("build_id", 1), ("created_at", -1)])
            col.insert_one(dict(run))
            run.pop("_id", None)
            # keep the collection bounded
            total = col.estimated_document_count()
            if total > 2000:
                old = col.find({}, {"_id": 1}).sort("created_at", 1).limit(total - 2000)
                ids = [d["_id"] for d in old]
                if ids:
                    col.delete_many({"_id": {"$in": ids}})
        except Exception:
            pass

    return run


def _run_member_map(run: dict) -> dict[str, list[str]]:
    """phase_id → sorted member codes, from a persisted run record."""
    out: dict[str, list[str]] = {}
    for wave in (run.get("execution") or {}).get("waves", []):
        for row in wave.get("rows", []):
            out[row["phase_id"]] = sorted(row.get("member_codes") or [])
    return out


def diff_runs(build_id: str, hash_a: str | None = None,
              hash_b: str | None = None, limit: int = 20) -> dict:
    """Compare two persisted runs of the same build (e.g. same seed vs a
    re-shuffle) and quantify how much the platoon assignments moved.

    If hashes are omitted the two MOST RECENT runs are diffed. Returns a
    per-phase membership delta plus an overall stability score.
    """
    runs = get_runs(build_id, limit=limit)
    if len(runs) < 2:
        return {"build_id": build_id, "error": "need at least two runs to diff",
                "runs_available": len(runs)}

    def _pick(h: str | None, fallback_idx: int) -> dict:
        if h:
            for r in runs:
                if r.get("plan_hash") == h:
                    return r
        return runs[fallback_idx]

    a = _pick(hash_a, 0)
    b = _pick(hash_b, 1)
    ma, mb = _run_member_map(a), _run_member_map(b)
    phases = sorted(set(ma) | set(mb))

    rows = []
    stable_phases = 0
    total_seats = moved_seats = 0
    for ph in phases:
        sa, sb = set(ma.get(ph, [])), set(mb.get(ph, []))
        added = sorted(sb - sa)
        removed = sorted(sa - sb)
        kept = sorted(sa & sb)
        union = len(sa | sb) or 1
        similarity = round(len(sa & sb) / union, 3)
        if not added and not removed:
            stable_phases += 1
        total_seats += len(sa | sb)
        moved_seats += len(added) + len(removed)
        rows.append({
            "phase_id": ph, "similarity": similarity,
            "kept": kept, "added": added, "removed": removed,
            "unchanged": not added and not removed,
        })

    stability = round(100 * (1 - moved_seats / max(1, total_seats)), 1)
    return {
        "build_id": build_id,
        "run_a": {"plan_hash": a.get("plan_hash"), "seed": a.get("seed"),
                  "created_at": a.get("created_at")},
        "run_b": {"plan_hash": b.get("plan_hash"), "seed": b.get("seed"),
                  "created_at": b.get("created_at")},
        "same_seed": a.get("seed") == b.get("seed"),
        "phase_count": len(phases),
        "stable_phases": stable_phases,
        "stability_pct": stability,
        "rows": rows,
    }


def get_runs(build_id: str, limit: int = 10) -> list[dict]:
    try:
        from core.databases import get_sync_db
        col = get_sync_db()["swarm_schedule_runs"]
        rows = list(col.find({"build_id": build_id}, {"_id": 0})
                    .sort("created_at", -1).limit(max(1, min(limit, 100))))
        return rows
    except Exception:
        return []


# ── participation / coverage stats ───────────────────────────────────────
def participation_stats(execution: dict) -> dict:
    """Who actually contributed, and how balanced is the load across legions?

    Derived from the execution's per-phase member assignments.
    """
    meta = _code_meta()
    seats: dict[str, int] = {}
    by_legion: dict[str, dict] = {}
    for wave in execution.get("waves", []):
        for row in wave.get("rows", []):
            for code in row.get("member_codes", []):
                if not code:
                    continue
                seats[code] = seats.get(code, 0) + 1
                m = meta.get(code, {})
                lid = m.get("legion_id") or "—"
                lg = by_legion.setdefault(lid, {
                    "legion_id": lid, "legion_name": m.get("legion_name") or lid,
                    "seats": 0, "agents": set(),
                })
                lg["seats"] += 1
                lg["agents"].add(code)

    legions = []
    for lg in by_legion.values():
        legions.append({
            "legion_id": lg["legion_id"], "legion_name": lg["legion_name"],
            "seats": lg["seats"], "distinct_agents": len(lg["agents"]),
        })
    legions.sort(key=lambda x: x["legion_id"])

    seat_vals = [l["seats"] for l in legions] or [0]
    spread = max(seat_vals) - min(seat_vals)
    total_seats = sum(seat_vals)
    # balance: 100% = perfectly even across the legions that participated.
    balance = round((1 - spread / max(total_seats, 1)) * 100, 1) if total_seats else 100.0

    top = sorted(seats.items(), key=lambda kv: -kv[1])[:8]
    top_agents = [
        {"code": c, "agent": meta.get(c, {}).get("agent"),
         "legion_name": meta.get(c, {}).get("legion_name"), "seats": n}
        for c, n in top
    ]
    return {
        "distinct_agents": len(seats),
        "total_seats": total_seats,
        "legions": legions,
        "legion_balance_pct": balance,
        "busiest_agent_seats": max(seats.values()) if seats else 0,
        "top_agents": top_agents,
    }


# ── derive from a REAL Galaxy-Studio build ───────────────────────────────
def execute_build(
    build_id: str,
    seed: int = 0,
    platoon_size: int = 5,
    rounds: int = 2,
    persist: bool = True,
) -> dict:
    """Plan + run the live DAG for a REAL build: phases come from the canonical
    build ladder, genre/context come from the galaxy_builds record."""
    game_ctx: dict[str, Any] = {}
    try:
        from core.databases import get_sync_db
        doc = get_sync_db()["galaxy_builds"].find_one({"build_id": build_id}, {"_id": 0})
        if doc:
            game_ctx = {
                "genre": doc.get("genre") or "rpg",
                "subgenre": doc.get("subgenre") or "",
                "title": doc.get("title") or doc.get("name") or "",
            }
    except Exception:
        pass
    game_ctx.setdefault("genre", "rpg")

    return execute_schedule(
        build_id=build_id, phases=list(BUILD_STAGES), objectives=[
            f"ship a complete {game_ctx.get('genre', 'rpg')} game"],
        seed=seed, platoon_size=platoon_size, game_ctx=game_ctx,
        rounds=rounds, persist=persist,
    )


# ── async job runner (lifts the live phase cap) ──────────────────────────
_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()


def _set_job(job_id: str, **fields):
    with _JOBS_LOCK:
        job = _JOBS.setdefault(job_id, {"job_id": job_id})
        job.update(fields)
    try:
        from core.databases import get_sync_db
        col = get_sync_db()["swarm_schedule_jobs"]
        col.update_one({"job_id": job_id}, {"$set": dict(_JOBS[job_id])}, upsert=True)
    except Exception:
        pass


def get_job(job_id: str) -> dict | None:
    with _JOBS_LOCK:
        if job_id in _JOBS:
            return dict(_JOBS[job_id])
    try:
        from core.databases import get_sync_db
        return get_sync_db()["swarm_schedule_jobs"].find_one({"job_id": job_id}, {"_id": 0})
    except Exception:
        return None


def start_async(kind: str, **kwargs) -> str:
    """Kick a planner execution on a background thread; returns a job_id.

    kind = 'execute' (free phases) or 'build' (real build ladder, no phase cap).
    """
    job_id = uuid.uuid4().hex[:16]
    _set_job(job_id, status="running", kind=kind, build_id=kwargs.get("build_id"),
             created_at=time.time(), result=None, error=None)

    def _worker():
        try:
            if kind == "build":
                res = execute_build(
                    build_id=kwargs["build_id"], seed=kwargs.get("seed", 0),
                    platoon_size=kwargs.get("platoon_size", 5), rounds=kwargs.get("rounds", 2),
                )
            else:
                # async free-form: bypass the online cap via a temporary lift
                global MAX_LIVE_PHASES
                saved = MAX_LIVE_PHASES
                MAX_LIVE_PHASES = max(saved, len(kwargs.get("phases") or []) or saved, 100)
                try:
                    res = execute_schedule(**kwargs)
                finally:
                    MAX_LIVE_PHASES = saved
            _set_job(job_id, status="done", finished_at=time.time(),
                     result={k: res[k] for k in ("plan_hash", "coverage", "verification",
                                                 "execution", "participation")})
        except Exception as ex:
            _set_job(job_id, status="error", finished_at=time.time(), error=str(ex))

    threading.Thread(target=_worker, daemon=True).start()
    return job_id
