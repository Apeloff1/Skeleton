"""Source-level safety regressions for opt-in containerized local Jeeves.

Actual Docker daemon, downloaded GGUF, GPU hardware and live qualification are
independent acceptance gates; these unit checks never claim those results.
"""
from __future__ import annotations

from pathlib import Path
import json
from unittest import mock

import pytest

from skeleton.app import docker_local_ai as engine
from scripts import local_ai_docker as host


def _fake_config(root: Path) -> dict[str, object]:
    return {
        "services": {
            "mongo": {}, "backend": {}, "frontend": {}, "chroma": {},
            "skeleton": {
                "environment": {**host.ENV_FENCE, **{k: "" for k in host.EMPTY_FENCE}},
                "read_only": True,
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "ports": [{"host_ip": "127.0.0.1", "published": "8010", "target": 8001}],
                "volumes": [{
                    "type": "bind", "source": str(root),
                    "target": "/app/local-ai", "read_only": True,
                }],
                "image": "skeleton-local-ai:dev",
                "mem_limit": 8589934592,
                "cpus": 4,
                "pids_limit": 512,
                "shm_size": 268435456,
            },
        },
    }


def test_hermetic_mount_rejects_escape_and_symlinks(tmp_path: Path) -> None:
    model = tmp_path / "model.gguf"
    model.write_bytes(b"GGUF")
    assert engine._member(tmp_path, "model.gguf") == model
    for member in ("/etc/passwd", "../file", "foo/../model.gguf",
                   "foo//model.gguf", "foo\\bar.gguf", ""):
        with pytest.raises(engine.DockerLocalAIError):
            engine._member(tmp_path, member)
    (tmp_path / "redirect").symlink_to(model)
    with pytest.raises(engine.DockerLocalAIError):
        engine._member(tmp_path, "redirect")
    with pytest.raises(engine.DockerLocalAIError):
        engine._member(tmp_path, "missing.gguf")


def test_manifest_must_be_create_only(tmp_path: Path) -> None:
    (tmp_path / engine.MANIFEST_NAME).write_text("not a valid manifest")
    with pytest.raises(engine.DockerLocalAIError, match="immutable"):
        engine.pin_deployment(model="not-present", executable="not-present",
                              profile="raw", context=4096, threads=1,
                              gpu_layers=0, root=tmp_path)


def test_local_only_runtime_environment_has_no_hosted_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine.os, "environ", dict(engine.os.environ))
    for key, value in {
        **host.ENV_FENCE,
        **{key: "" for key in host.EMPTY_FENCE},
    }.items():
        monkeypatch.setenv(key, value)
    engine._environment_guard(Path("/app/local-ai/jeeves.json"))
    monkeypatch.setenv("AI_SECONDARY_BASE_URL", "https://external.invalid")
    with pytest.raises(engine.DockerLocalAIError):
        engine._environment_guard(Path("/app/local-ai/jeeves.json"))
    monkeypatch.delenv("AI_SECONDARY_BASE_URL")
    monkeypatch.setenv("AI_LOCAL_GUARD_REQUIRED", "0")
    with pytest.raises(engine.DockerLocalAIError):
        engine._environment_guard(Path("/app/local-ai/jeeves.json"))


@pytest.mark.parametrize("modified,reason", [
    (lambda cfg: cfg["services"]["skeleton"]["environment"].update({"AI_PROVIDER": "openai"}), "fence"),
    (lambda cfg: cfg["services"]["skeleton"]["environment"].update({"OPENAI_API_KEY": "secret"}), "fence"),
    (lambda cfg: cfg["services"]["skeleton"].update({"read_only": False}), "read-only"),
    (lambda cfg: cfg["services"]["skeleton"]["volumes"][0].update({"read_only": False}), "read-only"),
    (lambda cfg: cfg["services"]["skeleton"]["ports"][0].update({"host_ip": "0.0.0.0"}), "loopback"),
    (lambda cfg: cfg["services"].update({"external_provider": {}}), "topology"),
])
def test_docker_contract_denies_drift(tmp_path: Path, modified, reason: str) -> None:
    config = _fake_config(tmp_path)
    modified(config)
    with pytest.raises(host.LocalDockerError):
        host._mount_from_compose(config)


def test_operator_uses_normalized_compose_and_never_echoes_secrets(tmp_path: Path) -> None:
    config = _fake_config(tmp_path)
    with mock.patch.object(host, "compose_command", return_value=["docker", "compose"]), (
        mock.patch.object(host, "_run", return_value=json.dumps(config))
    ):
        details = host.inspect_config("cpu", tmp_path)
    assert details["provider"] == "local"
    assert details["status"] == "compose_verified_not_inference_qualified"
    assert details["model_directory"] == str(tmp_path)
    assert "secret" not in json.dumps(details)


