"""
🧭 STUDIO PIPELINE — the flowchart's Central Workflow Orchestrator.

Aggregates, for one game, the status of every pipeline stage so creators see a
guided checklist of what's done and what's next:

  Mode → Core Spec → WorldForge → Narrative & Quests → Mechanics → Asset Genesis
       → Implementation → Playtest & QA → Build & Export

Each stage is derived from concrete signals already in the data (the playable doc,
design_specs, worldforge_worlds, asset_genesis) — read-only, no new writes.
"""
from __future__ import annotations

from fastapi import APIRouter

from routes.playable import _db, PLAYABILITY_THRESHOLD

router = APIRouter(prefix="/api/playable", tags=["playable"])


def _stage(key, label, icon, status, detail="", route=None):
    return {"key": key, "label": label, "icon": icon, "status": status,
            "detail": detail, "route": route}


@router.get("/{pid}/pipeline")
async def pipeline(pid: str):
    """Stage-by-stage build status for a game (the Studio Pipeline tracker)."""
    g = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "html": 0})
    if not g:
        return {"error": "not found"}

    # ── gather signals ──
    has_spec = bool(g.get("spec_id"))
    world = await _db.worldforge_worlds.find_one(
        {"source": "playable", "source_id": pid}, {"_id": 0, "world_id": 1, "name": 1, "pois": 1})
    world_pois = len((world or {}).get("pois") or [])
    asset_status = g.get("asset_status") or "none"
    gen_kinds = await _db.asset_genesis.distinct("kind", {"game_id": pid})
    is_ready = g.get("status") == "ready"
    score = int(g.get("playability_score") or 0)
    ev = g.get("evaluation") or {}
    ev_ok = bool(ev.get("available"))
    kb = await _db.game_kb.find_one({"game_id": pid}, {"_id": 0, "artifacts": 1, "approvals": 1})
    arts = (kb or {}).get("artifacts") or {}
    approvals = (kb or {}).get("approvals") or {}
    has_core_specs = "core_specs" in arts
    has_mech = "mechanics_config" in arts
    has_proc = "procedural_config" in arts
    has_lore = "lore_graph" in arts
    has_quest = "quest_db" in arts
    has_build = "build_manifest" in arts
    has_qa = "qa_report" in arts
    kb_updated = (kb or {}).get("updated_at")
    kb_synced = g.get("kb_applied_at")
    kb_drift = bool(kb_updated and kb_synced and kb_updated > kb_synced) or (bool(kb_updated) and not kb_synced)

    stages = []
    # 1) Mode
    mode = g.get("derive_mode") or g.get("genre") or "original"
    stages.append(_stage("mode", "Mode", "🎮", "done", str(mode), "/playable"))
    # 2) Core spec / questionnaire → core_specs.json (forgeable)
    spec_done = has_spec or has_core_specs
    s = _stage("spec", "Core Spec", "📋", "done" if spec_done else "todo",
               "core_specs.json" if has_core_specs else ("design spec" if has_spec else "not built"),
               "/galaxy-studio")
    s["forge"] = "spec"
    stages.append(s)
    # 3) WorldForge → lore_graph.json (forgeable)
    world_done = bool(world) or has_lore
    w = _stage("world", "WorldForge", "🌍", "done" if world_done else "todo",
               "lore_graph.json" if has_lore else ((world or {}).get("name", "") if world else "not built"),
               "/worldforge")
    w["forge"] = "world"
    stages.append(w)
    # 4) Narrative & Quests → quest_DB.json (forgeable)
    narrative_done = (bool(world) and world_pois > 0) or has_quest
    n = _stage("narrative", "Narrative & Quests", "📖",
               "done" if narrative_done else ("partial" if world else "todo"),
               "quest_DB.json" if has_quest else (f"{world_pois} POIs" if world else "not started"),
               "/worldforge")
    n["forge"] = "narrative"
    stages.append(n)
    # 5) Mechanics & Systems → mechanics_config.json (forgeable)
    mech_done = has_mech or has_spec
    m = _stage("mechanics", "Mechanics", "⚙️", "done" if mech_done else "todo",
               "mechanics_config.json" if has_mech else ("from spec" if has_spec else "not defined"),
               "/galaxy-studio")
    m["forge"] = "mechanics"
    stages.append(m)
    # 6) Procedural Generation → procedural_config.json (forgeable) — flowchart stage 7
    proc_done = has_proc
    p = _stage("procedural", "Procedural", "🧬", "done" if proc_done else "todo",
               (f"{len((arts.get('procedural_config') or {}).get('requirements', []))} reqs"
                if has_proc else "PCG: requirements / consistency / optimization"),
               "/game-kb")
    p["forge"] = "procedural"
    stages.append(p)
    # 7) Asset Genesis
    a_status = {"complete": "done", "partial": "partial", "none": "todo"}.get(asset_status, "todo")
    stages.append(_stage(
        "assets", "Asset Genesis", "🎨", a_status,
        f"{len(gen_kinds)}/4 kinds", f"/asset-genesis?game={pid}"))
    # 7) Implementation
    stages.append(_stage(
        "implementation", "Implementation", "🛠️", "done" if (is_ready and g.get("version")) else "todo",
        ("KB-synced · " if g.get("kb_applied") else "") + f"v{g.get('version', 1)} · {round((g.get('bytes') or 0) / 1024, 1)}KB",
        "/playable"))
    # 8) Playtest & QA → qa_report.json (forgeable)
    qa_done = (ev_ok and score >= PLAYABILITY_THRESHOLD) or has_qa
    qa = _stage("qa", "Playtest & QA", "🧪",
                "done" if qa_done else ("partial" if (ev_ok or has_qa) else "todo"),
                (f"QA {(arts.get('qa_report') or {}).get('score', '?')}" if has_qa
                 else (f"score {score} · {ev.get('verdict', '–')}" if ev_ok else "not evaluated")),
                "/playable")
    qa["forge"] = "qa"
    stages.append(qa)
    # 9) Build & Export → build_manifest.json (forgeable, deterministic)
    build_done = bool(g.get("exported")) or has_build
    b = _stage("build", "Build & Export", "📦", "done" if build_done else "todo",
               "build_manifest.json" if has_build else ("exported" if g.get("exported") else "not exported"),
               "/playable")
    b["forge"] = "build"
    stages.append(b)

    # attach human-approval status (Iterate & Refine loop) to every stage
    for st in stages:
        appr = approvals.get(st["key"])
        st["approved"] = bool(appr and appr.get("approved"))

    done = sum(1 for s in stages if s["status"] == "done")
    approved_count = sum(1 for s in stages if s.get("approved"))
    nxt = next((s for s in stages if s["status"] != "done"), None)
    return {
        "game_id": pid, "title": g.get("title", ""),
        "stages": stages, "done": done, "total": len(stages),
        "percent": round(done / len(stages) * 100),
        "approved_count": approved_count,
        "next": nxt["key"] if nxt else None,
        "next_label": nxt["label"] if nxt else "Complete!",
        "kb_drift": kb_drift, "kb_synced_at": kb_synced, "kb_updated_at": kb_updated,
    }
