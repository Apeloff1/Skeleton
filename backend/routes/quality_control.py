"""
Quality Control Agent v16.5 — Sentinel
AAA Game Studio Standards Enforcement
Standards set at year of creation. No indie quality accepted.

Also hosts the /polish endpoints (forge quality-gate churn): the polish loop
lives in routes/quality_polish.py; the endpoints are mounted here because
core/routes_registry.py is append-managed and this module is already registered
and quality-owned.
"""

import os
from fastapi import APIRouter, Body, Query
from datetime import datetime, timezone
from typing import Dict, List, Any

from core.databases import client as _MONGO
from routes.quality import MIN_QUALITY
from routes.quality_polish import polish_pass, MAX_POLISH_PASSES
import routes.game_kb_polish  # noqa: F401 — boot-time polish wiring into game_kb._llm_json

router = APIRouter(prefix="/api/quality-control", tags=["quality-control"])
_db = _MONGO[os.environ.get("DB_NAME", "test_database")]

CURRENT_YEAR = datetime.now().year

QA_STANDARDS: Dict[str, Any] = {
    "standards_year": CURRENT_YEAR,
    "agent_name": "Sentinel",
    "agent_role": "Quality Control Director",
    "veto_power": True,
    "minimum_quality": "AAA",
    "rejected_tiers": ["indie", "prototype", "placeholder", "stub", "MVP"],

    "technical_standards": {
        "code_quality": {
            "min_test_coverage": 80,
            "max_cyclomatic_complexity": 15,
            "required_documentation": True,
            "no_todo_in_production": True,
            "no_console_log_in_production": True,
            "type_safety": "strict",
            "error_handling": "comprehensive",
        },
        "performance": {
            "target_fps": 60,
            "max_frame_time_ms": 16.67,
            "max_memory_budget_mb": 4096,
            "max_draw_calls": 3000,
            "max_triangles_per_frame": 10_000_000,
            "max_load_time_seconds": 5,
            "streaming_required": True,
        },
        "graphics": {
            "min_resolution": "1080p",
            "hdr_support": True,
            "pbr_required": True,
            "global_illumination": "required",
            "anti_aliasing": "TAA or MSAA 4x minimum",
            "shadow_quality": "cascaded shadow maps",
            "post_processing": ["bloom", "DOF", "motion_blur", "color_grading", "ambient_occlusion"],
        },
        "audio": {
            "spatial_audio": True,
            "adaptive_music": True,
            "min_sample_rate": 44100,
            "surround_support": "5.1 minimum",
        },
        "networking": {
            "max_latency_compensation_ms": 200,
            "rollback_support": True,
            "server_authoritative": True,
            "anticheat_required": True,
        }
    },

    "design_standards": {
        "ui_ux": {
            "accessibility": "WCAG 2.1 AA",
            "colorblind_modes": True,
            "controller_support": "full",
            "remappable_controls": True,
            "subtitle_support": True,
            "font_scaling": True,
        },
        "gameplay": {
            "onboarding": "progressive, non-intrusive",
            "difficulty_options": "minimum 3 tiers",
            "save_system": "autosave + manual",
            "respawn_system": "fair, no progress loss",
        },
        "content": {
            "no_placeholder_assets": True,
            "no_lorem_ipsum": True,
            "no_programmer_art": True,
            "voice_acting_quality": "professional",
            "localization_ready": True,
        }
    },

    "delivery_checklist": [
        "All features complete and tested",
        "Performance within budget on target platforms",
        "No critical or major bugs",
        "All placeholder content replaced",
        "Accessibility standards met",
        "Localization framework in place",
        "Save/load system working",
        "Settings menu complete",
        "Tutorial/onboarding complete",
        "Audio mix finalized",
        "Post-processing pipeline tuned",
        "Build pipeline automated",
        "Platform certification requirements met",
        "ESRB/PEGI rating considerations addressed",
        "Quality Control sign-off obtained",
    ]
}


@router.get("/standards")
async def get_standards():
    return QA_STANDARDS


@router.get("/checklist")
async def get_checklist():
    return {
        "checklist": QA_STANDARDS["delivery_checklist"],
        "enforced_by": "Sentinel (Quality Control Agent)",
        "standards_year": CURRENT_YEAR,
        "minimum_quality": "AAA",
        "veto_power": True,
    }


@router.post("/review")
async def review_submission(content: str = "", category: str = "code"):
    """Sentinel reviews a submission against AAA standards."""
    issues = []
    if not content or len(content) < 10:
        issues.append({"severity": "critical", "issue": "Content too short or empty", "fix": "Provide complete implementation"})
    if "TODO" in content or "FIXME" in content:
        issues.append({"severity": "major", "issue": "Contains TODO/FIXME markers", "fix": "Complete all pending work"})
    if "console.log" in content and category == "code":
        issues.append({"severity": "minor", "issue": "Contains debug logging", "fix": "Remove or replace with proper logging"})
    if "placeholder" in content.lower():
        issues.append({"severity": "critical", "issue": "Contains placeholder content", "fix": "Replace with production-quality content"})

    passed = len([i for i in issues if i["severity"] == "critical"]) == 0

    return {
        "verdict": "APPROVED" if passed else "REJECTED",
        "quality_tier": "AAA" if passed and len(issues) == 0 else "AA" if passed else "REJECTED",
        "issues": issues,
        "reviewed_by": "Sentinel",
        "standards_year": CURRENT_YEAR,
        "message": "Meets AAA standards." if passed and len(issues) == 0 else "Approved with minor notes." if passed else "Does not meet AAA standards. Revisions required."
    }


# ───────────────────────────────────────────────────────────────────────────
# ✨ POLISH endpoints — iterate a forge artifact until it clears the 95 gate.
# stage key → game_kb artifact key (mirrors snowball_improve._STAGE_ART)
_STAGE_ART = {"spec": "core_specs", "world": "lore_graph", "narrative": "quest_db",
              "mechanics": "mechanics_config", "procedural": "procedural_config",
              "assets": "asset_manifest", "qa": "qa_report", "build": "build_manifest",
              "launch": "launch_manifest"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/polish/artifact")
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


@router.post("/polish/{pid}/stage/{stage}")
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
