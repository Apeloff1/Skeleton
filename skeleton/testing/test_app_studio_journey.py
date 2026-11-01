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
    assert not output.exists()  # deterministic preflight rejects before construction
    assert not receipt.exists()

def test_existing_export_reverified_without_rebuild_or_source_mutation(tmp_path, capsys):
    from hashlib import sha256
    from skeleton.ai.game_builder.offline_receipt_inspection import inspect_verified_receipt

    source = _intent(tmp_path)
    output = tmp_path / "game"
    assert run_app_cli([
        "studio-journey", "--intent", str(source), "--output", str(output),
        "--trusted-local-operator",
    ]) == 0
    capsys.readouterr()
    release = (output / "release.json").read_bytes()
    before = (output / "index.html").read_bytes()
    receipt = tmp_path / "reverified.json"
    assert run_app_cli([
        "studio-journey", "--verify-existing", "--output", str(output),
        "--expected-manifest-sha256", sha256(release).hexdigest(),
        "--receipt", str(receipt), "--trusted-local-operator",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["schema"] == "skeleton.app.first_playable_journey_verification.v1"
    assert result["offline_gameplay_reexecuted"] is True
    assert result["replayed_actions"] > 0
    assert result["native_device_qualified"] is False
    assert result["release_certified"] is False
    assert (output / "index.html").read_bytes() == before
    assert (output / "release.json").read_bytes() == release
    assert inspect_verified_receipt(
        receipt, expected_sha256=result["independent_receipt_sha256"],
        authorized=True,
    )["receipt_integrity_verified"] is True


def test_receipt_collision_rejected_before_any_game_export(tmp_path, capsys):
    source = _intent(tmp_path)
    output = tmp_path / "game"
    receipt = tmp_path / "existing.json"
    receipt.write_text("operator-owned", encoding="utf-8")
    assert run_app_cli([
        "studio-journey", "--intent", str(source), "--output", str(output),
        "--receipt", str(receipt), "--trusted-local-operator",
    ]) == 2
    assert not output.exists()
    assert receipt.read_text(encoding="utf-8") == "operator-owned"
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_receipt_symlink_parent_rejected_before_any_game_export(tmp_path, capsys):
    source = _intent(tmp_path)
    output = tmp_path / "game"
    private = tmp_path / "private"
    private.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(private, target_is_directory=True)
    assert run_app_cli([
        "studio-journey", "--intent", str(source), "--output", str(output),
        "--receipt", str(alias / "receipt.json"), "--trusted-local-operator",
    ]) == 2
    assert not output.exists()
    assert not (private / "receipt.json").exists()
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_existing_source_requires_authority_and_external_pin(tmp_path, capsys):
    source = _intent(tmp_path)
    output = tmp_path / "game"
    assert run_app_cli([
        "studio-journey", "--intent", str(source), "--output", str(output),
        "--trusted-local-operator",
    ]) == 0
    capsys.readouterr()
    for args in (
        ["--verify-existing"],
        ["--verify-existing", "--trusted-local-operator"],
        ["--verify-existing", "--expected-manifest-sha256", "0" * 64,
         "--trusted-local-operator"],
        ["--verify-existing", "--intent", str(source),
         "--expected-manifest-sha256", "0" * 64, "--trusted-local-operator"],
    ):
        assert run_app_cli(["studio-journey", "--output", str(output), *args]) == 2
        assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert (output / "release.json").is_file()


def test_existing_source_mutation_fails_closed_without_receipt(tmp_path, capsys):
    from hashlib import sha256

    source = _intent(tmp_path)
    output = tmp_path / "game"
    assert run_app_cli([
        "studio-journey", "--intent", str(source), "--output", str(output),
        "--trusted-local-operator",
    ]) == 0
    capsys.readouterr()
    pin = sha256((output / "release.json").read_bytes()).hexdigest()
    (output / "index.html").write_text("modified", encoding="utf-8")
    receipt = tmp_path / "must-not-exist.json"
    assert run_app_cli([
        "studio-journey", "--verify-existing", "--output", str(output),
        "--expected-manifest-sha256", pin, "--receipt", str(receipt),
        "--trusted-local-operator",
    ]) == 2
    assert not receipt.exists()
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"

def test_existing_export_preflight_never_runs_studio(tmp_path, monkeypatch, capsys):
    from skeleton.app import studio_journey

    source = _intent(tmp_path)
    output = tmp_path / "game"
    output.mkdir()
    (output / "marker").write_text("owner", encoding="utf-8")

    def unexpected_studio(*_args, **_kwargs):
        raise AssertionError("game construction must not run on occupied target")

    monkeypatch.setattr(studio_journey, "run_original_game_studio", unexpected_studio)
    assert run_app_cli([
        "studio-journey", "--intent", str(source), "--output", str(output),
        "--trusted-local-operator",
    ]) == 2
    assert (output / "marker").read_text(encoding="utf-8") == "owner"
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_export_parent_symlink_preflight_never_runs_studio(tmp_path, monkeypatch, capsys):
    from skeleton.app import studio_journey

    source = _intent(tmp_path)
    owned = tmp_path / "owned"
    owned.mkdir()
    alias = tmp_path / "link"
    alias.symlink_to(owned, target_is_directory=True)

    def unexpected_studio(*_args, **_kwargs):
        raise AssertionError("game construction must not run through symlink")

    monkeypatch.setattr(studio_journey, "run_original_game_studio", unexpected_studio)
    assert run_app_cli([
        "studio-journey", "--intent", str(source),
        "--output", str(alias / "game"), "--trusted-local-operator",
    ]) == 2
    assert not (owned / "game").exists()
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"

def test_app_inspects_archived_receipt_without_replaying_source(tmp_path, capsys):
    source = _intent(tmp_path)
    output = tmp_path / "game"
    receipt = tmp_path / "archived.json"
    assert run_app_cli([
        "studio-journey", "--intent", str(source), "--output", str(output),
        "--receipt", str(receipt), "--trusted-local-operator",
    ]) == 0
    original = json.loads(capsys.readouterr().out)
    assert run_app_cli([
        "studio-journey", "--inspect-receipt", "--receipt", str(receipt),
        "--expected-receipt-sha256", original["independent_receipt_sha256"],
        "--trusted-local-operator",
    ]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["schema"] == "skeleton.app.first_playable_receipt_inspection.v1"
    assert inspected["receipt_integrity_verified"] is True
    assert inspected["gameplay_reexecuted_now"] is False
    assert inspected["release_certified"] is False
    assert inspected["canonical_inspection"]["native_hardware_tested"] is False


def test_app_archived_receipt_rejects_bad_pin_authority_and_mode_mix(tmp_path, capsys):
    source = _intent(tmp_path)
    output = tmp_path / "game"
    receipt = tmp_path / "archived.json"
    assert run_app_cli([
        "studio-journey", "--intent", str(source), "--output", str(output),
        "--receipt", str(receipt), "--trusted-local-operator",
    ]) == 0
    capsys.readouterr()
    attempts = (
        ["--inspect-receipt", "--receipt", str(receipt),
         "--expected-receipt-sha256", "0" * 64, "--trusted-local-operator"],
        ["--inspect-receipt", "--receipt", str(receipt),
         "--expected-receipt-sha256", "0" * 64],
        ["--inspect-receipt", "--receipt", str(receipt), "--output", str(output),
         "--expected-receipt-sha256", "0" * 64, "--trusted-local-operator"],
        ["--inspect-receipt", "--receipt", str(receipt), "--trusted-local-operator"],
    )
    for args in attempts:
        assert run_app_cli(["studio-journey", *args]) == 2
        assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert (output / "release.json").is_file()

def test_first_run_onboarding_builds_original_game_without_intent_file(tmp_path, capsys):
    output = tmp_path / "first-game"
    receipt = tmp_path / "first-game-receipt.json"
    assert run_app_cli([
        "studio-journey", "--onboard", "--project-id", "new-original-001",
        "--title", "Moonlit Compass", "--seed", "1729",
        "--output", str(output), "--receipt", str(receipt),
        "--trusted-local-operator",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["project_id"] == "new-original-001"
    assert result["offline_gameplay_reexecuted"] is True
    assert result["native_device_qualified"] is False
    assert result["model_inference_observed"] is False
    assert result["release_certified"] is False
    assert (output / "index.html").is_file()
    assert (output / "godot" / "project.godot").is_file()
    assert receipt.is_file()


@pytest.mark.parametrize("args", [
    ["--onboard", "--project-id", "bad id", "--title", "Original", "--seed", "7"],
    ["--onboard", "--project-id", "safe", "--title", "Original",
     "--seed", "7", "--width", "10"],
    ["--onboard", "--project-id", "safe", "--title", "Original",
     "--seed", "-1"],
    ["--onboard", "--project-id", "safe", "--title", "Original",
     "--seed", "7", "--theme", "unapproved"],
    ["--onboard", "--project-id", "safe", "--title", "Original"],
])
def test_first_run_onboarding_rejects_invalid_input_before_export(
    tmp_path, capsys, args,
):
    output = tmp_path / "game"
    assert run_app_cli([
        "studio-journey", *args, "--output", str(output),
        "--trusted-local-operator",
    ]) == 2
    assert not output.exists()
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_onboarding_rejects_unauthorized_or_ambiguous_modes(tmp_path, capsys):
    output = tmp_path / "game"
    source = _intent(tmp_path)
    base = [
        "studio-journey", "--onboard", "--project-id", "original",
        "--title", "Original", "--seed", "9", "--output", str(output),
    ]
    assert run_app_cli(base) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert run_app_cli(base + [
        "--intent", str(source), "--trusted-local-operator",
    ]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert not output.exists()

@pytest.mark.parametrize("kind", ["final_symlink", "ancestor_symlink", "hardlink"])
def test_untrusted_intent_path_rejected_before_game_build(tmp_path, capsys, kind):
    source = _intent(tmp_path)
    output = tmp_path / "game"
    if kind == "final_symlink":
        incoming = tmp_path / "alias.json"
        incoming.symlink_to(source)
    elif kind == "ancestor_symlink":
        private = tmp_path / "private"
        private.mkdir()
        nested = private / "intent.json"
        nested.write_bytes(source.read_bytes())
        alias = tmp_path / "alias"
        alias.symlink_to(private, target_is_directory=True)
        incoming = alias / "intent.json"
    else:
        incoming = tmp_path / "hardlink.json"
        incoming.hardlink_to(source)
    assert run_app_cli([
        "studio-journey", "--intent", str(incoming), "--output", str(output),
        "--trusted-local-operator",
    ]) == 2
    assert not output.exists()
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


@pytest.mark.parametrize("raw", [
    '{"project_id":"a","project_id":"b"}',
    '{"seed":NaN}',
    '{"project_id":"a"}',
])
def test_untrusted_intent_json_rejected_without_game_export(tmp_path, capsys, raw):
    source = tmp_path / "malformed.json"
    source.write_text(raw, encoding="utf-8")
    output = tmp_path / "game"
    assert run_app_cli([
        "studio-journey", "--intent", str(source), "--output", str(output),
        "--trusted-local-operator",
    ]) == 2
    assert not output.exists()
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_first_run_rejects_world_writable_intent_without_export(tmp_path, capsys):
    source = _intent(tmp_path)
    source.chmod(0o666)
    output = tmp_path / "game"
    assert run_app_cli([
        "studio-journey", "--intent", str(source), "--output", str(output),
        "--trusted-local-operator",
    ]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert not output.exists()


def test_first_run_rejects_intent_changed_between_descriptor_reads(
    tmp_path, capsys, monkeypatch,
):
    from skeleton.app import studio_journey
    source = _intent(tmp_path)
    output = tmp_path / "game"
    real_read = studio_journey._read
    reads = 0

    def replace_after_first(fd, path, budget, **kwargs):
        nonlocal reads
        value = real_read(fd, path, budget, **kwargs)
        reads += 1
        if reads == 1:
            source.write_bytes(value + b" ")
        return value

    monkeypatch.setattr(studio_journey, "_read", replace_after_first)
    assert run_app_cli([
        "studio-journey", "--intent", str(source), "--output", str(output),
        "--trusted-local-operator",
    ]) == 2
    assert reads == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert not output.exists()


def test_first_run_rejects_same_byte_intent_inode_substitution(
    tmp_path, capsys, monkeypatch,
):
    from skeleton.app import studio_journey
    source = _intent(tmp_path)
    output = tmp_path / "game"
    real_read = studio_journey._read
    reads = 0

    def replace_same_bytes_after_first(fd, path, budget, **kwargs):
        nonlocal reads
        value = real_read(fd, path, budget, **kwargs)
        reads += 1
        if reads == 1:
            source.rename(tmp_path / "old-intent.json")
            source.write_bytes(value)
        return value

    monkeypatch.setattr(studio_journey, "_read", replace_same_bytes_after_first)
    assert run_app_cli([
        "studio-journey", "--intent", str(source), "--output", str(output),
        "--trusted-local-operator",
    ]) == 2
    assert reads == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert not output.exists()


def test_first_run_rejects_deeply_nested_intent_json_without_export(
    tmp_path, capsys,
):
    source = tmp_path / "intent.json"
    source.write_bytes(b"[" * 1500 + b"0" + b"]" * 1500)
    output = tmp_path / "game"
    assert run_app_cli([
        "studio-journey", "--intent", str(source), "--output", str(output),
        "--trusted-local-operator",
    ]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert not output.exists()


def test_first_run_accepts_independently_pinned_original_intent(
    tmp_path, capsys,
):
    from hashlib import sha256
    source = _intent(tmp_path)
    pin = sha256(source.read_bytes()).hexdigest()
    output = tmp_path / "pinned-game"
    assert run_app_cli([
        "studio-journey", "--intent", str(source),
        "--expected-intent-sha256", pin, "--output", str(output),
        "--trusted-local-operator",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["original_intent_independently_pinned"] is True
    assert result["independent_intent_sha256"] == pin
    assert result["offline_gameplay_reexecuted"] is True
    assert result["release_certified"] is False
    assert (output / "release.json").exists()


@pytest.mark.parametrize("pin", ["0" * 64, "A" * 64, "abc", "z" * 64])
def test_first_run_rejects_wrong_or_malformed_intent_pin_before_export(
    tmp_path, capsys, pin,
):
    source = _intent(tmp_path)
    output = tmp_path / "game"
    assert run_app_cli([
        "studio-journey", "--intent", str(source),
        "--expected-intent-sha256", pin, "--output", str(output),
        "--trusted-local-operator",
    ]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert not output.exists()


def test_independent_intent_pin_rejected_for_inline_onboarding(
    tmp_path, capsys,
):
    output = tmp_path / "game"
    assert run_app_cli([
        "studio-journey", "--onboard", "--project-id", "fresh",
        "--title", "Original Game", "--seed", "42",
        "--expected-intent-sha256", "a" * 64,
        "--output", str(output), "--trusted-local-operator",
    ]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert not output.exists()
