"""Source-leased authored quest revision save migration contracts."""
from __future__ import annotations

import copy
import json
import os

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, replay_quest, start_quest,
)
from skeleton.ai.game_builder.studio_quest_revision_migration import (
    SCHEMA, FILENAME, compile_quest_revision_migration,
    replay_quest_revision_migration, compile_quest_migration_handoff,
    publish_quest_revision_migration, restore_quest_revision_migration,
)
from skeleton.ai.agents.jeeves.studio_world_tool_router import (
    route_world_tool, world_tool_catalog,
)
from skeleton.ai.agents.jeeves.studio_quest_revision_migration_tool import REQUEST_SCHEMA

PROJECT = "studio_puzzle_expedition_copper_mesa"


def fixture():
    docs = read_blueprint(PROJECT)
    program = compile_quest_program(docs)
    old = [list((stage.key, stage.alternatives[0])) for stage in program.stages]
    source_key = "stage_graph" if docs["quest"].get("stage_graph") else "stages"
    new_choice = program.stages[0].alternatives[0] + " revised"
    revision = {
        "schema": "skeleton.game_builder.studio_author_revision_request.v1",
        "project_id": PROJECT,
        "expected_source_digest": audit_canon_source(
            docs, authorized=True)["source_digest"],
        "edits": [{"section": "quest",
                   "path": [source_key, 0, "alternatives", 0],
                   "value": new_choice}],
    }
    plan = {
        "revision_request": revision, "actions": old, "remaps": [],
        "target_ending": program.endings[0][0],
    }
    leases = {
        "authorized": True,
        "expected_source_digest": program.source_digest,
        "expected_initial_session_digest": start_quest(
            docs, authorized=True).digest,
    }
    return docs, plan, leases, new_choice


def test_no_implicit_choice_migration_and_replay_proof():
    docs, plan, leases, _ = fixture()
    report = compile_quest_revision_migration(docs, plan, **leases)
    assert report["schema"] == SCHEMA
    assert report["status"] == "requires_explicit_remap"
    assert report["migrated_actions"] == []
    assert report["first_unmigrated_index"] == 0
    assert report["dropped_old_actions"] == plan["actions"]
    assert not report["playable_handoff_allowed"]
    assert report["canonical_old_replay_verified"]
    assert report["canonical_revised_replay_verified"]
    assert replay_quest_revision_migration(docs, report, authorized=True) == report
    with pytest.raises(StudioQuestError):
        compile_quest_migration_handoff(docs, report, authorized=True)


def test_explicit_approved_remap_replays_new_quest():
    docs, plan, leases, new_choice = fixture()
    plan["remaps"] = [{
        "stage_id": plan["actions"][0][0],
        "from_choice": plan["actions"][0][1],
        "to_choice": new_choice,
    }]
    report = compile_quest_revision_migration(docs, plan, **leases)
    assert report["migrated_actions"][0][1] == new_choice
    assert len(report["migrated_actions"]) == len(plan["actions"])
    assert report["first_unmigrated_index"] is None
    assert report["status"] in ("migrated", "ending_unmet")
    assert report["external_authorship_verified"] is False
    assert report["release_certified"] is False
    assert replay_quest_revision_migration(docs, report, authorized=True) == report
    if report["playable_handoff_allowed"]:
        handoff = compile_quest_migration_handoff(
            docs, report, authorized=True)
        assert handoff["revised_quest_session_digest"] == report["new_session_digest"]
        assert handoff["native_gameplay_verified"] is False
    else:
        with pytest.raises(StudioQuestError):
            compile_quest_migration_handoff(docs, report, authorized=True)


def test_stale_leases_invalid_mapping_and_forged_receipts_fail_closed():
    docs, plan, leases, new_choice = fixture()
    with pytest.raises(PermissionError):
        compile_quest_revision_migration(
            docs, plan, **{**leases, "authorized": False})
    for key in ("expected_source_digest", "expected_initial_session_digest"):
        with pytest.raises(StudioQuestError):
            compile_quest_revision_migration(
                docs, plan, **{**leases, key: "0" * 64})
    for bad in (
        [{"stage_id": plan["actions"][0][0],
          "from_choice": "forged", "to_choice": new_choice}],
        [{"stage_id": plan["actions"][0][0],
          "from_choice": plan["actions"][0][1], "to_choice": "forged"}],
        [{"stage_id": "unknown", "from_choice": "x", "to_choice": "y"}],
    ):
        invalid = {**plan, "remaps": bad}
        with pytest.raises(StudioQuestError):
            compile_quest_revision_migration(docs, invalid, **leases)
    report = compile_quest_revision_migration(docs, plan, **leases)
    tampered = copy.deepcopy(report)
    tampered["playable_handoff_allowed"] = True
    with pytest.raises(StudioQuestError):
        replay_quest_revision_migration(docs, tampered, authorized=True)
    drift = copy.deepcopy(docs)
    drift["quest"]["stage_graph" if drift["quest"].get("stage_graph") else "stages"][0]["reward"] = "changed"
    with pytest.raises(StudioQuestError):
        replay_quest_revision_migration(drift, report, authorized=True)


