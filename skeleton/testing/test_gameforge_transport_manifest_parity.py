"""Guard creator-CLI and authenticated command transport against engine drift.

Fixtures isolate the shared pipeline entrypoint. These tests prove dispatch
and manifest projection parity, not successful real Godot boot/playability.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from skeleton.__main__ import main
from skeleton.application import build_runtime_command_service
from skeleton.context import operator_state, pipeline


_MANIFEST = {
    "schema": "skeleton.forge.source_manifest.v1",
    "file_count": 2,
    "files": {
        "project.godot": "a" * 64,
        "scenes/start.tscn": "b" * 64,
    },
    "sha256": "c" * 64,
}


class _PipelineFixture:
    calls: list[dict] = []

    def __init__(self, *, cockpit=None) -> None:
        self.cockpit = cockpit

    @classmethod
    def live(cls, *, cockpit=None):
        return cls(cockpit=cockpit)

    def execute(self, vision, **kwargs):
        self.calls.append({"vision": vision, **kwargs})
        return {
            "succeeded": True,
            "source_manifest": dict(_MANIFEST),
            "run": {"stages": []},
            "era": "fixture",
            "forge": {"file_count": 2},
            "mass": 1.0,
            "complete": True,
            "sim": {"passed": True},
            "playtest": {"status": "off"},
        }


class _LegacySpec:
    def __init__(self) -> None:
        self.calls = []

    def run(self, answers, **kwargs):
        self.calls.append({"answers": answers, **kwargs})
        return {"legacy_format": kwargs["target"]}


@pytest.fixture
def shared_pipeline(monkeypatch):
    _PipelineFixture.calls = []
    monkeypatch.setattr(pipeline, "GameForgeRun", _PipelineFixture)
    monkeypatch.setattr(operator_state, "read_steering", lambda: None)
    return _PipelineFixture


def test_cli_and_command_api_choose_same_canonical_godot_engine_and_manifest(
    shared_pipeline, capsys
):
    exit_code = main(["run", "a quiet forest", "--json"])
    assert exit_code == 0
    cli = json.loads(capsys.readouterr().out)
    legacy = _LegacySpec()
    response = build_runtime_command_service(
        SimpleNamespace(gameforge=legacy)
    ).execute("run", {"vision": "a quiet forest"})
    assert response.ok is True
    assert response.data["engine"] == "gameforge_ten_stage"
    assert cli["source_manifest"] == response.data["game"]["source_manifest"]
    assert len(shared_pipeline.calls) == 2
    assert all(call["vision"] == "a quiet forest" for call in shared_pipeline.calls)
    assert all(call["target"] == "godot" for call in shared_pipeline.calls)
    assert all(call["repair_mode"] == "apply" for call in shared_pipeline.calls)
    assert not legacy.calls


@pytest.mark.parametrize("field,value", [
    ("out", "/tmp/from-http"),
    ("project_root", "/tmp/from-http"),
    ("overwrite", True),
])
def test_command_godot_refuses_remote_filesystem_access(
    shared_pipeline, field, value
):
    response = build_runtime_command_service(
        SimpleNamespace(gameforge=_LegacySpec())
    ).execute("run", {"vision": "a quiet forest", field: value})
    assert response.ok is False
    assert response.to_payload()["error"]["code"] == "invalid_argument"
    assert shared_pipeline.calls == []


@pytest.mark.parametrize("target", ["json", "yaml"])
def test_legacy_spec_engine_requires_explicit_target(shared_pipeline, target):
    legacy = _LegacySpec()
    response = build_runtime_command_service(
        SimpleNamespace(gameforge=legacy)
    ).execute("run", {"answers": {}, "target": target})
    assert response.ok is True
    assert response.data["game"] == {"legacy_format": target}
    assert len(legacy.calls) == 1
    assert legacy.calls[0]["target"] == target
    assert shared_pipeline.calls == []
