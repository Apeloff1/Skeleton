"""One-command boot sequence driven end-to-end with injected process/probe fakes."""

from __future__ import annotations

import os
import socket
import stat
import subprocess
import sys

import pytest

from skeleton.deployment.boot import (
    BOOT_STEPS,
    BootOptions,
    Booter,
    StepStatus,
    boot,
    child_environment,
    default_launcher,
    stop_process,
)
from skeleton.deployment.envfile import load_env_file
from skeleton.deployment.profile import get_profile

TOKEN = "Zq8vT2mX9rL4wB7nK1pD6sF3hJ0cY5gA"


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class FakeProcess:
    def __init__(self, pid: int = 4242, exit_after_polls: int | None = None, wait_code: int = 0,
                 interrupt: bool = False) -> None:
        self.pid = pid
        self.polls = 0
        self.exit_after_polls = exit_after_polls
        self.wait_code = wait_code
        self.interrupt = interrupt
        self.terminated = False
        self.killed = False
        self.returncode: int | None = None

    def poll(self):
        self.polls += 1
        if self.returncode is not None:
            return self.returncode
        if self.exit_after_polls is not None and self.polls > self.exit_after_polls:
            self.returncode = 3
        return self.returncode

    def wait(self, timeout=None):
        if self.interrupt and not self.terminated:
            raise KeyboardInterrupt
        if self.returncode is None:
            self.returncode = -15 if self.terminated else self.wait_code
        return self.returncode

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True
        self.returncode = -9


class Launcher:
    def __init__(self, process: FakeProcess | None = None, error: OSError | None = None) -> None:
        self.process = process or FakeProcess()
        self.error = error
        self.calls: list[tuple] = []

    def __call__(self, argv, env, cwd, log_path):
        self.calls.append((list(argv), dict(env), cwd, log_path))
        if self.error:
            raise self.error
        return self.process


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def fetch_after(ready_after: int):
    state = {"calls": 0}

    def fetch(url, timeout):
        state["calls"] += 1
        if state["calls"] <= ready_after * 2:
            raise OSError("connection refused")
        return 200, b'{"status": "up"}'

    return fetch


def make_booter(profile, launcher=None, fetch=None, clock=None, lines=None, **options):
    options.setdefault("network_checks", False)
    clock = clock or Clock()
    return Booter(
        profile,
        BootOptions(**options),
        launcher=launcher or Launcher(),
        fetch=fetch or fetch_after(0),
        sleep=clock.sleep,
        clock=clock,
        emit=(lines.append if lines is not None else None),
        base_env={"PATH": "/bin", "SKL_SERVER_PORT": "1", "OPENAI_API_KEY": "sk-live", "HOME": "/h"},
    )


def local(tmp_path, **changes):
    return get_profile("local").with_overrides(data_dir=str(tmp_path / "data"), port=free_port(), **changes)


def statuses(result):
    return [(step.name, step.status) for step in result.steps]


def test_full_foreground_boot_sequence(tmp_path) -> None:
    launcher = Launcher(FakeProcess(wait_code=0))
    lines: list[str] = []
    result = make_booter(local(tmp_path), launcher=launcher, fetch=fetch_after(2), lines=lines).run()
    assert [s.name for s in result.steps] == list(BOOT_STEPS)
    assert result.ok and result.exit_code() == 0
    assert result.pid == 4242
    assert result.returncode == 0
    assert result.step("ready").data["attempts"] == 3
    assert (tmp_path / "data").is_dir()
    assert any(line.startswith("[deploy] ready") for line in lines)
    argv, env, cwd, log_path = launcher.calls[0]
    assert "skeleton.api.server:create_app" in argv
    assert env["SKL_SERVER_PORT"] != "1"  # inherited SKL_* replaced by the profile
    assert env["SKL_OPERATION_STATE_PATH"].startswith(str(tmp_path / "data"))
    assert env["OPENAI_API_KEY"] == "sk-live"  # online profile keeps provider keys
    assert log_path is None


def test_data_dir_is_created_private(tmp_path) -> None:
    make_booter(local(tmp_path)).run()
    if os.name == "posix":
        mode = stat.S_IMODE((tmp_path / "data").stat().st_mode)
        assert mode & 0o007 == 0


def test_dry_run_has_no_side_effects(tmp_path) -> None:
    launcher = Launcher()
    result = make_booter(local(tmp_path), launcher=launcher, dry_run=True,
                         write_env=str(tmp_path / "e.env")).run()
    assert result.ok and result.dry_run
    assert launcher.calls == []
    assert not (tmp_path / "data").exists()
    assert not (tmp_path / "e.env").exists()
    planned = {name for name, status in statuses(result) if status is StepStatus.PLANNED}
    assert planned == {"prepare", "env_file", "launch", "ready", "serve"}
    assert "skeleton.api.server:create_app" in result.step("launch").detail