def test_private_exclusive_migration_custody_and_tamper(tmp_path):
    docs, plan, leases, _ = fixture()
    report = compile_quest_revision_migration(docs, plan, **leases)
    published = publish_quest_revision_migration(
        docs, report, tmp_path, authorized=True)
    assert published["file_write_performed"]
    path = tmp_path / FILENAME
    assert path.stat().st_mode & 0o077 == 0
    assert restore_quest_revision_migration(
        docs, tmp_path, authorized=True,
        expected_source_digest=leases["expected_source_digest"]) == report
    with pytest.raises(FileExistsError):
        publish_quest_revision_migration(docs, report, tmp_path, authorized=True)
    forged = json.loads(path.read_text())
    forged["status"] = "migrated"
    path.write_text(json.dumps(forged))
    with pytest.raises(StudioQuestError):
        restore_quest_revision_migration(
            docs, tmp_path, authorized=True,
            expected_source_digest=leases["expected_source_digest"])


def test_jeeves_router_requires_explicit_authoring_authority():
    catalog = world_tool_catalog()
    name = "studio_original_quest_revision_migration"
    entry = next(x for x in catalog["tools"] if x["name"] == name)
    assert entry["explicit_authoring_permission_required"] is True
    with pytest.raises(PermissionError):
        route_world_tool({"tool": name, "arguments": {
            "schema": REQUEST_SCHEMA}}, authorized=True)
    with pytest.raises(StudioQuestError):
        route_world_tool({"tool": name, "arguments": {
            "schema": REQUEST_SCHEMA, "authorized": True}},
            authorized=True, allow_authoring=True)

def test_offline_migration_editor_csp_and_explicit_recompile(tmp_path):
    from skeleton.ai.game_builder.studio_quest_revision_migration_editor import (
        EXPORT_SCHEMA, render_quest_migration_editor,
        import_quest_migration_editor_export,
    )
    docs, plan, leases, new_choice = fixture()
    baseline = compile_quest_revision_migration(docs, plan, **leases)
    html, proof = render_quest_migration_editor(
        docs, baseline, authorized=True)
    assert b"script-src 'sha256-" in html
    assert b"connect-src 'none'" in html
    assert proof["authoring_export_only"] is True
    assert proof["release_certified"] is False
    updated = copy.deepcopy(plan)
    updated["remaps"] = [{
        "stage_id": plan["actions"][0][0],
        "from_choice": plan["actions"][0][1],
        "to_choice": new_choice,
    }]
    payload = {
        "schema": EXPORT_SCHEMA, "project_id": PROJECT,
        "old_quest_source_digest": baseline["old_quest_source_digest"],
        "initial_session_digest": baseline["initial_session_digest"],
        "baseline_migration_digest": baseline["migration_digest"],
        "authoring": updated,
    }
    path = tmp_path / "migration_edit.json"
    path.write_text(json.dumps(payload))
    os.chmod(path, 0o600)
    result = import_quest_migration_editor_export(
        docs, baseline, path, **leases)
    assert result["migrated_actions"][0][1] == new_choice
    assert len(result["migrated_actions"]) == len(updated["actions"])
    payload["baseline_migration_digest"] = "0" * 64
    path.write_text(json.dumps(payload))
    with pytest.raises(StudioQuestError):
        import_quest_migration_editor_export(
            docs, baseline, path, **leases)


def test_offline_migration_editor_rejects_symlink_and_duplicate_json(tmp_path):
    from skeleton.ai.game_builder.studio_quest_revision_migration_editor import (
        import_quest_migration_editor_export,
    )
    docs, plan, leases, _ = fixture()
    baseline = compile_quest_revision_migration(docs, plan, **leases)
    path = tmp_path / "migration_edit.json"
    path.write_text('{"schema":"a","schema":"b"}')
    os.chmod(path, 0o600)
    with pytest.raises(StudioQuestError):
        import_quest_migration_editor_export(
            docs, baseline, path, **leases)
    target = tmp_path / "target"
    target.write_text("{}")
    link = tmp_path / "linked.json"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unsupported")
    with pytest.raises(OSError):
        import_quest_migration_editor_export(
            docs, baseline, link, **leases)
