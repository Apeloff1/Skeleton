"""Live Docker local-AI admission tests using hermetic synthetic daemon responses.

The test suite does not contact Docker, start a service, inspect host secrets
or classify physical GPU inference. It proves negative security decisions.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from unittest import mock

import pytest

from scripts import local_ai_docker as host
from scripts import local_ai_runtime_attestation as runtime
from skeleton.testing.test_docker_local_ai import _fake_config


IDS = {name: chr(ord("a") + i) * 64 for i, name in enumerate(
    ("mongo", "skeleton", "backend", "frontend", "chroma")
)}
IMAGE_ID = "sha256:" + "f" * 64


def _setup(root: Path, mode: str = "cpu") -> tuple[dict, dict[str, dict]]:
    config = _fake_config(root)
    config["name"] = "docker"
    if mode == "nvidia":
        config["services"]["skeleton"]["deploy"] = {
            "resources": {"reservations": {"devices": [
                {"driver": "nvidia", "count": 1, "capabilities": ["gpu"]}
            ]}}
    if mode == "rocm":
        config["services"]["skeleton"]["group_add"] = ["109"]
        config["services"]["skeleton"]["devices"] = [
            {"source": "/dev/kfd", "target": "/dev/kfd"},
            {"source": "/dev/dri", "target": "/dev/dri"},
        ]
    docs = {}
    for name in runtime._REQUIRED:
        service = config["services"][name]
        port = service["ports"][0]
        binding = {"HostIp": port["host_ip"], "HostPort": str(port["published"])}
        port_map = {str(port["target"]) + "/tcp": [binding]}
        mounts = []
        for item in service.get("volumes", []):
            mount = {
                "Type": item["type"], "Destination": item["target"],
                "Source": item["source"], "RW": not item["read_only"],
            }
            if item["type"] == "volume":
                mount["Name"] = item["source"]
            mounts.append(mount)
        hostconfig = {
            "PortBindings": port_map,
            "Privileged": False,
            "NetworkMode": "docker_tutolage",
            "CapAdd": None, "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"],
            "ReadonlyRootfs": name in ("skeleton", "backend"),
            "Memory": 8589934592, "ShmSize": 268435456,
            "PidsLimit": 512, "NanoCpus": 4_000_000_000,
            "DeviceRequests": None, "Devices": None,
            "GroupAdd": [],
        }
        if name == "skeleton" and mode == "nvidia":
            hostconfig["DeviceRequests"] = [{
                "Driver": "nvidia", "Count": 1, "Capabilities": [["gpu"]],
            }]
        if name == "skeleton" and mode == "rocm":
            hostconfig["Devices"] = [
                {"PathOnHost": "/dev/kfd", "PathInContainer": "/dev/kfd"},
                {"PathOnHost": "/dev/dri", "PathInContainer": "/dev/dri"},
            ]
            hostconfig["GroupAdd"] = ["109"]
        docs[name] = {
            "Id": IDS[name], "Image": IMAGE_ID,
            "State": {
                "Running": True,
                **({"Health": {"Status": "healthy"}}
                   if name in runtime._PROTECTED else {}),
            },
            "Config": {
                "Labels": {"com.docker.compose.service": name,
                           "com.docker.compose.project": "docker"},
                "Env": [f"{key}={value}" for key, value in
                        service.get("environment", {}).items()],
            },
            "HostConfig": hostconfig,
            "Mounts": mounts,
            "NetworkSettings": {"Ports": deepcopy(port_map),
                                "Networks": {"docker_tutolage": {}}},
        }
    return config, docs


def _run_simulator(config: dict, docs: dict[str, dict], *, chroma_running: bool = False):
    def run(argv, **kwargs):
        assert kwargs.get("capture") is True
        if "config" in argv:
            return json.dumps(config)
        if "ps" in argv and "-q" in argv:
            name = argv[-1]
            return IDS[name] if name in runtime._REQUIRED or chroma_running else ""
        if argv[:3] == ["docker", "inspect", "--type=container"]:
            wanted = argv[-1]
            for doc in docs.values():
                if doc["Id"] == wanted:
                    return json.dumps([doc])
            return json.dumps([])
        if argv[:3] == ["docker", "image", "inspect"]:
            return IMAGE_ID + "\n"
        raise AssertionError("unexpected read-only Docker command: " + repr(argv))
    return run


def _attest(root: Path, config: dict, docs: dict[str, dict], *,
            mode: str = "cpu", chroma_running: bool = False) -> dict:
    with (mock.patch.object(host, "compose_command", return_value=["docker", "compose"]),
          mock.patch.object(host, "_run", side_effect=_run_simulator(
              config, docs, chroma_running=chroma_running))):
        return runtime.attest_runtime(mode, root)


@pytest.mark.parametrize("mode", ("cpu", "nvidia", "rocm"))
def test_actual_container_attestation_accepts_canonical_synthetic_runtime(
    tmp_path: Path, mode: str,
) -> None:
    config, docs = _setup(tmp_path, mode)
    result = _attest(tmp_path, config, docs, mode=mode)
    assert result["mode"] == mode
    assert result["services_verified"] == list(runtime._REQUIRED)
    assert result["container_image_ids_compared"]["skeleton"] == IMAGE_ID
    assert result["container_image_ids_compared"]["mongo"] == IMAGE_ID
    assert result["database_epoch_qualified"] is False
    assert result["guarded_chat_qualified"] is False
    assert result["gpu_offload_qualified"] is False
    assert result["application_recovery_qualified"] is False


@pytest.mark.parametrize("name", runtime._REQUIRED)
def test_any_running_service_cannot_expose_wildcard_interface(
    tmp_path: Path, name: str,
) -> None:
    config, docs = _setup(tmp_path)
    port = next(iter(docs[name]["HostConfig"]["PortBindings"].values()))
    port[0]["HostIp"] = "0.0.0.0"
    with pytest.raises(host.LocalDockerError, match="ingress"):
        _attest(tmp_path, config, docs)


@pytest.mark.parametrize("name", runtime._REQUIRED)
def test_any_service_cannot_publish_extra_ports(tmp_path: Path, name: str) -> None:
    config, docs = _setup(tmp_path)
    docs[name]["HostConfig"]["PortBindings"]["9001/tcp"] = [{
        "HostIp": "127.0.0.1", "HostPort": "9001",
    }]
    with pytest.raises(host.LocalDockerError, match="unexpected ports"):
        _attest(tmp_path, config, docs)


@pytest.mark.parametrize("name", runtime._REQUIRED)
def test_running_service_must_belong_to_canonical_project(tmp_path: Path, name: str) -> None:
    config, docs = _setup(tmp_path)
    docs[name]["Config"]["Labels"]["com.docker.compose.project"] = "imposter"
    with pytest.raises(host.LocalDockerError, match="project identity"):
        _attest(tmp_path, config, docs)


@pytest.mark.parametrize("name", ("mongo", "backend", "skeleton"))
def test_unhealthy_authoritative_service_denies_live_attestation(
    tmp_path: Path, name: str,
) -> None:
    config, docs = _setup(tmp_path)
    docs[name]["State"]["Health"]["Status"] = "unhealthy"
    with pytest.raises(host.LocalDockerError, match="health"):
        _attest(tmp_path, config, docs)


@pytest.mark.parametrize("name", runtime._REQUIRED)
def test_unexpected_stopped_service_fails_closed(tmp_path: Path, name: str) -> None:
    config, docs = _setup(tmp_path)
    docs[name]["State"]["Running"] = False
    with pytest.raises(host.LocalDockerError, match="not running"):
        _attest(tmp_path, config, docs)


@pytest.mark.parametrize("name", ("mongo", "backend", "skeleton"))
def test_live_authoritative_volume_cannot_become_read_only(
    tmp_path: Path, name: str,
) -> None:
    config, docs = _setup(tmp_path)
    target = "/data/db" if name == "mongo" else "/app/data"
    state = next(item for item in docs[name]["Mounts"] if item["Destination"] == target)
    state["RW"] = False
    with pytest.raises(host.LocalDockerError, match="write authority"):
        _attest(tmp_path, config, docs)


def test_live_model_directory_must_remain_read_only(tmp_path: Path) -> None:
    config, docs = _setup(tmp_path)
    model = next(x for x in docs["skeleton"]["Mounts"]
                 if x["Destination"] == "/app/local-ai")
    model["RW"] = True
    with pytest.raises(host.LocalDockerError, match="write authority"):
        _attest(tmp_path, config, docs)


def test_live_model_bind_source_must_not_be_redirected(tmp_path: Path) -> None:
    config, docs = _setup(tmp_path)
    model = next(x for x in docs["skeleton"]["Mounts"]
                 if x["Destination"] == "/app/local-ai")
    model["Source"] = str(tmp_path / "untrusted")
    with pytest.raises(host.LocalDockerError, match="bind source"):
        _attest(tmp_path, config, docs)


def test_live_volume_owner_must_not_drift(tmp_path: Path) -> None:
    config, docs = _setup(tmp_path)
    volume = next(x for x in docs["mongo"]["Mounts"]
                  if x["Destination"] == "/data/db")
    volume["Name"] = "another_project_mongo_data"
    with pytest.raises(host.LocalDockerError, match="volume identity"):
        _attest(tmp_path, config, docs)


def test_actual_image_id_cannot_be_stale(tmp_path: Path) -> None:
    config, docs = _setup(tmp_path)
    docs["skeleton"]["Image"] = "sha256:" + "1" * 64
    with pytest.raises(host.LocalDockerError, match="image bytes"):
        _attest(tmp_path, config, docs)


def test_runtime_cannot_restore_hosted_credential(tmp_path: Path) -> None:
    config, docs = _setup(tmp_path)
    docs["skeleton"]["Config"]["Env"].append("OPENAI_API_KEY=synthetic-untrusted-value")
    with pytest.raises(host.LocalDockerError, match="live engine exposes"):
        _attest(tmp_path, config, docs)


def test_runtime_cannot_swap_mongo_credentials(tmp_path: Path) -> None:
    config, docs = _setup(tmp_path)
    actual = docs["backend"]["Config"]["Env"]
    docs["backend"]["Config"]["Env"] = [
        field if not field.startswith("MONGO_URL=") else "MONGO_URL=changed"
        for field in actual
    ]
    with pytest.raises(host.LocalDockerError, match="environment differs"):
        _attest(tmp_path, config, docs)


@pytest.mark.parametrize("name", ("skeleton", "backend"))
def test_application_cannot_become_privileged(tmp_path: Path, name: str) -> None:
    config, docs = _setup(tmp_path)
    docs[name]["HostConfig"]["Privileged"] = True
    with pytest.raises(host.LocalDockerError, match="privileged"):
        _attest(tmp_path, config, docs)


@pytest.mark.parametrize("field,value", [
    ("ReadonlyRootfs", False), ("CapDrop", None), ("SecurityOpt", []),
])
def test_live_engine_security_restrictions_cannot_be_removed(
    tmp_path: Path, field: str, value: object,
) -> None:
    config, docs = _setup(tmp_path)
    docs["skeleton"]["HostConfig"][field] = value
    with pytest.raises(host.LocalDockerError, match="privilege restriction"):
        _attest(tmp_path, config, docs)


@pytest.mark.parametrize("field,value", [
    ("Memory", 4_000_000), ("PidsLimit", 100000), ("NanoCpus", 12_000_000_000),
    ("ShmSize", 4096),
])
def test_effective_running_resource_bounds_must_match_rendered_compose(
    tmp_path: Path, field: str, value: int,
) -> None:
    config, docs = _setup(tmp_path)
    docs["skeleton"]["HostConfig"][field] = value
    with pytest.raises(host.LocalDockerError, match="differ"):
        _attest(tmp_path, config, docs)


def test_cpu_profile_denies_surprise_gpu_request(tmp_path: Path) -> None:
    config, docs = _setup(tmp_path)
    docs["skeleton"]["HostConfig"]["DeviceRequests"] = [{
        "Driver": "nvidia", "Count": 1, "Capabilities": [["gpu"]],
    }]
    with pytest.raises(host.LocalDockerError, match="CPU-only"):
        _attest(tmp_path, config, docs)


def test_nvidia_profile_requires_actual_single_device_request(tmp_path: Path) -> None:
    config, docs = _setup(tmp_path, "nvidia")
    docs["skeleton"]["HostConfig"]["DeviceRequests"] = None
    with pytest.raises(host.LocalDockerError, match="NVIDIA"):
        _attest(tmp_path, config, docs, mode="nvidia")


def test_rocm_profile_requires_matching_applied_device_set(tmp_path: Path) -> None:
    config, docs = _setup(tmp_path, "rocm")
    docs["skeleton"]["HostConfig"]["Devices"].pop()
    with pytest.raises(host.LocalDockerError, match="ROCm"):
        _attest(tmp_path, config, docs, mode="rocm")


def test_rocm_profile_requires_applied_render_group(tmp_path: Path) -> None:
    config, docs = _setup(tmp_path, "rocm")
    docs["skeleton"]["HostConfig"]["GroupAdd"] = []
    with pytest.raises(host.LocalDockerError, match="render group"):
        _attest(tmp_path, config, docs, mode="rocm")


def test_unqualified_chroma_container_cannot_silently_start(tmp_path: Path) -> None:
    config, docs = _setup(tmp_path)
    with pytest.raises(host.LocalDockerError, match="Chroma"):
        _attest(tmp_path, config, docs, chroma_running=True)


def test_inspection_receipts_cannot_echo_database_secrets(tmp_path: Path) -> None:
    config, docs = _setup(tmp_path)
    docs["mongo"]["HostConfig"]["PortBindings"]["27017/tcp"][0]["HostIp"] = "0.0.0.0"
    with pytest.raises(host.LocalDockerError) as error:
        _attest(tmp_path, config, docs)
    assert "synthetic_custody_value" not in str(error.value)
    assert "MONGO_URL=" not in str(error.value)


def test_read_only_attestation_has_no_container_mutation_commands(tmp_path: Path) -> None:
    config, docs = _setup(tmp_path)
    observed = []
    original = _run_simulator(config, docs)
    def traced(argv, **kwargs):
        observed.append(argv)
        return original(argv, **kwargs)
    with (mock.patch.object(host, "compose_command", return_value=["docker", "compose"]),
          mock.patch.object(host, "_run", side_effect=traced)):
        runtime.attest_runtime("cpu", tmp_path)
    assert observed
    assert all("up" not in command and "down" not in command
               and "run" not in command and "build" not in command
               and "rm" not in command and "prune" not in command
               for command in observed)


@pytest.mark.parametrize("name", runtime._REQUIRED)
def test_live_container_cannot_join_unexpected_network(
    tmp_path: Path, name: str,
) -> None:
    config, docs = _setup(tmp_path)
    docs[name]["NetworkSettings"]["Networks"]["untrusted_bridge"] = {}
    with pytest.raises(host.LocalDockerError, match="network membership"):
        _attest(tmp_path, config, docs)


@pytest.mark.parametrize("name", runtime._REQUIRED)
def test_live_container_cannot_switch_network_mode(
    tmp_path: Path, name: str,
) -> None:
    config, docs = _setup(tmp_path)
    docs[name]["HostConfig"]["NetworkMode"] = "other_project_bridge"
    with pytest.raises(host.LocalDockerError, match="network mode"):
        _attest(tmp_path, config, docs)