def test_plan_restores_dry_run_flag(tmp_path) -> None:
    booter = make_booter(local(tmp_path), launcher=Launcher())
    assert booter.plan().dry_run is True
    assert booter.options.dry_run is False


def test_validation_failure_stops_before_any_side_effect(tmp_path) -> None:
    launcher = Launcher()
    profile = get_profile("selfhost").with_overrides(data_dir=str(tmp_path / "d"), port=free_port())
    result = make_booter(profile, launcher=launcher).run()
    assert not result.ok
    assert result.failed_step == "validate"
    assert result.exit_code() == 2
    assert "DEP011" in result.step("validate").detail
    assert launcher.calls == []
    assert not (tmp_path / "d").exists()
    assert result.steps[-1].name == "validate"


def test_generated_token_is_persisted_to_private_env_file(tmp_path) -> None:
    env_path = tmp_path / "conf" / "skeleton.env"
    launcher = Launcher()
    profile = get_profile("selfhost").with_overrides(
        data_dir=str(tmp_path / "d"), port=free_port(), host="127.0.0.1", chroma_persist=False,
        allowed_tenants="t", allowed_capabilities="c")
    result = make_booter(profile, launcher=launcher, generate_token=True, write_env=str(env_path)).run()
    assert result.ok, result.to_dict()
    assert result.step("token").status is StepStatus.OK
    written = load_env_file(env_path)
    token = written["SKL_ENGINE_SERVICE_TOKEN"]
    assert len(token) >= 32
    assert launcher.calls[0][1]["SKL_ENGINE_SERVICE_TOKEN"] == token
    assert token not in str(result.to_dict())
    if os.name == "posix":
        assert stat.S_IMODE(env_path.stat().st_mode) == 0o600


def test_generated_token_without_env_file_warns(tmp_path) -> None:
    result = make_booter(local(tmp_path), generate_token=True).run()
    assert result.step("token").status is StepStatus.WARN
    assert "this run only" in result.step("token").detail


def test_existing_token_is_kept(tmp_path) -> None:
    launcher = Launcher()
    result = make_booter(local(tmp_path, service_token=TOKEN), launcher=launcher, generate_token=True).run()
    assert result.step("token").detail == "engine service token provided"
    assert launcher.calls[0][1]["SKL_ENGINE_SERVICE_TOKEN"] == TOKEN


def test_preflight_blocks_on_busy_port(tmp_path) -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        profile = get_profile("local").with_overrides(data_dir=str(tmp_path / "d"),
                                                      port=listener.getsockname()[1])
        launcher = Launcher()
        result = make_booter(profile, launcher=launcher).run()
    finally:
        listener.close()
    assert result.failed_step == "preflight"
    assert "port" in result.step("preflight").detail
    assert launcher.calls == []
    assert result.exit_code() == 1


def test_skip_preflight(tmp_path) -> None:
    result = make_booter(local(tmp_path), skip_preflight=True).run()
    assert result.step("preflight").status is StepStatus.SKIPPED
    assert result.ok


def test_launch_failure_is_reported(tmp_path) -> None:
    result = make_booter(local(tmp_path), launcher=Launcher(error=FileNotFoundError(2, "No such file"))).run()
    assert result.failed_step == "launch"
    assert "cannot start server" in result.step("launch").detail


def test_server_exiting_before_ready_fails(tmp_path) -> None:
    process = FakeProcess(exit_after_polls=1)
    result = make_booter(local(tmp_path), launcher=Launcher(process), fetch=fetch_after(100)).run()
    assert result.failed_step == "ready"
    assert result.returncode == 3
    assert "exited with code 3" in result.step("ready").detail


def test_readiness_timeout_stops_the_server(tmp_path) -> None:
    process = FakeProcess()
    clock = Clock()
    result = make_booter(local(tmp_path), launcher=Launcher(process), fetch=fetch_after(10_000), clock=clock,
                         ready_timeout_s=5, poll_interval_s=1).run()
    assert result.failed_step == "ready"
    assert process.terminated
    assert "server stopped" in result.step("ready").detail
    assert "connection refused" in result.step("ready").detail
    assert clock.now >= 5


def test_readiness_waits_for_ready_status_not_just_http(tmp_path) -> None:
    calls = {"n": 0}

    def fetch(url, timeout):
        calls["n"] += 1
        if url.endswith("/ready") and calls["n"] < 6:
            return 200, b'{"status": "down", "probes": [{"name": "db", "ok": false}]}'
        return 200, b'{"status": "up"}'

    result = make_booter(local(tmp_path), fetch=fetch).run()
    assert result.ok
    assert result.step("ready").data["attempts"] > 1


