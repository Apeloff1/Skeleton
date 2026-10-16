"""Non-compensable 20-area P0 game-release acceptance.

The source-based game-production gap atlas is the baseline. Neither locally
claimed expert scores nor syntactically valid manifests qualify an installed
consumer game. This diagnostic never writes creative sources or model weights.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

SCHEMA = "skeleton.jeeves.game_p0_acceptance.v1"
# IDs and scope are pinned to docs/GAME_PRODUCTION_GAP_ATLAS_2026-10-16.md.
GATES = (
    ("P0-01", "end_to_end_product_assembly", "actual fresh-install, author-to-ending consumer journey"),
    ("P0-02", "real_jeeves_model", "real production checkpoint/provider dispatch and approved source integration"),
    ("P0-03", "canonical_story_continuity", "complete signed story history and no-drift replay"),
    ("P0-04", "creative_writing_quality", "independent qualified blind novel/editorial reviews"),
    ("P0-05", "film_direction_quality", "rendered and independently screened original film sequences"),
    ("P0-06", "narrative_causality", "source-linked setup/payoff and independent comprehension evidence"),
    ("P0-07", "character_dramatic_arcs", "verified desire, reversal, change and audience understanding"),
    ("P0-08", "dialogue_performance", "measured original voiced performance and professional table read"),
    ("P0-09", "interactive_player_agency", "multiple materially different full playable endings"),
    ("P0-10", "full_scene_production", "every selected authored scene rendered, signed and playtested"),
    ("P0-11", "book_film_game_adaptation", "signed novel/shot/game bridge in running project"),
    ("P0-12", "world_cast_memory", "correct long-horizon retrieval over finished project"),
    ("P0-13", "independent_adversarial_reviews", "independently authenticated multidisciplinary expert reviews"),
    ("P0-14", "author_rights_approvals", "protected creator approval, provenance and legal clearance"),
    ("P0-15", "complete_quest_arcs", "all intended quest branches, failures and recovery paths run"),
    ("P0-16", "runnable_engine_integration", "complete editor-to-asset-to-scene runtime for claimed systems"),
    ("P0-17", "full_game_playthrough", "real installed start-to-ending runs, save/load and branches"),
    ("P0-18", "native_console_rendering", "measured actual frames/controller/native hardware per target"),
    ("P0-19", "integrated_audio_engine", "executed adaptive/spatial original audio and hearing QA"),
    ("P0-20", "finished_release", "reproducible signed native game package, first install and rollback"),
)


# Whole-app P0 is strictly above the 20 game-specific release areas.
# These entries track previously specified independent AI-chat/app gates;
# historical Dragon's 22-gate baseline is a further separate qualification.
CROSS_LANE_REQUIREMENTS = (
    ("CHAT-01", "in_app_conversation_and_project_selection"),
    ("CHAT-02", "real_local_checkpoint_load_generate_and_stop"),
    ("CHAT-03", "durable_conversation_branching_and_recovery"),
    ("CHAT-04", "streaming_cancel_retry_and_reconnect"),
    ("CHAT-05", "jeeves_active_editor_project_and_runtime_awareness"),
    ("CHAT-06", "reviewable_ai_project_edits_and_undo"),
    ("CHAT-07", "cited_governed_project_and_research_retrieval"),
    ("CHAT-10", "complete_installed_ai_chat_acceptance"),
    ("APP-TS", "full_frontend_typescript_compilation"),
    ("APP-MODEL", "real_checkpoint_inference_and_output"),
    ("APP-STUBS", "complete_stub_and_truncation_classification"),
    ("APP-E2E", "full_real_game_and_app_playthroughs"),
    ("APP-INSTALL", "first_install_and_reopen"),
    ("APP-STUDIO", "academy_galaxy_snowball_jeeves_cockpit_unified_ui"),
    ("DRAGON-P0", "dragon_reproducibility_and_rights_bound_learning"),
)


def assess_p0(root: Path) -> dict[str, Any]:
    """Report observed source progress separately from independent release proof.

    No field in this read-only diagnostic may turn a missing human, hardware,
    legal, native-binary or checkpoint acceptance into success.
    """
    from skeleton.developer.game_cli import _load, _read_forge
    _load(root)
    signals: dict[str, Any] = {
        "canonical_gameforge_build_hash_verified": False,
        "signed_story_gameplay_dossier_replayed": False,
        "signed_narrative_history_checked": False,
        "all_authored_quest_stages_replayed": False,
        "playable_story_binding_complete": False,
        "real_native_install_test_verified": False,
        "real_professional_editor_or_player_review_verified": False,
        "real_model_checkpoint_and_training_verified": False,
        "real_commercial_game_release_verified": False,
    }
    errors: dict[str, str] = {}
    try:
        _, files, source = _read_forge(root)
        signals["canonical_gameforge_build_hash_verified"] = bool(files and source.get("sha256"))
    except (OSError, ValueError, KeyError) as exc:
        errors["gameforge"] = str(exc)

    gameplay_file = root / "design" / "story_gameplay_dossier.json"
    if gameplay_file.is_file() or gameplay_file.is_symlink():
        try:
            from skeleton.developer.jeeves_game_direction_cli import gameplay
            checked = gameplay(root, source="design/story_gameplay_dossier.json", passes=1)
            signals["signed_story_gameplay_dossier_replayed"] = True
            signals["signed_narrative_history_checked"] = True
            signals["all_authored_quest_stages_replayed"] = not checked["unexecuted_quest_stages"]
            signals["playable_story_binding_complete"] = bool(
                checked["story_gameplay_coverage_complete"]
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors["story_gameplay"] = str(exc)

    creative_file = root / "design" / "story_direction_packet.json"
    if creative_file.is_file() or creative_file.is_symlink():
        try:
            from skeleton.developer.jeeves_game_direction_cli import direction
            checked = direction(
                root, action="direction-audit",
                source="design/story_direction_packet.json", passes=1,
            )
            signals["signed_narrative_history_checked"] = bool(
                checked.get("canonical_source_replay_passed", checked.get("ok", False))
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors["story_direction"] = str(exc)

    technical = {
        "P0-03": signals["signed_narrative_history_checked"],
        "P0-09": signals["signed_story_gameplay_dossier_replayed"],
        "P0-11": signals["playable_story_binding_complete"],
        "P0-15": signals["all_authored_quest_stages_replayed"],
        "P0-17": signals["all_authored_quest_stages_replayed"],
    }
    gates = [
        {
            "id": gid, "domain": domain, "required_exit_evidence": proof,
            "source_level_progress_detected": bool(technical.get(gid, False)),
            "independently_release_qualified": False,
            "state": "blocked_unverified",
            "missing": "independent real-world acceptance on exact project and release",
        }
        for gid, domain, proof in GATES
    ]
    return {
        "ok": True, "schema": SCHEMA, "action": "p0-acceptance",
        "project": str(root), "required_p0_gates": len(gates),
        "independently_qualified_p0_gates": 0,
        "blocked_p0_gates": len(gates),
        "p0_complete": False, "product_release_qualified": False,
        "game_specific_p0_scope": "P0-01..P0-20; whole-app P0 is broader",
        "additional_noncompensable_app_p0": [
            {"id": name, "required": requirement, "state": "blocked_unverified"}
            for name, requirement in CROSS_LANE_REQUIREMENTS
        ],
        "historical_dragon_22_gate_baseline_not_qualified_by_this_command": True,
        "whole_application_p0_complete": False,
        "technical_source_signals": signals,
        "unavailable_or_invalid_source_evidence": errors,
        "gates": gates,
        "no_fabricated_human_hardware_model_or_native_signoff": True,
    }
