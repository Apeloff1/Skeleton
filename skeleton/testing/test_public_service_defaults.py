"""Public service endpoints must remain available with default host ports.

These are source-level contract tests; they do not certify a live installation.
"""
from dataclasses import replace
from pathlib import Path

import pytest

from skeleton.app.assembly import load_manifest, public_service_urls


def test_default_public_endpoints_are_returned_without_port_overrides(tmp_path: Path):
    manifest = load_manifest()
    urls = public_service_urls(tmp_path, manifest=manifest, environ={})
    for name in ("frontend", "backend", "skeleton"):
        assert urls[name] == manifest.service(name).public_url
        assert urls[name]


def test_single_override_does_not_hide_other_services(tmp_path: Path):
    manifest = load_manifest()
    urls = public_service_urls(tmp_path, manifest=manifest, environ={"FRONTEND_PORT": "31999"})
    assert urls["frontend"].endswith(":31999")
    for name in ("backend", "skeleton"):
        assert urls[name] == manifest.service(name).public_url


def test_port_collision_remains_fail_closed(tmp_path: Path):
    with pytest.raises(ValueError, match="must differ"):
        public_service_urls(
            tmp_path, manifest=load_manifest(),
            environ={"FRONTEND_PORT": "8001", "BACKEND_PORT": "8001"},
        )


def test_missing_public_url_is_not_exposed(tmp_path: Path):
    manifest = load_manifest()
    services = tuple(
        replace(service, public_url="") if service.name == "frontend" else service
        for service in manifest.services
    )
    urls = public_service_urls(tmp_path, manifest=replace(manifest, services=services), environ={})
    assert "frontend" not in urls
    assert urls["backend"] == manifest.service("backend").public_url


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("CHROMA_PORT", "3000"),
        ("CHROMA_PORT", "8001"),
        ("CHROMA_PORT", "8010"),
        ("CHROMA_PORT", "27017"),
        ("FRONTEND_PORT", "8000"),
        ("BACKEND_PORT", "8000"),
        ("SKELETON_PORT", "8000"),
        ("MONGO_PORT", "8000"),
    ],
)
def test_chroma_host_port_collisions_fail_closed(tmp_path: Path, key: str, value: str):
    with pytest.raises(ValueError, match="must differ"):
        public_service_urls(tmp_path, manifest=load_manifest(), environ={key: value})


def test_independent_chroma_port_override_is_visible(tmp_path: Path):
    manifest = load_manifest()
    urls = public_service_urls(tmp_path, manifest=manifest, environ={"CHROMA_PORT": "31998"})
    assert urls["chroma"].endswith(":31998")
    for name in ("frontend", "backend", "skeleton"):
        assert urls[name] == manifest.service(name).public_url
