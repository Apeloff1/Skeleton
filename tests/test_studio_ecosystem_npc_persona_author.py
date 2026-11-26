"""NPC persona editing uses canonical revision, private bundle and Jeeves parity."""
import json

import pytest

from skeleton.ai.agents.jeeves.studio_walk_tool import (
    NPC_AUTHOR_REQUEST_SCHEMA, execute_npc_author_tool,
)
from skeleton.ai.game_builder.studio_ecosystem_author_revision import (
    load_revision_bundle,
)
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_npc_persona_author import (
    NPC_AUTHOR_SCHEMA, preview_npc_persona_revision,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

PROJECT = "studio_arena_fighting_glacial_fjord"


def fixture():
    docs = read_blueprint(PROJECT)
    npc = docs["cast"]["support"][0]
    source = audit_canon_source(docs, authorized=True)["source_digest"]
    return docs, npc["id"], source


def test_persona_edit_compiles_original_html_without_catalog_mutation():
    docs, npc_id, source = fixture()
    before = json.dumps(docs, sort_keys=True)
    changes = {"knows": "The archive contains a sealed passage to the eastern quay."}
    revised, html, receipt, detail = preview_npc_persona_revision(
        docs, npc_id=npc_id, changes=changes,
        expected_source_digest=source, authorized=True)
    assert detail["schema"] == NPC_AUTHOR_SCHEMA
    assert detail["playable_html_compiled"] is True
    assert detail["private_bundle_written"] is False
    assert detail["original_catalog_unchanged"] is True
    assert detail["revised_source_digest"] != source
    assert receipt["revised_source_digest"] == detail["revised_source_digest"]
    assert len(html) > 100 and b"<html" in html.lower()
    assert revised["cast"]["support"][0]["knows"] == changes["knows"]
    assert revised["cast"]["support"][0]["id"] == npc_id
    assert json.dumps(docs, sort_keys=True) == before
    assert (revised, html, receipt, detail) == preview_npc_persona_revision(
        docs, npc_id=npc_id, changes=changes,
        expected_source_digest=source, authorized=True)


@pytest.mark.parametrize("override", [
    {"npc_id": "../bad"}, {"npc_id": "unknown"}, {"npc_id": True},
    {"changes": {}}, {"changes": {"role": "Admin"}},
    {"changes": {"knows": " "}}, {"changes": {"name": True}},
    {"changes": {"knows": "x" * 513}},
    {"expected_source_digest": "0" * 64},
])
def test_invalid_persona_edits_fail_closed(override):
    docs, npc_id, source = fixture()
    kwargs = dict(npc_id=npc_id, changes={"knows": "A new original secret."},
                  expected_source_digest=source, authorized=True)
    kwargs.update(override)
    with pytest.raises(StudioQuestError):
        preview_npc_persona_revision(docs, **kwargs)


def test_operator_authority_required():
    docs, npc_id, source = fixture()
    with pytest.raises(PermissionError):
        preview_npc_persona_revision(
            docs, npc_id=npc_id, changes={"knows": "New original lore."},
            expected_source_digest=source, authorized=False)


def test_cli_writes_private_playable_bundle_and_typed_jeeves_parity(tmp_path, capsys):
    from scripts.studio_ecosystem_cli import main
    docs, npc_id, source = fixture()
    changes = {"knows": "A small original signal marks the passage."}
    request = {"schema": NPC_AUTHOR_REQUEST_SCHEMA,
               "project_id": PROJECT, "npc_id": npc_id,
               "changes": changes, "expected_source_digest": source}
    typed = execute_npc_author_tool(request, authorized=True)
    target = tmp_path / "npc-persona"
    args = ["--project", PROJECT, "--author-npc", "--npc-author-id", npc_id,
            "--npc-author-knows", changes["knows"],
            "--npc-author-expected-digest", source, "--output", str(target)]
    assert main(args) == 0
    written = json.loads(capsys.readouterr().out)
    assert written["author"] == typed["detail"]
    assert sorted(p.name for p in target.iterdir()) == [
        "receipt.json", "source.json", "story.html"]
    restored, receipt = load_revision_bundle(
        target, authorized=True, project_id=PROJECT)
    assert receipt == written["receipt"]
    assert restored["cast"]["support"][0]["knows"] == changes["knows"]
    with pytest.raises(SystemExit):
        main(args)
    with pytest.raises(StudioQuestError):
        execute_npc_author_tool({**request, "unknown": 1}, authorized=True)
    with pytest.raises(PermissionError):
        execute_npc_author_tool(request, authorized=False)
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--author-npc"])
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--author-npc", "--dialogue-stage",
              "--npc-author-id", npc_id, "--npc-author-knows", changes["knows"],
              "--npc-author-expected-digest", source, "--output", str(target)])
