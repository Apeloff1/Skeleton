"""Real Godot export E2E: forged era → Linux/Web builds → exported binary boots."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from skeleton.forge import export as ex
from skeleton.forge import playtest as pt
from skeleton.forge.eras import compile_era
from skeleton.forge.godot_emit import emit_godot

_BIN = pt.resolve_binary()[0]
_REQUIRED = bool(os.environ.get("SKELETON_REQUIRE_GODOT"))
_TEMPLATES = Path(os.path.expanduser("~/.local/share/godot/export_templates/4.3.stable/linux_release.x86_64"))


def _files(era="extraction_now"):
    return emit_godot(compile_era(era), title="Export")


def test_export_validates_inputs(tmp_path):
    with pytest.raises(ValueError):
        ex.export_build({"a.gd": ""}, tmp_path)
    with pytest.raises(ValueError):
        ex.export_build(_files(), tmp_path, presets=("Switch",))
    with pytest.raises(ValueError):
        ex.export_build(_files(), tmp_path, presets=())
    files = dict(_files())
    files["export_presets.cfg"] = files["export_presets.cfg"].replace('name="Web"', 'name="Browser"')
    with pytest.raises(ValueError):
        ex.export_build(files, tmp_path, presets=("Web",))


def test_export_unavailable_without_binary(tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "resolve_binary", lambda binary=None: (None, "missing-godot-binary", False))
    report = ex.export_build(_files(), tmp_path)
    assert report["status"] == "unavailable"
    assert report["passed"] is False


def test_emitted_web_preset_is_single_threaded():
    cfg = _files()["export_presets.cfg"]
    assert "variant/thread_support=false" in cfg


@pytest.mark.skipif((_BIN is None or not _TEMPLATES.is_file()) and not _REQUIRED,
                    reason="needs Godot + 4.3 export templates")
def test_real_linux_and_web_export_boots(tmp_path):
    report = ex.export_build(_files("soulslike"), tmp_path, presets=("Linux", "Web"), boot_frames=60)
    assert report["status"] == "passed", {k: (v.get("reason"), v.get("log_tail", "")[-400:])
                                         for k, v in report.get("presets", {}).items()}
    linux = report["presets"]["Linux"]
    assert linux["boot"]["passed"] is True
    assert (tmp_path / "linux" / "game.x86_64").stat().st_size > 1_000_000
    assert (tmp_path / "linux" / "game.pck").is_file()
    assert (tmp_path / "web" / "index.html").is_file()
    assert (tmp_path / "web" / "index.wasm").is_file()
