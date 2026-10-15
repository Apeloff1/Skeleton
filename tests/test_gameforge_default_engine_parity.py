"""Creator command routing contract: one implicit Godot engine for CLI and API.

This is a routing/manifest-propagation unit contract, not a Godot boot test.
Full deterministic emitted-file parity and headless boot need their own CI evidence.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from skeleton.app.runtime.command_contracts import CommandError
from skeleton.app.runtime.runtime_commands import _run_handler
from skeleton.context.pipeline import GameForgeRun


class _LegacySpecForge:
    def __init__(self):
        self.calls = []

    def run(self, answers, **options):
        self.calls.append((dict(answers), dict(options)))
        return {"legacy_spec": True, "target": options["target"]}


@pytest.mark.parametrize("target", [None, "godot"])
def test_implicit_and_explicit_godot_use_cli_pipeline(monkeypatch, target):
    calls = []
    manifest = {
        "schema": "skeleton.gameforge.source_manifest.v1",
        "file_count": 1,
        "files": {"project.godot": "b" * 64},
        "sha256": "a" * 64,
    }

    def capture(self, vision, **options):
        calls.append((vision, dict(options)))
        return {"succeeded": True, "source_manifest": manifest}

    monkeypatch.setattr(GameForgeRun, "execute", capture)
    legacy = _LegacySpecForge()
    payload = {
        "answers": {"genre": "adventure", "theme": "forest"},
        "vision": "A new original forest adventure",
        "playtest": "off",
    }
    if target is not None:
        payload["target"] = target

    result = _run_handler(SimpleNamespace(gameforge=legacy))(payload)
    assert result["engine"] == "gameforge_ten_stage"
    assert result["game"]["source_manifest"] == manifest
    assert len(calls) == 1
    assert calls[0][0] == payload["vision"]
    assert calls[0][1]["answers"] == payload["answers"]
    assert calls[0][1]["target"] == "godot"
    assert calls[0][1]["playtest"] == "off"
    assert legacy.calls == []


@pytest.mark.parametrize("target", ["json", "yaml"])
def test_legacy_spec_formats_must_be_selected_explicitly(target):
    legacy = _LegacySpecForge()
    result = _run_handler(SimpleNamespace(gameforge=legacy))({
        "answers": {"genre": "adventure"},
        "target": target,
        "title": "Original adventure",
    })
    assert result["game"] == {"legacy_spec": True, "target": target}
    assert result["status"] == "generated"
    assert legacy.calls[0][1]["target"] == target


@pytest.mark.parametrize("parameter", ["out", "project_root", "overwrite"])
def test_default_route_rejects_remote_filesystem_controls(monkeypatch, parameter):
    monkeypatch.setattr(
        GameForgeRun, "execute",
        lambda *_args, **_kwargs: pytest.fail("Path-bearing request reached the forge"),
    )
    with pytest.raises(CommandError):
        _run_handler(SimpleNamespace(gameforge=_LegacySpecForge()))({
            "answers": {}, parameter: "/tmp/untrusted",
        })


def test_default_route_rejects_unknown_answer_before_forge(monkeypatch):
    monkeypatch.setattr(
        GameForgeRun, "execute",
        lambda *_args, **_kwargs: pytest.fail("Unvalidated answers reached the forge"),
    )
    with pytest.raises(CommandError):
        _run_handler(SimpleNamespace(gameforge=_LegacySpecForge()))({
            "answers": {"unapproved_question": "anything"},
        })
