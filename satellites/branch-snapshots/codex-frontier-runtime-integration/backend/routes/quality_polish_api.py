"""
✨ POLISH API — HTTP surface for the quality-gate polish loop.

Endpoints (mounted under /api/polish):
  POST /artifact            polish one inline artifact {kind, content} until 95
  POST /{pid}/stage/{stage} fetch a game's forge artifact from the KB, polish it,
                            and persist the improved version back (marks the stage
                            fresh + records the pass trail on the KB doc)

Both return the full pass trail so the score lift is inspectable. The polish loop
itself lives in routes/quality_polish.py — this module is only the transport.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Query

from core.databases import client as _MONGO
from routes.quality import MIN_QUALITY
from routes.quality_polish import polish_pass, MAX_POLISH_PASSES

router = APIRouter(prefix="/api/polish", tags=["polish"])
_db = _MONGO[os.environ.get("DB_NAME", "test_database")]

# stage key → game_kb artifact key (mirrors snowball_improve._STAGE_ART)
_STAGE_ART = {"spec": "core_specs", "world": "lore_graph", "narrative": "quest_db",
              "mechanics": "mechanics_config", "procedural": "procedural_config",
              "assets": "asset_manifest", "qa": "qa_report", "build": "build_manifest",
              "launch": "launch_manifest"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/artifact")
async def polish_inline(
    kind: str = Body(..., embed=True),
    content=Body(..., embed=True),
    simulate: bool = Query(False),
    max_passes: int = Query(MAX_POLISH_PASSES, ge=1, le=10),
):
    """✨ Polish one inline artifact against the 95 gate. Non-destructive."""
    if not kind or content in (None, ""):
        return {"error": "'kind' and 'content' are required."}
    result = await polish_pass(kind, content, simulate=simulate, max_passes=max_passes)
    return {"kind": kind, "gate": MIN_QUALITY, **result}


@router.post("/{pid}/stage/{stage}")
async def polish_game_stage(
    pid: str, stage: str,
    simulate: bool = Query(False),
    max_passes: int = Query(MAX_POLISH_PASSES, ge=1, le=10),
):
    """✨ Polish one stage of a game in place: load the KB artifact, iterate it
    against the gate, persist the best version back, and record the pass trail."""
    art_key = _STAGE_ART.get(stage)
    if not art_key:
        return {"error": f"unknown stage '{stage}'", "valid": list(_STAGE_ART.keys())}
    kb = await _db.game_kb.find_one({"game_id": pid}, {"_id": 0, "artifacts": 1})
    artifact = ((kb or {}).get("artifacts") or {}).get(art_key)
    if not artifact:
        return {"error": f"no artifact for stage '{stage}' (artifact '{art_key}') on game {pid}"}

    result = await polish_pass(stage, artifact, simulate=simulate, artifact=artifact,
                               max_passes=max_passes)

    # persist the best version + trail
    await _db.game_kb.update_one(
        {"game_id": pid},
        {"$set": {
            "game_id": pid,
            f"artifacts.{art_key}": result["content"],
            f"stale.{art_key}": False,
            f"polish.{art_key}": {
                "at": _now(), "score": result["score"], "passed": result["passed"],
                "improved_by": result["improved_by"], "passes": result["passes"],
            },
        }},
        upsert=True,
    )
    return {"game_id": pid, "stage": stage, "artifact": art_key, "gate": MIN_QUALITY,
            **{k: v for k, v in result.items() if k != "content"},
            "persisted": True}
