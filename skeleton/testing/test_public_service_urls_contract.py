"""Default and overridden public endpoint contracts for installed startup.

These tests are deterministic URL-contract checks, not device qualification.
"""

from pathlib import Path

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
