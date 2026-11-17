"""Adversarial tests for the rendered local-only Compose application boundary.

Static fixture values are synthetic. No Docker daemon, network, weights or
application state is touched by these tests.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from scripts.local_ai_compose_boundary import (
    ComposeBoundaryError, validate_compose_boundary,
)
from scripts import local_ai_docker as host
from skeleton.testing.test_docker_local_ai import _fake_config


def _valid(tmp_path: Path) -> dict:
    return _fake_config(tmp_path)


def test_full_boundary_accepts_canonical_local_stack(tmp_path: Path) -> None:
    observed = validate_compose_boundary(_valid(tmp_path))
    assert observed["browser_destinations"] == "loopback_only"
    assert observed["database_transport"] == "authenticated_internal"
    assert observed["state_mounts"] == "canonical_named_volumes"
    assert observed["actual_network_qualified"] is False
    assert observed["application_recovery_qualified"] is False


def test_profiled_chroma_can_be_absent(tmp_path: Path) -> None:
    config = _valid(tmp_path)
    config["services"].pop("chroma")
    assert validate_compose_boundary(config)["chroma_profile"] == "absent"


@pytest.mark.parametrize("name", ["mongo", "backend", "frontend", "skeleton", "chroma"])
@pytest.mark.parametrize("host_ip", ["0.0.0.0", "::", "", None, "192.0.2.22"])
def test_every_service_refuses_nonloopback_port(
    tmp_path: Path, name: str, host_ip: str | None,
) -> None:
    config = _valid(tmp_path)
    config["services"][name]["ports"][0]["host_ip"] = host_ip
    with pytest.raises(ComposeBoundaryError, match="non-loopback"):
        validate_compose_boundary(config)


@pytest.mark.parametrize("name", ["mongo", "backend", "frontend", "skeleton", "chroma"])
def test_every_service_refuses_multiple_port_exposure(tmp_path: Path, name: str) -> None:
    config = _valid(tmp_path)
    config["services"][name]["ports"].append({"host_ip": "127.0.0.1", "target": 99, "published": 99})
    with pytest.raises(ComposeBoundaryError, match="exactly one"):
        validate_compose_boundary(config)


@pytest.mark.parametrize("name", ["mongo", "backend", "frontend", "skeleton", "chroma"])
@pytest.mark.parametrize("key,value", [
    ("privileged", True), ("network_mode", "host"), ("ipc", "host"),
    ("cap_add", ["SYS_ADMIN"]), ("extra_hosts", ["shadow:127.0.0.1"]),
])
def test_service_privilege_expansion_is_denied(
    tmp_path: Path, name: str, key: str, value: object,
) -> None:
    config = _valid(tmp_path)
    config["services"][name][key] = value
    with pytest.raises(ComposeBoundaryError, match="privileged"):
        validate_compose_boundary(config)


@pytest.mark.parametrize("url", [
    "https://example.invalid/api", "http://10.1.2.3:8001",
    "http://localhost:8002", "http://localhost:8001/?private=1",
    "http://alice:token@localhost:8001", "http://localhost:8001/path",
    "file:///etc/passwd", "http://[::]:8001",
])
def test_frontend_remote_or_mutated_backend_urls_are_denied(tmp_path: Path, url: str) -> None:
    config = _valid(tmp_path)
    config["services"]["frontend"]["environment"]["EXPO_PUBLIC_BACKEND_URL"] = url
    config["services"]["frontend"]["build"]["args"]["EXPO_PUBLIC_BACKEND_URL"] = url
    with pytest.raises(ComposeBoundaryError, match="frontend"):
        validate_compose_boundary(config)


def test_frontend_runtime_must_match_baked_url(tmp_path: Path) -> None:
    config = _valid(tmp_path)
    config["services"]["frontend"]["build"]["args"]["EXPO_PUBLIC_BACKEND_URL"] = "http://127.0.0.1:8001"
    with pytest.raises(ComposeBoundaryError, match="origins differ"):
        validate_compose_boundary(config)


def test_frontend_requires_actual_rendered_host_port(tmp_path: Path) -> None:
    config = _valid(tmp_path)
    config["services"]["backend"]["ports"][0]["published"] = "18001"
    with pytest.raises(ComposeBoundaryError, match="frontend"):
        validate_compose_boundary(config)


def test_frontend_can_use_matching_local_nondefault_ports(tmp_path: Path) -> None:
    config = _valid(tmp_path)
    config["services"]["backend"]["ports"][0]["published"] = "18001"
    config["services"]["skeleton"]["ports"][0]["published"] = "18010"
    for key, origin in (
        ("EXPO_PUBLIC_BACKEND_URL", "http://127.0.0.1:18001"),
        ("EXPO_PUBLIC_SKELETON_URL", "http://localhost:18010"),
    ):
        config["services"]["frontend"]["environment"][key] = origin
        config["services"]["frontend"]["build"]["args"][key] = origin
    assert validate_compose_boundary(config)["browser_destinations"] == "loopback_only"


@pytest.mark.parametrize("uri", [
    "mongodb://mongo:27017/skeleton",
    "mongodb://user@mongo:27017/skeleton?authSource=admin",
    "mongodb://user:password@db.invalid:27017/skeleton?authSource=admin",
    "mongodb://user:password@mongo:27018/skeleton?authSource=admin",
    "mongodb://user:password@mongo:27017/skeleton",
    "mongodb+srv://user:password@mongo/skeleton?authSource=admin",
])
def test_mongo_requires_authenticated_service_local_transport(
    tmp_path: Path, uri: str,
) -> None:
    config = _valid(tmp_path)
    config["services"]["backend"]["environment"]["MONGO_URL"] = uri
    with pytest.raises(ComposeBoundaryError, match="Mongo connection"):
        validate_compose_boundary(config)


@pytest.mark.parametrize("name,target", [
    ("mongo", "/data/db"), ("mongo", "/data/configdb"),
    ("backend", "/app/data"), ("skeleton", "/app/data"),
    ("chroma", "/chroma/chroma"),
])
def test_authoritative_data_cannot_be_redirected_or_lost(
    tmp_path: Path, name: str, target: str,
) -> None:
    config = _valid(tmp_path)
    volumes = config["services"][name]["volumes"]
    for volume in volumes:
        if volume["target"] == target:
            volume["type"] = "bind"
            volume["source"] = str(tmp_path / "host-mount")
    with pytest.raises(ComposeBoundaryError, match="state volume"):
        validate_compose_boundary(config)


def test_chroma_cannot_start_without_explicit_full_profile(tmp_path: Path) -> None:
    config = _valid(tmp_path)
    config["services"]["chroma"]["profiles"] = []
    with pytest.raises(ComposeBoundaryError, match="Chroma recovery hold"):
        validate_compose_boundary(config)


def test_mongo_image_cannot_be_mutable_tag(tmp_path: Path) -> None:
    config = _valid(tmp_path)
    config["services"]["mongo"]["image"] = "mongo:latest"
    with pytest.raises(ComposeBoundaryError, match="digest"):
        validate_compose_boundary(config)


def test_backend_cannot_redirect_local_engine(tmp_path: Path) -> None:
    config = _valid(tmp_path)
    config["services"]["backend"]["environment"]["SKELETON_INTERNAL_URL"] = "http://elsewhere.invalid"
    with pytest.raises(ComposeBoundaryError, match="backend-to-engine"):
        validate_compose_boundary(config)


def test_backend_cannot_disable_local_only_model(tmp_path: Path) -> None:
    config = _valid(tmp_path)
    config["services"]["backend"]["environment"]["JEEVES_LOCAL_ONLY"] = "0"
    with pytest.raises(ComposeBoundaryError, match="backend-to-engine"):
        validate_compose_boundary(config)


def test_full_boundary_is_enforced_by_operator_without_leaking_credentials(
    tmp_path: Path,
) -> None:
    config = _valid(tmp_path)
    config["services"]["mongo"]["ports"][0]["host_ip"] = "0.0.0.0"
    with pytest.raises(host.LocalDockerError, match="boundary admission failed") as err:
        host._validate_config("cpu", config)
    assert "synthetic_custody_value" not in str(err.value)
    assert "mongodb:" not in str(err.value)
