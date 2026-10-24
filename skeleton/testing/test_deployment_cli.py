"""``python -m skeleton deploy`` CLI and its wiring into the package entry point."""

from __future__ import annotations

import io
import json
import os
import socket
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from skeleton.__main__ import main as skeleton_main
from skeleton.deployment.boot import BootResult, BootStep, StepStatus
from skeleton.deployment.cli import build_parser, run_deploy_cli
from skeleton.deployment.envfile import load_env_file

REPO_ROOT = Path(__file__).resolve().parents[2]
TOKEN = "Zq8vT2mX9rL4wB7nK1pD6sF3hJ0cY5gA"


def run(argv, environ=None, **kwargs):
    out, err = io.StringIO(), io.StringIO()
    code = run_deploy_cli(argv, environ={} if environ is None else environ, out=out, err=err, **kwargs)
    return code, out.getvalue(), err.getvalue()


def run_json(argv, environ=None, **kwargs):
    code, out, err = run(argv, environ, **kwargs)
    return code, json.loads(out), err


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def test_help_and_empty_invocation() -> None:
    for argv in ([], ["help"], ["--help"]):
        code, out, _ = run(argv)
        assert code == 0
        assert "boot" in out and "manifest" in out


def test_unknown_action_and_bad_option_exit_2() -> None:
    code, _out, err = run(["bogus"])
    assert code == 2 and "invalid choice" in err
    code, _out, err = run(["show", "--port", "abc"])
    assert code == 2 and "invalid int" in err


def test_subcommand_help_exits_zero(capsys) -> None:
    code, _out, _err = run(["boot", "--help"])
    assert code == 0
    assert "--dry-run" in capsys.readouterr().out


def test_parser_exposes_every_action() -> None:
    parser = build_parser()
    actions = next(a for a in parser._actions if a.dest == "action")  # noqa: SLF001
    assert set(actions.choices) == {"profiles", "show", "validate", "env", "check", "probe", "manifest",
                                    "units", "boot"}


def test_profiles() -> None:
    code, payload, _ = run_json(["profiles"])
    assert code == 0
    assert [p["name"] for p in payload["profiles"]][:4] == ["local", "selfhost", "offline", "test"]


def test_show_masks_token_and_applies_overrides() -> None:
    code, payload, _ = run_json(["show", "--profile", "selfhost", "--port", "9100", "--set", "workers=2"],
                                environ={"SKL_ENGINE_SERVICE_TOKEN": TOKEN})
    assert code == 0
    profile = payload["profile"]
    assert profile["port"] == 9100 and profile["workers"] == 2
    assert profile["service_token"] == "**********"
    assert TOKEN not in json.dumps(payload)
    assert len(payload["fingerprint"]) == 64


def test_no_environ_ignores_shell_variables() -> None:
    _code, payload, _ = run_json(["show", "--no-environ"], environ={"SKL_SERVER_PORT": "9999"})
    assert payload["profile"]["port"] == 8001
    _code, payload, _ = run_json(["show"], environ={"SKL_SERVER_PORT": "9999"})
    assert payload["profile"]["port"] == 9999


def test_in_memory_and_data_dir_flags(tmp_path) -> None:
    _code, payload, _ = run_json(["show", "--in-memory"])
    assert payload["profile"]["durable"] is False
    _code, payload, _ = run_json(["show", "--data-dir", str(tmp_path)])
    assert payload["profile"]["data_dir"] == str(tmp_path)


def test_validate_exit_codes() -> None:
    code, payload, _ = run_json(["validate", "--profile", "local"])
    assert code == 0 and payload["ok"] is True
    code, payload, _ = run_json(["validate", "--profile", "selfhost", "--no-fs"])
    assert code == 2 and "DEP011" in [i["code"] for i in payload["issues"]]
    env = {"SKL_ENGINE_SERVICE_TOKEN": TOKEN}
    code, payload, _ = run_json(["validate", "--profile", "selfhost", "--no-fs"], environ=env)
    assert code == 0 and payload["warning_count"] == 2  # wildcard allow-lists
    code, payload, _ = run_json(["validate", "--profile", "selfhost", "--no-fs", "--strict"], environ=env)
    assert code == 2 and payload["strict"] is True


