"""Source-bound Dragon repair triage for real native CPU evidence.

Derives bounded, actionable review proposals from hash-linked E2E run history.
No screen capture, copyrighted ROM material, source rewriting, emulator
execution, shell commands, automatic retries, knowledge promotion or AI weight
changes. A stale run never becomes a current recommendation.
"""
from __future__ import annotations

from pathlib import Path

from .contracts import canonical_digest
from .studio_campaign import CampaignOrder
from .studio_execution_history import inspect_execution_history

SCHEMA = "skeleton.game_builder.dragon_native_repair_triage.v1"
_FIELD_WORK = {
    "PlayerX": ("directional_input_or_collision",
                "Compare input mapping, tile collision and X-coordinate increments"),
    "PlayerY": ("directional_input_or_collision",
                "Compare input mapping, tile collision and Y-coordinate increments"),
    "TurnCount": ("missed_or_repeated_controller_turn",
                  "Inspect D-pad polling, held-button cooldown and input cadence"),
    "TurnCountHigh": ("missed_or_repeated_controller_turn",
                      "Inspect counter carry and action replay boundaries"),
    "Score": ("collectible_goal_score_divergence",
              "Recheck native +10 collectible and +100 goal low-byte arithmetic"),
    "ScoreHigh": ("collectible_goal_score_divergence",
                  "Recheck carry into high-byte score and long-level totals"),
    "Health": ("hazard_collision_rule_divergence",
               "Compare native hazard entry and Python one-health-loss semantics"),
    "Level": ("level_transition_rule_divergence",
              "Check level completion, next-level spawn and terminal +1 counter"),
    "GemsRemaining": ("collectible_consumption_divergence",
                      "Compare each original collectible and repeat-pickup prevention"),
    "GameWon": ("premature_or_missing_terminal_state",
                "Inspect exact last goal and remaining-collectible condition"),
    "GameLost": ("unexpected_early_loss",
                 "Check hazard damage and terminal input lockdown"),
}


def triage_native_gameplay(
    order: CampaignOrder, campaign: str | Path, *,
    authorized: bool,
) -> dict:
    if authorized is not True:
        raise PermissionError("Dragon CPU repair triage requires explicit local authority")
    if not isinstance(order, CampaignOrder):
        raise ValueError("typed original production order required")
    history = inspect_execution_history(order, campaign, authorized=True)
    current = history["latest_still_matches_current_source"]
    finding = history["latest_cpu_divergence"] if current else None
    items = []
    if finding:
        changed = finding.get("changed_fields", [])
        if finding.get("category") == "cpu_state_diverged":
            used = set()
            for field in changed:
                key, action = _FIELD_WORK[field]
                if key in used:
                    continue
                used.add(key)
                items.append({
                    "category": key,
                    "first_mismatch_action": finding.get("first_action"),
                    "diagnostic_digest": finding["diagnostic_digest"],
                    "suggested_examination": action,
                    "must_retest_original_game": True,
                    "automatic_code_edit_allowed": False,
                })
        elif finding.get("category") == "controller_action_boundary_mismatch":
            items.append({
                "category": "missed_or_repeated_controller_turn",
                "first_mismatch_action": finding.get("first_action"),
                "diagnostic_digest": finding["diagnostic_digest"],
                "suggested_examination":
                    "Inspect replay button cadence and machine turn-counter observations",
                "must_retest_original_game": True,
                "automatic_code_edit_allowed": False,
            })
        else:
            items.append({
                "category": "incomplete_or_invalid_emulator_telemetry",
                "first_mismatch_action": finding.get("first_action"),
                "diagnostic_digest": finding["diagnostic_digest"],
                "suggested_examination":
                    "Re-execute exact source-bound ROM replay and collect the full CPU log",
                "must_retest_original_game": True,
                "automatic_code_edit_allowed": False,
            })
    body = {
        "schema": SCHEMA,
        "campaign_identity": history["campaign_identity"],
        "current_assurance_report_digest": history["current_assurance_report_digest"],
        "history_digest": history["history_digest"],
        "last_run_digest": history["latest_run_digest"],
        "latest_history_current": current,
        "recorded_cpu_divergence_events": history["recorded_cpu_divergence_events"],
        "proposal_count": len(items),
        "proposals": items,
        "review_required": True,
        "stale_history_proposals_blocked": not current,
        "native_cpu_runtime_passed": False,
        "model_weights_modified": False,
        "knowledge_promoted": False,
        "source_code_modified": False,
    }
    return {**body, "triage_digest": canonical_digest(body)}


__all__ = ["triage_native_gameplay", "SCHEMA"]
