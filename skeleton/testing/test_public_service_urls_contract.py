"""Default and overridden public endpoint contracts for installed startup.

These tests are deterministic URL-contract checks, not device qualification.
"""

from pathlib import Path
from dataclasses import replace

import pytest

from skeleton.app.assembly import load_manifest, public_service_urls


def test_public_service_urls_contains_defaults_without_overrides(tmp_path: Path):
    urls = public_service_urls(tmp_path, manifest=load_manifest(), environ={})
    assert {"frontend", "backend", "skeleton"} <= urls.keys()
    manifest = load_manifest()
    for name in ("frontend", "backend", "skeleton"):
        assert urls[name] == manifest.service(name).public_url


def test_public_service_urls_preserves_unmodified_services(tmp_path: Path):
    manifest = load_manifest()
    urls = public_service_urls(
        tmp_path, manifest=manifest, environ={"FRONTEND_PORT": "31999"}
    )
    assert urls["frontend"].endswith(":31999")
    assert urls["backend"] == manifest.service("backend").public_url
    assert urls["skeleton"] == manifest.service("skeleton").public_url


def test_public_service_urls_rejects_colliding_ports(tmp_path: Path):
    with pytest.raises(ValueError, match="must differ"):
        public_service_urls(
            tmp_path, manifest=load_manifest(),
            environ={"FRONTEND_PORT": "8001", "BACKEND_PORT": "8001"},
        )


@pytest.mark.parametrize("invalid_url", [
    "http://localhost:bad",
    "http://localhost:65536",
    "http://localhost:-1",
])
def test_port_override_rejects_invalid_packaged_endpoint(tmp_path: Path, invalid_url: str):
    manifest = load_manifest()
    services = tuple(
        replace(service, public_url=invalid_url) if service.name == "frontend" else service
        for service in manifest.services
    )
    manifest = replace(manifest, services=services)
    with pytest.raises(ValueError, match="invalid public URL port"):
        public_service_urls(tmp_path, manifest=manifest, environ={"FRONTEND_PORT": "31999"})


@pytest.mark.parametrize("invalid_url", [
    "http://localhost:3000\\n",
    "http://localhost:3000\\t",
    " http://localhost:3000",
    "http://localhost:3000\\\\@remote.example",
    "http://localhost:3000/\\rpath",
])
def test_port_override_rejects_unsafe_packaged_url(tmp_path: Path, invalid_url: str):
    manifest = load_manifest()
    services = tuple(
        replace(service, public_url=invalid_url) if service.name == "frontend" else service
        for service in manifest.services
    )
    with pytest.raises(ValueError, match="unsafe public URL"):
        public_service_urls(
            tmp_path, manifest=replace(manifest, services=services),
            environ={"FRONTEND_PORT": "31999"},
        )


@pytest.mark.parametrize("control", [chr(0), chr(9), chr(10), chr(13), chr(31), chr(127)])
def test_port_override_rejects_control_characters(tmp_path: Path, control: str):
    manifest = load_manifest()
    services = tuple(
        replace(service, public_url="http://localhost:3000/" + control + "ready")
        if service.name == "frontend" else service
        for service in manifest.services
    )
    with pytest.raises(ValueError, match="unsafe public URL"):
        public_service_urls(
            tmp_path, manifest=replace(manifest, services=services),
            environ={"FRONTEND_PORT": "31999"},
        )


@pytest.mark.parametrize("invalid_url", [
    "http://localhost:bad",
    "http://localhost:65536",
    "http://localhost:3000?token=secret",
    "http://user:password@localhost:3000",
    "http://remote.example:3000",
    "http://localhost:3000/\\\\unsafe",
])
def test_default_public_url_fails_closed_without_override(tmp_path: Path, invalid_url: str):
    manifest = load_manifest()
    services = tuple(
        replace(service, public_url=invalid_url) if service.name == "frontend" else service
        for service in manifest.services
    )
    with pytest.raises(ValueError, match="public URL"):
        public_service_urls(tmp_path, manifest=replace(manifest, services=services), environ={})
