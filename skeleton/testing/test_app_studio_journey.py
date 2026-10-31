"""Real app CLI -> canonical game studio -> exported playable source -> replay."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.ai.game_builder.playable_world import GameBuildIntent
from skeleton.app.cli import run_app_cli
from skeleton.app.studio_journey import (
    FirstPlayableJourneyError, build_first_playable_journey,
)


def _intent(tmp_path: Path) -> Path:
    intent = GameBuildIntent(
        project_id="first-playable-001", title="Original Lantern",
        subtitle="A source-bound offline journey", seed=1729,
        levels=1, width=9, height=9, collectibles_per_level=1,
        hazards_per_level=0, starting_health=3,
    )
    source = tmp_path / "intent.json"
    source.write_text(json.dumps(intent.to_payload()), encoding="utf-8")
    return source


def test_app_first_playable_journey_real_export_and_replay(tmp_path, capsys):
    source = _intent(tmp_path)
    output = tmp_path / "game"
    assert run_app_cli([
        "studio-journey", "--intent", str(source), "--output", str(output),
        "--trusted-local-operator",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["schema"] == "skeleton.app.first_playable_journey.v1"
    assert result["status"] == "source_playable_verified_release_blocked"
    assert result["offline_gameplay_reexecuted"] is True
    assert result["verification_receipt"]["project_id"] == "first-playable-001"
    assert result["verification_receipt"]["replayed_actions"] > 0
    assert result["model_inference_observed"] is False
    assert result["native_godot_executed"] is False
    assert result["native_device_qualified"] is False
    assert result["rights_certified"] is False
    assert result["release_certified"] is False
    assert result["consumer_blockers"]
    assert (output / "index.html").is_file()
    assert (output / "godot" / "project.godot").is_file()
    assert (output / "proof" / "verified_solution.json").is_file()
    assert (output / "release.json").is_file()


def test_authorization_is_required_before_build_or_export(tmp_path, capsys):
    source = _intent(tmp_path)
    output = tmp_path / "game"
    assert run_app_cli([
        "studio-journey", "--intent", str(source), "--output", str(output),
    ]) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["source_playable_verified"] is False
    assert error["release_certified"] is False
    assert not output.exists()


@pytest.mark.parametrize("attempts,practice", [(63, 0), (513, 0), (64, -1), (64, 9)])
def test_invalid_work_budgets_fail_before_mutation(tmp_path, attempts, practice):
    source = _intent(tmp_path)
    with pytest.raises(FirstPlayableJourneyError):
        build_first_playable_journey(
            source, tmp_path / "game", authorized=True,
            mirror_attempts=attempts, practice_games=practice,
        )
    assert not (tmp_path / "game").exists()


def test_existing_export_is_not_overwritten(tmp_path, capsys):
    source = _intent(tmp_path)
    output = tmp_path / "game"
    output.mkdir()
    marker = output / "owner.txt"
    marker.write_text("preserve", encoding="utf-8")
    assert run_app_cli([
        "studio-journey", "--intent", str(source), "--output", str(output),
        "--trusted-local-operator",
    ]) == 2
    assert marker.read_text(encoding="utf-8") == "preserve"
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_unverified_export_does_not_become_success_receipt(
    tmp_path, monkeypatch, capsys,
):
    from skeleton.app import studio_journey
    source = _intent(tmp_path)
    output = tmp_path / "game"

    def fail_verification(*_args, **_kwargs):
        raise studio_journey.DualRuntimeVerificationError(
            "simulated post-export source mutation"
        )

    monkeypatch.setattr(studio_journey, "verify_exported_package", fail_verification)
    assert run_app_cli([
        "studio-journey", "--intent", str(source), "--output", str(output),
        "--trusted-local-operator",
    ]) == 2
    result = json.loads(capsys.readouterr().err)
    assert result["source_playable_verified"] is False
    assert result["release_certified"] is False
    assert output.exists()  # operator must quarantine; never unsafe recursive deletion


def test_nonexistent_intent_fails_closed_without_export(tmp_path, capsys):
    output = tmp_path / "game"
    assert run_app_cli([
        "studio-journey", "--intent", str(tmp_path / "missing.json"),
        "--output", str(output), "--trusted-local-operator",
    ]) == 2
    assert not output.exists()
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_verified_journey_publishes_independently_inspectable_receipt(
    tmp_path, capsys,
):
    from skeleton.ai.game_builder.offline_receipt_inspection import (
        inspect_verified_receipt,
    )
    source = _intent(tmp_path)
    output = tmp_path / "game"
    receipt = tmp_path / "verified-replay.json"
    assert run_app_cli([
        "studio-journey", "--intent", str(source), "--output", str(output),
        "--receipt", str(receipt), "--trusted-local-operator",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["receipt_file"] == str(receipt)
    assert receipt.is_file()
    inspected = inspect_verified_receipt(
        receipt, expected_sha256=result["independent_receipt_sha256"],
        authorized=True,
    )
    assert inspected["receipt_integrity_verified"] is True
    assert inspected["gameplay_reexecuted_now"] is False
    assert inspected["release_certified"] is False
    assert result["verification_receipt"]["offline_gameplay_reexecuted"] is True


def test_receipt_inside_source_package_is_rejected_without_false_success(
    tmp_path, capsys,
):
    source = _intent(tmp_path)
    output = tmp_path / "game"
    receipt = output / "receipt.json"
    assert run_app_cli([
        "studio-journey", "--intent", str(source), "--output", str(output),
        "--receipt", str(receipt), "--trusted-local-operator",
    ]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert (output / "release.json").is_file()
    assert not receipt.exists()
