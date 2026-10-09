"""Headless regression verification for real stdlib desktop game preview."""
from __future__ import annotations

import pytest

from skeleton.ai.runtime.gameplay_capabilities import (
    GameplayError, platformer_step,
)
from skeleton.app.offline_game_preview import (
    DEFAULT_SEED, HEIGHT, WIDTH, OfflineGamePreview,
)


def test_preview_has_actual_admitted_solvable_level_and_game_state():
    game = OfflineGamePreview()
    frame = game.snapshot()
    assert len(frame.tiles) == HEIGHT == 12
    assert len(frame.tiles[0]) == WIDTH == 18
    assert frame.frame == 0
    assert frame.avatar == (1, 1)
    assert frame.goal == (16, 10)
    assert frame.won is False
    assert frame.grounded is False
    assert frame.as_dict()["model_inference_used"] is False
    assert frame.as_dict()["new_training_examples"] == 0
    assert sum(line.count("S") for line in frame.tiles) == 1
    assert sum(line.count("G") for line in frame.tiles) == 1


def test_preview_step_uses_exact_shared_model_free_platformer_primitive():
    game = OfflineGamePreview()
    before = game.snapshot()
    one = game.tick(right=True)
    actual = platformer_step({
        "tiles": list(before.tiles),
        "avatar": {"x": 1, "y": 1, "vx": 0, "vy": 0},
        "control": {"left": False, "right": True, "jump": False},
    })
    assert one.avatar == (
        actual["avatar"]["x"], actual["avatar"]["y"],
    )
    assert game.avatar == actual["avatar"]
    assert one.won == actual["goal_reached"]
    assert one.frame == 1


def test_game_preview_is_playable_to_a_genuine_goal_and_freezes_when_won():
    game = OfflineGamePreview()
    history = []
    for _ in range(18):
        history.append(game.tick(right=True))
    assert any(frame.won for frame in history)
    final = history[-1]
    assert final.won is True
    assert final.avatar == final.goal == (16, 10)
    assert final.frame <= 18
    assert game.tick(right=True) == final
    assert game.tick(jump=True) == final


def test_game_preview_reset_restores_initial_player_and_replay_is_deterministic():
    a = OfflineGamePreview(seed=DEFAULT_SEED)
    b = OfflineGamePreview(seed=DEFAULT_SEED)
    controls = [
        {"left": False, "right": True, "jump": False},
        {"left": False, "right": True, "jump": False},
        {"left": True, "right": False, "jump": False},
        {"left": False, "right": False, "jump": True},
    ] * 4
    states_a = [a.tick(**control).as_dict() for control in controls]
    states_b = [b.tick(**control).as_dict() for control in controls]
    assert states_a == states_b
    recovered = a.reset()
    assert recovered.frame == 0
    assert recovered.avatar == (1, 1)
    assert recovered.won is False
    assert a.tick(right=True).as_dict() == b.reset().as_dict() | {
        "frame": 1, "avatar": {"x": 2, "y": 2},
        "grounded": False,
    }


@pytest.mark.parametrize("buttons", [
    {"left": 1},
    {"right": "true"},
    {"jump": None},
])
def test_preview_controls_do_not_coerce_untrusted_types(buttons):
    game = OfflineGamePreview()
    with pytest.raises(GameplayError, match="boolean"):
        game.tick(**buttons)
    assert game.frame == 0


@pytest.mark.parametrize("seed", [-1, 2**31, True, "one"])
def test_preview_refuses_invalid_seed_without_opening_tk(seed):
    with pytest.raises(GameplayError):
        OfflineGamePreview(seed=seed)


def test_preview_cli_requires_explicit_user_request_and_valid_mode(capsys):
    from skeleton.app.offline_cli import main

    assert main(["--game-seed", "9"]) == 2
    assert main(["--game-preview", "--json"]) == 2
    assert main(["--game-preview", "--model", "weights.json"]) == 2
    assert main(["--game-preview", "--queue-status"]) == 2
    assert main(["--game-preview", "--game-seed", "-1"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "game" in captured.err.lower()


def test_preview_cli_is_routed_in_standalone_and_unified_app_without_tk(
    monkeypatch, capsys,
):
    from skeleton.app import offline_game_preview
    from skeleton.app.offline_cli import main
    from skeleton.app.cli import run_app_cli

    calls: list[int] = []
    def fake_window(seed: int) -> int:
        calls.append(seed)
        return 0

    monkeypatch.setattr(offline_game_preview, "run_game_preview", fake_window)
    assert main(["--game-preview"]) == 0
    assert main(["--game-preview", "--game-seed", "42"]) == 0
    assert run_app_cli([
        "local-ai", "--game-preview", "--game-seed", "31",
    ]) == 0
    assert calls == [DEFAULT_SEED, 42, 31]
    assert capsys.readouterr().out == ""


def test_preview_core_has_no_network_or_model_dependency():
    import inspect
    from skeleton.app import offline_game_preview
    source = inspect.getsource(offline_game_preview)
    assert "subprocess" not in source
    assert "requests." not in source
    assert "urllib." not in source
    assert "model.generate" not in source
    assert "train(" not in source
    assert "import tkinter as tk" in source
    assert "platformer_step(" in source
