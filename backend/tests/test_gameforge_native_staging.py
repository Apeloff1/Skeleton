"""Native GameForge exports stage privately and publish through governed storage."""

from __future__ import annotations

import asyncio
import io
import subprocess
from pathlib import Path
from zipfile import ZipFile

import pytest

from fastapi import HTTPException
from routes import gameforge_build as routes


PRINCIPAL = {"email": "builder@example.test", "tenant_id": "test-tenant", "role": "editor"}


def _instrument(monkeypatch):
    roots: list[Path] = []
    published: list[dict] = []
    original = routes._artifact_build

    def allocate(*args, **kwargs):
        root = Path(kwargs["artifacts_root"])
        roots.append(root)
        assert root != Path(routes._ARTIFACTS)
        assert root.is_dir()
        return original(*args, **kwargs)

    def publish(**kwargs):
        published.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr(routes, "_artifact_build", allocate)
    monkeypatch.setattr(routes, "_governed_register", publish)
    monkeypatch.setattr(routes, "_governed_store", lambda: object())
    monkeypatch.setattr(routes, "_owned_gamefiles", lambda _game, _user: [{"filename": "scene.gd"}])
    monkeypatch.setattr(routes, "code_execution_enabled", lambda: True)
    return roots, published


def test_native_godot_stages_privately_and_cleans_after_publish(monkeypatch):
    roots, published = _instrument(monkeypatch)
    monkeypatch.setattr(routes, "_godot_bin", lambda: None)

    result = asyncio.run(
        routes.build_godot(routes.BuildBody(game_name="QAStage"),
                           user=PRINCIPAL)
    )

    assert result["ok"] is True
    assert result["importable_godot_project"] is True
    assert result["engine_validated"] is False  # no native-engine attestation fabricated
    assert len(roots) == len(published) == 1
    assert not roots[0].exists()
    assert published[0]["tenant_id"] == "test-tenant"
    assert published[0]["kind"] == "godot"
    with ZipFile(io.BytesIO(published[0]["payload"])) as archive:
        assert {"project.godot", "main.gd", "main.tscn", "gamefiles.json"} == set(archive.namelist())


def test_native_desktop_stages_privately_and_cleans_after_publish(monkeypatch):
    roots, published = _instrument(monkeypatch)
    monkeypatch.setattr(routes, "_has_pyinstaller", lambda: True)

    def fake_run(command, **kwargs):
        assert kwargs["timeout"] == 110
        dest = Path(command[command.index("--distpath") + 1])
        name = command[command.index("--name") + 1]
        dest.mkdir(parents=True, exist_ok=True)
        (dest / name).write_bytes(b"synthetic local binary fixture")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = asyncio.run(
        routes.build_desktop(routes.DesktopBody(game_name="QAStage"),
                             user=PRINCIPAL)
    )
    assert result["ok"] is True
    assert result["binary_bytes"] > 0
    assert len(roots) == len(published) == 1
    assert not roots[0].exists()
    assert published[0]["tenant_id"] == "test-tenant"
    assert published[0]["kind"] == "desktop"
    with ZipFile(io.BytesIO(published[0]["payload"])) as archive:
        assert len(archive.namelist()) == 1
        assert archive.read(archive.namelist()[0]) == b"synthetic local binary fixture"


def test_native_scratch_is_deleted_when_governed_publication_fails(monkeypatch):
    roots, _ = _instrument(monkeypatch)
    monkeypatch.setattr(routes, "_godot_bin", lambda: None)

    def refused(**_kwargs):
        raise RuntimeError("storage policy unavailable")

    monkeypatch.setattr(routes, "_governed_register", refused)
    with pytest.raises(RuntimeError, match="storage policy unavailable"):
        asyncio.run(
            routes.build_godot(routes.BuildBody(game_name="QAStage"),
                               user=PRINCIPAL)
        )
    assert roots and not roots[0].exists()


@pytest.mark.parametrize(
    ("exit_code", "output", "expected"),
    [
        (0, "GameForge Godot build", True),
        (0, "", False),
        (1, "GameForge Godot build", False),
        (1, "", False),
    ],
)
def test_godot_engine_evidence_requires_exit_zero_and_scene_marker(
    monkeypatch, exit_code: int, output: str, expected: bool
):
    roots, published = _instrument(monkeypatch)
    monkeypatch.setattr(routes, "_godot_bin", lambda: "/virtual/godot")

    def fake_run(command, **kwargs):
        if "--version" in command:
            return subprocess.CompletedProcess(command, 0, stdout="4.3.stable", stderr="")
        return subprocess.CompletedProcess(command, exit_code, stdout=output, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = asyncio.run(
        routes.build_godot(routes.BuildBody(game_name="QAStage"),
                           user=PRINCIPAL)
    )
    assert len(roots) == len(published) == 1
    assert not roots[0].exists()
    assert result["engine_validated"] is expected
    assert result["headless_exported"] is False
    assert result["engine_log"] == (
        "engine_validated" if expected else "engine_validation_failed"
    )


def test_desktop_timeout_releases_private_workspace(monkeypatch):
    roots, published = _instrument(monkeypatch)
    monkeypatch.setattr(routes, "_has_pyinstaller", lambda: True)

    def timed_out(command, **_kwargs):
        raise subprocess.TimeoutExpired(command, 110)

    monkeypatch.setattr(subprocess, "run", timed_out)
    result = asyncio.run(
        routes.build_desktop(routes.DesktopBody(game_name="QAStage"),
                             user=PRINCIPAL)
    )
    assert result == {"ok": False, "error": "pyinstaller build timed out"}
    assert len(roots) == 1
    assert not roots[0].exists()
    assert published == []


def test_native_exports_refuse_unbound_artifact_owner_before_execution(monkeypatch):
    """No staging, compiler execution, or publication when custody is unavailable."""
    builds = []
    monkeypatch.setattr(routes, "_owned_gamefiles", lambda _name, _user: [{"filename": "scene.gd"}])
    monkeypatch.setattr(routes, "_artifact_build", lambda *_args, **_kwargs: builds.append(True))
    monkeypatch.setattr(routes, "code_execution_enabled", lambda: True)
    for build, body in (
        (routes.build_godot, routes.BuildBody(game_name="QAStage")),
        (routes.build_desktop, routes.DesktopBody(game_name="QAStage")),
    ):
        with pytest.raises(HTTPException) as raised:
            asyncio.run(build(body, user=PRINCIPAL))
        assert raised.value.status_code == 503
        assert raised.value.detail["code"] == "artifact_owner_unavailable"
    assert builds == []


def test_native_exports_reject_missing_authenticated_owner(monkeypatch):
    monkeypatch.setattr(routes, "_owned_gamefiles", lambda _name, user: routes.auth.require_authenticated_identity(user))
    for build, body in (
        (routes.build_godot, routes.BuildBody(game_name="QAStage")),
        (routes.build_desktop, routes.DesktopBody(game_name="QAStage")),
    ):
        with pytest.raises(HTTPException) as raised:
            asyncio.run(build(body, user={"tenant_id": "test-tenant"}))
        assert raised.value.status_code == 401
