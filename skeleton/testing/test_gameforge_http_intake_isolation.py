"""HTTP GameForge intake cannot materialize arbitrary server files."""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from skeleton.testing.test_gameforge_http_e2e import _post, client


@pytest.mark.parametrize("field,value", [
    ("project_root", "output/unrequested"),
    ("out", "output/unrequested"),
    ("overwrite", True),
])
def test_intake_rejects_server_disk_parameters(client, field, value):
    result = _post(client, "/gameforge/intake", {
        "answers": {"genre": "rpg"}, field: value,
    })
    assert result.status_code == 422, result.text


def test_in_memory_intake_still_produces_verifiable_source_hashes(client):
    from skeleton.forge.source_manifest import source_manifest

    result = _post(client, "/gameforge/intake", {
        "answers": {"genre": "rpg"}, "include_files": True,
    })
    assert result.status_code == 200, result.text
    payload = result.json()
    assert payload["source_manifest"] == source_manifest(payload["files"])
    assert payload["project"] is None
