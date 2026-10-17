"""Crash-safe, source-bound audit history of full Jeeves production E2E runs.

A summary is append-only and hash-linked under the existing cross-platform
process lock. An entry is accepted only if its exact assurance-report digest
is still current; no source, runtime, app screen or AI model is modified.
This is bounded local history, not an asynchronous monitoring service.
"""
from __future__ import annotations

from pathlib import Path

from .contracts import canonical_digest
from .studio_campaign import CampaignOrder, _atomic_json, _load_json
from .studio_campaign_assurance import _inspect_production_assurance_unlocked
from .studio_campaign_lock import campaign_lock

SCHEMA = "skeleton.game_builder.studio_qualification_history.v1"
ENTRY_SCHEMA = "skeleton.game_builder.studio_qualification_history_entry.v1"
_MAX_RUNS = 4_096


class StudioQualificationHistoryError(ValueError):
    """Reported E2E success, history integrity or original source is invalid."""


def _read_history(root: Path, identity: str) -> dict:
    path = root / "qualification_history.json"
    if path.is_symlink():
        raise StudioQualificationHistoryError("qualification journal must never be a link")
    if not path.exists():
        body = {
            "schema": SCHEMA, "campaign_identity": identity,
            "entries": [],
        }
        return {**body, "history_digest": canonical_digest(body)}
    raw = _load_json(path)
    if (raw.get("schema") != SCHEMA or raw.get("campaign_identity") != identity
            or type(raw.get("entries")) is not list
            or not 0 <= len(raw["entries"]) <= _MAX_RUNS):
        raise StudioQualificationHistoryError("journal source identity or entry budget invalid")
    if canonical_digest({k: v for k, v in raw.items()
                         if k != "history_digest"}) != raw.get("history_digest"):
        raise StudioQualificationHistoryError("stored qualification history modified")
    previous = None
    for index, entry in enumerate(raw["entries"]):
        if (type(entry) is not dict or entry.get("schema") != ENTRY_SCHEMA
                or entry.get("sequence") != index + 1
                or entry.get("previous_entry_digest") != previous
                or type(entry.get("run_digest")) is not str
                or type(entry.get("assurance_report_digest")) is not str
                or entry.get("full_release_qualified") is not False
                or entry.get("model_weights_updated") is not False
                or canonical_digest({k: v for k, v in entry.items()
                                     if k != "entry_digest"}) != entry.get("entry_digest")):
            raise StudioQualificationHistoryError("historical receipt chain is not canonical")
        previous = entry["entry_digest"]
    return raw


def record_execution_run(
    order: CampaignOrder, campaign: str | Path, run: dict, *,
    authorized: bool,
) -> dict:
    if authorized is not True:
        raise PermissionError("reviewable game production history requires local authority")
    if not isinstance(order, CampaignOrder) or type(run) is not dict:
        raise StudioQualificationHistoryError("typed source and completed run receipt required")
    if (run.get("schema") != "skeleton.game_builder.studio_execution_campaign.v1"
            or run.get("full_release_qualified") is not False
            or run.get("model_weights_updated") is not False
            or canonical_digest({k: v for k, v in run.items()
                                 if k != "run_digest"}) != run.get("run_digest")):
        raise StudioQualificationHistoryError("E2E run source receipt does not validate")
    root = Path(campaign)
    with campaign_lock(root):
        checked = _inspect_production_assurance_unlocked(order, root)
        if (checked["campaign_identity"] != run.get("campaign_identity")
                or checked["report_digest"] != run.get("assurance_report_digest")):
            raise StudioQualificationHistoryError("run report is stale for this game version")
        history = _read_history(root, checked["campaign_identity"])
        entries = history["entries"]
        if len(entries) >= _MAX_RUNS:
            raise StudioQualificationHistoryError("bounded qualification history is full")
        item = {
            "schema": ENTRY_SCHEMA,
            "sequence": len(entries) + 1,
            "campaign_identity": checked["campaign_identity"],
            "run_digest": run["run_digest"],
            "assurance_report_digest": checked["report_digest"],
            "previous_entry_digest": entries[-1]["entry_digest"] if entries else None,
            "verified_stage_attempts": run["verified_stage_attempts"],
            "blocked_stage_attempts": run["blocked_stage_attempts"],
            "unsupported_stage_attempts": run["unsupported_stage_attempts"],
            "native_cartridge_victories": checked["native_rom_machine_code_playthroughs_verified"],
            "actual_browser_replays": checked["browser_javascript_playthroughs_verified"],
            "actual_godot_replays": checked["godot_headless_playthroughs_verified"],
            "full_release_qualified": False,
            "model_weights_updated": False,
        }
        item["entry_digest"] = canonical_digest(item)
        updated = {
            "schema": SCHEMA,
            "campaign_identity": checked["campaign_identity"],
            "entries": [*entries, item],
        }
        updated["history_digest"] = canonical_digest(updated)
        _atomic_json(root / "qualification_history.json", updated)
        return item


def inspect_execution_history(
    order: CampaignOrder, campaign: str | Path, *, authorized: bool,
) -> dict:
    if authorized is not True:
        raise PermissionError("production qualification history requires operator authority")
    if not isinstance(order, CampaignOrder):
        raise StudioQualificationHistoryError("typed original production order required")
    root = Path(campaign)
    with campaign_lock(root):
        report = _inspect_production_assurance_unlocked(order, root)
        historical = _read_history(root, report["campaign_identity"])
        rows = historical["entries"]
        return {
            "schema": SCHEMA,
            "campaign_identity": report["campaign_identity"],
            "current_assurance_report_digest": report["report_digest"],
            "history_digest": historical["history_digest"],
            "recorded_runs": len(rows),
            "latest_run_digest": rows[-1]["run_digest"] if rows else None,
            "latest_still_matches_current_source": (
                rows[-1]["assurance_report_digest"] == report["report_digest"]
                if rows else False
            ),
            "runs_without_recorded_blockers": sum(x["blocked_stage_attempts"] == 0
                                 and x["unsupported_stage_attempts"] == 0
                                 for x in rows),
            "complete_game_release_certified": False,
            "model_training_performed": False,
        }


__all__ = [
    "StudioQualificationHistoryError", "record_execution_run",
    "inspect_execution_history",
]
