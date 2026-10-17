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
from .studio_production_blocker_taxonomy import classify_production_blockers

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


_STAGE_EVIDENCE = {
    "source": ("source_receipt_digest", "source_receipt_digest"),
    "rom": ("evidence_digest", "native_binary_evidence_digest"),
    "emulator": ("evidence_digest", "real_emulator_evidence_digest"),
    "browser": ("evidence_digest", "browser_javascript_evidence_digest"),
    "godot": ("evidence_digest", "godot_headless_evidence_digest"),
    "canvas": ("evidence_digest", "generated_canvas_evidence_digest"),
}


def validate_stage_evidence(entries: list[dict], report: dict) -> None:
    """No stage can claim success absent its exact independently audited artifact."""
    if type(entries) is not list or type(report) is not dict:
        raise StudioQualificationHistoryError("canonical production report required")
    targets = report.get("targets")
    if type(targets) is not list or len(targets) > 64:
        raise StudioQualificationHistoryError("bounded production target inventory required")
    indexed = {}
    for row in targets:
        if type(row) is not dict or type(row.get("target")) is not str:
            raise StudioQualificationHistoryError("invalid source assurance target")
        if row["target"] in indexed:
            raise StudioQualificationHistoryError("repeated source assurance target")
        indexed[row["target"]] = row
    for event in entries:
        if type(event) is not dict or event.get("target") not in indexed:
            raise StudioQualificationHistoryError("stage claims an unknown project target")
        if event.get("status") != "verified":
            continue
        stage = event.get("stage")
        if stage not in _STAGE_EVIDENCE:
            raise StudioQualificationHistoryError("unknown successful production stage")
        event_key, proof_key = _STAGE_EVIDENCE[stage]
        observed = event.get(event_key)
        independently_checked = indexed[event["target"]].get(proof_key)
        if (type(observed) is not str or len(observed) != 64
                or any(c not in "0123456789abcdef" for c in observed)
                or observed != independently_checked):
            raise StudioQualificationHistoryError(
                "claimed successful stage lacks exact independently verified evidence"
            )


def _validated_native_failure_events(run: dict, targets: tuple[str, ...]) -> list[dict]:
    events = run.get("events")
    if type(events) is not list or len(events) > 4096:
        raise StudioQualificationHistoryError("bounded original game E2E event list required")
    classifications = ("verified", "blocked", "unsupported")
    required = ("target", "stage", "status", "blocker")
    stage_ids = ("source", "rom", "emulator", "browser", "godot", "canvas")
    requested = run.get("requested_stages")
    if (type(requested) is not list or not requested
            or len(set(requested)) != len(requested)
            or any(stage not in stage_ids for stage in requested)
            or requested != sorted(requested, key=stage_ids.index)):
        raise StudioQualificationHistoryError("invalid original studio execution stage order")
    counts = {status: 0 for status in classifications}
    seen = set()
    failures: list[dict] = []
    for event in events:
        if (type(event) is not dict or any(key not in event for key in required)
                or event["target"] not in targets
                or event["stage"] not in requested
                or event["status"] not in counts
                or (event["target"], event["stage"]) in seen
                or (event["status"] == "verified" and event["blocker"] is not None)
                or (event["status"] != "verified" and (
                    type(event["blocker"]) is not str
                    or not 1 <= len(event["blocker"]) <= 256))):
            raise StudioQualificationHistoryError("E2E report contains a false or repeated stage")
        seen.add((event["target"], event["stage"]))
        counts[event["status"]] += 1
        issue = event.get("first_cpu_divergence")
        if issue is None:
            continue
        if (event["stage"] != "emulator" or event["status"] != "blocked"
                or type(issue) is not dict or type(issue.get("category")) is not str
                or issue["category"] not in (
                    "sample_count_mismatch", "controller_action_boundary_mismatch",
                    "malformed_cpu_sample", "malformed_cpu_state", "cpu_state_diverged"
                )
                or len(issue) > 8):
            raise StudioQualificationHistoryError("unverified or oversized CPU divergence")
        if issue["category"] == "cpu_state_diverged":
            changed = issue.get("changed_fields")
            if (type(changed) is not list or len(changed) > 11
                    or any(key not in (
                        "Level", "PlayerX", "PlayerY", "Health", "Score",
                        "ScoreHigh", "TurnCount", "TurnCountHigh",
                        "GemsRemaining", "GameWon", "GameLost",
                    ) for key in changed)
                    or any(type(issue.get(name)) is not dict
                           or set(issue[name]) != set(changed)
                           or any(type(value) is not int or not 0 <= value <= 255
                                  for value in issue[name].values())
                           for name in ("expected", "observed"))):
                raise StudioQualificationHistoryError("native CPU anomaly contains unreviewed data")
        failures.append({
            "target": event["target"], "category": issue["category"],
            "diagnostic_digest": canonical_digest(issue),
            "first_action": issue.get("action", issue.get("expected_action")),
            "changed_fields": issue.get("changed_fields", []),
        })
    if (len(events) != run.get("total_stage_attempts")
            or counts["verified"] != run.get("verified_stage_attempts")
            or counts["blocked"] != run.get("blocked_stage_attempts")
            or counts["unsupported"] != run.get("unsupported_stage_attempts")):
        raise StudioQualificationHistoryError("E2E stage classifications differ from run summary")
    return failures


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
    native_failures = _validated_native_failure_events(run, order.targets)
    classified = classify_production_blockers(run["events"], limit=16)
    root = Path(campaign)
    with campaign_lock(root):
        checked = _inspect_production_assurance_unlocked(order, root)
        validate_stage_evidence(run["events"], checked)
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
            "native_cpu_divergence_count": len(native_failures),
            "first_native_cpu_divergence": native_failures[0] if native_failures else None,
            "classified_stage_blockers": classified["findings"],
            "unlisted_stage_blocker_categories": classified["omitted_after_limit"],
            "blocker_classification_digest": classified["classification_digest"],
            "native_cartridge_victories": checked["native_rom_machine_code_playthroughs_verified"],
            "native_cpu_checkpoint_samples_verified": checked["native_cpu_checkpoint_samples_verified"],
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
            "recorded_cpu_divergence_events": sum(
                entry.get("native_cpu_divergence_count", 0) for entry in rows
            ),
            "latest_cpu_divergence": (
                rows[-1].get("first_native_cpu_divergence") if rows else None
            ),
            "latest_stage_blockers": (
                rows[-1].get("classified_stage_blockers", []) if rows else []
            ),
            "latest_unlisted_blocker_categories": (
                rows[-1].get("unlisted_stage_blocker_categories", 0) if rows else 0
            ),
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
    "StudioQualificationHistoryError", "validate_stage_evidence",
    "record_execution_run",
    "inspect_execution_history",
]
