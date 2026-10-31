"""Source-leased authored revisions, playable handoff and negative paths."""
from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_author_revision import (
    REVISION_SCHEMA, preview_canon_revision, write_revision_bundle,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

PROJECT = "studio_arena_fighting_glacial_fjord"

def request(docs, edits=None):
    return {"schema": REVISION_SCHEMA, "project_id": PROJECT,
            "expected_source_digest": audit_canon_source(docs, authorized=True)["source_digest"],
            "edits": edits if edits is not None else [
                {"section": "narrative", "path": ["premise"],
                 "value": "Miro Rook must document the fjord's contested records before the thaw."},
                {"section": "narrative", "path": ["plot_beats", 0, "goal"],
                 "value": "Verify an independent account of the thaw and its witnesses."},
            ]}

def test_revision_compiles_and_persists_original_interactive_story(tmp_path):
    docs = read_blueprint(PROJECT)
    snapshot = deepcopy(docs)
    revised, html, receipt = preview_canon_revision(docs, request(docs), authorized=True)
    assert docs == snapshot
    assert revised["narrative"]["premise"] != docs["narrative"]["premise"]
    assert receipt["revised_source_digest"] != receipt["base_source_digest"]
    assert receipt["canon_consistent"] is True
    assert receipt["release_certified"] is False
    assert b"Original interactive quest" in html
    assert b"Authored goal:" in html
    assert b"premise" in html
    assert b"Miro Rook must document" in html
    out = tmp_path / "revision"
    write_revision_bundle(out, revised, html, receipt)
    assert json.loads((out / "source.json").read_text()) == revised
    assert json.loads((out / "receipt.json").read_text()) == receipt
    assert (out / "story.html").read_bytes() == html
    with pytest.raises(StudioQuestError):
        write_revision_bundle(out, revised, html, receipt)

def test_revision_rejects_unauthorized_stale_and_protected_fields():
    docs = read_blueprint(PROJECT)
    req = request(docs)
    with pytest.raises(PermissionError):
        preview_canon_revision(docs, req, authorized=False)
    with pytest.raises(StudioQuestError):
        preview_canon_revision(docs, {**req, "expected_source_digest": "0" * 64}, authorized=True)
    for edit in [
        {"section": "narrative", "path": ["endings", 0, "requires"], "value": "win"},
        {"section": "cast", "path": ["protagonist", "id"], "value": "attacker"},
        {"section": "quest", "path": ["stage_graph", 0, "reward"], "value": "fake"},
        {"section": "scene", "path": ["episode_plan", True, "site"], "value": "invalid"},
    ]:
        with pytest.raises(StudioQuestError):
            preview_canon_revision(docs, request(docs, [edit]), authorized=True)

def test_revision_rejects_duplicate_noop_malformed_and_contradictory_edits():
    docs = read_blueprint(PROJECT)
    edits = request(docs)["edits"]
    with pytest.raises(StudioQuestError):
        preview_canon_revision(docs, request(docs, edits + edits), authorized=True)
    with pytest.raises(StudioQuestError):
        preview_canon_revision(docs, request(docs, [
            {"section": "narrative", "path": ["premise"],
             "value": docs["narrative"]["premise"]}]), authorized=True)
    with pytest.raises(StudioQuestError):
        preview_canon_revision(docs, request(docs, [
            {"section": "scene", "path": ["episode_plan", 0, "dialogue_hook"],
             "value": "unlisted_person"}]), authorized=True)
    for bad in ["x\nunsafe", "\ud800", "x" * 513]:
        with pytest.raises(StudioQuestError):
            preview_canon_revision(docs, request(docs, [
                {"section": "narrative", "path": ["premise"], "value": bad}
            ]), authorized=True)
