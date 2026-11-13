"""Exact-run, bounded Godot source export at the HTTP surface.

The standard run remains source-light. Only an explicit include_files
request for a succeeded source-sealed Godot run may carry the source map.
No network, filesystem publication, or external Godot binary is needed.
"""
from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi import HTTPException

from backend.routes.skeleton_gameforge import RunRequest, run
from skeleton.context.pipeline import GameForgeRun
from skeleton.forge.source_manifest import source_manifest


def stub(monkeypatch, payload: dict) -> list[dict]:
    calls: list[dict] = []

    class Stub:
        def execute(self, vision, **kwargs):
            calls.append({"vision": vision, **kwargs})
            return deepcopy(payload)

    monkeypatch.setattr(GameForgeRun, "live", lambda: Stub())
    return calls


def fixture(files: dict[str, str] | None = None, *, succeeded: bool = True) -> dict:
    files = files if files is not None else {
        "project.godot": 'config_version=5\nrun/main_scene="res://scenes/main.tscn"\n',
        "scenes/main.tscn": '[gd_scene format=3]\n',
        "scripts/quest.gd": 'extends Node\n',
    }
    return {
        "succeeded": succeeded, "files": files,
        "source_manifest": source_manifest(files),
    }


def test_default_http_run_removes_source_bodies_without_changing_run_request(monkeypatch):
    calls = stub(monkeypatch, fixture())
    out = run(RunRequest(vision="A local original game"))
    assert out["succeeded"] is True
    assert out["file_names"] == sorted(fixture()["files"])
    assert "files" not in out
    assert "source_export" not in out
    assert calls[-1]["project_root"] is None
    assert "include_files" not in calls[-1]


def test_opted_in_archive_preserves_original_exact_run_and_source_digest(monkeypatch):
    original = fixture()
    calls = stub(monkeypatch, original)
    out = run(RunRequest(vision="A local original game", include_files=True))
    assert calls[-1]["vision"] == "A local original game"
    assert out["files"] == original["files"]
    assert out["source_manifest"] == original["source_manifest"]
    assert out["source_export"] == {
        "status": "ready",
        "bytes": sum(len(body.encode("utf-8")) for body in original["files"].values()),
        "file_count": len(original["files"]),
        "manifest_sha256": original["source_manifest"]["sha256"],
    }


@pytest.mark.parametrize("mutator", [
    lambda p: p["files"].__setitem__("scripts/quest.gd", "extends Node\\n# injected\\n"),
    lambda p: p["source_manifest"]["files"].__setitem__("scripts/quest.gd", "0" * 64),
    lambda p: p["source_manifest"].__setitem__("sha256", "0" * 64),
    lambda p: p["files"].__setitem__("scripts/nul.gd", "extends Node\\n"),
    lambda p: p["files"].__setitem__(".git/config", "private\\n"),
    lambda p: p["files"].__setitem__("assets/con.gd", "extends Node\\n"),
    lambda p: p["files"].__setitem__("scripts/quest.gd", chr(0xD800)),
])
def test_source_export_recomputes_full_manifest_and_rejects_unsafe_paths(monkeypatch, mutator):
    payload = fixture()
    mutator(payload)
    stub(monkeypatch, payload)
    out = run(RunRequest(vision="An original Godot world", include_files=True))
    assert out["source_export"]["status"] == "unavailable"
    assert "files" not in out


@pytest.mark.parametrize("path, overwrite", [
    ("/tmp/gameforge-export", False),
    ("../../private/server-files", True),
    ("C:\\\\Users\\\\Public\\\\GameForge", False),
    ("", False),
    (None, True),
])
def test_remote_run_cannot_write_or_overwrite_server_files(monkeypatch, path, overwrite):
    invoked = []

    class NeverCall:
        def execute(self, *args, **kwargs):
            invoked.append((args, kwargs))
            raise AssertionError("remote filesystem write path must be rejected before execution")

    monkeypatch.setattr(GameForgeRun, "live", lambda: NeverCall())
    with pytest.raises(HTTPException) as refused:
        run(RunRequest(
            vision="My local-only original Godot project",
            project_root=path,
            overwrite=overwrite,
            include_files=True,
        ))
    assert refused.value.status_code == 400
    assert "cannot write server project paths" in refused.value.detail
    assert invoked == []


def test_http_run_ignores_project_publication_even_if_model_defaults_change(monkeypatch):
    calls = stub(monkeypatch, fixture())
    out = run(RunRequest(
        vision="An original game", project_root=None, overwrite=False,
        include_files=True,
    ))
    assert out["succeeded"] is True
    assert calls[-1]["project_root"] is None
    assert calls[-1]["overwrite"] is False
    assert out["source_export"]["status"] == "ready"


def test_non_godot_export_fails_closed_without_transferring_source_bodies(monkeypatch):
    stub(monkeypatch, fixture())
    out = run(RunRequest(target="json", include_files=True))
    assert out["source_export"]["status"] == "unavailable"
    assert "files" not in out


def test_failed_run_or_unsealed_source_is_never_download_ready(monkeypatch):
    unsuccessful = fixture(succeeded=False)
    stub(monkeypatch, unsuccessful)
    out = run(RunRequest(include_files=True))
    assert out["source_export"]["status"] == "unavailable"
    assert "files" not in out

    tampered = fixture()
    tampered["source_manifest"]["sha256"] = None
    stub(monkeypatch, tampered)
    out = run(RunRequest(include_files=True))
    assert out["source_export"]["status"] == "unavailable"
    assert "files" not in out


@pytest.mark.parametrize("oversize", ["bytes", "files"])
def test_source_payload_budget_fails_closed_without_failing_underlying_build(monkeypatch, oversize):
    if oversize == "bytes":
        files = {"project.godot": "x" * (8 * 1024 * 1024 + 1)}
    else:
        files = {"project.godot": "config_version=5\n"}
        files.update({f"scripts/source_{i}.gd": "extends Node\n" for i in range(256)})
    original = fixture(files)
    stub(monkeypatch, original)
    out = run(RunRequest(include_files=True))
    assert out["succeeded"] is True
    assert out["source_export"]["status"] == "unavailable"
    assert "files" not in out
    assert out["file_names"] == sorted(files)
