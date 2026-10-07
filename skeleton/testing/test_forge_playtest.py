"""Forge playable-build gate: questionnaire → forge → repair → headless boot.

Static tests always run. Tests marked ``needs_godot`` boot the emitted
project in a real headless Godot 4 and are skipped when no binary resolves
(set ``SKELETON_GODOT_BIN`` to enable them locally / in CI).
"""
from __future__ import annotations

import pytest

from skeleton.context.pipeline import GameForgeRun
from skeleton.context.questionnaire import BEATS
from skeleton.forge import playtest as pt
from skeleton.forge.eras import ERA_IDS, compile_era
from skeleton.forge.godot_emit import emit_godot
from skeleton.forge.verify_loop import forge_verify_until_green

_BIN, _SOURCE, _ = pt.resolve_binary()
needs_godot = pytest.mark.skipif(_BIN is None, reason="no Godot binary (set SKELETON_GODOT_BIN)")

ANSWERS = {b["id"]: next(iter(b["options"])) for b in BEATS if b["id"] != "era_explicit"}


@pytest.fixture(autouse=True)
def _keep_provenance(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    yield


def _files(era: str = "extraction_now"):
    return emit_godot(compile_era(era), title="Playtest")


def _stage(payload, name):
    return next(s for s in payload["run"]["stages"] if s.get("name") == name)


# ---------------------------------------------------------------- static


@pytest.mark.parametrize("raw,want", [
    (None, "off"), (False, "off"), (True, "auto"), ("auto", "auto"),
    ("REQUIRE", "require"), (" off ", "off"),
])
def test_normalise_mode(raw, want):
    assert pt.normalise_mode(raw) == want


def test_normalise_mode_rejects_unknown():
    with pytest.raises(ValueError):
        pt.normalise_mode("sometimes")


def test_scan_log_keeps_errors_and_drops_benign_noise():
    log = (
        "Godot Engine v4.3.stable\n"
        "SCRIPT ERROR: Parse Error: Expected expression.\n"
        "   at: GDScript::reload (res://scripts/a.gd:3)\n"
        "ERROR: No export template found at the expected path:\n"
        "ERROR: Failed to load script \"res://b.gd\" with error \"Parse error\".\n"
        "WARNING: something harmless\n"
    )
    errors = pt.scan_log(log)
    assert errors == [
        "SCRIPT ERROR: Parse Error: Expected expression.",
        "ERROR: Failed to load script \"res://b.gd\" with error \"Parse error\".",
    ]


def test_playtest_validates_inputs():
    with pytest.raises(ValueError):
        pt.playtest({"a.gd": "extends Node\n"})
    with pytest.raises(ValueError):
        pt.playtest(_files(), frames=0)
    with pytest.raises(ValueError):
        pt.playtest(_files(), frames=True)


def test_playtest_unavailable_without_binary(monkeypatch):
    monkeypatch.setattr(pt, "resolve_binary", lambda binary=None: (None, "missing-godot-binary", False))
    report = pt.playtest(_files())
    assert report["status"] == "unavailable"
    assert report["passed"] is False
    assert report["reason"] == "missing-godot-binary"


def test_resolve_binary_argument_missing(tmp_path):
    path, source, verified = pt.resolve_binary(str(tmp_path / "nope"))
    assert (path, source, verified) == (None, "argument-missing", False)


def test_export_presets_are_godot4_format():
    cfg = _files()["export_presets.cfg"]
    assert "Linux/X11" not in cfg
    for index, platform in enumerate(("Linux", "Windows Desktop", "Web")):
        assert f"[preset.{index}]" in cfg
        assert f"[preset.{index}.options]" in cfg
        assert f'platform="{platform}"' in cfg
    for key in ("export_filter=", "include_filter=", "exclude_filter=",
                "dedicated_server=", "custom_features=", "encrypt_pck="):
        assert cfg.count(key) == 3, key


def test_execute_rejects_bad_modes():
    with pytest.raises(ValueError):
        GameForgeRun().execute("a heist", playtest="maybe")
    with pytest.raises(ValueError):
        GameForgeRun().execute("a heist", repair_mode="rewrite")


def test_execute_playtest_off_by_default():
    payload = GameForgeRun().execute("", answers=ANSWERS)
    assert payload["succeeded"] is True
    assert payload["playtest"] is None


def test_execute_auto_without_binary_is_informative(monkeypatch):
    monkeypatch.setattr(pt, "resolve_binary", lambda binary=None: (None, "missing-godot-binary", False))
    payload = GameForgeRun().execute("", answers=ANSWERS, playtest="auto")
    assert payload["succeeded"] is True
    assert payload["playtest"]["status"] == "unavailable"


def test_execute_require_without_binary_fails_emit(monkeypatch):
    monkeypatch.setattr(pt, "resolve_binary", lambda binary=None: (None, "missing-godot-binary", False))
    payload = GameForgeRun().execute("", answers=ANSWERS, playtest="require")
    assert payload["succeeded"] is False
    emit = _stage(payload, "emit")
    assert "playtest unavailable" in str(emit.get("error"))


def test_execute_repair_mode_reaches_verify_loop():
    for mode in ("apply", "suggest"):
        payload = GameForgeRun().execute("", answers=ANSWERS, repair_mode=mode)
        assert payload["forge"]["verify_loop"]["repair_mode"] == mode


# ------------------------------------------------------- real headless boot


@needs_godot
def test_questionnaire_to_playable_build_end_to_end():
    payload = GameForgeRun().execute("", answers=ANSWERS, playtest="require")
    assert payload["succeeded"] is True, [
        (s.get("name"), s.get("error")) for s in payload["run"]["stages"] if s.get("error")
    ]
    assert payload["complete"] is True
    assert payload["forge"]["verification"]["accepted"] is True
    assert payload["sim"]["passed"] is True
    assert payload["playtest"]["status"] == "passed"
    assert payload["playtest"]["errors"] == []


@needs_godot
def test_vision_composed_build_boots():
    payload = GameForgeRun().execute(
        "", answers={"genre": "metroidvania", "theme": "dark-fantasy"},
        archetype="auto", playtest="require",
    )
    assert payload["succeeded"] is True
    assert payload["playtest"]["passed"] is True


@needs_godot
@pytest.mark.parametrize("era", ERA_IDS[::6])
def test_canonical_eras_boot(era):
    report = pt.playtest(_files(era), frames=60)
    assert report["status"] == "passed", report["errors"]


@needs_godot
def test_playtest_catches_a_parse_error():
    files = dict(_files())
    files["scripts/player/player_controller.gd"] = "extends CharacterBody2D\nfunc _ready():\n\tvar x = 1 +\n"
    report = pt.playtest(files, frames=30)
    assert report["status"] == "failed"
    assert any("Parse Error" in e for e in report["errors"])


@needs_godot
def test_broken_build_is_repaired_then_boots(tmp_path):
    files = dict(_files())
    files["scripts/player/player_controller.gd"] = "func _ready():\n\tOS.execute(\"rm\", [\"-rf\", \"/\"])\n"
    del files["scripts/autoloads/event_bus.gd"]
    loop = forge_verify_until_green(files, request="extraction heist", root=tmp_path,
                                    pack=compile_era("extraction_now"))
    assert loop["accepted"] is True
    assert loop["repair_mode"] == "apply"
    repaired = loop["files"]
    assert "OS.execute(" not in "\n".join(
        ln for ln in repaired["scripts/player/player_controller.gd"].splitlines() if not ln.lstrip().startswith("#")
    )
    report = pt.playtest(repaired, frames=60)
    assert report["status"] == "passed", report["errors"]


@needs_godot
def test_suggest_mode_leaves_build_broken(tmp_path):
    files = dict(_files())
    del files["scripts/autoloads/event_bus.gd"]
    loop = forge_verify_until_green(files, request="extraction heist", root=tmp_path,
                                    pack=compile_era("extraction_now"), repair_mode="suggest")
    assert "scripts/autoloads/event_bus.gd" not in loop["files"]
    assert pt.playtest(loop["files"], frames=30)["status"] == "failed"
