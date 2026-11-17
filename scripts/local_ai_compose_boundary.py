"""Fail-closed admission for the *entire* local-Jeeves Compose boundary.

Inspect effective Docker Compose JSON, not source YAML or guessed defaults.
Never include interpolated credentials, URI text or private mount paths in errors.
This is configuration evidence only, not a live-network or recovery attestation.
"""
from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

_LOOPBACK = frozenset(("127.0.0.1", "::1"))
_PORTS = {"skeleton": 8001, "backend": 8001, "mongo": 27017, "chroma": 8000}
_SHA_IMAGE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
_STATE_MOUNTS = {
    "skeleton": {"/app/data": "skeleton_data"},
    "backend": {"/app/data": "backend_data"},
    "mongo": {"/data/db": "mongo_data", "/data/configdb": "mongo_config"},
    "chroma": {"/chroma/chroma": "chroma_data"},
}


class ComposeBoundaryError(ValueError):
    """Effective Compose changes crossed a local-only admission boundary."""


def _service(services: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    service = services.get(name)
    if not isinstance(service, dict):
        raise ComposeBoundaryError("canonical service boundary is missing")
    if (service.get("privileged") is True or service.get("network_mode")
            or service.get("pid") in ("host", "service:docker")
            or service.get("ipc") == "host" or service.get("cap_add")
            or service.get("extra_hosts")):
        raise ComposeBoundaryError("service has a privileged or redirected boundary")
    return service


def _port(service: Mapping[str, Any], target: int | None) -> int:
    ports = service.get("ports")
    if not isinstance(ports, list) or len(ports) != 1:
        raise ComposeBoundaryError("service must publish exactly one loopback port")
    p = ports[0]
    if not isinstance(p, dict) or p.get("host_ip") not in _LOOPBACK:
        raise ComposeBoundaryError("service publishes a non-loopback ingress")
    if p.get("protocol", "tcp") != "tcp":
        raise ComposeBoundaryError("non-TCP service ingress cannot be admitted")
    for key in ("target", "published"):
        value = p.get(key)
        if type(value) not in (int, str) or not str(value).isdecimal():
            raise ComposeBoundaryError("service port must be an explicit integer")
        if not 1 <= int(value) <= 65535:
            raise ComposeBoundaryError("service port is outside the TCP range")
    if target is not None and int(p["target"]) != target:
        raise ComposeBoundaryError("canonical service target port changed")
    return int(p["published"])


def _state_volume(service: Mapping[str, Any], name: str) -> None:
    volumes = service.get("volumes")
    if not isinstance(volumes, list):
        raise ComposeBoundaryError("canonical persistent state volume is unavailable")
    for target, source_suffix in _STATE_MOUNTS[name].items():
        mounted = [m for m in volumes if isinstance(m, dict) and m.get("target") == target]
        if len(mounted) != 1:
            raise ComposeBoundaryError("canonical state mount was removed or duplicated")
        volume = mounted[0]
        source = volume.get("source")
        if (volume.get("type") != "volume" or volume.get("read_only") is True
                or not isinstance(source, str)
                or not (source == source_suffix or source.endswith("_" + source_suffix))):
            raise ComposeBoundaryError("canonical writable state volume was redirected")


def _environment(service: Mapping[str, Any]) -> Mapping[str, Any]:
    env = service.get("environment")
    if not isinstance(env, dict):
        raise ComposeBoundaryError("service environment was not resolved")
    return env


def _mongodb_uri(value: object) -> None:
    if not isinstance(value, str) or len(value) > 8192:
        raise ComposeBoundaryError("Mongo connection is not authenticated")
    try:
        parsed = urlsplit(value)
        options = parse_qs(parsed.query, keep_blank_values=True)
        allowed = (parsed.scheme == "mongodb" and parsed.hostname == "mongo"
                   and parsed.port == 27017 and not parsed.fragment
                   and bool(unquote(parsed.username or ""))
                   and bool(unquote(parsed.password or ""))
                   and len(options.get("authSource", [])) == 1
                   and bool(options["authSource"][0]))
    except (ValueError, TypeError):
        allowed = False
    if not allowed:
        raise ComposeBoundaryError("Mongo connection must use authenticated internal service")


def _browser_url(value: object, port: int) -> None:
    if not isinstance(value, str) or len(value) > 2048:
        raise ComposeBoundaryError("frontend API destination is unavailable")
    try:
        url = urlsplit(value)
        allowed = (url.scheme == "http" and url.hostname in ("localhost", *_LOOPBACK)
                   and url.port == port and url.username is None
                   and url.password is None and not url.query and not url.fragment
                   and url.path in ("", "/"))
    except (ValueError, TypeError):
        allowed = False
    if not allowed:
        raise ComposeBoundaryError("frontend may reference only the published local API")


def validate_compose_boundary(topology: Mapping[str, Any]) -> dict[str, object]:
    """Verify local browser/engine ingress and durable authority; no side effects."""
    if not isinstance(topology, dict) or not isinstance(topology.get("services"), dict):
        raise ComposeBoundaryError("rendered Compose service map is unavailable")
    services = topology["services"]
    expected = set(_PORTS) if "chroma" in services else set(_PORTS) - {"chroma"}
    if set(services) != expected:
        raise ComposeBoundaryError("Compose service topology is not canonical")
    nodes = {name: _service(services, name) for name in expected}
    published = {
        name: _port(service, _PORTS.get(name))
        for name, service in nodes.items()
    }
    # Frontend's container port can be configured independently.
    _port(nodes["frontend"], None) if "frontend" in nodes else None
    for name, service in nodes.items():
        _state_volume(service, name)
    for name in ("mongo", "chroma"):
        if name in nodes and not _SHA_IMAGE.fullmatch(str(nodes[name].get("image", ""))):
            raise ComposeBoundaryError("database image must be SHA-256 digest-pinned")
    if "chroma" in nodes and nodes["chroma"].get("profiles") != ["full"]:
        raise ComposeBoundaryError("Chroma recovery hold requires explicit optional profile")
    mongo = _environment(nodes["mongo"])
    if not str(mongo.get("MONGO_INITDB_ROOT_USERNAME", "")).strip() or not str(
        mongo.get("MONGO_INITDB_ROOT_PASSWORD", "")
    ).strip():
        raise ComposeBoundaryError("Mongo root authentication is unavailable")
    _mongodb_uri(_environment(nodes["backend"]).get("MONGO_URL"))
    _mongodb_uri(_environment(nodes["skeleton"]).get("SKL_MONGO_URI"))
    backend = _environment(nodes["backend"])
    if (backend.get("SKELETON_INTERNAL_URL") != "http://skeleton:8001"
            or backend.get("JEEVES_LOCAL_ONLY") != "1"
            or backend.get("JEEVES_PRIMARY_MODEL_ID") != "jeeves"
            or not str(backend.get("SKL_ENGINE_SERVICE_TOKEN", "")).strip()):
        raise ComposeBoundaryError("backend-to-engine local-only service fence differs")
    frontend = _environment(nodes["frontend"])
    build = nodes["frontend"].get("build")
    args = build.get("args") if isinstance(build, dict) else None
    if not isinstance(args, dict):
        raise ComposeBoundaryError("frontend build destinations are unverified")
    for key, port in (("EXPO_PUBLIC_BACKEND_URL", published["backend"]),
                      ("EXPO_PUBLIC_SKELETON_URL", published["skeleton"])):
        _browser_url(frontend.get(key), port)
        if frontend.get(key) != args.get(key):
            raise ComposeBoundaryError("frontend build and runtime API origins differ")
    return {
        "browser_destinations": "loopback_only",
        "database_transport": "authenticated_internal",
        "state_mounts": "canonical_named_volumes",
        "chroma_profile": "optional" if "chroma" in nodes else "absent",
        "actual_network_qualified": False,
        "application_recovery_qualified": False,
    }