@pytest.mark.parametrize("mode,required", [
    ("cpu", []),
    ("nvidia", ["--gpus", "1"]),
    ("rocm", ["--device", "/dev/kfd:/dev/kfd", "--group-add", "109"]),
])
def test_one_shot_docker_commands_are_offline_and_hardened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, required: list[str],
) -> None:
    monkeypatch.setenv("SKL_LOCAL_AI_RENDER_GID", "109")
    fake = {
        "model_directory": str(tmp_path), "image": "skeleton-local-ai:dev",
        "limits": {"memory": "8g", "cpus": "4", "pids_limit": "512", "shm_size": "256m"},
        "render_gid": "109" if mode == "rocm" else None,
    }
    with mock.patch.object(host, "inspect_config", return_value=fake):
        argv = host._isolated_container(mode, "preflight", root=tmp_path)
    assert argv[:3] == ["docker", "run", "--rm"]
    for value in ("--network", "none", "--read-only",
                  "--pull=never", "--cap-drop", "ALL", "readonly"):
        assert value in " ".join(argv)
    assert argv[-4:] == ["python", "-m", "skeleton.app.docker_local_ai", "preflight"]
    for value in required:
        assert value in argv
    with mock.patch.object(host, "inspect_config", return_value=fake):
        pin = host._isolated_container(mode, "pin", root=tmp_path,
                                       extra=["--model", "model.gguf"])
    assert "target=/app/local-ai,readonly" not in pin
    assert "target=/app/local-ai" in pin


