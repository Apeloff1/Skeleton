"""App CLI integration for independent read-only offline replay comparison."""
from __future__ import annotations

import json

import pytest

from skeleton.app.cli import run_app_cli


def _create(tmp_path, capsys, name="comparison-world", seed=1729):
    root = tmp_path / (name + "-source")
    assert run_app_cli([
        "studio-journey", "--onboard", "--project-id", name,
        "--title", "Original Lantern", "--seed", str(seed),
        "--output", str(root), "--trusted-local-operator",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    return root, result["trusted_in_process_manifest_sha256"]


def _save(tmp_path, capsys, root, manifest, name, moves):
    save = tmp_path / (name + ".json")
    assert run_app_cli([
        "studio-journey", "--play-existing", "--output", str(root),
        "--expected-manifest-sha256", manifest, "--moves", moves,
        "--save", str(save), "--trusted-local-operator",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    return save, result["independent_save_sha256"]


def _compare(root, manifest, left, left_pin, right, right_pin):
    return [
        "studio-journey", "--compare-saves", "--output", str(root),
        "--expected-manifest-sha256", manifest,
        "--left-save", str(left), "--left-sha256", left_pin,
        "--right-save", str(right), "--right-sha256", right_pin,
        "--trusted-local-operator",
    ]


def test_two_playable_saves_diverge_at_first_changed_action(tmp_path, capsys):
    root, manifest = _create(tmp_path, capsys)
    left, left_pin = _save(tmp_path, capsys, root, manifest, "left", "up,right")
    right, right_pin = _save(tmp_path, capsys, root, manifest, "right", "up,left")
    original = ((root / "release.json").read_bytes(), left.read_bytes(), right.read_bytes())
    assert run_app_cli(_compare(root, manifest, left, left_pin, right, right_pin)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["schema"] == "skeleton.app.offline_save_comparison.v1"
    assert result["first_divergent_action_index"] == 1
    assert result["identical_history"] is False
    assert result["left_actions"] == result["right_actions"] == 2
    assert result["source_verified_before_after"] is True
    assert result["both_saves_replayed"] is True
    assert result["read_only"] is True
    assert result["native_device_qualified"] is False
    assert result["release_certified"] is False
    assert original == ((root / "release.json").read_bytes(), left.read_bytes(), right.read_bytes())


def test_identical_save_compares_without_mutation(tmp_path, capsys):
    root, manifest = _create(tmp_path, capsys)
    save, pin = _save(tmp_path, capsys, root, manifest, "single", "up")
    assert run_app_cli(_compare(root, manifest, save, pin, save, pin)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["first_divergent_action_index"] is None
    assert result["identical_history"] is True
    assert result["left_replay_digest"] == result["right_replay_digest"]


def test_prefix_save_diverges_at_missing_next_action(tmp_path, capsys):
    root, manifest = _create(tmp_path, capsys)
    short, short_pin = _save(tmp_path, capsys, root, manifest, "short", "up")
    long, long_pin = _save(tmp_path, capsys, root, manifest, "long", "up,right")
    assert run_app_cli(_compare(root, manifest, short, short_pin, long, long_pin)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["first_divergent_action_index"] == 1
    assert result["left_actions"] == 1
    assert result["right_actions"] == 2


@pytest.mark.parametrize("case", ["wrong_left_pin", "wrong_right_pin", "tampered_left", "tampered_right"])
def test_tampered_or_unpinned_save_never_produces_comparison(tmp_path, capsys, case):
    root, manifest = _create(tmp_path, capsys)
    left, left_pin = _save(tmp_path, capsys, root, manifest, "left", "up")
    right, right_pin = _save(tmp_path, capsys, root, manifest, "right", "right")
    if case == "wrong_left_pin":
        left_pin = "0" * 64
    elif case == "wrong_right_pin":
        right_pin = "0" * 64
    elif case == "tampered_left":
        left.write_bytes(left.read_bytes() + b" ")
    else:
        right.write_bytes(right.read_bytes() + b" ")
    assert run_app_cli(_compare(root, manifest, left, left_pin, right, right_pin)) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_foreign_world_save_is_not_comparable_even_with_valid_pin(tmp_path, capsys):
    root, manifest = _create(tmp_path, capsys, "world-alpha", 1729)
    other, other_manifest = _create(tmp_path, capsys, "world-beta", 1729)
    left, left_pin = _save(tmp_path, capsys, root, manifest, "left", "up")
    right, right_pin = _save(tmp_path, capsys, other, other_manifest, "right", "up")
    assert run_app_cli(_compare(root, manifest, left, left_pin, right, right_pin)) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


@pytest.mark.parametrize("change", ["no_authority", "missing_pin", "play_mode", "onboard_mode", "extra_save", "missing_left"])
def test_comparison_mode_rejects_mixed_or_unauthorized_options(tmp_path, capsys, change):
    args = [
        "studio-journey", "--compare-saves", "--output", str(tmp_path / "source"),
        "--expected-manifest-sha256", "a" * 64,
        "--left-save", str(tmp_path / "left.json"), "--left-sha256", "b" * 64,
        "--right-save", str(tmp_path / "right.json"), "--right-sha256", "c" * 64,
        "--trusted-local-operator",
    ]
    if change == "no_authority":
        args.remove("--trusted-local-operator")
    elif change == "missing_pin":
        args.remove("--right-sha256")
        args.remove("c" * 64)
    elif change == "play_mode":
        args.append("--play-existing")
    elif change == "onboard_mode":
        args.append("--onboard")
    elif change == "extra_save":
        args.extend(["--save", str(tmp_path / "new.json")])
    else:
        args.remove("--left-save")
        args.remove(str(tmp_path / "left.json"))
    assert run_app_cli(args) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_comparison_options_never_leak_into_new_build_mode(tmp_path, capsys):
    target = tmp_path / "never-built"
    assert run_app_cli([
        "studio-journey", "--onboard", "--project-id", "original",
        "--title", "Original", "--seed", "1", "--output", str(target),
        "--left-save", str(tmp_path / "save.json"), "--trusted-local-operator",
    ]) == 2
    assert not target.exists()
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_source_tamper_rejected_without_writing_to_saves(tmp_path, capsys):
    root, manifest = _create(tmp_path, capsys)
    left, left_pin = _save(tmp_path, capsys, root, manifest, "left", "up")
    right, right_pin = _save(tmp_path, capsys, root, manifest, "right", "right")
    original = (left.read_bytes(), right.read_bytes())
    (root / "index.html").write_text("tampered", encoding="utf-8")
    assert run_app_cli(_compare(root, manifest, left, left_pin, right, right_pin)) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert (left.read_bytes(), right.read_bytes()) == original


def test_changed_source_before_save_publication_cannot_leave_new_save(tmp_path, capsys, monkeypatch):
    from skeleton.app import studio_journey

    root, manifest = _create(tmp_path, capsys)
    save = tmp_path / "not-published.json"
    def fail_prepublication(*_args, **_kwargs):
        raise studio_journey.DualRuntimeVerificationError("source changed during replay")
    monkeypatch.setattr(studio_journey, "verify_exported_package", fail_prepublication)
    assert run_app_cli([
        "studio-journey", "--play-existing", "--output", str(root),
        "--expected-manifest-sha256", manifest, "--moves", "up",
        "--save", str(save), "--trusted-local-operator",
    ]) == 2
    assert not save.exists()
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
