"""
🤖 MULTI-AGENT GROUPCHAT — auto-runs the whole pipeline with agent hand-offs.

An Orchestrator hands each stage to the owning agent (WorldForgeAgent, NarrativeQuestAgent, …).
Before each stage the agent RECALLS relevant canon (RAG), then forges its artifact (reusing the
KB forges + provenance/invalidation). Every message is appended to a live transcript so the UI
can render the conversation. Sequential, resumable, fully automatic.
"""
from __future__ import annotations

import os
import uuid
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter

from core.databases import client as _MONGO
from routes.game_kb import _FORGES, _stamped, _AGENT_BY_STAGE
from routes.canon_rag import _recall
from routes.jeeves_voice import AGENT_CAST  # 🎙️ per-agent voice cast (War-Room)

router = APIRouter(prefix="/api/groupchat", tags=["groupchat"])
_db = _MONGO[os.environ.get("DB_NAME", "test_database")]

_LADDER = ["spec", "world", "narrative", "mechanics", "procedural", "assets", "qa", "build", "launch"]
_LABEL = {"spec": "Core Specs", "world": "WorldForge", "narrative": "Narrative & Quests",
          "mechanics": "Mechanics", "procedural": "Procedural", "assets": "Asset Pipeline",
          "qa": "Playtest & QA", "build": "Build & Package", "launch": "Launch Prep"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _say(job_id: str, transcript: list, agent: str, text: str, kind: str = "msg", **extra):
    # 🎙️ War-Room: tag every line with the speaking agent's cast voice/tone so
    # the UI can play it back in that agent's distinct voice.
    cast = AGENT_CAST.get(agent)
    if cast and "tone" not in extra:
        extra["tone"] = cast["tone"]
    transcript.append({"agent": agent, "text": text, "kind": kind, "at": _now(), **extra})
    await _db.groupchat_jobs.update_one(
        {"job_id": job_id}, {"$set": {"transcript": transcript, "updated_at": _now()}})


async def _run_groupchat(pid: str, job_id: str, only_missing: bool, only_stale: bool = False):
    transcript: list = []
    kb = await _db.game_kb.find_one({"game_id": pid}, {"_id": 0, "artifacts": 1, "stale": 1})
    have = set(((kb or {}).get("artifacts") or {}).keys())
    stale_set = set((kb or {}).get("stale") or {})
    art_of = {"spec": "core_specs", "world": "lore_graph", "narrative": "quest_db",
              "mechanics": "mechanics_config", "procedural": "procedural_config",
              "assets": "asset_manifest", "qa": "qa_report", "build": "build_manifest",
              "launch": "launch_manifest"}

    await _say(job_id, transcript, "Orchestrator",
               "Kicking off the build. I'll hand each stage to its agent in order.", "system")
    done = 0
    for stage in _LADDER:
        agent = _AGENT_BY_STAGE.get(stage, "Agent")
        skip = (only_missing and art_of[stage] in have) or (only_stale and art_of[stage] not in stale_set)
        if skip:
            await _say(job_id, transcript, "Orchestrator",
                       f"{_LABEL[stage]} is up to date — skipping.", "skip")
            done += 1
            await _db.groupchat_jobs.update_one(
                {"job_id": job_id}, {"$set": {"current": stage, "done": done, "total": len(_LADDER)}})
            continue
        await _db.groupchat_jobs.update_one(
            {"job_id": job_id}, {"$set": {"current": stage, "done": done, "total": len(_LADDER)}})
        await _say(job_id, transcript, "Orchestrator", f"@{agent}, please build {_LABEL[stage]}.", "handoff")
        # RAG: the agent recalls relevant canon before generating
        hits = await _recall(pid, _LABEL[stage] + " " + stage, 4)
        if hits:
            await _say(job_id, transcript, agent,
                       "Recalled canon: " + ", ".join(f"{h['type']}:{h['name']}" for h in hits),
                       "recall", count=len(hits))
        # 🧠 Vault: load domain knowledge for this stage (manual passes + quality uplift)
        try:
            from core.stage_vault import vault_brief
            vb = vault_brief(stage)
            await _say(job_id, transcript, agent, "🧠 " + vb, "vault")
            await _db.game_kb.update_one(
                {"game_id": pid}, {"$set": {f"vault_context.{stage}": vb}}, upsert=True)
        except Exception:
            pass
        try:
            res = await _stamped(pid, stage, _FORGES[stage](pid))
        except Exception as e:  # noqa
            res = {"ok": False, "error": str(e)[:200]}
        if res.get("ok"):
            done += 1
            await _say(job_id, transcript, agent,
                       f"✅ Done — {res.get('summary', _LABEL[stage] + ' built')}", "result", ok=True)
        else:
            await _say(job_id, transcript, agent,
                       f"⚠️ {res.get('error', 'could not complete')} — moving on.", "result", ok=False)
        await _db.groupchat_jobs.update_one(
            {"job_id": job_id}, {"$set": {"done": done, "total": len(_LADDER)}})

    await _say(job_id, transcript, "Orchestrator",
               f"Build finished — {done}/{len(_LADDER)} stages complete.", "system")
    await _db.groupchat_jobs.update_one(
        {"job_id": job_id}, {"$set": {"job_status": "done", "done": done, "current": None,
                                      "finished_at": _now()}})


@router.post("/{pid}/run/async")
async def run_groupchat(pid: str, only_missing: bool = True, only_stale: bool = False):
    """🤖 Auto-run the pipeline via agent hand-offs. only_missing=true builds just the gaps;
    only_stale=true rebuilds ONLY stages flagged stale by the dependency graph (Auto-resolve)."""
    g = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "playable_id": 1})
    if not g:
        return {"error": "game not found"}
    if only_stale:
        only_missing = False
    job_id = uuid.uuid4().hex
    await _db.groupchat_jobs.insert_one({
        "job_id": job_id, "game_id": pid, "job_status": "running", "transcript": [],
        "current": None, "done": 0, "total": len(_LADDER), "created_at": _now()})
    asyncio.create_task(_run_groupchat(pid, job_id, only_missing, only_stale))
    return {"job_id": job_id, "job_status": "running", "total": len(_LADDER)}


@router.get("/job/{job_id}")
async def groupchat_job(job_id: str):
    """Live transcript + progress for a GroupChat run."""
    j = await _db.groupchat_jobs.find_one({"job_id": job_id}, {"_id": 0})
    if not j:
        return {"error": "job not found"}
    return j