def test_validate_reports_profile_errors_as_json() -> None:
    code, payload, _ = run_json(["validate", "--profile", "nope"])
    assert code == 2
    assert payload["error"]["type"] == "ProfileError"


def test_env_render_is_redacted_by_default_and_parseable(tmp_path) -> None:
    environ = {"SKL_ENGINE_SERVICE_TOKEN": TOKEN}
    code, out, _ = run(["env", "--profile", "selfhost"], environ=environ)
    assert code == 0
    assert TOKEN not in out
    assert "SKL_ENGINE_SERVICE_TOKEN=**********" in out
    code, out, _ = run(["env", "--profile", "selfhost", "--reveal"], environ=environ)
    assert f"SKL_ENGINE_SERVICE_TOKEN={TOKEN}" in out
    code, payload, _ = run_json(["env", "--json"])
    assert payload["SKL_ENVIRONMENT"] == "development"


def test_env_out_writes_private_file_and_round_trips(tmp_path) -> None:
    target = tmp_path / "skeleton.env"
    code, payload, _ = run_json(["env", "--profile", "selfhost", "--out", str(target)],
                                environ={"SKL_ENGINE_SERVICE_TOKEN": TOKEN})
    assert code == 0 and payload["path"] == str(target)
    assert load_env_file(target)["SKL_ENGINE_SERVICE_TOKEN"] == TOKEN
    if os.name == "posix":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
    code, shown, _ = run_json(["show", "--profile", "test", "--env-file", str(target)])
    assert shown["profile"]["environment"] == "production"
    assert shown["profile"]["data_dir"] == "/var/lib/skeleton"


def test_env_file_errors_are_reported(tmp_path) -> None:
    bad = tmp_path / "bad.env"
    bad.write_text("not a line\n", encoding="utf-8")
    code, payload, _ = run_json(["show", "--env-file", str(bad)])
    assert code == 2 and payload["error"]["type"] == "EnvFileError"


def test_check_runs_preflight(tmp_path) -> None:
    code, payload, _ = run_json(["check", "--data-dir", str(tmp_path), "--port", str(free_port()),
                                 "--no-network"])
    assert code == 0, payload
    assert payload["kind"] == "deployment_health"
    assert payload["profile"] == "local"
    code, payload, _ = run_json(["check", "--kind", "liveness", "--no-port"])
    assert {r["kind"] for r in payload["results"]} == {"liveness"}


def test_check_fails_on_busy_port(tmp_path) -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        code, payload, _ = run_json(["check", "--kind", "startup", "--data-dir", str(tmp_path),
                                     "--port", str(listener.getsockname()[1])])
    finally:
        listener.close()
    assert code == 1
    assert any(r["name"] == "port" and r["status"] == "fail" for r in payload["results"])


def test_probe_reports_unreachable_instance() -> None:
    code, payload, _ = run_json(["probe", "--url", f"http://127.0.0.1:{free_port()}", "--timeout", "0.5"])
    assert code == 1
    assert payload["status"] == "fail"
    code, payload, _ = run_json(["probe", "--url", "ftp://x"])
    assert code == 2


