"""Reject malformed startup topology before compose or setup is invoked."""

from __future__ import annotations

import json
from importlib import resources

import pytest

from skeleton.app.assembly import parse_manifest


def _payload() -> dict:
    return json.loads(resources.files("skeleton.app").joinpath("manifest.json").read_text())


@pytest.mark.parametrize(
    "selection",
    [
        "backend",
        None,
        {"backend": True},
        ["backend", "backend"],
        ["backend", 42],
        ["backend", None],
        ["backend", " "],
        ["backend", " backend"],
    ],
)
@pytest.mark.parametrize("field", ["default_services", "full_services"])
def test_service_selections_reject_noncanonical_entries(field: str, selection: object) -> None:
    payload = _payload()
    payload["app"][field] = selection
    with pytest.raises(ValueError, match=field):
        parse_manifest(payload)


@pytest.mark.parametrize(
    "edges",
    [
        {"backend": ["skeleton"], "skeleton": ["backend"]},
        {"backend": ["skeleton"], "skeleton": ["mongo"], "mongo": ["backend"]},
        {"frontend": ["backend"], "backend": ["frontend"]},
    ],
)
def test_indirect_dependency_cycles_rejected(edges: dict[str, list[str]]) -> None:
    payload = _payload()
    for service in payload["services"]:
        if service["name"] in edges:
            service["depends_on"] = edges[service["name"]]
    with pytest.raises(ValueError, match="dependency cycle"):
        parse_manifest(payload)


def test_packaged_manifest_has_acyclic_unique_service_selections() -> None:
    manifest = parse_manifest(_payload())
    assert len(set(manifest.default_services)) == len(manifest.default_services)
    assert len(set(manifest.full_services)) == len(manifest.full_services)
