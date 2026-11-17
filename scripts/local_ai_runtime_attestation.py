#!/usr/bin/env python3
"""Read-only proof of running Docker local-AI boundaries, not product readiness.

This auditor compares actual daemon state with the *rendered*, fully validated
Compose topology and Docker image IDs. It never logs inspect payloads, because
container environment arrays and effective Compose include private credentials.
It does not issue a Docker create/up/build or mutate any volume.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
from typing import Any, Mapping

from scripts import local_ai_docker as host

_CONTAINER_ID = re.compile(r"[a-f0-9]{12,64}\Z")
_IMAGE_ID = re.compile(r"sha256:[a-f0-9]{64}\Z")
_REQUIRED = ("mongo", "skeleton", "backend", "frontend")
_REQUIRED_MOUNTS = {
    "mongo": {"/data/db", "/data/configdb"},
    "skeleton": {"/app/local-ai", "/app/data"},
    "backend": {"/app/data"},
    "frontend": set(),
}
_PROTECTED = frozenset({"mongo", "skeleton", "backend"})


def _json(raw: str, *, limit: int, label: str) -> Any:
    if not isinstance(raw, str) or len(raw) > limit:
        raise host.LocalDockerError(label + " exceeded its private JSON budget")
    try:
        return json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise host.LocalDockerError(label + " did not return valid JSON") from exc


def _inspection(command: list[str], root: Path) -> dict[str, Any]:
    raw = host._run(command, root=root, capture=True)
    doc = _json(raw, limit=2 * 1024 * 1024, label="Docker inspect")
    if not isinstance(doc, list) or len(doc) != 1 or not isinstance(doc[0], dict):
        raise host.LocalDockerError("Docker inspect must report exactly one container")
    return doc[0]


def _expected_mounts(service: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    volumes = service.get("volumes", [])
    if not isinstance(volumes, list):
        raise host.LocalDockerError("rendered Compose volume map is invalid")
    result: dict[str, dict[str, Any]] = {}
    for item in volumes:
        if not isinstance(item, dict) or not isinstance(item.get("target"), str):
            raise host.LocalDockerError("rendered Compose mount is invalid")
        target = item["target"]
        if target in result:
            raise host.LocalDockerError("rendered Compose has duplicate mounts")
        result[target] = item
    return result


def _compare_mounts(name: str, service: Mapping[str, Any], doc: Mapping[str, Any]) -> None:
    expected = _expected_mounts(service)
    if set(expected) != _REQUIRED_MOUNTS[name]:
        raise host.LocalDockerError("running service has an unexpected Compose mount")
    mounts = doc.get("Mounts")
    if not isinstance(mounts, list):
        raise host.LocalDockerError("running service mount inventory is unavailable")
    observed: dict[str, dict[str, Any]] = {}
    for mount in mounts:
        if not isinstance(mount, dict) or not isinstance(mount.get("Destination"), str):
            raise host.LocalDockerError("Docker mount descriptor is invalid")
        target = mount["Destination"]
        if target in observed:
            raise host.LocalDockerError("Docker container has duplicate mount targets")
        observed[target] = mount
    if set(observed) != set(expected):
        raise host.LocalDockerError("Docker live mount set differs from canonical Compose")
    for dest, spec in expected.items():
        actual = observed[dest]
        if actual.get("Type") != spec.get("type"):
            raise host.LocalDockerError("Docker live mount type changed")
        if actual.get("RW") is not (not bool(spec.get("read_only", False))):
            raise host.LocalDockerError("Docker live mount write authority differs")
        if spec.get("type") == "volume":
            if actual.get("Name") != spec.get("source"):
                raise host.LocalDockerError("Docker live volume identity changed")
        elif spec.get("type") == "bind":
            if (not isinstance(spec.get("source"), str)
                    or actual.get("Source") != spec["source"]):
                raise host.LocalDockerError("Docker live bind source differs")
        else:
            raise host.LocalDockerError("Docker has an unsupported canonical mount type")


def _compare_ports(service: Mapping[str, Any], doc: Mapping[str, Any]) -> None:
    expected = service.get("ports")
    if not isinstance(expected, list) or len(expected) != 1 or not isinstance(expected[0], dict):
        raise host.LocalDockerError("rendered Compose has an invalid port contract")
    port = expected[0]
    target = str(port.get("target")) + "/tcp"
    wanted = (str(port.get("host_ip")), str(port.get("published")))
    hostconfig = doc.get("HostConfig")
    if not isinstance(hostconfig, dict):
        raise host.LocalDockerError("Docker host configuration is unavailable")
    bindings = hostconfig.get("PortBindings")
    if not isinstance(bindings, dict):
        raise host.LocalDockerError("Docker host port bindings are unavailable")
    published: dict[str, list[Any]] = {
        key: value for key, value in bindings.items() if value
    }
    if set(published) != {target} or not isinstance(published[target], list) or len(published[target]) != 1:
        raise host.LocalDockerError("running container published unexpected ports")
    bound = published[target][0]
    if not isinstance(bound, dict) or (
        str(bound.get("HostIp")) != wanted[0] or str(bound.get("HostPort")) != wanted[1]
    ):
        raise host.LocalDockerError("running container ingress differs from Compose")
    network = doc.get("NetworkSettings")
    ports = network.get("Ports") if isinstance(network, dict) else None
    if not isinstance(ports, dict) or ports.get(target) != published[target]:
        raise host.LocalDockerError("actual published port differs from requested ingress")


def _integer(value: object, *, name: str) -> int:
    if type(value) is not int or value < 0:
        raise host.LocalDockerError("Docker " + name + " is missing or invalid")
    return value


def _bytes(value: object) -> int:
    text = host._bounded_limit(value, name="memory").lower()
    match = re.fullmatch(r"([1-9][0-9]{0,14})(?:\.([0-9]{1,3}))?([kmgt]b?)?", text)
    if not match:
        raise host.LocalDockerError("Compose memory limit cannot be independently matched")
    scale = {"": 1, "k": 1024, "m": 1024 ** 2, "g": 1024 ** 3, "t": 1024 ** 4}
    suffix = (match.group(3) or "").rstrip("b")
    whole = match.group(1) + ("." + match.group(2) if match.group(2) else "")
    try:
        count = Decimal(whole) * scale[suffix]
    except (InvalidOperation, KeyError) as exc:
        raise host.LocalDockerError("Compose memory limit is invalid") from exc
    if count != int(count):
        raise host.LocalDockerError("Compose memory limit must resolve to whole bytes")
    return int(count)


def _engine_limits(service: Mapping[str, Any], doc: Mapping[str, Any]) -> None:
    hostconfig = doc.get("HostConfig")
    if not isinstance(hostconfig, dict):
        raise host.LocalDockerError("Docker engine resource contract is unavailable")
    for key, field in (("mem_limit", "Memory"), ("shm_size", "ShmSize")):
        if _integer(hostconfig.get(field), name=field) != _bytes(service.get(key)):
            raise host.LocalDockerError("running engine memory resources differ from Compose")
    expected_pids = int(host._bounded_limit(service.get("pids_limit"), name="pids_limit"))
    if _integer(hostconfig.get("PidsLimit"), name="PidsLimit") != expected_pids:
        raise host.LocalDockerError("running engine PID bound differs from Compose")
    try:
        expected_cpu = Decimal(host._bounded_limit(service.get("cpus"), name="cpus"))
        nano = expected_cpu * 1_000_000_000
    except (InvalidOperation, ValueError) as exc:
        raise host.LocalDockerError("Compose CPU bound cannot be verified") from exc
    if nano != int(nano) or _integer(hostconfig.get("NanoCpus"), name="NanoCpus") != int(nano):
        raise host.LocalDockerError("running engine CPU bound differs from Compose")


def _gpu(mode: str, doc: Mapping[str, Any], configured: Mapping[str, Any]) -> None:
    hostconfig = doc["HostConfig"]
    requests = hostconfig.get("DeviceRequests") or []
    devices = hostconfig.get("Devices") or []
    if not isinstance(requests, list) or not isinstance(devices, list):
        raise host.LocalDockerError("Docker GPU device authority is malformed")
    if mode == "cpu":
        if requests or devices:
            raise host.LocalDockerError("CPU-only engine unexpectedly exposes accelerator devices")
    elif mode == "nvidia":
        if len(requests) != 1 or devices:
            raise host.LocalDockerError("NVIDIA engine device admission differs")
        request = requests[0]
        caps = request.get("Capabilities") if isinstance(request, dict) else None
        if (not isinstance(request, dict) or request.get("Driver") != "nvidia"
                or request.get("Count") != 1 or not isinstance(caps, list)
                or not any(isinstance(group, list) and "gpu" in group for group in caps)):
            raise host.LocalDockerError("NVIDIA engine does not have one GPU reservation")
    elif mode == "rocm":
        if requests or len(devices) != 2:
            raise host.LocalDockerError("ROCm engine device authority differs")
        if {(item.get("PathOnHost"), item.get("PathInContainer"))
            for item in devices if isinstance(item, dict)} != {
                ("/dev/kfd", "/dev/kfd"), ("/dev/dri", "/dev/dri")
        }:
            raise host.LocalDockerError("ROCm engine device paths differ")
        gid = str(configured.get("group_add", [""])[0])
        if gid not in [str(value) for value in hostconfig.get("GroupAdd", [])]:
            raise host.LocalDockerError("ROCm render group was not applied")
    else:
        raise host.LocalDockerError("unsupported accelerator mode")


def _live_env(name: str, service: Mapping[str, Any], doc: Mapping[str, Any]) -> None:
    """Require all Compose-owned variables identical; never return their values."""
    env = service.get("environment")
    config = doc.get("Config")
    if not isinstance(env, dict) or not isinstance(config, dict):
        raise host.LocalDockerError("running service environment is unavailable")
    raw = config.get("Env")
    if not isinstance(raw, list) or not all(isinstance(x, str) and "=" in x for x in raw):
        raise host.LocalDockerError("Docker environment array is malformed")
    observed: dict[str, str] = {}
    for item in raw:
        key, value = item.split("=", 1)
        if key in observed:
            raise host.LocalDockerError("Docker service duplicates environment keys")
        observed[key] = value
    for key, value in env.items():
        if not isinstance(key, str) or not isinstance(value, str) or observed.get(key) != value:
            raise host.LocalDockerError("runtime environment differs from rendered Compose")
    if name == "skeleton":
        if any(observed.get(key) != value for key, value in host.ENV_FENCE.items()):
            raise host.LocalDockerError("live engine local-only fence differs")
        if any(str(observed.get(key, "")).strip() for key in host.EMPTY_FENCE):
            raise host.LocalDockerError("live engine exposes a hosted inference fallback")


def _compare_network(doc: Mapping[str, Any], topology: Mapping[str, Any]) -> None:
    network = doc.get("NetworkSettings")
    live = network.get("Networks") if isinstance(network, dict) else None
    effective = topology.get("networks")
    bridge = effective.get("tutolage") if isinstance(effective, dict) else None
    target = bridge.get("name") if isinstance(bridge, dict) else None
    if (not isinstance(live, dict) or not isinstance(target, str)
            or set(live) != {target} or not isinstance(live[target], dict)):
        raise host.LocalDockerError("running container has unexpected network membership")
    hostconfig = doc.get("HostConfig")
    if not isinstance(hostconfig, dict) or hostconfig.get("NetworkMode") != target:
        raise host.LocalDockerError("running container has a different network mode")


def _live_container(
    name: str, doc: Mapping[str, Any], topology: Mapping[str, Any], mode: str,
) -> None:
    service = topology["services"][name]
    state = doc.get("State")
    config = doc.get("Config")
    hostconfig = doc.get("HostConfig")
    if not all(isinstance(item, dict) for item in (state, config, hostconfig)):
        raise host.LocalDockerError("Docker container inspection is incomplete")
    if state.get("Running") is not True:
        raise host.LocalDockerError("canonical application container is not running")
    health = state.get("Health")
    if name in _PROTECTED and (
        not isinstance(health, dict) or health.get("Status") != "healthy"
    ):
        raise host.LocalDockerError("canonical service health check is not healthy")
    if isinstance(health, dict) and health.get("Status") == "unhealthy":
        raise host.LocalDockerError("canonical service reports unhealthy")
    labels = config.get("Labels")
    if not isinstance(labels, dict) or labels.get("com.docker.compose.service") != name:
        raise host.LocalDockerError("container is not the expected Compose service")
    if (not isinstance(topology.get("name"), str)
            or labels.get("com.docker.compose.project") != topology["name"]):
        raise host.LocalDockerError("container has a different Compose project identity")
    if (hostconfig.get("Privileged") is True or hostconfig.get("NetworkMode") in (
            "host", "none") or str(hostconfig.get("NetworkMode", "")).startswith("container:")
            or hostconfig.get("CapAdd")):
        raise host.LocalDockerError("container acquired a noncanonical privileged boundary")
    if name in ("skeleton", "backend"):
        if (hostconfig.get("ReadonlyRootfs") is not True
                or "ALL" not in (hostconfig.get("CapDrop") or [])
                or not any(str(option).startswith("no-new-privileges")
                           for option in (hostconfig.get("SecurityOpt") or []))):
            raise host.LocalDockerError("live application privilege restriction was removed")
    _compare_network(doc, topology)
    _compare_ports(service, doc)
    _compare_mounts(name, service, doc)
    _live_env(name, service, doc)
    if name == "skeleton":
        _engine_limits(service, doc)
        _gpu(mode, doc, service)


def _image_matches(name: str, service: Mapping[str, Any], doc: Mapping[str, Any],
                   root: Path) -> None:
    expected = service.get("image")
    if not isinstance(expected, str) or not expected:
        return  # Compose-generated image name not independently identified here.
    raw = host._run(["docker", "image", "inspect", "--format", "{{.Id}}", expected],
                    root=root, capture=True).strip()
    if not _IMAGE_ID.fullmatch(raw) or doc.get("Image") != raw:
        raise host.LocalDockerError("running service image bytes differ from selected image")


def attest_runtime(mode: str, root: Path = host.ROOT) -> dict[str, object]:
    """Only READ daemon and effective Compose; never infer inference readiness."""
    command = host.compose_command(mode, root)
    raw = host._run([*command, "config", "--format", "json"], root=root, capture=True)
    topology = _json(raw, limit=2 * 1024 * 1024, label="Compose configuration")
    validated = host._validate_config(mode, topology)
    if not isinstance(topology.get("name"), str) or not topology["name"]:
        raise host.LocalDockerError("Compose project identity is unavailable")
    verified: list[str] = []
    image_ids: dict[str, str] = {}
    for name in _REQUIRED:
        cid = host._run([*command, "ps", "-q", name], root=root, capture=True).strip()
        if not _CONTAINER_ID.fullmatch(cid):
            raise host.LocalDockerError("canonical service has no unique running container")
        doc = _inspection(["docker", "inspect", "--type=container", cid], root)
        if doc.get("Id") != cid:
            raise host.LocalDockerError("Docker inspected a different container identity")
        _live_container(name, doc, topology, mode)
        _image_matches(name, topology["services"][name], doc, root)
        if isinstance(topology["services"][name].get("image"), str):
            image_ids[name] = doc["Image"]
        verified.append(name)
    if "chroma" in topology["services"]:
        # The optional database's legacy data recovery is not qualified.
        # A separate explicit migration approval must precede live use.
        cid = host._run([*command, "ps", "-q", "chroma"], root=root, capture=True).strip()
        if cid:
            raise host.LocalDockerError("optional Chroma is running without recovery qualification")
    return {
        "schema": "skeleton.local-ai.docker.runtime-attestation.v1",
        "status": "running_boundary_verified_not_guarded_chat_qualified",
        "mode": mode,
        "services_verified": verified,
        "compose_boundary": validated["compose_boundary"],
        "container_image_ids_compared": image_ids,
        "database_epoch_qualified": False,
        "guarded_chat_qualified": False,
        "model_inference_executed": False,
        "gpu_offload_qualified": False,
        "application_recovery_qualified": False,
    }
