#!/usr/bin/env python3
"""Strictly opt-in, no-pull, exact-image-ID first launch of local Jeeves Docker.

This phase is not a recovery/upgrade/migration tool. Existing Compose
containers or named data volumes are hard blockers; never stop, prune,
recreate, retag or overwrite them. Complete GGUF native one-shot qualification
must succeed *before* any new application volume can be created. The launched
containers are independently inspected after Docker Compose --wait. A running
container is not a protected Jeeves chat authorization.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Mapping

from scripts import local_ai_docker as host
from scripts import local_ai_image_bundle as bundle
from scripts import local_ai_offline_compose as binding

SCHEMA = "skeleton.local-ai.docker.offline-fresh-launch.v1"
ROLES = tuple(bundle.ROLES)
CID = re.compile(r"[a-f0-9]{64}\Z")
VOLUME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,254}\Z")
MAX_VOLUMES = 32
MAX_INSPECT_BYTES = 2 * 1024 * 1024
MAX_VOLUME_INVENTORY = 4 * 1024 * 1024
_ALLOWED_IP = frozenset(("127.0.0.1", "::1"))


class OfflineLaunchError(host.LocalDockerError):
    """The installed local Jeeves image set cannot safely create fresh state."""


def _prefix(mode: str, destination: Path, root: Path) -> list[str]:
    if destination.name in ("", ".", ".."):
        raise OfflineLaunchError("offline Compose binding path invalid")
    return [
        *host.compose_command(mode, root), "-f",
        str(destination / binding.FILE),
    ]


def _volume_names(source: Mapping[str, Any]) -> list[str]:
    services = source.get("services")
    if not isinstance(services, dict):
        raise OfflineLaunchError("canonical fresh-state service map missing")
    names: set[str] = set()
    for role in ROLES:
        service = services.get(role)
        if not isinstance(service, dict):
            raise OfflineLaunchError("canonical fresh-state service missing")
        mounts = service.get("volumes", [])
        if not isinstance(mounts, list):
            raise OfflineLaunchError("canonical Docker mount list invalid")
        for mount in mounts:
            if not isinstance(mount, dict):
                raise OfflineLaunchError("canonical Docker mount metadata invalid")
            if mount.get("type") == "volume":
                value = mount.get("source")
                if not isinstance(value, str) or not VOLUME.fullmatch(value):
                    raise OfflineLaunchError("canonical named volume path invalid")
                names.add(value)
            elif mount.get("type") != "bind":
                raise OfflineLaunchError("unexpected Docker storage mount type")
    if not names or len(names) > MAX_VOLUMES:
        raise OfflineLaunchError("fresh-state Docker volume inventory invalid")
    return sorted(names)


def _fresh(mode: str, destination: Path, root: Path,
           canonical: Mapping[str, Any]) -> list[str]:
    """Check the entire target project and its exact canonical data volumes."""
    command = _prefix(mode, destination, root)
    project = canonical.get("name")
    if not isinstance(project, str) or not project:
        raise OfflineLaunchError("canonical Docker project name is missing")
    # A service-scoped compose ps can miss renamed, stopped or orphaned
    # containers from the same project. Scan the entire daemon project.
    all_project = host._run([
        "docker", "ps", "-a", "--no-trunc",
        "--filter", "label=com.docker.compose.project=" + project,
        "--format", "{{.ID}}",
    ], root=root, capture=True)
    if not isinstance(all_project, str) or len(all_project) > 8192:
        raise OfflineLaunchError("complete Docker project inventory unavailable")
    if any(line.strip() for line in all_project.splitlines()):
        raise OfflineLaunchError("existing Docker project member requires recovery")
    for role in ROLES:
        output = host._run([
            *command, "ps", "--all", "--quiet", role,
        ], root=root, capture=True)
        if not isinstance(output, str) or len(output) > 4096 or output.strip():
            raise OfflineLaunchError("existing local AI container requires recovery authority")
    names = _volume_names(canonical)
    raw = host._run([
        "docker", "volume", "ls", "--format", "{{.Name}}",
    ], root=root, capture=True)
    if not isinstance(raw, str) or len(raw) > MAX_VOLUME_INVENTORY:
        raise OfflineLaunchError("existing Docker volume inventory unavailable")
    current = set()
    for value in raw.splitlines():
        name = value.strip()
        if not name or len(name) > 255 or not VOLUME.fullmatch(name):
            raise OfflineLaunchError("Docker volume inventory is malformed")
        current.add(name)
    if current.intersection(names):
        raise OfflineLaunchError("existing canonical volume requires recovery not first install")
    return names


def plan_fresh_offline_launch(mode: str, archive: Path, overlay_directory: Path, *,
                              expected_receipt_sha256: str,
                              root: Path = host.ROOT) -> dict[str, Any]:
    """Read-only first install admission: refuses all existing canonical state."""
    verification = binding.verify_binding(
        mode, archive, overlay_directory,
        expected_receipt_sha256=expected_receipt_sha256, root=root,
    )
    original = binding._original(mode, root)
    if original["name"] != verification["project"]:
        raise OfflineLaunchError("canonical Compose project changed during launch admission")
    volumes = _fresh(mode, overlay_directory, root, original)
    return {
        "schema": SCHEMA,
        "status": "fresh_local_only_deployment_preflight_no_containers_started",
        "project": verification["project"],
        "mode": mode,
        "platform": verification["platform"],
        "source_receipt_file_sha256": verification["source_receipt_file_sha256"],
        "images": verification["images"],
        "expected_new_volume_count": len(volumes),
        "existing_target_containers": 0,
        "existing_target_volumes": 0,
        "image_refs_bound_by_immutable_id": True,
        "no_build_required": True,
        "no_registry_pull_required": True,
        "will_create_app_state_on_explicit_launch": True,
        "freshness_check_atomic_with_docker": False,
        "containers_started": False,
        "gguf_executed": False,
        "guarded_chat_qualified": False,
        "database_recovery_qualified": False,
        "release_qualified": False,
    }



def _attest_internal_bridge(name: str, project: str, root: Path) -> None:
    """Inspect actual daemon network, not only the Compose source property."""
    if (not isinstance(name, str) or not VOLUME.fullmatch(name)
            or not isinstance(project, str) or not project):
        raise OfflineLaunchError("internal local-only Docker bridge identity invalid")
    raw = host._run([
        "docker", "network", "inspect", "--format", "{{json .}}", name,
    ], root=root, capture=True)
    if not isinstance(raw, str) or not 0 < len(raw) <= MAX_INSPECT_BYTES:
        raise OfflineLaunchError("physical Docker bridge inspection unavailable")
    inspected = binding._decode(
        raw, ceiling=MAX_INSPECT_BYTES, label="Docker bridge inspection"
    )
    if not isinstance(inspected, dict):
        raise OfflineLaunchError("physical Docker bridge metadata invalid")
    labels = inspected.get("Labels")
    if (inspected.get("Name") != name
            or inspected.get("Driver") != "bridge"
            or inspected.get("Internal") is not True
            or inspected.get("Attachable") is not False
            or not isinstance(labels, dict)
            or labels.get("com.docker.compose.project") != project
            or labels.get("com.docker.compose.network") != "tutolage"):
        raise OfflineLaunchError(
            "physical local-AI bridge permits external routes or differs from Compose"
        )


def _inspect(mode: str, destination: Path, root: Path,
             canonical: Mapping[str, Any],
             ids: Mapping[str, str]) -> list[dict[str, Any]]:
    prefix = _prefix(mode, destination, root)
    service_map = canonical["services"]
    network = canonical["networks"]["tutolage"]["name"]
    project = canonical["name"]
    _attest_internal_bridge(network, project, root)
    results: list[dict[str, Any]] = []
    observed: set[str] = set()
    for role in ROLES:
        cid = host._run([
            *prefix, "ps", "--all", "--quiet", role,
        ], root=root, capture=True).strip()
        if not CID.fullmatch(cid) or cid in observed:
            raise OfflineLaunchError("offline Compose container identity unavailable")
        observed.add(cid)
        raw = host._run([
            "docker", "inspect", "--format", "{{json .}}", cid,
        ], root=root, capture=True)
        if not isinstance(raw, str) or not 0 < len(raw) <= MAX_INSPECT_BYTES:
            raise OfflineLaunchError("offline container runtime inspection unavailable")
        detail = binding._decode(raw, ceiling=MAX_INSPECT_BYTES,
                                 label="offline Docker container inspection")
        if not isinstance(detail, dict):
            raise OfflineLaunchError("offline Docker inspection is not an object")
        config, state = detail.get("Config"), detail.get("State")
        host_config, network_settings = (
            detail.get("HostConfig"), detail.get("NetworkSettings")
        )
        if any(not isinstance(x, dict) for x in (
            config, state, host_config, network_settings
        )):
            raise OfflineLaunchError("offline Docker container state metadata unavailable")
        labels = config.get("Labels")
        if (not isinstance(labels, dict)
                or labels.get("com.docker.compose.project") != project
                or labels.get("com.docker.compose.service") != role
                or detail.get("Image") != ids[role]
                or state.get("Running") is not True
                or type(state.get("Pid")) is not int
                or state["Pid"] <= 0
                or host_config.get("Privileged") is not False
                or host_config.get("NetworkMode") == "host"
                or host_config.get("PidMode") == "host"
                or host_config.get("CapAdd")):
            raise OfflineLaunchError("offline container identity or isolation differs")
        networks = network_settings.get("Networks")
        if not isinstance(networks, dict) or set(networks) != {network}:
            raise OfflineLaunchError("offline container escaped canonical bridge")
        desired = service_map[role]
        if desired.get("read_only") is True and host_config.get("ReadonlyRootfs") is not True:
            raise OfflineLaunchError("offline read-only root filesystem not enforced")
        if role == "skeleton":
            drops = host_config.get("CapDrop")
            opts = host_config.get("SecurityOpt")
            if (not isinstance(drops, list)
                    or "ALL" not in [str(x).upper() for x in drops]
                    or not isinstance(opts, list)
                    or not any(x in ("no-new-privileges", "no-new-privileges:true")
                               for x in opts)
                    or type(host_config.get("Memory")) is not int
                    or host_config["Memory"] <= 0
                    or type(host_config.get("PidsLimit")) is not int
                    or host_config["PidsLimit"] <= 0):
                raise OfflineLaunchError("offline Jeeves resource or privilege guard missing")
        expected_ports = desired.get("ports")
        observed_ports = host_config.get("PortBindings")
        if not isinstance(expected_ports, list) or not isinstance(observed_ports, dict):
            raise OfflineLaunchError("offline container port inventory unavailable")
        expected_port_targets = {
            str(item["target"]) + "/tcp": str(item["published"])
            for item in expected_ports
        }
        if set(observed_ports) != set(expected_port_targets):
            raise OfflineLaunchError("offline container published port map differs")
        for target, hosts in observed_ports.items():
            if not isinstance(hosts, list) or len(hosts) != 1:
                raise OfflineLaunchError("offline host port binding count differs")
            host_binding = hosts[0]
            if (not isinstance(host_binding, dict)
                    or host_binding.get("HostIp") not in _ALLOWED_IP
                    or str(host_binding.get("HostPort")) != expected_port_targets[target]):
                raise OfflineLaunchError("offline Docker container published nonlocal port")
        expected_mounts = desired.get("volumes", [])
        actual_mounts = detail.get("Mounts")
        if not isinstance(actual_mounts, list) or not isinstance(expected_mounts, list):
            raise OfflineLaunchError("offline container mount inventory unavailable")
        mounted = {entry.get("Destination"): entry for entry in actual_mounts
                   if isinstance(entry, dict) and isinstance(entry.get("Destination"), str)}
        if len(mounted) != len(expected_mounts) or len(actual_mounts) != len(mounted):
            raise OfflineLaunchError("offline Docker container gained unauthorized mounts")
        for item in expected_mounts:
            actual = mounted.get(item.get("target"))
            if not isinstance(actual, dict) or actual.get("Type") != item.get("type"):
                raise OfflineLaunchError("offline Docker container mount differs")
            source_key = "Name" if item["type"] == "volume" else "Source"
            if actual.get(source_key) != item.get("source"):
                raise OfflineLaunchError("offline Docker container mount source differs")
            expected_rw = not bool(item.get("read_only", False))
            if actual.get("RW") is not expected_rw:
                raise OfflineLaunchError("offline Docker mount read-only mode changed")
        if isinstance(desired.get("healthcheck"), dict):
            health = state.get("Health")
            if not isinstance(health, dict) or health.get("Status") != "healthy":
                raise OfflineLaunchError("offline container mandatory healthcheck did not pass")
        results.append({
            "role": role,
            "image_id": ids[role],
            "running": True,
            "health_observed": state.get("Health", {}).get("Status")
            if isinstance(state.get("Health"), dict) else "running_without_healthcheck",
            "loopback_ingress": True,
            "canonical_network_only": True,
            "canonical_mounts_only": True,
        })
    return results


def attest_running_offline(mode: str, archive: Path, overlay_directory: Path, *,
                           expected_receipt_sha256: str,
                           root: Path = host.ROOT) -> dict[str, Any]:
    """Read-only post-start image/container/network/mount admission."""
    artifact = binding.verify_binding(
        mode, archive, overlay_directory,
        expected_receipt_sha256=expected_receipt_sha256, root=root,
    )
    original = binding._original(mode, root)
    if original.get("name") != artifact.get("project"):
        raise OfflineLaunchError("offline application project identity changed")
    ids = {row["service"]: row["image_id"] for row in artifact["images"]}
    containers = _inspect(mode, overlay_directory, root, original, ids)
    return {
        "schema": "skeleton.local-ai.docker.offline-running-containers.v1",
        "status": "four_running_exact_image_containers_not_protected_chat",
        "project": artifact["project"],
        "mode": mode,
        "source_receipt_file_sha256": artifact["source_receipt_file_sha256"],
        "containers": containers,
        "containers_observed": 4,
        "immutable_image_ids_verified": True,
        "all_ingress_loopback_only": True,
        "fresh_state_recovery_qualified": False,
        "guarded_chat_qualified": False,
        "writer_epoch_qualified": False,
        "release_qualified": False,
    }


def launch_fresh_offline(mode: str, archive: Path, overlay_directory: Path, *,
                         expected_receipt_sha256: str,
                         allow_new_app_volumes: bool = False,
                         root: Path = host.ROOT) -> dict[str, Any]:
    """Only explicit fresh installations may start actual writable services.

    A race with another independent Docker client cannot be excluded with
    read-only preflight. Existing state and interrupted startup are managed
    manually; never attempt unsafe automatic rollback or volume pruning.
    """
    if allow_new_app_volumes is not True:
        raise OfflineLaunchError("explicit new application volume creation approval required")
    before = plan_fresh_offline_launch(
        mode, archive, overlay_directory,
        expected_receipt_sha256=expected_receipt_sha256, root=root,
    )
    native = binding.qualify_offline_model(
        mode, archive, overlay_directory,
        expected_receipt_sha256=expected_receipt_sha256,
        root=root,
    )
    if native.get("model_turn_executed") is not True:
        raise OfflineLaunchError("no qualifying real local GGUF generation receipt")
    second = plan_fresh_offline_launch(
        mode, archive, overlay_directory,
        expected_receipt_sha256=expected_receipt_sha256, root=root,
    )
    if second != before:
        raise OfflineLaunchError("offline startup source or fresh-state inventory changed")
    command = _prefix(mode, overlay_directory, root)
    host._run([
        *command, "up", "-d", "--no-build", "--no-recreate", "--pull", "never",
        "--wait", "--wait-timeout", "180", *ROLES,
    ], root=root)
    # Healthcheck success does not attest the guarded chat application.
    inspected = attest_running_offline(
        mode, archive, overlay_directory,
        expected_receipt_sha256=expected_receipt_sha256, root=root,
    )
    try:
        provider = host.live_ai_status(mode, root)
        provider_observed = provider.get("observed") is True
        provider_ready = provider.get("ready") is True
    except host.LocalDockerError:
        provider_observed = False
        provider_ready = False
    return {
        "schema": SCHEMA,
        "status": "offline_containers_started_not_guarded_chat_qualified",
        "project": before["project"],
        "mode": mode,
        "source_receipt_file_sha256": before["source_receipt_file_sha256"],
        "containers": inspected["containers"],
        "containers_started": True,
        "volumes_may_contain_application_writes": True,
        "new_state_recovery_rehearsed": False,
        "native_gguf_one_shot_qualified": True,
        "native_model_sha256": native["model_sha256"],
        "backend_provider_status_observed": provider_observed,
        "backend_provider_available": provider_ready,
        "guarded_chat_qualified": False,
        "independent_reviewer_attested": False,
        "writer_epoch_qualified": False,
        "release_qualified": False,
    }


__all__ = [
    "plan_fresh_offline_launch", "attest_running_offline", "launch_fresh_offline",
]
