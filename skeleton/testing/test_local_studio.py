"""Local Studio: security boundary, build-to-project flow, editor, playtest and export."""

from __future__ import annotations

import io
import json
import subprocess
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from skeleton.app import local_studio as ls
from skeleton.app import windows_first_install as wfi

SECRET = "fedcba9876543210" * 4
PORT = 8710
HOST = {"host": f"127.0.0.1:{PORT}"}


def _proc(stdout: str = "", rc: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], rc, stdout, "")


@pytest.fixture()
def studio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Real canonical app + Studio composed exactly like ``serve`` does."""
    from skeleton.api.server import create_app

    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)
    monkeypatch.setenv("SKELETON_HOME", str(tmp_path / "home"))
    canonical = create_app()
    opened: list[Path] = []
    godot = tmp_path / "godot"
    godot.write_text("x")

    def runner(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        if "--script" in cmd:
            return _proc('FORGE_INTERACTIVE_OK {"won":true}\n')
        if "--quit-after" in cmd:
            return _proc("CORE_LOOP_OK genre=platformer marker=goal:7\n")
        return _proc("")

    holder: dict[str, Any] = {}
    settings = ls.StudioSettings(
        port=PORT, games_dir=tmp_path / "games", seal_secret=SECRET,
        godot=lambda: godot, runner=runner,
        opener=lambda project, binary: opened.append(project) or 4242,
        client_factory=lambda s: wfi.ApiClient("http://testserver", secret=SECRET, opener=holder["opener"]),
    )
    app = ls.compose(canonical, ls.create_studio_app(settings))
    with TestClient(app, base_url=f"http://127.0.0.1:{PORT}") as http:
        class _Resp:
            def __init__(self, r: Any) -> None:
                self.status, self._raw = r.status_code, r.content

            def read(self) -> bytes:
                return self._raw

            def __enter__(self) -> "_Resp":
                return self

            def __exit__(self, *exc: object) -> None:
                return None

        def opener(req: Any, timeout: float) -> _Resp:
            import urllib.error

            path = req.full_url.split("http://testserver", 1)[1]
            r = http.request(req.get_method(), path, content=req.data, headers=dict(req.header_items()))
            if r.status_code >= 400:
                raise urllib.error.HTTPError(req.full_url, r.status_code, "err", {}, io.BytesIO(r.content))
            return _Resp(r)

        holder["opener"] = opener
        auth = {ls.TOKEN_HEADER: settings.token}
        yield http, settings, auth, opened


def _build(http: TestClient, auth: dict[str, str], brief: str = wfi.SAMPLE_BRIEF) -> dict[str, Any]:
    started = http.post("/studio/api/builds", json={"brief": brief, "playtest": "off"}, headers=auth)
    assert started.status_code == 202, started.text
    build_id = started.json()["build_id"]
    for _ in range(200):
        view = http.get(f"/studio/api/builds/{build_id}", headers=auth).json()
        if view["status"] in {"succeeded", "failed", "cancelled"}:
            return view
        import time

        time.sleep(0.05)
    raise AssertionError("build did not finish")


def test_static_shell_has_strict_security_headers(studio) -> None:
    http, _settings, _auth, _ = studio
    page = http.get("/studio/")
    assert page.status_code == 200
    assert "<script type=\"module\" src=\"/studio/app.js\"></script>" in page.text
    assert "script-src 'self'" in page.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert page.headers["x-content-type-options"] == "nosniff"
    assert page.headers["referrer-policy"] == "no-referrer"
    assert http.get("/studio/app.js").headers["content-type"].startswith("text/javascript")
    assert http.get("/studio/app.css").status_code == 200
    assert http.get("/studio/secrets.json").status_code == 404
    assert http.get("/studio", follow_redirects=False).status_code == 308
    assert "<script>" not in page.text and "onclick=" not in page.text


def test_api_requires_token_loopback_host_and_same_origin(studio) -> None:
    http, settings, auth, _ = studio
    assert http.get("/studio/api/projects").status_code == 401
    assert http.get("/studio/api/projects", headers={ls.TOKEN_HEADER: "x" * 43}).status_code == 401
    assert http.get("/studio/api/projects", headers={**auth, "host": "evil.example:8710"}).status_code == 403
    assert http.get("/studio/api/projects", headers={**auth, "origin": "http://evil.example"}).status_code == 403
    ok = http.get("/studio/api/projects", headers={**auth, "origin": f"http://127.0.0.1:{PORT}"})
    assert ok.status_code == 200 and ok.json() == {"projects": []}
    # The canonical API is untouched: still sealed, and not reachable with the Studio token.
    assert http.get("/api/v1/health", headers=auth).status_code == 401
    assert settings.url.startswith(f"http://127.0.0.1:{PORT}/studio/#token=")


def test_status_reports_health_without_secrets(studio) -> None:
    http, settings, auth, _ = studio
    body = http.get("/studio/api/status", headers=auth).json()
    assert body["schema"] == ls.STATUS_SCHEMA and body["api_healthy"] is True
    assert body["projects"] == 0
    raw = json.dumps(body)
    assert SECRET not in raw and settings.token not in raw


def test_build_persists_project_once_then_edit_playtest_open_export(studio) -> None:
    http, settings, auth, opened = studio
    view = _build(http, auth)
    assert view["status"] == "succeeded", view
    assert view["genre"] == "platformer" and view["project"]
    name = view["project"]
    again = http.get(f"/studio/api/builds/{view['build_id']}", headers=auth).json()
    assert again["project"] == name
    assert len(list(settings.games_dir.iterdir())) == 1

    listing = http.get("/studio/api/projects", headers=auth).json()["projects"]
    assert [p["name"] for p in listing] == [name] and listing[0]["genre"] == "platformer"

    detail = http.get(f"/studio/api/projects/{name}", headers=auth).json()
    paths = {f["path"] for f in detail["files"]}
    assert "project.godot" in paths and ls.SIDECAR not in paths
    script = next(f["path"] for f in detail["files"] if f["path"].endswith(".gd"))

    read = http.get(f"/studio/api/projects/{name}/file", params={"path": script}, headers=auth).json()
    assert read["editable"] is True and read["content"]
    edited = read["content"] + "\n# tuned in Studio\n"
    saved = http.put(f"/studio/api/projects/{name}/file", json={"path": script, "content": edited}, headers=auth)
    assert saved.status_code == 200 and saved.json()["saved"] is True
    assert (settings.games_dir / name / script).read_text(encoding="utf-8") == edited

    played = http.post(f"/studio/api/projects/{name}/playtest", headers=auth).json()
    assert played["ok"] is True and [s["step"] for s in played["steps"]] == ["import", "core_loop", "interactive"]
    assert http.get("/studio/api/projects", headers=auth).json()["projects"][0]["last_playtest"]["ok"] is True

    assert http.post(f"/studio/api/projects/{name}/open", headers=auth).json() == {"opened": True, "pid": 4242}
    assert opened == [settings.games_dir / name]

    exported = http.get(f"/studio/api/projects/{name}/export.zip", headers=auth)
    assert exported.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(exported.content)).namelist()
    assert f"{name}/project.godot" in names and f"{name}/{ls.SIDECAR}" not in names
    assert all(n.startswith(f"{name}/") for n in names)


@pytest.mark.parametrize("path", ["../escape.gd", "/etc/passwd", "C:/x.gd", "scripts/../../x.gd", "a\\..\\..\\x.gd"])
def test_file_routes_refuse_traversal(studio, path: str) -> None:
    http, settings, auth, _ = studio
    name = _build(http, auth)["project"]
    assert http.get(f"/studio/api/projects/{name}/file", params={"path": path}, headers=auth).status_code in {404, 422}
    put = http.put(f"/studio/api/projects/{name}/file", json={"path": path, "content": "x"}, headers=auth)
    assert put.status_code in {404, 422}
    assert not (settings.games_dir / "escape.gd").exists()


def test_editor_refuses_new_files_sidecar_and_oversize(studio) -> None:
    http, _settings, auth, _ = studio
    name = _build(http, auth)["project"]
    url = f"/studio/api/projects/{name}/file"
    assert http.put(url, json={"path": "new_file.gd", "content": "x"}, headers=auth).status_code == 404
    assert http.put(url, json={"path": ls.SIDECAR, "content": "{}"}, headers=auth).status_code == 422
    big = "x" * (ls.MAX_EDIT_BYTES + 1)
    assert http.put(url, json={"path": "project.godot", "content": big}, headers=auth).status_code == 413


def test_unknown_projects_and_builds_are_404(studio) -> None:
    http, _settings, auth, _ = studio
    for path in ("/studio/api/projects/nope", "/studio/api/projects/..%2F..", "/studio/api/builds/job_missing",
                 "/studio/api/projects/nope/export.zip"):
        assert http.get(path, headers=auth).status_code == 404, path


@pytest.mark.parametrize("payload,fragment", [
    ({"brief": ""}, "Describe"),
    ({"brief": "   "}, "Describe"),
    ({"brief": "x" * (ls.MAX_BRIEF_CHARS + 1)}, "under"),
    ({"brief": "a platformer", "playtest": "maybe"}, "playtest"),
])
def test_build_validation_messages(studio, payload: dict[str, Any], fragment: str) -> None:
    http, _settings, auth, _ = studio
    response = http.post("/studio/api/builds", json=payload, headers=auth)
    assert response.status_code == 422 and fragment in response.json()["detail"]


def test_write_studio_url_is_owner_only(tmp_path: Path) -> None:
    settings = ls.StudioSettings(port=PORT, games_dir=tmp_path / "g", seal_secret=SECRET)
    target = ls.write_studio_url(settings, tmp_path / "run")
    assert target.read_text().strip() == settings.url
    import os
    import stat

    if os.name != "nt":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_serve_refuses_remote_studio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)
    with pytest.raises(wfi.FirstInstallError, match="loopback-only"):
        wfi.serve("0.0.0.0", PORT, allow_remote=True, studio=True)
