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
    # Enter the clear start shaft before walking the guaranteed ground
    # lane. Random overhead platforms may obstruct naive top-lane walking.
    for _ in range(12):
        history.append(game.tick())
    for _ in range(18):
        history.append(game.tick(right=True))
        if history[-1].won:
            break
    assert any(frame.won for frame in history)
    final = history[-1]
    assert final.won is True
    assert final.avatar == final.goal == (16, 10)
    assert final.frame <= 30
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
    fresh = OfflineGamePreview(seed=DEFAULT_SEED)
    assert a.tick(right=True).as_dict() == fresh.tick(right=True).as_dict()


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


def test_game_preview_headless_qualification_reaches_goal_across_seeds():
    from skeleton.app.offline_game_preview import verify_game_preview

    for seed in (0, 1, 23, DEFAULT_SEED, 2**31 - 1):
        one = verify_game_preview(seed)
        two = verify_game_preview(seed)
        assert one == two
        assert one["schema_version"] == "skeleton.app.offline_game_preview_check.v1"
        assert one["terminal_won"] is True
        assert one["source_level_goal_reachable"] is True
        assert one["replay_deterministic"] is True
        assert 16 <= one["frames_verified"] <= 32
        assert len(one["replay_sha256"]) == 64
        assert one["training_examples_added"] == 0
        assert one["native_display_opened"] is False
        assert one["installed_tk_display_verified"] is False
        assert one["model_inference_used"] is False


def test_preview_seed_changes_real_platform_geometry_without_blocking_ground_lane():
    levels = [OfflineGamePreview(seed).tiles for seed in range(8)]
    assert len(set(levels)) >= 7
    for tiles in levels:
        assert all(tiles[y][1] != "#" for y in range(1, HEIGHT - 1))
        assert all(tiles[HEIGHT - 2][x] != "#" for x in range(1, WIDTH - 1))
        assert sum(line.count("G") for line in tiles) == 1


def test_game_preview_check_can_run_through_both_installed_cli_entrypoints(capsys):
    import json
    from skeleton.app.offline_cli import main
    from skeleton.app.cli import run_app_cli

    assert main(["--game-preview-check", "--game-seed", "42", "--json"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["terminal_won"] is True
    assert receipt["native_display_opened"] is False
    assert run_app_cli([
        "local-ai", "--game-preview-check", "--game-seed", "42", "--json",
    ]) == 0
    assert json.loads(capsys.readouterr().out) == receipt
    assert main(["--game-preview-check", "--model", "fake-model.json"]) == 2
    assert main(["--game-preview-check", "--queue-status"]) == 2
    assert main(["--game-preview-check", "--game-seed", "-1"]) == 1
    assert capsys.readouterr().out == ""


def test_native_tk_preview_draws_and_reacts_to_keys_when_present(monkeypatch):
    import sys
    from types import SimpleNamespace
    from skeleton.app.offline_game_preview import run_game_preview

    seen = {"draws": 0, "windows": 0, "destroyed": False, "pulses": 0}

    class FakeCanvas:
        def __init__(self, *_args, **_kwargs):
            pass
        def pack(self):
            pass
        def delete(self, *_args):
            pass
        def create_rectangle(self, *_args, **_kwargs):
            seen["draws"] += 1
        def create_oval(self, *_args, **_kwargs):
            seen["draws"] += 1
        def create_text(self, *_args, **_kwargs):
            seen["draws"] += 1

    class FakeWindow:
        def __init__(self):
            seen["windows"] += 1
            self.bindings = {}
            self.scheduled = []

        def title(self, value):
            assert "Offline Game Preview" in value
        def resizable(self, horizontal, vertical):
            assert not horizontal and not vertical
        def bind(self, name, callback):
            self.bindings[name] = callback
        def protocol(self, name, callback):
            assert name == "WM_DELETE_WINDOW"
            self.close = callback
        def after(self, delay, callback):
            assert delay == 100
            self.scheduled.append(callback)
        def focus_force(self):
            pass
        def mainloop(self):
            self.bindings["<KeyPress>"](SimpleNamespace(keysym="Right"))
            for _ in range(3):
                self.scheduled.pop(0)()
                seen["pulses"] += 1
            self.bindings["<KeyRelease>"](SimpleNamespace(keysym="Right"))
            self.bindings["<KeyPress>"](SimpleNamespace(keysym="Escape"))
        def destroy(self):
            seen["destroyed"] = True

    class FakeTclError(Exception):
        pass

    monkeypatch.setitem(sys.modules, "tkinter", SimpleNamespace(
        Tk=FakeWindow, Canvas=FakeCanvas, TclError=FakeTclError,
    ))
    assert run_game_preview(seed=42) == 0
    assert seen["windows"] == 1
    assert seen["draws"] > 20
    assert seen["pulses"] == 3
    assert seen["destroyed"] is True


def test_missing_desktop_display_does_not_disable_headless_replay(monkeypatch):
    import sys
    from types import SimpleNamespace
    from skeleton.app.offline_game_preview import run_game_preview, verify_game_preview

    class FakeTclError(Exception):
        pass

    def no_display():
        raise FakeTclError("missing desktop")

    monkeypatch.setitem(sys.modules, "tkinter", SimpleNamespace(
        Tk=no_display, TclError=FakeTclError,
    ))
    with pytest.raises(GameplayError, match="display"):
        run_game_preview()
    assert verify_game_preview()["terminal_won"] is True


def test_preview_never_appends_to_immutable_training_bank():
    import hashlib
    from pathlib import Path
    from skeleton.app.offline_game_preview import verify_game_preview

    bank = Path(__file__).resolve().parents[2] / (
        "skeleton/ai/training/datasets/offline_foundations_v1"
    )
    before = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in bank.iterdir() if path.is_file()
    }
    verify_game_preview(1729)
    assert before == {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in bank.iterdir() if path.is_file()
    }
