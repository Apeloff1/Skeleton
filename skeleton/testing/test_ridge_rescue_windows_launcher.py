"""Windows double-click launcher and ASCII gameplay fallbacks."""
from __future__ import annotations

from pathlib import Path

from skeleton.game.gameplay.ridge_rescue.consumer_bundle import build_bundle
from skeleton.game.gameplay.ridge_rescue.consumer_cli import _view
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore


def test_portable_windows_launcher_is_fixed_and_double_clickable(tmp_path):
    report = build_bundle(SlotStore(tmp_path / "saves"))
    script = Path(report["windows_launcher"]).read_text(encoding="ascii")
    assert Path(report["path"]).name in script
    assert "play --ascii" in script
    assert "py -3" in script
    assert "sys.version_info >= (3, 11)" in script
    assert "if not defined PY" in script
    assert "%~dp0" in script
    assert "powershell" not in script.lower()


def test_ascii_fallback_renders_playable_map(tmp_path):
    current = SlotStore(tmp_path / "saves").new("game")
    screen = _view(current, ascii_mode=True)
    assert screen.isascii()
    assert "Actions:" in screen
    assert "Chapter:" in screen
    assert "Stamina" in screen


def test_windows_smoke_launcher_executes_source_and_portable_acceptance():
    script = (Path(__file__).resolve().parents[2] / "scripts" / "windows" /
              "cinder-ridge-smoke.cmd").read_text(encoding="ascii")
    assert "consumer smoke" in script
    assert "sys.version_info >= (3, 11)" in script
    assert "consumer portable-smoke" in script
    assert script.index("consumer smoke") < script.index("consumer portable-smoke")
    assert "if errorlevel 1 goto :failed" in script
    assert "No release qualification is granted" in script
    assert "exit /b 1" in script
    assert "powershell" not in script.lower()