def test_no_wait_and_detach(tmp_path) -> None:
    launcher = Launcher()
    result = make_booter(local(tmp_path), launcher=launcher, wait_ready=False, foreground=False,
                         log_path=str(tmp_path / "s.log")).run()
    assert result.ok
    assert result.step("ready").status is StepStatus.SKIPPED
    assert result.step("serve").data == {"detached": True}
    assert launcher.calls[0][3] == str(tmp_path / "s.log")
    assert result.returncode is None


def test_server_crash_while_serving_fails(tmp_path) -> None:
    result = make_booter(local(tmp_path), launcher=Launcher(FakeProcess(wait_code=1))).run()
    assert result.failed_step == "serve"
    assert result.returncode == 1
    assert not result.ok


def test_operator_interrupt_is_a_clean_stop(tmp_path) -> None:
    process = FakeProcess(interrupt=True)
    result = make_booter(local(tmp_path), launcher=Launcher(process)).run()
    assert process.terminated
    assert result.ok and result.returncode == 0
    assert result.step("serve").detail == "stopped by operator"
    assert result.step("serve").data["child_returncode"] == -15


def test_relative_data_dir_is_anchored_at_cwd_option(tmp_path) -> None:
    launcher = Launcher()
    profile = get_profile("local").with_overrides(data_dir="rel/data", port=free_port())
    result = make_booter(profile, launcher=launcher, cwd=str(tmp_path)).run()
    assert result.ok
    assert (tmp_path / "rel" / "data").is_dir()
    env = launcher.calls[0][1]
    assert env["SKL_OPERATION_STATE_PATH"] == str(tmp_path / "rel/data/operation_state.sqlite")
    assert launcher.calls[0][2] == str(tmp_path)


def test_child_environment_offline_strips_provider_keys_and_stale_config() -> None:
    base = {"OPENAI_API_KEY": "sk", "EMERGENT_LLM_KEY": "e", "SKL_MONGO_URI": "mongodb://stale",
            "SKELETON_PUBLIC_DEV_SURFACES": "1", "PATH": "/bin"}
    env = child_environment(get_profile("offline").with_overrides(service_token=TOKEN), base)
    assert "OPENAI_API_KEY" not in env and "EMERGENT_LLM_KEY" not in env
    assert "SKL_MONGO_URI" not in env
    assert "SKELETON_PUBLIC_DEV_SURFACES" not in env
    assert env["PATH"] == "/bin"
    assert env["SKELETON_OFFLINE"] == "1"
    assert env["PYTHONUNBUFFERED"] == "1"
    assert env["SKL_ENGINE_SERVICE_TOKEN"] == TOKEN


def test_result_dict_shape(tmp_path) -> None:
    payload = make_booter(local(tmp_path), dry_run=True).run().to_dict()
    assert payload["kind"] == "deployment_boot"
    assert payload["failed_step"] is None
    assert [s["name"] for s in payload["steps"]] == list(BOOT_STEPS)


def test_boot_convenience_wrapper(tmp_path) -> None:
    result = boot(local(tmp_path), BootOptions(dry_run=True, network_checks=False))
    assert result.ok and result.dry_run


def test_stop_process_escalates_to_kill() -> None:
    class Stubborn(FakeProcess):
        def wait(self, timeout=None):
            if not self.killed:
                raise subprocess.TimeoutExpired("x", timeout)
            return -9

    process = Stubborn()
    assert stop_process(process, grace_s=0.01) == -9
    assert process.terminated and process.killed

    done = FakeProcess()
    done.returncode = 0
    assert stop_process(done) == 0
    assert not done.terminated


def test_default_launcher_runs_and_detaches_real_process(tmp_path) -> None:
    attached = default_launcher([sys.executable, "-c", "print('hi')"], dict(os.environ), str(tmp_path), None)
    assert attached.wait(timeout=30) == 0
    log = tmp_path / "logs" / "child.log"
    detached = default_launcher([sys.executable, "-c", "print('detached-ok')"], dict(os.environ), None, str(log))
    assert detached.wait(timeout=30) == 0
    assert "detached-ok" in log.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["local", "test"])
def test_builtin_dev_profiles_plan_cleanly(name: str, tmp_path) -> None:
    profile = get_profile(name).with_overrides(port=free_port())
    if profile.data_dir is not None:
        profile = profile.with_overrides(data_dir=str(tmp_path / "d"))
    result = make_booter(profile, dry_run=True).run()
    assert result.ok, result.to_dict()