def test_manifest_build_write_and_verify(tmp_path) -> None:
    root = tmp_path / "root"
    (root / "skeleton").mkdir(parents=True)
    (root / "skeleton" / "a.py").write_text("a = 1\n", encoding="utf-8")
    (root / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "1"\n', encoding="utf-8")
    out = tmp_path / "manifest.json"
    code, payload, _ = run_json(["manifest", "--root", str(root), "--out", str(out), "--git-sha", "abc",
                                 "--with-profile", "--profile", "test"])
    assert code == 0
    assert payload["file_count"] == 2 and payload["git_sha"] == "abc"
    assert payload["profile"]["name"] == "test"
    code, payload, _ = run_json(["manifest", "--root", str(root), "--verify", str(out)])
    assert code == 0 and payload["ok"] is True
    (root / "skeleton" / "a.py").write_text("tampered\n", encoding="utf-8")
    code, payload, _ = run_json(["manifest", "--root", str(root), "--verify", str(out)])
    assert code == 1 and payload["modified"] == ["skeleton/a.py"]
    code, payload, _ = run_json(["manifest", "--root", str(root), "--full"])
    assert [f["path"] for f in payload["files"]] == ["pyproject.toml", "skeleton/a.py"]
    code, payload, _ = run_json(["manifest", "--root", str(root)])
    assert "files" not in payload


def test_manifest_errors_exit_2(tmp_path) -> None:
    code, payload, _ = run_json(["manifest", "--verify", str(tmp_path / "missing.json")])
    assert code == 2 and payload["error"]["type"] == "ManifestError"


def test_units_systemd_and_compose(tmp_path) -> None:
    code, out, _ = run(["units", "--profile", "selfhost", "--user", "svc"])
    assert code == 0 and "[Service]" in out and "User=svc" in out
    code, out, _ = run(["units", "--format", "compose", "--profile", "local", "--image", "img:1"])
    assert code == 0 and 'image: "img:1"' in out
    target = tmp_path / "units" / "skeleton.service"
    code, payload, _ = run_json(["units", "--out", str(target)])
    assert code == 0 and target.read_text(encoding="utf-8").startswith("[Unit]")


def test_boot_dry_run_plans_without_launching(tmp_path) -> None:
    code, payload, err = run_json(["boot", "--dry-run", "--data-dir", str(tmp_path / "d"),
                                   "--port", str(free_port()), "--no-network"])
    assert code == 0, payload
    assert payload["dry_run"] is True
    assert payload["steps"][-1]["status"] == "planned"
    assert "[deploy] launch" in err
    assert not (tmp_path / "d").exists()


def test_boot_maps_options_and_exit_codes(tmp_path) -> None:
    captured = {}

    class FakeBooter:
        def __init__(self, profile, options, emit=None, base_env=None):
            captured.update(profile=profile, options=options, base_env=base_env)
            emit("[deploy] fake")

        def run(self):
            result = BootResult(profile="local", fingerprint="f", url="u", dry_run=False)
            result.steps.append(BootStep("validate", StepStatus.FAILED, "bad"))
            return result

    code, payload, err = run_json(
        ["boot", "--detach", "--log", str(tmp_path / "s.log"), "--timeout", "7", "--generate-token",
         "--write-env", str(tmp_path / "e.env"), "--skip-preflight", "--no-settings", "--no-network",
         "--reload", "--no-wait"],
        environ={"X": "1"},
        booter_factory=FakeBooter,
    )
    assert code == 2 and payload["failed_step"] == "validate"
    options = captured["options"]
    assert options.foreground is False and options.log_path == str(tmp_path / "s.log")
    assert options.ready_timeout_s == 7 and options.generate_token and options.skip_preflight
    assert options.check_settings is False and options.network_checks is False
    assert options.reload is True and options.wait_ready is False
    assert options.write_env == str(tmp_path / "e.env")
    assert captured["base_env"] == {"X": "1"}
    assert "[deploy] fake" in err


def test_attached_boot_does_not_use_log_file() -> None:
    captured = {}

    class FakeBooter:
        def __init__(self, profile, options, emit=None, base_env=None):
            captured["options"] = options

        def run(self):
            return BootResult(profile="local", fingerprint="f", url="u", dry_run=False)

    code, _payload, _ = run_json(["boot"], booter_factory=FakeBooter)
    assert code == 0
    assert captured["options"].log_path is None and captured["options"].foreground is True


def test_package_entry_point_dispatches_deploy(capsys) -> None:
    assert skeleton_main(["deploy", "profiles"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "deployment_profiles"


def test_package_help_lists_deploy(capsys) -> None:
    assert skeleton_main(["help"]) == 0
    assert "deploy      Self-host deployment" in capsys.readouterr().out


def test_python_dash_m_subprocess_smoke(tmp_path) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("SKL_")}
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    completed = subprocess.run(
        [sys.executable, "-m", "skeleton", "deploy", "validate", "--profile", "test", "--no-settings"],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["ok"] is True


@pytest.mark.parametrize("action", ["show", "validate", "env", "units"])
def test_profile_file_option(action: str, tmp_path) -> None:
    document = tmp_path / "p.json"
    document.write_text(json.dumps({"name": "edge", "port": 9500, "environment": "test"}), encoding="utf-8")
    code, _out, _err = run([action, "--profile-file", str(document), "--no-environ"])
    assert code == 0
