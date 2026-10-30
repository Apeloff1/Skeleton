"""Contract checks for indexed original studio briefs and the existing compiler."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import (
    SECTIONS, StudioEcosystemError, catalog_index, list_blueprints,
    read_blueprint, compile_preview,
)


def test_catalog_has_linked_original_vertical_slices():
    records = catalog_index()
    assert len(records) == len(records)
    assert len({(item["genre"], item["biome"]) for item in records}) == len(records)
    assert len({item["id"] for item in records}) == len(records)
    assert len(SECTIONS) == 8
    for item in records:
        parts = read_blueprint(item["id"])
        assert set(parts) == set(SECTIONS)
        assert parts["verification"]["release_certified"] is False
        assert parts["narrative"]["release_certified"] is False


def test_can_filter_and_compile_offline_playable_proof():
    record = list_blueprints(genre="puzzle_expedition")[0]
    assert all(item["genre"] == "puzzle_expedition"
               for item in list_blueprints(genre="puzzle_expedition"))
    assert all(item["biome"] == record["biome"]
               for item in list_blueprints(biome=record["biome"]))
    with pytest.raises(PermissionError):
        compile_preview(record["id"], authorized=False)
    result = compile_preview(record["id"], authorized=True)
    assert result.proof.final_state.status == "won"
    assert result.playable.world_digest == result.world.digest


def test_rejects_unregistered_id_and_ambiguous_json(tmp_path: Path):
    with pytest.raises(StudioEcosystemError):
        read_blueprint("../escape")
    with pytest.raises(StudioEcosystemError):
        read_blueprint("unsafe_unknown")
    root = tmp_path / "catalog"
    root.mkdir()
    (root / "index.json").write_text('{"schema":"x","schema":"y"}')
    with pytest.raises(StudioEcosystemError):
        catalog_index(root=root)


def test_rejects_broken_cross_document_identity(tmp_path: Path):
    from shutil import copytree
    from skeleton.ai.game_builder.studio_ecosystem_catalog import ROOT
    source = catalog_index()[0]
    root = tmp_path / "catalog"
    root.mkdir()
    (root / "index.json").write_bytes((ROOT / "index.json").read_bytes())
    copytree(ROOT / source["id"], root / source["id"])
    audio = root / source["id"] / "audio.json"
    payload = json.loads(audio.read_text())
    payload["release_certified"] = True
    audio.write_text(json.dumps(payload))
    with pytest.raises(StudioEcosystemError):
        read_blueprint(source["id"], root=root)
