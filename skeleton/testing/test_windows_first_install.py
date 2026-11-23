"""Tests for the native Windows first-install adapter (doctor/build/play/smoke)."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import urllib.error
from pathlib import Path
from typing import Any

import pytest

from skeleton.app import windows_first_install as wfi

SECRET = "0123456789abcdef" * 4


class _Resp:
    def __init__(self, status: int, body: Any) -> None:
        self.status = status
        self._raw = json.dumps(body).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> "_Resp":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _proc(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


# ------------------------------------------------------------------ helpers


def test_slugify_and_dirs_follow_env_precedence(tmp_path: Path) -> None:
    assert wfi.slugify("Rain-slick Ledges: Above!") == "rain-slick-ledges-above"
    assert wfi.slugify("!!!") == "game"
    assert len(wfi.slugify("x" * 200)) <= 48
    env = {"LOCALAPPDATA": str(tmp_path / "local")}
    assert wfi.default_data_root(env) == tmp_path / "local" / "Skeleton"
    assert wfi.default_games_dir(env) == tmp_path / "local" / "Skeleton" / "games"
    env["SKELETON_HOME"] = str(tmp_path / "home")
    assert wfi.default_games_dir(env) == tmp_path / "home" / "games"
    env["SKELETON_GAMES_DIR"] = str(tmp_path / "g")
    assert wfi.default_games_dir(env) == tmp_path / "g"


@pytest.mark.parametrize("text,expected", [
    ("4.6.stable.official.89cea1439", (4, 6)),
    ("4.3.stable.official.77dcf97d8\n", (4, 3)),
    ("3.5.3.stable", (3, 5)),
    ("Godot Engine", None),
    ("", None),
])
def test_parse_godot_version(text: str, expected: tuple[int, int] | None) -> None:
    assert wfi.parse_godot_version(text) == expected


def test_find_godot_prefers_explicit_env(tmp_path: Path) -> None:
    binary = tmp_path / "Godot_v4.6-stable_win64_console.exe"
    binary.write_text("x")
    assert wfi.find_godot({"SKELETON_GODOT_BIN": str(binary), "PATH": ""}) == binary
    assert wfi.find_godot({"SKELETON_GODOT_BIN": str(tmp_path / "missing"), "PATH": ""}) is None


# ------------------------------------------------------------------ doctor


def _doctor_env(tmp_path: Path, **extra: str) -> dict[str, str]:
    binary = tmp_path / "godot"
    binary.write_text("x")
    env = {"SKELETON_HOME": str(tmp_path / "home"), "SKELETON_GODOT_BIN": str(binary),
           "GF_SEAL_SECRET": SECRET, "PATH": ""}
    env.update(extra)
    return env


def test_doctor_ready_with_godot_4_and_secret(tmp_path: Path) -> None:
    report = wfi.doctor(env=_doctor_env(tmp_path), runner=lambda *a, **k: _proc("4.6.stable.official\n"))
    assert report["schema"] == wfi.DOCTOR_SCHEMA
    assert report["ok"] is True, report
    ids = {c["id"]: c for c in report["checks"]}
    assert ids["godot"]["ok"] and ids["seal_secret"]["ok"] and ids["games_dir"]["ok"]
    assert "no model provider" in ids["ai_provider"]["detail"]
    assert SECRET not in json.dumps(report)


def test_doctor_rejects_godot_3_and_missing_secret(tmp_path: Path) -> None:
    env = _doctor_env(tmp_path)
    del env["GF_SEAL_SECRET"]
    report = wfi.doctor(env=env, runner=lambda *a, **k: _proc("3.5.3.stable\n"))
    failed = {c["id"] for c in report["checks"] if not c["ok"]}
    assert report["ok"] is False
    assert {"godot", "seal_secret"} <= failed
    assert all(c["remediation"] for c in report["checks"] if not c["ok"])


def test_doctor_godot_optional_when_not_required(tmp_path: Path) -> None:
    env = _doctor_env(tmp_path)
    env["SKELETON_GODOT_BIN"] = str(tmp_path / "missing")
    report = wfi.doctor(env=env, runner=lambda *a, **k: _proc(""), require_godot=False)
    assert report["ok"] is True


def test_doctor_reports_unconfigured_hosted_key_without_value(tmp_path: Path) -> None:
    report = wfi.doctor(env=_doctor_env(tmp_path, AI_PROVIDER="openai"), runner=lambda *a, **k: _proc("4.6.stable"))
    provider = next(c for c in report["checks"] if c["id"] == "ai_provider")
    assert provider["required"] is False and "no key" in provider["detail"]


# ------------------------------------------------------------------ project writing


def test_write_project_files_writes_atomically(tmp_path: Path) -> None:
    dest = tmp_path / "games" / "my-game"
    written = wfi.write_project_files({"project.godot": "config_version=5\n", "scenes/main.tscn": "[gd_scene]\n"}, dest)
    assert written == ["project.godot", "scenes/main.tscn"]
    assert (dest / "scenes" / "main.tscn").read_text() == "[gd_scene]\n"
    assert not dest.with_name("my-game.partial").exists()


@pytest.mark.parametrize("name", ["../evil.gd", "/abs.gd", "C:/win.gd", "a/../../b.gd", "a\\..\\b.gd", ""])
def test_write_project_files_refuses_unsafe_paths(tmp_path: Path, name: str) -> None:
    with pytest.raises(wfi.FirstInstallError):
        wfi.write_project_files({"project.godot": "x", name: "x"}, tmp_path / "g")
    assert not (tmp_path / "evil.gd").exists()


def test_write_project_files_requires_project_and_empty_destination(tmp_path: Path) -> None:
    with pytest.raises(wfi.FirstInstallError, match="project.godot"):
        wfi.write_project_files({"main.gd": "x"}, tmp_path / "a")
    assert not (tmp_path / "a").exists() and not (tmp_path / "a.partial").exists()
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "keep.txt").write_text("mine")
    with pytest.raises(wfi.FirstInstallError, match="not empty"):
        wfi.write_project_files({"project.godot": "x"}, busy)
    assert (busy / "keep.txt").read_text() == "mine"
    with pytest.raises(wfi.FirstInstallError):
        wfi.write_project_files({}, tmp_path / "empty")


def test_unique_project_dir_and_latest(tmp_path: Path) -> None:
    first = wfi.unique_project_dir(tmp_path, "Ash Tunnels", clock=lambda: 0.0)
    first.mkdir()
    second = wfi.unique_project_dir(tmp_path, "Ash Tunnels", clock=lambda: 0.0)
    assert second != first and second.name.startswith(first.name)
    assert wfi.latest_project(tmp_path) is None
    (first / "project.godot").write_text("x")
    assert wfi.latest_project(tmp_path) == first


# ------------------------------------------------------------------ API client


class _FakeApi:
    def __init__(self, views: list[dict[str, Any]], ack_status: int = 202) -> None:
        self.views = views
        self.ack_status = ack_status
        self.requests: list[tuple[str, str, dict[str, str], Any]] = []

    def __call__(self, req: Any, timeout: float) -> _Resp:
        body = json.loads(req.data) if req.data else None
        headers = {k.lower(): v for k, v in req.header_items()}
        self.requests.append((req.get_method(), req.full_url, headers, body))
        if req.full_url.endswith("/api/v1/health"):
            return _Resp(200, {"status": "healthy"})
        if req.get_method() == "POST":
            if self.ack_status != 202:
                raise urllib.error.HTTPError(req.full_url, self.ack_status, "x", {}, io.BytesIO(b'{"detail":"no"}'))
            return _Resp(202, {"execution_id": "job_1", "status_ref": "/api/v1/game/build/job_1"})
        return _Resp(200, self.views.pop(0) if len(self.views) > 1 else self.views[0])


def _succeeded(files: dict[str, str] | None = None) -> dict[str, Any]:
    return {"execution_id": "job_1", "status": "succeeded", "progress": 1.0, "message": "complete",
            "result": {"ok": True, "proof": "CORE_LOOP_OK genre=platformer marker=goal:7",
                       "spec": {"title": "Rain Ledges", "genre": "platformer"},
                       "playtest": {"status": "passed"}, "stubbed": ["audio"],
                       "files": files if files is not None else {"project.godot": "x", "main.gd": "y"}}}


def test_client_requires_secret() -> None:
    with pytest.raises(wfi.FirstInstallError):
        wfi.ApiClient("http://127.0.0.1:1", secret="")


def test_build_via_api_seals_requests_and_writes_project(tmp_path: Path) -> None:
    api = _FakeApi([{"status": "running", "progress": 0.5, "message": "proving"}, _succeeded()])
    client = wfi.ApiClient("http://127.0.0.1:8710/", secret=SECRET, opener=api)
    client.wait_healthy(timeout=1, sleep=lambda _s: None)
    messages: list[str] = []
    built = wfi.build_via_api(client, "A small platformer", tmp_path, echo=messages.append)
    assert built["schema"] == wfi.BUILD_SCHEMA and built["ok"] is True
    assert built["file_count"] == 2 and Path(built["project_dir"]).joinpath("project.godot").is_file()
    assert built["proof"].startswith("CORE_LOOP_OK")
    posted = [r for r in api.requests if r[0] == "POST"][0]
    assert posted[3] == {"brief": "A small platformer", "playtest": "require", "deadline_s": 120.0, "include_files": True}
    assert all(r[2].get("x-gf-seal") for r in api.requests)
    assert SECRET not in json.dumps([r[2] for r in api.requests])
    assert any("proving" in m for m in messages)


def test_build_via_api_fails_closed(tmp_path: Path) -> None:
    failed = {"execution_id": "job_1", "status": "failed", "error": {"code": "handler_error"}}
    client = wfi.ApiClient("http://h", secret=SECRET, opener=_FakeApi([failed]))
    with pytest.raises(wfi.FirstInstallError, match="failed"):
        wfi.build_via_api(client, "brief", tmp_path, echo=lambda _m: None)
    no_proof = _succeeded()
    no_proof["result"]["proof"] = ""
    client = wfi.ApiClient("http://h", secret=SECRET, opener=_FakeApi([no_proof]))
    with pytest.raises(wfi.FirstInstallError, match="CORE_LOOP_OK"):
        wfi.build_via_api(client, "brief", tmp_path, echo=lambda _m: None)
    client = wfi.ApiClient("http://h", secret=SECRET, opener=_FakeApi([_succeeded()], ack_status=422))
    with pytest.raises(wfi.FirstInstallError, match="HTTP 422"):
        wfi.build_via_api(client, "brief", tmp_path, echo=lambda _m: None)
    assert list(tmp_path.iterdir()) == []


def test_build_poll_times_out() -> None:
    ticks = iter(range(1000))
    client = wfi.ApiClient("http://h", secret=SECRET, opener=_FakeApi([{"status": "running"}]))
    with pytest.raises(wfi.FirstInstallError, match="did not finish"):
        client.build("b", poll_timeout=3, sleep=lambda _s: None, clock=lambda: float(next(ticks)))


def test_wait_healthy_times_out_with_remediation() -> None:
    def refused(req: Any, timeout: float) -> _Resp:
        raise urllib.error.URLError("refused")

    ticks = iter(range(1000))
    client = wfi.ApiClient("http://h", secret=SECRET, opener=refused)
    with pytest.raises(wfi.FirstInstallError) as err:
        client.wait_healthy(timeout=2, sleep=lambda _s: None, clock=lambda: float(next(ticks)))
    assert "doctor" in err.value.remediation


# ------------------------------------------------------------------ play


def _project(tmp_path: Path, *, replay: bool = True) -> Path:
    project = tmp_path / "p"
    (project / "scripts" / "runtime").mkdir(parents=True)
    (project / "project.godot").write_text("x")
    if replay:
        (project / "scripts" / "runtime" / "interactive_smoke.gd").write_text("x")
    return project


def test_play_check_requires_both_markers(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def runner(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        calls.append(cmd)
        if "--import" in cmd:
            return _proc("imported")
        if "--script" in cmd:
            return _proc('noise\nFORGE_INTERACTIVE_OK {"won":true}\n')
        return _proc("CORE_LOOP_OK genre=platformer marker=goal:7\n")

    result = wfi.play_check(_project(tmp_path), Path("godot"), runner=runner)
    assert result["ok"] is True, result
    assert [s["step"] for s in result["steps"]] == ["import", "core_loop", "interactive"]
    assert result["steps"][2]["marker"].startswith("FORGE_INTERACTIVE_OK")
    assert all("--headless" in c for c in calls)


def test_play_check_fails_without_marker_and_keeps_log(tmp_path: Path) -> None:
    def runner(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        return _proc("SCRIPT ERROR: boom") if "--quit-after" in cmd else _proc("")

    result = wfi.play_check(_project(tmp_path), Path("godot"), runner=runner)
    assert result["ok"] is False
    assert result["steps"][-1]["step"] == "core_loop" and "boom" in result["steps"][-1]["log_tail"]


def test_play_check_timeout_is_failure(tmp_path: Path) -> None:
    def runner(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        if "--import" in cmd:
            return _proc("")
        raise subprocess.TimeoutExpired(cmd, 1, output="CORE_LOOP_OK late")

    result = wfi.play_check(_project(tmp_path), Path("godot"), runner=runner)
    assert result["ok"] is False and result["steps"][-1]["returncode"] == 124


def test_play_check_skips_replay_only_when_project_has_none(tmp_path: Path) -> None:
    runner = lambda cmd, **kw: _proc("CORE_LOOP_OK x") if "--quit-after" in cmd else _proc("")  # noqa: E731
    result = wfi.play_check(_project(tmp_path, replay=False), Path("godot"), runner=runner)
    assert result["ok"] is True and result["steps"][-1].get("skipped")
    with pytest.raises(wfi.FirstInstallError):
        wfi.play_check(tmp_path / "nope", Path("godot"), runner=runner)


# ------------------------------------------------------------------ serve / cli


def test_serve_refuses_remote_bind_and_missing_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(wfi.FirstInstallError, match="non-loopback"):
        wfi.serve("0.0.0.0", 8710)
    monkeypatch.delenv("GF_SEAL_SECRET", raising=False)
    monkeypatch.delenv("GF_SEAL_KEYRING", raising=False)
    with pytest.raises(wfi.FirstInstallError, match="GF_SEAL_SECRET"):
        wfi.serve("127.0.0.1", 8710)


def test_cli_doctor_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("SKELETON_HOME", str(tmp_path))
    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)
    code = wfi.main(["--json", "doctor", "--no-godot"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0 and out["schema"] == wfi.DOCTOR_SCHEMA and out["ok"] is True
    assert SECRET not in json.dumps(out)


def test_cli_play_without_games_reports_remediation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                                    capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("SKELETON_HOME", str(tmp_path))
    assert wfi.main(["--json", "play", "--check"]) == 2
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and "build" in out["remediation"]


# ------------------------------------------------------------------ integration: real API app


def test_real_api_builds_and_returns_files_through_seal_gate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The adapter drives the canonical app (seal gate, charter, queue, builder) end to end."""
    from fastapi.testclient import TestClient

    from skeleton.api.server import create_app

    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)
    app = create_app()
    with TestClient(app) as http:
        def opener(req: Any, timeout: float) -> _Resp:
            path = req.full_url.split("http://testserver", 1)[1]
            response = http.request(req.get_method(), path, content=req.data,
                                    headers=dict(req.header_items()))
            if response.status_code >= 400:
                raise urllib.error.HTTPError(req.full_url, response.status_code, "err", {},
                                             io.BytesIO(response.content))
            return _Resp(response.status_code, response.json())

        unsealed = http.get("/api/v1/health")
        assert unsealed.status_code == 401
        client = wfi.ApiClient("http://testserver", secret=SECRET, opener=opener)
        client.wait_healthy(timeout=30)
        built = wfi.build_via_api(client, wfi.SAMPLE_BRIEF, tmp_path, playtest="off", echo=lambda _m: None)
        wrong = wfi.ApiClient("http://testserver", secret="f" * 64, opener=opener)
        with pytest.raises(wfi.FirstInstallError, match="did not become healthy"):
            wrong.wait_healthy(timeout=0.3, interval=0.1)
    project = Path(built["project_dir"])
    assert built["genre"] == "platformer"
    assert (project / "project.godot").is_file()
    assert (project / "scripts" / "runtime" / "interactive_smoke.gd").is_file()
    assert built["file_count"] >= 10
