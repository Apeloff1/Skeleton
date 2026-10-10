"""Test real original CHIP-8 executable gaming, keypad UX and Tk boundaries."""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

from skeleton.app.offline_chip8_preview import (
    OriginalChip8Game, verify_native_chip8_player, run_native_chip8_preview,
)
from skeleton.app.offline_cli import main as offline_console
from skeleton.app.cli import run_app_cli
from skeleton.ai.runtime.chip8_machine import Chip8Error


@pytest.mark.parametrize("seed", [0, 1, 42, 1729, 65535])
def test_chip8_native_game_is_real_bytecode_with_independent_winning_trace(seed):
    session = OriginalChip8Game(seed=seed)
    first = session.frame()
    assert first["won"] is False
    assert first["current_cell_state"] == session.compiled["initial_state"]
    assert first["waiting_for_key"] is True
    assert first["copyrighted_rom_loaded"] is False
    assert first["hardware_1970s_verified"] is False
    assert first["license_publication_verified"] is False
    assert first["training_examples_added"] == 0
    for key in session.compiled["shortest_path_keys"]:
        final = session.key(key)
    assert final["won"] is True
    assert final["rom_sha256"] == session.compiled["rom_sha256"]
    assert final["inputs_applied"] == len(session.compiled["shortest_path_keys"])
    assert session.key(4) == final
    proof = verify_native_chip8_player(seed)
    assert proof["original_player_won"] is True
    assert proof["win_state_reached"] is True
    assert proof["controller_events"] == final["inputs_applied"]
    assert proof["rom_sha256"] == final["rom_sha256"]
    assert proof["native_window_was_opened"] is False
    assert proof["real_vintage_hardware_verified"] is False
    assert proof["copyrighted_firmware_included"] is False
    assert proof["model_inference_used"] is False
    assert proof["training_examples_added"] == 0
    assert verify_native_chip8_player(seed) == proof


def test_original_native_chip8_enforces_map_collision_and_clean_reset():
    session = OriginalChip8Game(seed=42)
    before = session.frame()
    blocked = session.key(4)
    assert blocked["current_cell_state"] == before["current_cell_state"]
    assert blocked["display_sha256"] == before["display_sha256"]
    assert blocked["inputs_applied"] == 1
    session.key(6)
    reset = session.reset()
    assert reset["current_cell_state"] == before["current_cell_state"]
    assert reset["display_sha256"] == before["display_sha256"]
    assert reset["inputs_applied"] == 0
    assert reset["won"] is False
    assert reset["rom_sha256"] == before["rom_sha256"]


@pytest.mark.parametrize("key", [-1, 16, True, 1.2, "4", None])
def test_chip8_native_key_event_is_strictly_validated(key):
    session = OriginalChip8Game()
    before = session.frame()
    with pytest.raises(Chip8Error):
        session.key(key)
    assert session.frame() == before


def test_both_application_consoles_accept_real_chip8_win_qualification(capsys):
    assert offline_console(["--chip8-demo-check", "--json"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["original_player_won"] is True
    assert receipt["copyrighted_firmware_included"] is False
    assert run_app_cli(["local-ai", "--chip8-demo-check", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == receipt
    assert receipt["training_examples_added"] == 0


def test_chip8_native_window_displays_generated_pixels_and_receives_real_keys(monkeypatch):
    observed = {"draw": 0, "windows": 0, "destroyed": False, "key": 0}
    class FakeCanvas:
        def __init__(self, *_a, **_k):
            pass
        def pack(self):
            pass
        def delete(self, *_a):
            pass
        def create_rectangle(self, *_a, **_k):
            observed["draw"] += 1
        def create_text(self, *_a, **_k):
            observed["draw"] += 1

    class FakeRoot:
        def __init__(self):
            observed["windows"] += 1
            self.onkey = None
        def title(self, value):
            assert "Original CHIP-8 Game" in value
        def resizable(self, x, y):
            assert x is False and y is False
        def bind(self, name, callback):
            assert name == "<KeyPress>"
            self.onkey = callback
        def focus_force(self):
            pass
        def mainloop(self):
            for value in ("Left", "Right", "R", "Escape"):
                self.onkey(SimpleNamespace(keysym=value))
                observed["key"] += 1
        def destroy(self):
            observed["destroyed"] = True

    class FakeTclError(Exception):
        pass
    monkeypatch.setitem(sys.modules, "tkinter", SimpleNamespace(
        Tk=FakeRoot, Canvas=FakeCanvas, TclError=FakeTclError,
    ))
    assert run_native_chip8_preview(seed=42) == 0
    assert observed["windows"] == 1
    assert observed["draw"] > 8
    assert observed["key"] == 4
    assert observed["destroyed"] is True


def test_chip8_native_display_failure_keeps_headless_gameplay_operational(monkeypatch):
    class FakeTclError(Exception):
        pass
    def no_window():
        raise FakeTclError("no GUI")
    monkeypatch.setitem(sys.modules, "tkinter", SimpleNamespace(
        Tk=no_window, TclError=FakeTclError,
    ))
    with pytest.raises(Chip8Error, match="desktop"):
        run_native_chip8_preview()
    assert verify_native_chip8_player()["original_player_won"]


def test_native_game_entrypoint_routes_to_original_chip8_mode_without_web_browser(
    monkeypatch,
):
    import importlib.util
    from pathlib import Path
    entrypoint = Path("packaging/windows/game_preview_entry.py").resolve()
    spec = importlib.util.spec_from_file_location("skeleton_game_preview_entry_test", entrypoint)
    assert spec is not None and spec.loader is not None
    entry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entry)
    called = []
    monkeypatch.setattr(entry, "run_native_chip8_preview",
                        lambda: called.append("chip8") or 0)
    assert entry.main(["--chip8-demo"]) == 0
    assert called == ["chip8"]


def test_default_native_chip8_seed_matches_installed_original_rom_exporter():
    from scripts.game.export_chip8 import _original_capsule, compile_chip8_homebrew
    expected = compile_chip8_homebrew(_original_capsule(1729))
    native = verify_native_chip8_player()
    assert native["rom_sha256"] == expected["rom_sha256"]
    assert OriginalChip8Game().compiled["rom_sha256"] == expected["rom_sha256"]
