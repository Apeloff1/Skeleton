"""Persistence owners share paths without writing during path resolution."""
from pathlib import Path

from skeleton.organism import paths


def test_all_state_paths_resolve_beneath_the_selected_root(tmp_path):
    names = {
        "quality_path": "quality.jsonl",
        "state_path": "state.json",
        "galaxy_path": "galaxy.json",
        "kv_path": "kv.json",
        "ledger_path": "ledger.jsonl",
        "helix_sense_path": "helix_sense.jsonl",
        "helix_snap_path": "helix_snap.jsonl",
    }
    for helper, filename in names.items():
        assert getattr(paths, helper)(tmp_path) == tmp_path / "organism" / filename
        assert getattr(paths, helper)() == Path(".skeleton/organism") / filename
    assert paths.organism_root(tmp_path) == paths.organism_dir(tmp_path)
    assert not (tmp_path / "organism").exists()


def test_galaxy_shelf_roundtrip_keeps_roots_isolated(tmp_path):
    from skeleton.distributed.galaxy.system import GalaxySystem
    from skeleton.distributed.galaxy import shelf

    original = GalaxySystem()
    original.pulses = 7
    shelf.save(original, root=tmp_path / "first")
    restored = GalaxySystem()
    assert shelf.load(restored, root=tmp_path / "second") == {"loaded": 0}
    assert shelf.load(restored, root=tmp_path / "first")["loaded"] == 1
    assert restored.pulses == 7


def test_ledger_and_helix_consumers_import_with_shared_paths():
    from skeleton.organism import helix, ledger, shelf

    assert helix.helix_sense_path is paths.helix_sense_path
    assert ledger.ledger_path is paths.ledger_path
    assert shelf.state_path is paths.state_path
