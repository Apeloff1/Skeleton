"""Jeeves and CLI parity for source-leased authored revisions."""
import json

import pytest

from skeleton.ai.agents.jeeves.studio_walk_tool import (
    AUTHOR_REVISION_REQUEST_SCHEMA, execute_author_revision_tool,
)
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

PROJECT = "studio_arena_fighting_glacial_fjord"

def _request():
    docs = read_blueprint(PROJECT)
    return {"schema": AUTHOR_REVISION_REQUEST_SCHEMA, "project_id": PROJECT,
            "expected_source_digest": audit_canon_source(docs, authorized=True)["source_digest"],
            "edits": [{"section": "narrative", "path": ["premise"],
                       "value": "The independent archive needs a new public audit before the thaw."}]}

def test_jeeves_revision_preview_is_typed_and_operator_gated():
    req = _request()
    with pytest.raises(PermissionError):
        execute_author_revision_tool(req, authorized=False)
    result = execute_author_revision_tool(req, authorized=True)
    assert result["detail"]["revised_source_digest"] != req["expected_source_digest"]
    assert result["file_write_performed"] is False
    assert result["impact"]["new_save_required"] is True
    assert result["impact"]["changed_path_count"] == 1
    assert result["release_certified"] is False
    with pytest.raises(StudioQuestError):
        execute_author_revision_tool({**req, "extra": True}, authorized=True)

def test_cli_revision_writes_source_html_and_receipt(tmp_path, capsys):
    from scripts.studio_ecosystem_cli import main
    req = _request()
    req["schema"] = "skeleton.game_builder.studio_author_revision_request.v1"
    output = tmp_path / "original-revision"
    assert main(["--project", PROJECT, "--author-revision",
                 "--revision-request", json.dumps(req),
                 "--output", str(output)]) == 0
    response = json.loads(capsys.readouterr().out)
    assert response["receipt"]["canon_consistent"] is True
    assert (output / "source.json").exists()
    assert (output / "story.html").exists()
    assert (output / "receipt.json").exists()


def test_cli_replays_and_audits_persisted_revised_story(tmp_path, capsys):
    from scripts.studio_ecosystem_cli import main
    from skeleton.ai.game_builder.studio_ecosystem_author_revision import (
        REVISION_SCHEMA, preview_canon_revision, write_revision_bundle,
    )
    docs = read_blueprint(PROJECT)
    req = _request()
    req["schema"] = REVISION_SCHEMA
    source, html, receipt = preview_canon_revision(docs, req, authorized=True)
    directory = tmp_path / "revision"
    write_revision_bundle(directory, source, html, receipt)
    assert main(["--project", PROJECT, "--audit-canon",
                 "--revision-source", str(directory)]) == 0
    audit = json.loads(capsys.readouterr().out)
    assert audit["source_digest"] == receipt["revised_source_digest"]
    assert main(["--project", PROJECT, "--play-walk",
                 "--revision-source", str(directory),
                 "--walk-events", "[]"]) == 0
    played = json.loads(capsys.readouterr().out)
    assert played["source_digest"] == receipt["revised_source_digest"]


def test_cli_revision_impact_from_registered_to_persisted_source(tmp_path, capsys):
    from scripts.studio_ecosystem_cli import main
    from skeleton.ai.game_builder.studio_ecosystem_author_revision import (
        REVISION_SCHEMA, preview_canon_revision, write_revision_bundle,
    )
    docs = read_blueprint(PROJECT)
    req = _request()
    req["schema"] = REVISION_SCHEMA
    revised, html, receipt = preview_canon_revision(docs, req, authorized=True)
    out = tmp_path / "revised"
    write_revision_bundle(out, revised, html, receipt)
    assert main(["--project", PROJECT, "--revision-impact",
                 "--revision-compare-source", str(out)]) == 0
    impact = json.loads(capsys.readouterr().out)
    assert impact["new_save_required"] is True
    assert impact["changed_paths"][0]["path"] == ["narrative", "premise"]
