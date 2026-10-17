"""E2E contract: Dragon witnesses canonical Jeeves production without claiming AI training."""
from __future__ import annotations

import hashlib
import json

from skeleton.developer.game_cli import run_game_cli
from skeleton.developer import jeeves_dragon_observer as dragon
from skeleton.developer import jeeves_game_production as production


def workspace(tmp_path):
    created = run_game_cli([
        "init", "dragon-journal-game", "--dir", str(tmp_path),
        "--vision", "An original game with replayable stages",
    ])
    assert created["ok"], created
    root = tmp_path / "dragon-journal-game"
    initialized = run_game_cli([
        "jeeves", "production-init", "--project", str(root),
        "--target", "eight_bit_tile_1983", "--genre", "Platformer",
        "--period", "1985-1989",
    ])
    assert initialized["ok"], initialized
    return root


def cli(root, action, *args):
    return run_game_cli(["jeeves", action, "--project", str(root), *args])


def test_consent_is_explicit_and_observation_does_not_train(tmp_path):
    root = workspace(tmp_path)
    assert not cli(root, "dragon-observe-start")["ok"]
    assert not cli(root, "dragon-observe-sync")["ok"]
    started = cli(root, "dragon-observe-start", "--consent")
    assert started["ok"] and started["existing"] is False
    assert cli(root, "dragon-observe-start", "--consent")["existing"]
    empty = cli(root, "dragon-observe-status")
    assert empty["records"] == 0 and empty["trained_checkpoints"] == 0
    assert empty["production"]["project_complete"] is False


def test_canonical_quality_recovery_is_idempotently_observed(tmp_path, monkeypatch):
    root = workspace(tmp_path)
    assert cli(root, "dragon-observe-start", "--consent")["ok"]
    call = {"i": 0}

    def probe(*args):
        call["i"] += 1
        outcome = "failed" if call["i"] == 1 else "passed"
        return outcome, hashlib.sha256(str(call["i"]).encode()).hexdigest(), (
            "canonical_source"
        ), "actual test double quality evaluator"

    monkeypatch.setattr(production, "_probe", probe)
    first = cli(root, "dragon-observe-cycle", "--gate", "source_integrity", "--passes", "2")
    assert first["ok"], first
    assert first["witness"]["appended"] == 2
    assert not first["project_complete"]
    assert first["new_learning_weights"] is False
    assert cli(root, "dragon-observe-sync")["appended"] == 0
    report = cli(root, "dragon-observe-status")
    assert report["canonical_production_observations"] == 2
    assert report["actor_counts"]["builder"] == 2
    assert report["pending_source_events"] == 0
    lessons = cli(root, "dragon-observe-lessons")
    assert lessons["total"] == 1 and len(lessons["candidates"]) == 1
    assert lessons["candidates"][0]["review_required"] is True
    assert lessons["promotion_performed"] is False


def test_recovery_after_source_commits_before_projection_sync(tmp_path, monkeypatch):
    root = workspace(tmp_path)
    assert cli(root, "dragon-observe-start", "--consent")["ok"]
    monkeypatch.setattr(production, "_probe", lambda *args:
        ("blocked", "b" * 64, "operator_observation", "checker unavailable"))
    assert production.cycle(root, passes=2, gate="full_playthrough")["recorded_events"] == 2
    report = dragon.status(root)
    assert report["pending_source_events"] == 2
    first = dragon.sync(root, limit=1)
    assert first["pending_source_events"] == 1
    second = dragon.sync(root, limit=1)
    assert second["pending_source_events"] == 0
    assert dragon.sync(root)["appended"] == 0


def test_operator_claim_does_not_inherit_canonical_trust(tmp_path):
    root = workspace(tmp_path)
    assert cli(root, "dragon-observe-start", "--consent")["ok"]
    forged = cli(
        root, "dragon-observe-action",
        "--actor", "jeeves", "--phase", "playthrough",
        "--event", "playtest", "--outcome", "passed",
        "--evidence", "a" * 64,
    )
    assert forged["ok"], forged
    assert forged["independently_verified"] is False
    status = cli(root, "dragon-observe-status")
    assert status["unverified_action_observations"] == 1
    assert status["production"]["remaining_gates"] == len(production.REQUIRED_GATES)
    assert cli(root, "dragon-observe-lessons")["total"] == 0
    assert not cli(root, "dragon-observe-action", "--actor", "unknown", "--phase",
                   "review", "--event", "study", "--outcome", "passed",
                   "--evidence", "a" * 64)["ok"]


