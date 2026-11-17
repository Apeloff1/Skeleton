"""Source-level safety regressions for opt-in containerized local Jeeves.

Actual Docker daemon, downloaded GGUF, GPU hardware and live qualification are
independent acceptance gates; these unit checks never claim those results.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
from unittest import mock

import pytest

from skeleton.app import docker_local_ai as engine
from scripts import local_ai_docker as host


def _fake_config(root: Path) -> dict[str, object]:
    config = {
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
                "build": {"args": {"SKL_LOCAL_ONLY_IMAGE": "1"}},
                "mem_limit": 8589934592,
                "cpus": 4,
                "pids_limit": 512,
                "shm_size": 268435456,
            },
        },
    }


    config["networks"] = {"tutolage": {"name": "docker_tutolage", "driver": "bridge"}}
    services = config["services"]
    user = "fixture_reader"
    password = "synthetic_custody_value"
    uri = f"mongodb://{user}:{password}@mongo:27017/skeleton?authSource=admin"
    services["skeleton"]["environment"].update({
        "SKL_MONGO_URI": uri, "SKL_ENGINE_SERVICE_TOKEN": "fixture-local-engine-token",
    })
    services["skeleton"]["volumes"].append({
        "type": "volume", "source": "docker_skeleton_data", "target": "/app/data",
        "read_only": False,
    })
    services["backend"] = {
        "environment": {
            "MONGO_URL": uri,
            "SKELETON_INTERNAL_URL": "http://skeleton:8001",
            "JEEVES_LOCAL_ONLY": "1",
            "JEEVES_PRIMARY_MODEL_ID": "jeeves",
            "SKL_ENGINE_SERVICE_TOKEN": "fixture-local-engine-token",
        },
        "ports": [{"host_ip": "127.0.0.1", "published": "8001", "target": 8001}],
        "volumes": [{"type": "volume", "source": "docker_backend_data",
                     "target": "/app/data", "read_only": False}],
    }
    services["frontend"] = {
        "ports": [{"host_ip": "127.0.0.1", "published": "3000", "target": 3000}],
        "environment": {
            "EXPO_PUBLIC_BACKEND_URL": "http://localhost:8001",
            "EXPO_PUBLIC_SKELETON_URL": "http://localhost:8010",
        },
        "build": {"args": {
            "EXPO_PUBLIC_BACKEND_URL": "http://localhost:8001",
            "EXPO_PUBLIC_SKELETON_URL": "http://localhost:8010",
        }},
    }
    services["mongo"] = {
        "image": "mongo:fixture@sha256:" + "a" * 64,
        "ports": [{"host_ip": "127.0.0.1", "published": "27017", "target": 27017}],
        "environment": {
            "MONGO_INITDB_ROOT_USERNAME": "admin",
            "MONGO_INITDB_ROOT_PASSWORD": password,
        },
        "volumes": [
            {"type": "volume", "source": "docker_mongo_data",
             "target": "/data/db", "read_only": False},
            {"type": "volume", "source": "docker_mongo_config",
             "target": "/data/configdb", "read_only": False},
        ],
    }
    services["chroma"] = {
        "image": "chroma:fixture@sha256:" + "b" * 64,
        "ports": [{"host_ip": "127.0.0.1", "published": "8000", "target": 8000}],
        "profiles": ["full"],
        "volumes": [{"type": "volume", "source": "docker_chroma_data",
                     "target": "/chroma/chroma", "read_only": False}],
    }
    for service in services.values():
        service["networks"] = {"tutolage": None}
    return config


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
    # Docker passes the whole bind specification as a single --mount value.
    assert any("target=/app/local-ai" in option for option in pin)
    assert not any("target=/app/local-ai,readonly" in option for option in pin)


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
        "providers": [{"id": "local", "model": "jeeves", "available": False,
                       "ownership": "engine-process"}],
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
                  {"providers": [{"id": "openai", "model": "gpt", "available": True,
                                  "ownership": "engine-process"}], "llm_available": True}):
        payload = {**sample, "llm_available": True, **patch}
        with mock.patch.object(host, "compose_command", return_value=["docker", "compose"]), (
            mock.patch.object(host, "_run", return_value=json.dumps(payload))
        ):
            assert host.live_ai_status("cpu", tmp_path)["ready"] is False


def test_host_up_never_claims_success_without_canonical_local_guard(tmp_path: Path) -> None:
    with (
        mock.patch.object(host, "_run_model_step", side_effect=[
            _model_receipt("preflight"), _model_receipt("qualify"),
        ]),
        mock.patch.object(host, "_run", return_value=""),
        mock.patch.object(host, "compose_command", return_value=["docker", "compose"]),
        mock.patch.object(host, "live_ai_status", return_value={
            "ready": False, "observed": True, "readiness_code": "local_guard_unavailable",
        }),
        mock.patch("scripts.local_ai_runtime_attestation.attest_runtime",
                   return_value={"status": "running_boundary_verified_not_guarded_chat_qualified"}),
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


_ZERO = "0" * 64
_ONE = "1" * 64
_TWO = "2" * 64


def _model_receipt(phase: str) -> dict[str, object]:
    fields = {
        "ok": True,
        "model_id": "jeeves",
        "provider": "local",
        "network_required": False,
        "model_sha256": _ZERO,
        "executable_sha256": _ONE,
        "manifest_sha256": _TWO,
    }
    if phase == "qualify":
        receipt = {
            **fields,
            "schema_version": "skeleton.local_model.qualification.v1",
            "status": "qualified",
            "runtime_kind": "llama.cpp-cli",
            "response_id": "qualified:" + _ZERO + ":" + _ONE,
        }
        # The model engine seals its receipt before the container CLI adds
        # the process-level ok wrapper.
        canonical = {key: value for key, value in receipt.items() if key != "ok"}
        receipt["receipt_digest"] = hashlib.sha256(json.dumps(
            canonical, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")).hexdigest()
        return receipt
    return {
        **fields,
        "schema": "skeleton.local-ai.docker.preflight.v1",
        "status": "pinned_not_inference_qualified" if phase == "pin"
                  else "artifact_verified_not_inference_qualified",
        "inference_executed": False,
        "model_bytes": 1048576,
        "gpu_layers_requested": 0,
        "context_size": 4096,
    }


@pytest.mark.parametrize("phase", ["pin", "preflight", "qualify"])
def test_operator_parses_real_phase_specific_receipt(phase: str) -> None:
    receipt = _model_receipt(phase)
    assert host._decode_receipt(json.dumps(receipt), phase) == receipt


@pytest.mark.parametrize("mutation", [
    {"ok": False},
    {"provider": "openai"},
    {"network_required": True},
    {"status": "qualified"},
    {"model_id": "secondary"},
    {"manifest_sha256": "not-a-sha"},
])
def test_preflight_receipt_refuses_false_positive(mutation: dict[str, object]) -> None:
    receipt = {**_model_receipt("preflight"), **mutation}
    with pytest.raises(host.LocalDockerError):
        host._decode_receipt(json.dumps(receipt), "preflight")


def test_qualification_receipt_byte_or_field_tamper_is_denied() -> None:
    receipt = _model_receipt("qualify")
    mutated = {**receipt, "status": "qualified", "response_id": receipt["response_id"] + "unrelated"}
    with pytest.raises(host.LocalDockerError, match="content changed"):
        host._decode_receipt(json.dumps(mutated), "qualify")


def test_qualify_receipt_rejects_standalone_text_and_fake_generation() -> None:
    for payload in ("response complete", "{}", "null", "[]", "not-json"):
        with pytest.raises(host.LocalDockerError):
            host._decode_receipt(payload, "qualify")
    for mutation in (
        {"response_id": "independent-but-not-bound"},
        {"receipt_digest": "not-a-real-digest"},
        {"runtime_kind": "hosted"},
        {"status": "pinned_not_inference_qualified"},
    ):
        receipt = {**_model_receipt("qualify"), **mutation}
        with pytest.raises(host.LocalDockerError):
            host._decode_receipt(json.dumps(receipt), "qualify")


def test_changed_model_between_offline_probes_denies_start() -> None:
    before = _model_receipt("preflight")
    after = {**_model_receipt("qualify"), "model_sha256": _ONE}
    with pytest.raises(host.LocalDockerError, match="changed between"):
        host._require_same_model(before, after)


def test_model_receipts_must_qualify_before_compose_up(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    preflight = _model_receipt("preflight")
    qualify = _model_receipt("qualify")
    def run(argv, **kwargs):
        calls.append(argv)
        if "preflight" in argv:
            return json.dumps(preflight)
        if "qualify" in argv:
            return json.dumps(qualify)
        return ""
    with (
        mock.patch.object(host, "_isolated_container", side_effect=lambda mode, action, **kw: ["docker", action]),
        mock.patch.object(host, "_run", side_effect=run),
        mock.patch.object(host, "compose_command", return_value=["docker", "compose"]),
        mock.patch.object(host, "live_ai_status", return_value={"ready": True}),
        mock.patch("scripts.local_ai_runtime_attestation.attest_runtime",
                   return_value={"status": "running_boundary_verified_not_guarded_chat_qualified"}),
    ):
        host.up("cpu", tmp_path)
    assert calls[0] == ["docker", "preflight"]
    assert calls[1] == ["docker", "qualify"]
    assert ["docker", "compose", "up", "-d", "--no-build",
            "--pull", "never", "--wait", "--wait-timeout", "180",
            "mongo", "skeleton", "backend", "frontend"] in calls


def test_unqualified_model_cannot_start_compose(tmp_path: Path) -> None:
    calls = []
    with (
        mock.patch.object(host, "_isolated_container", side_effect=lambda mode, action, **kw: ["docker", action]),
        mock.patch.object(host, "_run", side_effect=lambda argv, **kw: (calls.append(argv), "{}")[1]),
        mock.patch.object(host, "compose_command", return_value=["docker", "compose"]),
    ):
        with pytest.raises(host.LocalDockerError):
            host.up("cpu", tmp_path)
    assert not any("up" in argv for argv in calls)




def test_model_receipt_ok_wrapper_is_not_canonical_hash_input() -> None:
    original = _model_receipt("qualify")
    assert host._decode_receipt(json.dumps(original), "qualify") == original
    copied = dict(original)
    copied["ok"] = False
    with pytest.raises(host.LocalDockerError):
        host._decode_receipt(json.dumps(copied), "qualify")
    copied = dict(original)
    copied["receipt_digest"] = hashlib.sha256(json.dumps(
        {k: v for k, v in original.items() if k != "receipt_digest"},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    with pytest.raises(host.LocalDockerError, match="content changed"):
        host._decode_receipt(json.dumps(copied), "qualify")


def test_backend_provider_dict_projection_accepts_only_engine_owned_jeeves() -> None:
    """Mirror the real backend/routes/ai.py /api/ai/providers public schema."""
    sample = {
        "engine": "skeleton-engine", "active": "local",
        "availability_observed": True, "llm_available": True,
        "providers": [
            {"id": "local", "model": "jeeves", "available": True,
             "ownership": "engine-process", "execution_mode": "local"},
        ],
    }
    def evaluate(payload):
        with (
            mock.patch.object(host, "compose_command", return_value=["docker", "compose"]),
            mock.patch.object(host, "_run", return_value=json.dumps(payload)),
        ):
            return host.live_ai_status("cpu")
    assert evaluate(sample)["ready"] is True
    for altered in (
        {"providers": ["local"]},
        {"providers": []},
        {"providers": [{"id": "local", "model": "jeeves", "available": True,
                        "ownership": "hosted-provider"}]},
        {"providers": [{"id": "local", "model": "wrong", "available": True,
                        "ownership": "engine-process"}]},
        {"providers": [{"id": "local", "model": "jeeves", "available": False,
                        "ownership": "engine-process"}]},
        {"providers": sample["providers"] * 2},
        {"active": "openai"},
        {"availability_observed": False},
        {"llm_available": False},
    ):
        assert evaluate({**sample, **altered})["ready"] is False


def test_backend_provider_contract_is_structured_not_a_flat_id_list() -> None:
    # Avoid a regression that always reports an unavailable local provider.
    source = (Path(__file__).resolve().parents[2] / "backend/routes/ai.py").read_text(
        encoding="utf-8"
    )
    assert 'public_providers: list[dict[str, Any]]' in source
    assert '"ownership": "engine-process"' in source
    assert '"availability_observed": True' in source
    assert '"model": raw.get("model")' in source


def test_local_ai_docker_image_omits_optional_hosted_sdk_extra() -> None:
    root = Path(__file__).resolve().parents[2]
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    overlay = (root / "docker-compose.local-ai.yml").read_text(encoding="utf-8")
    assert "ARG SKL_LOCAL_ONLY_IMAGE=0" in dockerfile
    assert "local_only=os.environ.get('SKL_LOCAL_ONLY_IMAGE','0')" in dockerfile
    assert "([] if local_only=='1' else p['optional-dependencies']['hosted-inference'])" in dockerfile
    assert 'SKL_LOCAL_ONLY_IMAGE: "1"' in overlay


def test_local_image_rejects_hosted_dependency_profile_drift(tmp_path: Path) -> None:
    config = _fake_config(tmp_path)
    config["services"]["skeleton"]["build"]["args"]["SKL_LOCAL_ONLY_IMAGE"] = "0"
    with pytest.raises(host.LocalDockerError, match="exclude hosted"):
        host._mount_from_compose(config)
    config["services"]["skeleton"]["build"]["args"].pop("SKL_LOCAL_ONLY_IMAGE")
    with pytest.raises(host.LocalDockerError, match="exclude hosted"):
        host._mount_from_compose(config)


def test_optional_chroma_profile_absent_is_valid_canonical_assembly(tmp_path: Path) -> None:
    cfg = _fake_config(tmp_path)
    cfg["services"].pop("chroma")
    effective = host._validate_config("cpu", cfg)
    assert effective["services"] == 4
    assert effective["optional_chroma_present"] is False


def test_running_engine_waits_for_bounded_compose_health() -> None:
    source = (Path(__file__).resolve().parents[2] / "scripts/local_ai_docker.py").read_text()
    assert '"--wait", "--wait-timeout", "180"' in source
    assert '"--no-build"' in source


def test_extra_service_and_missing_mandatory_service_both_fail(tmp_path: Path) -> None:
    for modified in (
        lambda config: config["services"].update({"remote-inference": {}}),
        lambda config: config["services"].pop("mongo"),
    ):
        config = _fake_config(tmp_path)
        modified(config)
        with pytest.raises(host.LocalDockerError, match="topology"):
            host._validate_config("cpu", config)


def test_host_operator_exposes_nondestructive_model_custody_commands() -> None:
    source = (Path(__file__).resolve().parents[2] / "scripts/local_ai_docker.py").read_text(
        encoding="utf-8"
    )
    assert 'sub.add_parser("backup-model"' in source
    assert 'sub.add_parser("verify-model-backup"' in source
    assert "from scripts.local_ai_model_backup import backup_model" in source
    assert "from scripts.local_ai_model_backup import verify_backup" in source
    assert '"down", "-v"' not in source


@pytest.mark.parametrize("mode,layers,accepted", [
    ("cpu", 0, True),
    ("cpu", 1, False),
    ("nvidia", 0, False),
    ("nvidia", 16, True),
    ("rocm", 0, False),
    ("rocm", 32, True),
    ("rocm", -1, False),
    ("nvidia", 1025, False),
    ("cpu", True, False),
])
def test_pinned_gguf_gpu_layer_mode_must_match_selected_accelerator(
    mode: str, layers: object, accepted: bool,
) -> None:
    preflight = {**_model_receipt("preflight"), "gpu_layers_requested": layers}
    if accepted:
        host._validate_model_mode(mode, preflight)
    else:
        with pytest.raises(host.LocalDockerError):
            host._validate_model_mode(mode, preflight)


@pytest.mark.parametrize("context", [0, 255, 131073, True, None, "4096"])
def test_pinned_context_must_be_bounded_and_not_coerced(context: object) -> None:
    preflight = {**_model_receipt("preflight"), "context_size": context}
    with pytest.raises(host.LocalDockerError, match="context"):
        host._validate_model_mode("cpu", preflight)


def test_selected_gpu_pin_is_denied_before_model_or_docker_mutation() -> None:
    with mock.patch.object(host, "_run_model_step") as run:
        result = host.main(["--mode", "nvidia", "pin",
                            "--model", "fixture.gguf",
                            "--executable", "fixture-runtime",
                            "--gpu-layers", "0"])
    assert result == 2
    run.assert_not_called()


def test_canonical_standalone_qualify_checks_preflight_model_identity(
    tmp_path: Path,
) -> None:
    first = _model_receipt("preflight")
    completed = _model_receipt("qualify")
    with mock.patch.object(host, "_run_model_step", side_effect=[first, completed]) as run:
        assert host.main(["--mode", "cpu", "qualify"]) == 0
    assert [item.args[1] for item in run.call_args_list] == ["preflight", "qualify"]


def test_canonical_standalone_qualify_denies_mismatched_pinned_accelerator(
    tmp_path: Path,
) -> None:
    first = {**_model_receipt("preflight"), "gpu_layers_requested": 4}
    with mock.patch.object(host, "_run_model_step", side_effect=[first]) as run:
        assert host.main(["--mode", "cpu", "qualify"]) == 2
    assert run.call_count == 1  # No generation after a mismatched immutable pin.


def test_host_up_denies_pinned_gpu_mismatch_before_compose_up(
    tmp_path: Path,
) -> None:
    first = {**_model_receipt("preflight"), "gpu_layers_requested": 8}
    with (
        mock.patch.object(host, "_run_model_step", return_value=first) as step,
        mock.patch.object(host, "_run") as run,
    ):
        with pytest.raises(host.LocalDockerError, match="GPU layers"):
            host.up("cpu", tmp_path)
    assert step.call_count == 1
    run.assert_not_called()


def test_docker_operator_does_not_echo_untrusted_daemon_stdout_or_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    class Done:
        returncode = 0
        stdout = "synthetic private daemon output"
        stderr = "synthetic internal diagnostics"
    with mock.patch.object(host.subprocess, "run", return_value=Done()):
        assert host._run(["docker", "compose", "build", "skeleton"], root=tmp_path) == ""
    assert capsys.readouterr().out == ""


def test_compose_up_requires_no_implicit_pull_and_no_build() -> None:
    source = Path(host.__file__).read_text(encoding="utf-8")
    assert '"up", "-d", "--no-build"' in source
    assert '"--pull", "never", "--wait"' in source


def test_runtime_attestation_is_a_first_class_read_only_operator_action() -> None:
    source = Path(host.__file__).read_text(encoding="utf-8")
    assert 'sub.add_parser("attest-runtime"' in source
    assert 'from scripts.local_ai_runtime_attestation import attest_runtime' in source
