"""End-to-end operator steering across repeated CLI invocations."""
from __future__ import annotations
from unittest.mock import patch
from skeleton.__main__ import main
from skeleton.context.operator_state import read_steering
from skeleton.context.tensor import ContextTensor

def _success():
    return {"succeeded": True, "era": "cozy_wholesome", "mass": 1.0,
            "forge": {"file_count": 9}, "sim": {"passed": True},
            "playtest": {"status": "passed"}, "run": {"stages": []}}

def test_bind_persists_axes_through_next_build_and_snapshot(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SKELETON_COCKPIT_STATE", str(tmp_path / "cockpit.json"))
    assert main(["cockpit", "BIND", "ERA", "cozy_wholesome"]) == 0
    assert main(["cockpit", "BIND", "ARCHETYPE", "auto"]) == 0
    assert main(["cockpit", "SET", "AXIS", "intimacy", "0.95"]) == 0
    snap = tmp_path / "snapshot.json"
    assert main(["cockpit", "SNAPSHOT", "--out", str(snap)]) == 0
    assert main(["cockpit", "BIND", "ERA", "soulslike"]) == 0
    assert main(["cockpit", "RESTORE", str(snap)]) == 0
    assert read_steering()["tensor"]["era"] == "cozy_wholesome"
    with patch("skeleton.context.pipeline.GameForgeRun.live") as live:
        live.return_value.execute.return_value = _success()
        assert main(["run", "quiet", "village"]) == 0
    kwargs = live.return_value.execute.call_args.kwargs
    assert kwargs["era"] == "cozy_wholesome"
    assert kwargs["operator_tensor"]["intimacy"] == 0.95
    assert live.call_args.kwargs["cockpit"].archetype == "auto"
    assert "playtest=passed" in capsys.readouterr().out

def test_explicit_era_and_blend_override_saved_pin(tmp_path, monkeypatch):
    monkeypatch.setenv("SKELETON_COCKPIT_STATE", str(tmp_path / "cockpit.json"))
    assert main(["cockpit", "BIND", "ERA", "soulslike"]) == 0
    with patch("skeleton.context.pipeline.GameForgeRun.live") as live:
        live.return_value.execute.return_value = _success()
        assert main(["run", "game", "--era", "cozy_wholesome"]) == 0
        assert live.return_value.execute.call_args.kwargs["operator_tensor"] is None
        assert live.return_value.execute.call_args.kwargs["era"] == "cozy_wholesome"
        assert main(["run", "game", "--blend", "soulslike", "cozy_wholesome"]) == 0
        assert live.return_value.execute.call_args.kwargs["era"] is None
        assert live.return_value.execute.call_args.kwargs["blend"][:2] == ("soulslike", "cozy_wholesome")

def test_corrupt_state_recovery_and_failed_stage_visibility(tmp_path, monkeypatch, capsys):
    f = tmp_path / "cockpit.json"
    monkeypatch.setenv("SKELETON_COCKPIT_STATE", str(f))
    assert main(["cockpit", "BIND", "ERA", "soulslike"]) == 0
    snap = tmp_path / "snapshot.json"
    assert main(["cockpit", "SNAPSHOT", "--out", str(snap)]) == 0
    f.write_text('{"schema":"invalid"}', encoding="utf-8")
    with patch("skeleton.context.pipeline.GameForgeRun.live") as live:
        assert main(["run", "game"]) == 2
        live.assert_not_called()
    assert main(["cockpit", "RESTORE", str(snap)]) == 0
    assert read_steering()["tensor"]["era"] == "soulslike"
    with patch("skeleton.context.pipeline.GameForgeRun.live") as live:
        live.return_value.execute.return_value = {
            "succeeded": False, "era": "soulslike", "playtest": None,
            "run": {"stages": [{"status": "FAILED", "name": "emit",
                                "error": "RuntimeError: missing Godot"}]}}
        assert main(["run", "game", "--playtest", "require"]) == 1
    captured = capsys.readouterr()
    assert "stage=emit" in captured.err
    assert "missing Godot" in captured.err
    assert "playtest=not-reached" in captured.out

def test_operator_tensor_keeps_same_era_but_never_overrides_different_era():
    from skeleton.context.cockpit import Cockpit
    from skeleton.context.pipeline import _stage_tensor
    operator = ContextTensor.from_era("cozy_wholesome").with_axis("risk", 0.02)
    cockpit = Cockpit()
    with patch("skeleton.context.pipeline._commit"):
        _stage_tensor({"era": "cozy_wholesome", "cockpit": cockpit,
                       "operator_tensor": operator})
        assert cockpit.tensor["risk"] == 0.02
        _stage_tensor({"era": "soulslike", "cockpit": cockpit,
                       "operator_tensor": operator})
        assert cockpit.tensor.era == "soulslike"


def test_saved_blend_survives_cli_and_questionnaire_is_not_overridden_by_unbound_axes(tmp_path, monkeypatch):
    monkeypatch.setenv("SKELETON_COCKPIT_STATE", str(tmp_path / "cockpit.json"))
    assert main(["cockpit", "BLEND", "ERA", "soulslike", "cozy_wholesome", "0.25"]) == 0
    with patch("skeleton.context.pipeline.GameForgeRun.live") as live:
        live.return_value.execute.return_value = _success()
        assert main(["run", "dream"]) == 0
        assert live.return_value.execute.call_args.kwargs["blend"] == (
            "soulslike", "cozy_wholesome", 0.25)
        assert live.return_value.execute.call_args.kwargs["operator_tensor"] is None
    assert main(["cockpit", "BIND", "ARCHETYPE", "auto"]) == 0
    # Reset the blend only for this run; the explicit CLI era remains authoritative.
    with patch("skeleton.context.pipeline.GameForgeRun.live") as live:
        live.return_value.execute.return_value = _success()
        assert main(["run", "dream", "--era", "cozy_wholesome"]) == 0
        assert live.return_value.execute.call_args.kwargs["blend"] is None