def test_gpu_mode_requires_numeric_authorized_render_group(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SKL_LOCAL_AI_RENDER_GID", raising=False)
    fake = {
        "model_directory": str(tmp_path), "image": "skeleton-local-ai:dev",
        "limits": {"memory": "8g", "cpus": "4", "pids_limit": "512", "shm_size": "256m"},
        "render_gid": None,
    }
    with mock.patch.object(host, "inspect_config", return_value=fake):
        with pytest.raises(host.LocalDockerError):
            host._isolated_container("rocm", "qualify", root=tmp_path)


def test_host_command_builds_overlay_sequence(tmp_path: Path) -> None:
    for name in (host.BASE, host.LOCAL, *[x for x in host.GPU_OVERLAYS.values() if x]):
        (tmp_path / name).write_text("services: {}")
    (tmp_path / ".env").write_text("")
    for mode, extra in host.GPU_OVERLAYS.items():
        argv = host.compose_command(mode, tmp_path)
        assert argv.count("-f") == (3 if extra else 2)
        assert str(tmp_path / host.LOCAL) in argv


def test_missing_env_refuses_operator_side_effects(tmp_path: Path) -> None:
    with pytest.raises(host.LocalDockerError):
        host.compose_command("cpu", tmp_path)


def test_accelerator_overlays_change_only_canonical_engine() -> None:
    root = Path(__file__).resolve().parents[2]
    pytest.importorskip("yaml")
    import yaml
    for file in (host.LOCAL, *[x for x in host.GPU_OVERLAYS.values() if x]):
        payload = yaml.safe_load((root / file).read_text(encoding="utf-8"))
        assert set(payload) == {"services"}
        assert set(payload["services"]) == {"skeleton"}
    default = yaml.safe_load((root / host.LOCAL).read_text(encoding="utf-8"))
    environment = default["services"]["skeleton"]["environment"]
    assert environment["AI_PROVIDER"] == "local"
    assert environment["AI_LOCAL_DEPLOYMENT_PATH"] == "/app/local-ai/jeeves.json"
    assert environment["AI_LOCAL_MODEL_CATALOG_PATH"] == ""
    assert all(environment[k] == "" for k in host.EMPTY_FENCE)
    assert "volumes" not in default["services"]["skeleton"]  # preserve base custody


def test_no_model_execution_is_claimed_by_preflight_contract() -> None:
    assert engine.MODEL_ID == "jeeves"
    assert host.ENV_FENCE["AI_PROVIDER"] == "local"
    assert host.ENV_FENCE["AI_LOCAL_DEPLOYMENT_PATH"] == "/app/local-ai/jeeves.json"


def test_backend_live_readiness_rejects_missing_or_other_provider(tmp_path: Path) -> None:
    sample = {
        "engine": "skeleton-engine",
        "active": "local",
        "providers": ["local"],
        "availability_observed": True,
        "llm_available": False,
        "active_readiness_code": "local_guard_unavailable",
    }
    with mock.patch.object(host, "compose_command", return_value=["docker", "compose"]), (
        mock.patch.object(host, "_run", return_value=json.dumps(sample))
    ):
        result = host.live_ai_status("cpu", tmp_path)
    assert result["ready"] is False
    assert result["readiness_code"] == "local_guard_unavailable"
    assert result["inference_qualified"] is False

    for patch in ({"active": "openai", "llm_available": True},
                  {"availability_observed": False, "llm_available": True},
                  {"engine": "mock", "llm_available": True},
                  {"providers": ["openai"], "llm_available": True}):
        payload = {**sample, "llm_available": True, **patch}
        with mock.patch.object(host, "compose_command", return_value=["docker", "compose"]), (
            mock.patch.object(host, "_run", return_value=json.dumps(payload))
        ):
            assert host.live_ai_status("cpu", tmp_path)["ready"] is False


def test_host_up_never_claims_success_without_canonical_local_guard(tmp_path: Path) -> None:
    with (
        mock.patch.object(host, "_isolated_container", return_value=["docker", "run"]),
        mock.patch.object(host, "_run", return_value=""),
        mock.patch.object(host, "compose_command", return_value=["docker", "compose"]),
        mock.patch.object(host, "live_ai_status", return_value={
            "ready": False, "observed": True, "readiness_code": "local_guard_unavailable",
        }),
    ):
        with pytest.raises(host.LocalDockerError, match="trusted bootstrap"):
            host.up("cpu", tmp_path)


def test_qualification_resources_mirror_rendered_compose_limits(tmp_path: Path) -> None:
    config = _fake_config(tmp_path)
    config["services"]["skeleton"]["mem_limit"] = 17179869184
    config["services"]["skeleton"]["cpus"] = 6
    config["services"]["skeleton"]["pids_limit"] = 256
    config["services"]["skeleton"]["shm_size"] = 134217728
    with (
        mock.patch.object(host, "compose_command", return_value=["docker", "compose"]),
        mock.patch.object(host, "_run", return_value=json.dumps(config)),
    ):
        status = host.inspect_config("cpu", tmp_path)
    assert status["limits"] == {
        "memory": "17179869184", "cpus": "6",
        "pids_limit": "256", "shm_size": "134217728",
    }
    with mock.patch.object(host, "inspect_config", return_value=status):
        command = host._isolated_container("cpu", "qualify", root=tmp_path)
    assert command[command.index("--memory") + 1] == "17179869184"
    assert command[command.index("--cpus") + 1] == "6"
    assert command[command.index("--pids-limit") + 1] == "256"


@pytest.mark.parametrize("name,bad_value", [
    ("memory", "unlimited"), ("cpus", "-1"), ("pids_limit", 0),
    ("shm_size", "256m;echo secret"), ("memory", float("inf")),
])
def test_invalid_resource_limits_fail_closed(name: str, bad_value: object) -> None:
    with pytest.raises(host.LocalDockerError):
        host._bounded_limit(bad_value, name=name)


def test_rocm_effective_compose_devices_and_render_group_are_required(tmp_path: Path) -> None:
    config = _fake_config(tmp_path)
    config["services"]["skeleton"]["group_add"] = ["109"]
    config["services"]["skeleton"]["devices"] = [
        {"source": "/dev/kfd", "target": "/dev/kfd"},
        {"source": "/dev/dri", "target": "/dev/dri"},
    ]
    with (
        mock.patch.object(host, "compose_command", return_value=["docker", "compose"]),
        mock.patch.object(host, "_run", return_value=json.dumps(config)),
    ):
        status = host.inspect_config("rocm", tmp_path)
    assert status["render_gid"] == "109"
    config["services"]["skeleton"]["devices"].pop()
    with (
        mock.patch.object(host, "compose_command", return_value=["docker", "compose"]),
        mock.patch.object(host, "_run", return_value=json.dumps(config)),
    ):
        with pytest.raises(host.LocalDockerError):
            host.inspect_config("rocm", tmp_path)


def test_nvidia_effective_compose_device_reservation_is_required(tmp_path: Path) -> None:
    config = _fake_config(tmp_path)
    config["services"]["skeleton"]["deploy"] = {
        "resources": {"reservations": {"devices": [
            {"driver": "nvidia", "count": 1, "capabilities": ["gpu"]}
        ]}}
    }
    with (
        mock.patch.object(host, "compose_command", return_value=["docker", "compose"]),
        mock.patch.object(host, "_run", return_value=json.dumps(config)),
    ):
        assert host.inspect_config("nvidia", tmp_path)["mode"] == "nvidia"
    config["services"]["skeleton"]["deploy"]["resources"]["reservations"]["devices"][0]["count"] = 2
    with (
        mock.patch.object(host, "compose_command", return_value=["docker", "compose"]),
        mock.patch.object(host, "_run", return_value=json.dumps(config)),
    ):
        with pytest.raises(host.LocalDockerError):
            host.inspect_config("nvidia", tmp_path)


def test_unsafe_host_mount_path_and_image_are_rejected(tmp_path: Path) -> None:
    config = _fake_config(tmp_path)
    config["services"]["skeleton"]["image"] = "--privileged"
    with pytest.raises(host.LocalDockerError):
        host._mount_from_compose(config)
    config["services"]["skeleton"]["image"] = "skeleton-local-ai:dev"
    config["services"]["skeleton"]["volumes"][0]["source"] = str(tmp_path) + ",dst=/var/run/docker.sock"
    with pytest.raises(host.LocalDockerError):
        host._mount_from_compose(config)
