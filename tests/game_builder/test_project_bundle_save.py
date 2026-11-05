import pytest

from skeleton.ai.game_builder.project_bundle import project_save as ps
from skeleton.ai.game_builder.project_bundle.manifest import BundleError
from skeleton.kernel.game_save_plane import GameSavePlane
from skeleton.persistence.game_save_sqlite import SqliteCheckpointStore, open_game_save_db

from .conftest import edit


def test_save_and_load_roundtrip(ws, saver):
    m = saver.save_project(ws, "hero")
    v = saver.load("hero")
    assert m.sequence == 1 and v.manifest == m
    assert v.files["project.json"] == ws.read("current", "hero", "project.json")["content"]
    assert m.file_map() == {f.path: f.sha256 for f in ws.files("current", "hero")}


def test_large_file_is_chunked_and_versions_are_sequences(ws, saver):
    edit(ws, "hero", "notes/big.md", "x" * (ps.CHUNK_CHARS * 2 + 5))
    m1 = saver.save_project(ws, "hero")
    _, receipts = saver.plane.restore(ps.slot_for("hero"))
    assert receipts.page(chunk_id="notes/big.md#2").total == 1
    edit(ws, "hero", "notes/big.md", "small")
    m2 = saver.save_project(ws, "hero", label="trimmed")
    assert (m1.sequence, m2.sequence) == (1, 2) and m2.label == "trimmed"
    assert saver.load("hero", sequence=1).files["notes/big.md"].startswith("xxx")


def test_sqlite_store_persists_across_reopen(ws, tmp_path):
    db = str(tmp_path / "saves.db")
    s1 = ps.ProjectSaver(GameSavePlane(store=SqliteCheckpointStore(open_game_save_db(db))))
    m = s1.save_project(ws, "hero")
    s2 = ps.ProjectSaver(GameSavePlane(store=SqliteCheckpointStore(open_game_save_db(db))))
    assert s2.load("hero").manifest.content_digest == m.content_digest
    assert s2.next_sequence("hero") == 2


def test_restore_to_workspace_uses_review_flow(ws, saver):
    saver.save_project(ws, "hero")
    edit(ws, "hero", "game/readme.md", "# changed\n")
    edit(ws, "hero", "notes/extra.md", "new")
    with pytest.raises(PermissionError):
        saver.restore_to_workspace(ws, "hero", sequence=1, human_approved=False, authorized=True)
    out = saver.restore_to_workspace(ws, "hero", sequence=1, human_approved=True, authorized=True)
    assert out["written"] == ["game/readme.md"] and out["not_removed"] == ["notes/extra.md"]
    assert ws.read("current", "hero", "game/readme.md")["content"].startswith("# Original game")


def test_reserved_sections_and_passthrough(saver):
    with pytest.raises(BundleError):
        saver.save_files("hero", "platformer", {}, extra_sections={"files": {}})
    saver.save_files("hero", "platformer", {"a.md": "a"}, extra_sections={"gameplay": {"hp": 3}})
    assert saver.load("hero").sections["gameplay"] == {"hp": 3}


def test_missing_version_and_tampered_chunk(saver):
    with pytest.raises(BundleError):
        saver.load("ghost")
    sections, receipts = ps.build_state("hero", "platformer", {"a.md": "abc"})
    sections["files"]["a.md"]["sha256"] = "0" * 64
    with pytest.raises(BundleError):
        ps.files_from_state(sections, receipts)
