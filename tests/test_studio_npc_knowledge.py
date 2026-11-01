"""NPC knowledge provenance, guarded reveals, private custody and Jeeves parity."""
from __future__ import annotations

import io
import json
from pathlib import Path
import sys

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_dialogue_staging import compile_dialogue_staging
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, replay_quest,
)
from skeleton.ai.game_builder.studio_ecosystem_npc_knowledge import (
    REQUEST_SCHEMA, SCHEMA, compile_npc_knowledge, publish_npc_knowledge,
    render_npc_knowledge_html, source_knowledge_facts, verify_npc_knowledge,
)
from skeleton.ai.game_builder.studio_ecosystem_npc_knowledge_prompt import propose_npc_knowledge
from skeleton.ai.game_builder.studio_ecosystem_npc_knowledge_compare import compare_npc_knowledge
from skeleton.ai.agents.jeeves.studio_npc_knowledge_tool import (
    REQUEST_SCHEMA as TOOL_SCHEMA, execute_npc_knowledge_tool,
)
from skeleton.ai.agents.jeeves.studio_world_tool_router import (
    route_world_tool, world_tool_catalog,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def fixture():
    docs = read_blueprint(PROJECT)
    source = audit_canon_source(docs, authorized=True)["source_digest"]
    session = replay_quest(docs, [], authorized=True)
    staging = compile_dialogue_staging(
        docs, [], authorized=True, expected_source_digest=source)
    return docs, source, session, staging


def authoring():
    docs, source, session, staging = fixture()
    facts = source_knowledge_facts(
        docs, [], authorized=True, expected_source_digest=source,
        expected_session_digest=session.digest)
    cards = staging["cards"]
    for fact in facts["facts"]:
        source_index = next(i for i, c in enumerate(cards)
                            if c["scene_id"] == fact["scene_id"])
        for recipient in cards[source_index + 1:]:
            if recipient["npc_id"] != fact["npc_id"]:
                return {"schema": REQUEST_SCHEMA, "reveals": [{
                    "fact_id": fact["fact_id"],
                    "recipient_scene_id": recipient["scene_id"],
                    "required_alternative": None,
                }]}
    pytest.skip("project has no cross-NPC authored scene pair")


def test_pending_knowledge_never_mints_npc_speech():
    docs, source, session, _ = fixture()
    request = authoring()
    before = json.dumps(docs, sort_keys=True)
    compiled = compile_npc_knowledge(
        docs, [], request, authorized=True,
        expected_source_digest=source, expected_session_digest=session.digest)
    assert compiled["schema"] == SCHEMA
    assert compiled["pending_count"] == 1
    assert compiled["earned_count"] == 0
    assert compiled["npc_speech_verified"] is False
    assert compiled["release_certified"] is False
    assert all(not scene["received_facts"] for scene in compiled["scenes"])
    assert json.dumps(docs, sort_keys=True) == before
    assert compiled == compile_npc_knowledge(
        docs, [], request, authorized=True, expected_source_digest=source)


def test_completed_replay_earns_only_authored_source_facts():
    docs, source, _, _ = fixture()
    program = compile_quest_program(docs)
    actions = [[stage.key, stage.alternatives[0]] for stage in program.stages]
    session = replay_quest(docs, actions, authorized=True)
    compiled = compile_npc_knowledge(
        docs, actions, authoring(), authorized=True,
        expected_source_digest=source, expected_session_digest=session.digest)
    assert compiled["earned_count"] == 1
    assert compiled["pending_count"] == 0
    assert sum(len(scene["received_facts"]) for scene in compiled["scenes"]) == 1
    assert b"<script" not in render_npc_knowledge_html(compiled).lower()


@pytest.mark.parametrize("mutate", [
    lambda x: x.update({"schema": "forged"}),
    lambda x: x["reveals"][0].update({"fact_id": "forged"}),
    lambda x: x["reveals"][0].update({"recipient_scene_id": "forged"}),
    lambda x: x["reveals"][0].update({"required_alternative": True}),
    lambda x: x["reveals"][0].update({"extra": True}),
    lambda x: x["reveals"].append(dict(x["reveals"][0])),
])
def test_invalid_or_duplicate_reveal_fails_closed(mutate):
    docs, source, _, _ = fixture()
    request = authoring()
    mutate(request)
    with pytest.raises(StudioQuestError):
        compile_npc_knowledge(docs, [], request, authorized=True,
                              expected_source_digest=source)


def test_source_session_and_operator_authority_fail_closed():
    docs, source, _, _ = fixture()
    request = authoring()
    with pytest.raises(PermissionError):
        compile_npc_knowledge(docs, [], request, authorized=False,
                              expected_source_digest=source)
    for lease in ("0" * 64, True, "", None):
        with pytest.raises(StudioQuestError):
            compile_npc_knowledge(docs, [], request, authorized=True,
                                  expected_source_digest=lease)
    with pytest.raises(StudioQuestError):
        compile_npc_knowledge(docs, [], request, authorized=True,
                              expected_source_digest=source,
                              expected_session_digest="0" * 64)


def test_private_immutable_publication_and_tamper_rejection(tmp_path):
    docs, source, _, _ = fixture()
    request = authoring()
    compiled = compile_npc_knowledge(
        docs, [], request, authorized=True, expected_source_digest=source)
    publication = publish_npc_knowledge(
        compiled, tmp_path, authorized=True, documents=docs, actions=[])
    assert publication["file_write_performed"] is True
    path = tmp_path / "studio_npc_knowledge.json"
    assert path.is_file() and path.stat().st_mode & 0o077 == 0
    assert verify_npc_knowledge(
        docs, [], tmp_path, authorized=True, expected_source_digest=source) == compiled
    with pytest.raises(FileExistsError):
        publish_npc_knowledge(compiled, tmp_path, authorized=True,
                              documents=docs, actions=[])
    forged = dict(compiled)
    forged["earned_count"] += 1
    path.write_text(json.dumps(forged))
    with pytest.raises(StudioQuestError):
        verify_npc_knowledge(docs, [], tmp_path, authorized=True,
                             expected_source_digest=source)


def test_symlinked_destination_is_rejected(tmp_path):
    docs, source, _, _ = fixture()
    compiled = compile_npc_knowledge(
        docs, [], authoring(), authorized=True, expected_source_digest=source)
    destination = tmp_path / "private"
    destination.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(destination, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unsupported")
    with pytest.raises(OSError):
        publish_npc_knowledge(compiled, linked, authorized=True,
                              documents=docs, actions=[])


def test_prompt_plan_is_deterministic_and_uses_original_source_only():
    docs, source, session, _ = fixture()
    first = propose_npc_knowledge(
        docs, [], "share original NPC knowledge across scenes",
        authorized=True, expected_source_digest=source,
        expected_session_digest=session.digest)
    assert first == propose_npc_knowledge(
        docs, [], "share original NPC knowledge across scenes",
        authorized=True, expected_source_digest=source)
    assert first["model_inference_performed"] is False
    assert first["compiled"]["pending_count"] >= 1
    with pytest.raises(StudioQuestError):
        propose_npc_knowledge(docs, [], "bad\ncontrol", authorized=True,
                              expected_source_digest=source)


def test_typed_jeeves_router_matches_direct_adapter():
    docs, source, _, _ = fixture()
    request = {
        "schema": TOOL_SCHEMA, "project_id": PROJECT,
        "expected_source_digest": source, "actions": [],
        "authoring": authoring(),
    }
    envelope = {"tool": "studio_original_npc_knowledge", "arguments": request}
    assert "studio_original_npc_knowledge" in [
        entry["name"] for entry in world_tool_catalog()["tools"]]
    direct = execute_npc_knowledge_tool(request, authorized=True)
    routed = route_world_tool(envelope, authorized=True)
    assert routed["result"] == direct
    assert routed["file_write_performed"] is False
    assert routed == route_world_tool(envelope, authorized=True)


def test_cli_strict_authoring_round_trip(capsys):
    from scripts.studio_npc_knowledge_cli import main
    docs, source, _, _ = fixture()
    assert main(["--project", PROJECT, "--expected-source", source,
                 "--authoring-json", json.dumps(authoring()),
                 "--include-html"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["compiled"]["source_digest"] == source
    assert "<main>" in receipt["director_companion_html"]
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--expected-source", source,
              "--authoring-json", '{"schema":"a","schema":"b"}'])


def test_missing_authored_npc_knowledge_uses_goal_not_fabricated_testimony():
    docs, source, _, staging = fixture()
    rival = next(card for card in staging["cards"] if card["npc_id"] == "rival")
    first = rival["authored_cues"][0]
    assert first["kind"] == "npc_goal"
    assert first["source_ref"] == "cast.support.rival.goal"
    assert first["text"] == next(member["goal"] for member in
                                 docs["cast"]["support"] if member["id"] == "rival")
    facts = source_knowledge_facts(
        docs, [], authorized=True, expected_source_digest=source)
    assert all(fact["fact_id"] != rival["scene_id"] + ":npc_knowledge"
               for fact in facts["facts"])

def test_knowledge_branch_compare_is_choice_sensitive_and_replay_proven():
    docs, source, _, staging = fixture()
    request = authoring()
    fact = request["reveals"][0]["fact_id"]
    source_scene = fact.split(":", 1)[0]
    card = next(card for card in staging["cards"] if card["scene_id"] == source_scene)
    program = compile_quest_program(docs)
    source_stage = next(stage for stage in program.stages if stage.key == card["quest_stage"])
    if len(source_stage.alternatives) < 2:
        pytest.skip("no authored alternate source choice")
    request["reveals"][0]["required_alternative"] = source_stage.alternatives[0]
    first = [[stage.key, stage.alternatives[0]] for stage in program.stages]
    second = [[stage.key, (stage.alternatives[1] if stage.key == source_stage.key
                            else stage.alternatives[0])] for stage in program.stages]
    compared = compare_npc_knowledge(
        docs, first, second, request, authorized=True, expected_source_digest=source)
    assert compared["before_earned_count"] == 1
    assert compared["after_earned_count"] == 0
    assert compared["change_count"] == 1
    assert compared["scene_changes"][0]["lost_fact_ids"] == [fact]
    assert compared["source_replay_verified"] is True
    assert compared == compare_npc_knowledge(
        docs, first, second, request, authorized=True, expected_source_digest=source)
    with pytest.raises(StudioQuestError):
        compare_npc_knowledge(docs, first, second, request, authorized=True,
                              expected_source_digest="0" * 64)
    with pytest.raises(PermissionError):
        compare_npc_knowledge(docs, first, second, request, authorized=False,
                              expected_source_digest=source)


def test_jeeves_branch_compare_matches_canonical_engine():
    docs, source, _, staging = fixture()
    request = authoring()
    stage = compile_quest_program(docs).stages[0]
    request["reveals"][0]["required_alternative"] = stage.alternatives[0]
    actions = [[item.key, item.alternatives[0]]
               for item in compile_quest_program(docs).stages]
    tool = {"schema": TOOL_SCHEMA, "project_id": PROJECT,
            "expected_source_digest": source, "actions": actions,
            "compare_actions": actions, "authoring": request}
    direct = execute_npc_knowledge_tool(tool, authorized=True)
    routed = route_world_tool(
        {"tool": "studio_original_npc_knowledge", "arguments": tool},
        authorized=True)
    assert routed["result"] == direct
    assert direct["detail"]["comparison"]["change_count"] == 0

def test_actual_playable_director_zip_contains_source_verified_npc_knowledge():
    from hashlib import sha256
    import zipfile
    from skeleton.ai.game_builder.studio_ecosystem_director_handoff import (
        compile_director_handoff,
    )
    docs, source, _, _ = fixture()
    scenes = docs["scene"]["episode_plan"]
    schedule = {"scene_ticks": {scene["id"]: 5 for scene in scenes},
                "npc_turnaround_ticks": 2, "min_start_ticks": {}}
    recipe = docs["visual"]["asset_recipes"][0]["id"]
    assignments = {scene["id"]: {
        asset: recipe for asset in scene["assets"] + scene["interactive_objects"]}
        for scene in scenes}
    visual = sha256(json.dumps(docs["visual"], sort_keys=True,
                               separators=(",", ":"), ensure_ascii=True,
                               allow_nan=False).encode("ascii")).hexdigest()
    request = authoring()
    manifest, bundle = compile_director_handoff(
        docs, [], schedule, assignments, authorized=True,
        expected_source_digest=source, expected_visual_digest=visual,
        knowledge_authoring=request)
    assert manifest["npc_knowledge_earned_count"] == 0
    assert manifest["npc_knowledge_spoken_verified"] is False
    assert manifest["canonical_html5_gameplay_replay_verified"] is True
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        assert "index.html" in archive.namelist()
        assert "npc_knowledge.json" in archive.namelist()
        assert "npc_knowledge.html" in archive.namelist()
        receipt = json.loads(archive.read("npc_knowledge.json"))
        assert receipt["knowledge_digest"] == manifest["npc_knowledge_digest"]
        assert b"<script" not in archive.read("npc_knowledge.html").lower()
        for name, expected in manifest["file_hashes"].items():
            assert sha256(archive.read(name)).hexdigest() == expected
    assert (manifest, bundle) == compile_director_handoff(
        docs, [], schedule, assignments, authorized=True,
        expected_source_digest=source, expected_visual_digest=visual,
        knowledge_authoring=request)
    with pytest.raises(StudioQuestError):
        compile_director_handoff(
            docs, [], schedule, assignments, authorized=True,
            expected_source_digest=source, expected_visual_digest=visual,
            knowledge_authoring={"schema": REQUEST_SCHEMA, "reveals": [{
                **request["reveals"][0], "fact_id": "forged"}]})

def test_offline_editor_is_source_bound_and_csp_hashed():
    from skeleton.ai.game_builder.studio_ecosystem_npc_knowledge_editor import (
        render_npc_knowledge_editor,
    )
    docs, source, _, _ = fixture()
    compiled = compile_npc_knowledge(
        docs, [], authoring(), authorized=True, expected_source_digest=source)
    html, receipt = render_npc_knowledge_editor(
        docs, [], compiled, authorized=True)
    assert receipt["html_sha256"] == __import__("hashlib").sha256(html).hexdigest()
    assert receipt["authoring_export_only"] is True
    assert b"Content-Security-Policy" in html
    assert b"innerHTML" not in html
    assert b"eval(" not in html
    assert b"createObjectURL" in html
    assert b"studio_npc_knowledge_editor_export.v1" in html
    assert render_npc_knowledge_editor(docs, [], compiled, authorized=True) == (html, receipt)
    with pytest.raises(StudioQuestError):
        render_npc_knowledge_editor(
            docs, [], {**compiled, "earned_count": 999}, authorized=True)


def test_private_editor_import_checks_lease_and_duplicate_keys(tmp_path):
    from skeleton.ai.game_builder.studio_ecosystem_npc_knowledge_editor import (
        EXPORT_SCHEMA, load_npc_knowledge_editor_export,
    )
    docs, source, session, _ = fixture()
    payload = {
        "schema": EXPORT_SCHEMA, "project_id": PROJECT,
        "source_digest": source, "session_digest": session.digest,
        "authoring": authoring(),
    }
    path = tmp_path / "editor.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o600)
    kwargs = dict(authorized=True, expected_project_id=PROJECT,
                  expected_source_digest=source,
                  expected_session_digest=session.digest)
    assert load_npc_knowledge_editor_export(path, **kwargs) == authoring()
    with pytest.raises(StudioQuestError):
        load_npc_knowledge_editor_export(
            path, **{**kwargs, "expected_session_digest": "0" * 64})
    path.write_text('{"schema":"a","schema":"b"}')
    with pytest.raises(StudioQuestError):
        load_npc_knowledge_editor_export(path, **kwargs)


def test_editor_is_packaged_with_real_playable_director():
    from hashlib import sha256
    import zipfile
    from skeleton.ai.game_builder.studio_ecosystem_director_handoff import (
        compile_director_handoff,
    )
    docs, source, _, _ = fixture()
    scenes = docs["scene"]["episode_plan"]
    schedule = {"scene_ticks": {scene["id"]: 5 for scene in scenes},
                "npc_turnaround_ticks": 2, "min_start_ticks": {}}
    recipe = docs["visual"]["asset_recipes"][0]["id"]
    assignments = {scene["id"]: {
        asset: recipe for asset in scene["assets"] + scene["interactive_objects"]}
        for scene in scenes}
    visual = sha256(json.dumps(docs["visual"], sort_keys=True,
                               separators=(",", ":"), ensure_ascii=True,
                               allow_nan=False).encode("ascii")).hexdigest()
    manifest, bundle = compile_director_handoff(
        docs, [], schedule, assignments, authorized=True,
        expected_source_digest=source, expected_visual_digest=visual,
        knowledge_authoring=authoring())
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        editor = archive.read("npc_knowledge_editor.html")
        assert b"Content-Security-Policy" in editor
        assert sha256(editor).hexdigest() == manifest["file_hashes"]["npc_knowledge_editor.html"]
        assert manifest["offline_npc_knowledge_editor_receipt"]["html_sha256"] == sha256(editor).hexdigest()

def test_npc_knowledge_restore_rejects_hardlinked_receipt(tmp_path):
    import os

    docs, source, _, _ = fixture()
    compiled = compile_npc_knowledge(
        docs, [], authoring(), authorized=True, expected_source_digest=source)
    publish_npc_knowledge(
        compiled, tmp_path, authorized=True, documents=docs, actions=[])
    if os.name != "posix":
        pytest.skip("POSIX hardlink custody")
    alias = tmp_path / "knowledge-alias.json"
    os.link(tmp_path / "studio_npc_knowledge.json", alias)
    with pytest.raises(StudioQuestError, match="regular, owned, private"):
        verify_npc_knowledge(docs, [], tmp_path, authorized=True,
                             expected_source_digest=source)


def test_editor_import_rejects_hardlinked_export(tmp_path):
    import os
    from skeleton.ai.game_builder.studio_ecosystem_npc_knowledge_editor import (
        EXPORT_SCHEMA, load_npc_knowledge_editor_export,
    )

    docs, source, session, _ = fixture()
    path = tmp_path / "editor.json"
    path.write_text(json.dumps({
        "schema": EXPORT_SCHEMA, "project_id": PROJECT,
        "source_digest": source, "session_digest": session.digest,
        "authoring": authoring(),
    }), encoding="utf-8")
    path.chmod(0o600)
    if os.name != "posix":
        pytest.skip("POSIX hardlink custody")
    os.link(path, tmp_path / "editor-alias.json")
    with pytest.raises(StudioQuestError, match="private regular file"):
        load_npc_knowledge_editor_export(
            path, authorized=True, expected_project_id=PROJECT,
            expected_source_digest=source, expected_session_digest=session.digest)

def test_source_replayed_npc_lineage_cli_and_director_parity(capsys):
    from hashlib import sha256
    import zipfile
    from skeleton.ai.game_builder.studio_ecosystem_npc_lineage import (
        compile_npc_lineage, render_npc_lineage_html,
    )
    from skeleton.ai.game_builder.studio_ecosystem_director_handoff import (
        compile_director_handoff,
    )
    from scripts.studio_npc_knowledge_cli import main
    docs, source, session, _ = fixture()
    request = authoring()
    lineage = compile_npc_lineage(
        docs, [], request, authorized=True, expected_source_digest=source,
        expected_session_digest=session.digest)
    assert lineage["model_inference_performed"] is False
    assert lineage["reveal_count"] == len(request["reveals"])
    assert all("source_text" not in edge for edge in lineage["edges"])
    html = render_npc_lineage_html(lineage)
    assert b"Content-Security-Policy" in html
    assert b"<script" not in html
    assert main(["--project", PROJECT, "--expected-source", source,
                 "--authoring-json", json.dumps(request),
                 "--include-lineage"]) == 0
    cli = json.loads(capsys.readouterr().out)
    assert cli["lineage"] == lineage
    assert cli["lineage_html"] == html.decode("utf-8")
    scenes = docs["scene"]["episode_plan"]
    schedule = {"scene_ticks": {scene["id"]: 5 for scene in scenes},
                "npc_turnaround_ticks": 2, "min_start_ticks": {}}
    recipe = docs["visual"]["asset_recipes"][0]["id"]
    assignments = {scene["id"]: {
        asset: recipe for asset in scene["assets"] + scene["interactive_objects"]}
        for scene in scenes}
    visual = sha256(json.dumps(
        docs["visual"], sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()
    manifest, bundle = compile_director_handoff(
        docs, [], schedule, assignments, authorized=True,
        expected_source_digest=source, expected_visual_digest=visual,
        knowledge_authoring=request)
    assert manifest["npc_lineage_digest"] == lineage["lineage_digest"]
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        assert json.loads(archive.read("npc_lineage.json")) == lineage
        assert archive.read("npc_lineage.html") == html
        for name in ("npc_lineage.json", "npc_lineage.html"):
            assert sha256(archive.read(name)).hexdigest() == manifest["file_hashes"][name]


def test_npc_lineage_rejects_stale_leases_and_forged_display():
    from skeleton.ai.game_builder.studio_ecosystem_npc_lineage import (
        compile_npc_lineage, render_npc_lineage_html,
    )
    docs, source, session, _ = fixture()
    request = authoring()
    with pytest.raises(PermissionError):
        compile_npc_lineage(docs, [], request, authorized=False,
                            expected_source_digest=source)
    with pytest.raises(StudioQuestError):
        compile_npc_lineage(docs, [], request, authorized=True,
                            expected_source_digest="0" * 64)
    with pytest.raises(StudioQuestError):
        compile_npc_lineage(docs, [], request, authorized=True,
                            expected_source_digest=source,
                            expected_session_digest="0" * 64)
    lineage = compile_npc_lineage(
        docs, [], request, authorized=True, expected_source_digest=source)
    with pytest.raises(StudioQuestError):
        render_npc_lineage_html({**lineage, "earned_count": 999})
    assert lineage["session_digest"] == session.digest
