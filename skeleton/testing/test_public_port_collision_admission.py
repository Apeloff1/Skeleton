"""Host-published port admission must reject collisions before probing services."""

from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.app.assembly import load_manifest, public_service_urls, runtime_manifest


@pytest.mark.parametrize(
    "overrides",
    [
        {"CHROMA_PORT": "8001"},
        {"BACKEND_PORT": "8000"},
        {"CHROMA_PORT": "3000"},
        {"CHROMA_PORT": "8010"},
        {"CHROMA_PORT": "27017"},
        {"FRONTEND_PORT": "8000"},
    ],
)
def test_chroma_collision_rejected_by_runtime_and_public_urls(
    tmp_path: Path, overrides: dict[str, str]
) -> None:
    manifest = load_manifest()
    with pytest.raises(ValueError, match="must differ"):
        runtime_manifest(manifest, root=tmp_path, environ=overrides)
    with pytest.raises(ValueError, match="must differ"):
        public_service_urls(tmp_path, manifest=manifest, environ=overrides)


def test_distinct_custom_chroma_port_is_admitted(tmp_path: Path) -> None:
    manifest = load_manifest()
    urls = public_service_urls(tmp_path, manifest=manifest, environ={"CHROMA_PORT": "18000"})
    assert urls["chroma"].endswith(":18000")
    assert urls["backend"] == manifest.service("backend").public_url


def test_default_published_ports_remain_distinct(tmp_path: Path) -> None:
    urls = public_service_urls(tmp_path, manifest=load_manifest(), environ={})
    assert len(urls) == 4
    assert len(set(urls.values())) == 4


@pytest.mark.parametrize(
    "unsafe_url",
    [
        "http://operator:secret@localhost:8001",
        "http://localhost:8001/?token=private",
        "http://localhost:8001/#fragment",
    ],
)
def test_port_override_rejects_credentialed_or_decorated_manifest_urls(
    tmp_path: Path, unsafe_url: str
) -> None:
    from dataclasses import replace

    manifest = load_manifest()
    services = tuple(
        replace(service, public_url=unsafe_url) if service.name == "backend" else service
        for service in manifest.services
    )
    hostile = replace(manifest, services=services)
    with pytest.raises(ValueError, match="non-local public URL"):
        runtime_manifest(hostile, root=tmp_path, environ={"BACKEND_PORT": "18001"})
    with pytest.raises(ValueError, match="non-local public URL"):
        public_service_urls(tmp_path, manifest=hostile, environ={"BACKEND_PORT": "18001"})
