"""Exclusive private dialogue handoff export, import and tamper rejection."""
from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_dialogue_handoff import (
    HANDOFF_SCHEMA, export_dialogue_handoff, import_dialogue_handoff,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

PROJECT = "studio_arena_fighting_glacial_fjord"
ACTION = ["investigate", "Document fracturing ice without entering restricted ground"]


def test_dialogue_handoff_roundtrip_preserves_source_and_private_receipts(tmp_path):
    source = read_blueprint(PROJECT)
    original = deepcopy(source)
    output = tmp_path / "dialogue"
    receipt = export_dialogue_handoff(
        output, source, [ACTION], scene_id="contest", authorized=True)
    assert receipt["schema"] == HANDOFF_SCHEMA
    assert receipt["release_certified"] is False
    assert sorted(p.name for p in output.iterdir()) == ["dialogue.json", "receipt.json"]
    staging, verified = import_dialogue_handoff(output, source, authorized=True)
    assert receipt == verified
    assert staging["scene_count"] == 1
    assert staging["cards"][0]["status"] == "available"
    assert source == original
    with pytest.raises((StudioQuestError, FileExistsError)):
        export_dialogue_handoff(output, source, [], authorized=True)


def test_dialogue_handoff_rejects_tamper_and_stale_source(tmp_path):
    source = read_blueprint(PROJECT)
    output = tmp_path / "dialogue"
    export_dialogue_handoff(output, source, [], authorized=True)
    with pytest.raises(StudioQuestError):
        import_dialogue_handoff(
            output, source, expected_source_digest="0" * 64, authorized=True)
    receipt_path = output / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["release_certified"] = True
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(StudioQuestError):
        import_dialogue_handoff(output, source, authorized=True)


def test_dialogue_handoff_rejects_extra_files_and_linked_outputs(tmp_path):
    source = read_blueprint(PROJECT)
    output = tmp_path / "dialogue"
    export_dialogue_handoff(output, source, [], authorized=True)
    (output / "extra.json").write_text("{}")
    with pytest.raises(StudioQuestError):
        import_dialogue_handoff(output, source, authorized=True)
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(output, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unavailable")
    with pytest.raises(StudioQuestError):
        import_dialogue_handoff(linked, source, authorized=True)
    with pytest.raises(StudioQuestError):
        export_dialogue_handoff(linked, source, [], authorized=True)


def test_dialogue_handoff_cli_export_and_import(capsys, tmp_path):
    from scripts.studio_ecosystem_cli import main
    output = tmp_path / "dialogue"
    assert main(["--project", PROJECT, "--dialogue-stage",
                 "--dialogue-export", "--output", str(output),
                 "--dialogue-actions", json.dumps([ACTION])]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["schema"] == HANDOFF_SCHEMA
    assert main(["--project", PROJECT, "--dialogue-stage",
                 "--dialogue-import", str(output)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["cards"][0]["status"] == "completed"
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--dialogue-stage",
              "--dialogue-export"])
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--dialogue-stage",
              "--dialogue-import", str(output), "--dialogue-actions", "[]"])