def test_tampered_projection_and_deleted_canonical_source_fail_closed(tmp_path, monkeypatch):
    root = workspace(tmp_path)
    cli(root, "dragon-observe-start", "--consent")
    monkeypatch.setattr(production, "_probe", lambda *args:
        ("failed", "f" * 64, "canonical_source", "test double"))
    assert cli(root, "dragon-observe-cycle", "--gate", "source_integrity")["ok"]
    file = root / ".jeeves" / "production" / "dragon_observer" / "events" / "000000000001.json"
    snapshot = file.read_bytes()
    tampered = json.loads(snapshot)
    tampered["outcome"] = "passed"
    file.write_text(json.dumps(tampered))
    assert not cli(root, "dragon-observe-status")["ok"]
    file.write_bytes(snapshot)
    assert cli(root, "dragon-observe-status")["ok"]
    source = root / ".jeeves" / "production" / "events" / "000000000001.json"
    source.unlink()
    assert not cli(root, "dragon-observe-status")["ok"]


def test_revocation_erases_only_derived_projection(tmp_path, monkeypatch):
    root = workspace(tmp_path)
    assert cli(root, "dragon-observe-start", "--consent")["ok"]
    monkeypatch.setattr(production, "_probe", lambda *args:
        ("failed", "a" * 64, "canonical_source", "test double"))
    assert cli(root, "dragon-observe-cycle", "--gate", "source_integrity")["ok"]
    outcome = cli(root, "dragon-observe-revoke")
    assert outcome["ok"] and outcome["derived_observer_data_erased"]
    assert production.status(root)["recorded_events"] == 1
    assert not (root / ".jeeves" / "production" / "dragon_observer").exists()
    assert not cli(root, "dragon-observe-start", "--consent")["ok"]
    assert cli(root, "dragon-observe-revoke")["ok"]


def test_options_do_not_escape_observer_commands(tmp_path):
    root = workspace(tmp_path)
    assert not cli(root, "dragon-observe-start", "--consent", "--repair-generated")["ok"]
    cli(root, "dragon-observe-start", "--consent")
    assert not cli(root, "dragon-observe-sync", "--page-size", "257")["ok"]
    assert not cli(root, "dragon-observe-cycle", "--passes", "9")["ok"]
    assert not cli(root, "dragon-observe-status", "--evidence", "0" * 64)["ok"]


def test_opted_in_jeeves_cli_returns_are_observed_without_raw_payload(tmp_path):
    root = workspace(tmp_path)
    assert cli(root, "dragon-observe-start", "--consent")["ok"]
    response = cli(root, "production-status")
    assert response["ok"]
    assert response["dragon_observer"]["actual_cli_return_observed"] is True
    assert response["dragon_observer"]["raw_content_retained"] is False
    report = cli(root, "dragon-observe-status")
    assert report["instrumented_cli_observations"] == 1
    assert report["operator_claims"] == 0
    assert report["canonical_production_observations"] == 0
    assert report["production"]["project_complete"] is False


def test_bad_flags_and_corrupt_event_types_cannot_bypass_validation(tmp_path):
    root = workspace(tmp_path)
    assert cli(root, "dragon-observe-start", "--consent")["ok"]
    assert not cli(root, "production-status", "--actor", "dragon")["ok"]
    cli(root, "production-status")
    event_path = root / ".jeeves" / "production" / "dragon_observer" / "events" / "000000000001.json"
    corrupt = json.loads(event_path.read_text())
    corrupt["actor"] = {"actor": "jeeves"}
    corrupt["digest"] = production._digest({k: v for k, v in corrupt.items() if k != "digest"})
    event_path.write_text(json.dumps(corrupt))
    assert not cli(root, "dragon-observe-status")["ok"]
