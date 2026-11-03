"""Original lighthouse laptop path: actual custody, review, builder, replay, restore."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.jeeves.worlds.laptop_cli import run
from skeleton.jeeves.worlds.laptop_flow import LaptopFlow
from skeleton.jeeves.worlds.tools import invoke_world_tool, manifest
from skeleton.jeeves.worlds.world_canon import CanonError, canonical, digest

SAMPLES = Path(__file__).resolve().parents[2] / "examples" / "jeeves"


def sample(name):
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


def reject(code, action):
    with pytest.raises(CanonError) as error:
        action()
    assert error.value.code == code


def ready(tmp_path):
    flow = LaptopFlow(tmp_path)
    proposed = flow.propose(sample("lighthouse_brief.json"))
    assert proposed["review_required"]
    assert not flow.inspect("lighthouse")["reviewed"]
    reviewed = flow.review(
        "lighthouse", proposed["source_digest"],
        sample("lighthouse_review.json"),
        "Author approved the original rescue branch and flag consequences.")
    receipt = flow.compile("lighthouse", reviewed["source_digest"])
    assert flow.verify("lighthouse") == receipt
    return flow, proposed, reviewed, receipt


def test_original_prompt_review_compile_and_builder_handoff(tmp_path):
    flow, proposed, reviewed, receipt = ready(tmp_path)
    assert reviewed["source_digest"] != proposed["source_digest"]
    assert receipt["source_digest"] == reviewed["source_digest"]
    manifest = json.loads((tmp_path / receipt["builder_file"]).read_text())
    assert manifest["schema"] == "jeeves.world.builder_handoff.v1"
    assert manifest["canon_proof"]["ending_witnesses"]["resolution"] == ["pursue_goal"]
    assert "rescue" in [c["id"] for c in manifest["choice_edges"]]
    assert manifest["session_contract"] == "jeeves.world.session.v1"
    assert manifest["qualification"].endswith("not_engine_binary_or_device_certified")
    assert "Content-Security-Policy" in (tmp_path / receipt["html_file"]).read_text()


def test_replay_export_restore_and_no_clobber(tmp_path):
    flow, _, _, _ = ready(tmp_path)
    first = flow.create_session("lighthouse", "one")
    assert first["scene"]["id"] == "opening"
    second = flow.choose("lighthouse", "one", "rescue", first["session_digest"])
    assert second["scene"]["id"] == "shelter"
    reject("stale_session", lambda: flow.choose(
        "lighthouse", "one", "return", first["session_digest"]))
    final = flow.choose("lighthouse", "one", "return", second["session_digest"])
    assert final["ending"] is not None
    exported = flow.export_session("lighthouse", "one")
    restored = flow.create_session("lighthouse", "two", imported=exported)
    assert restored["scene"] == final["scene"]
    assert restored["session_digest"] == final["session_digest"]
    reject("session_already_exists", lambda: flow.create_session(
        "lighthouse", "two", imported=exported))
    exported["session"]["scene"] = "opening"
    reject("session_checksum_mismatch", lambda: flow.create_session(
        "lighthouse", "three", imported=exported))


def test_stale_review_and_artifact_tampering_fail_closed(tmp_path):
    flow, proposed, reviewed, receipt = ready(tmp_path)
    reject("stale_source", lambda: flow.compile(
        "lighthouse", proposed["source_digest"]))
    (tmp_path / receipt["builder_file"]).write_bytes(
        (tmp_path / receipt["builder_file"]).read_bytes() + b" ")
    reject("laptop_builder_mismatch", lambda: flow.verify("lighthouse"))
    flow.compile("lighthouse", reviewed["source_digest"])
    (tmp_path / receipt["html_file"]).write_bytes(b"forged html")
    reject("laptop_html_mismatch", lambda: flow.verify("lighthouse"))
    flow.compile("lighthouse", reviewed["source_digest"])
    world = flow.worlds.read("lighthouse")
    changed = dict(world)
    changed["prompt"] = world["prompt"] + " revised"
    flow.worlds.publish(changed, expected_digest=digest(world))
    reject("review_stale_source", lambda: flow.verify("lighthouse"))
    reject("review_stale_source", lambda: flow.create_session("lighthouse", "one"))


def test_no_unreviewed_compile_and_bad_operations(tmp_path):
    flow = LaptopFlow(tmp_path)
    proposed = flow.propose(sample("lighthouse_brief.json"))
    reject("review_required", lambda: flow.compile(
        "lighthouse", proposed["source_digest"]))
    reject("review_note_too_short", lambda: flow.review(
        "lighthouse", proposed["source_digest"], sample("lighthouse_review.json"), "yes"))
    reject("review_requires_change", lambda: flow.review(
        "lighthouse", proposed["source_digest"],
        {"action": "batch", "value": [
            {"action": "replace_scene", "value": flow.worlds.read("lighthouse")["scenes"][0]}]},
        "Explicit but unchanged author review must fail."))
    reject("unsupported_edit", lambda: flow.review(
        "lighthouse", proposed["source_digest"],
        {"action": "shell", "value": {}},
        "Disallow arbitrary executable edit operations."))


def test_cli_end_to_end_and_typed_errors(tmp_path, capsys):
    root = str(tmp_path)
    assert run(["--store", root, "propose", "--brief-file",
                str(SAMPLES / "lighthouse_brief.json")]) == 0
    proposed = json.loads(capsys.readouterr().out)["result"]
    assert run(["--store", root, "review", "--world-id", "lighthouse",
                "--expected-digest", proposed["source_digest"],
                "--operation-file", str(SAMPLES / "lighthouse_review.json"),
                "--review-note", "Reviewed original lighthouse rescue branch."]) == 0
    reviewed = json.loads(capsys.readouterr().out)["result"]
    assert run(["--store", root, "compile", "--world-id", "lighthouse",
                "--expected-digest", reviewed["source_digest"]]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    assert run(["--store", root, "verify", "--world-id", "lighthouse"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    assert run(["--store", root, "session-create", "--world-id", "lighthouse",
                "--slot", "player"]) == 0
    view = json.loads(capsys.readouterr().out)["result"]
    assert run(["--store", root, "session-choose", "--world-id", "lighthouse",
                "--slot", "player", "--choice-id", "rescue",
                "--expected-session-digest", view["session_digest"]]) == 0
    assert json.loads(capsys.readouterr().out)["result"]["scene"]["id"] == "shelter"
    assert run(["--store", root, "session-export", "--world-id", "lighthouse",
                "--slot", "player"]) == 0
    exported = json.loads(capsys.readouterr().out)["result"]
    export_file = tmp_path / "export.json"
    export_file.write_bytes(canonical(exported))
    assert run(["--store", root, "session-restore", "--world-id", "lighthouse",
                "--slot", "restored", "--export-file", str(export_file)]) == 0
    assert json.loads(capsys.readouterr().out)["result"]["scene"]["id"] == "shelter"
    assert run(["--store", root, "compile", "--world-id", "lighthouse",
                "--expected-digest", "0" * 64]) == 2
    failure = json.loads(capsys.readouterr().out)
    assert failure["error"] == "stale_source"
    assert failure["phase"] == "compile"
    assert failure["next_action"] == "inspect_source_and_repeat_review"


def test_readonly_jeeves_preview_matches_compiled_source(tmp_path):
    flow, _, reviewed, receipt = ready(tmp_path)
    names = {item["name"] for item in manifest()["tools"]}
    assert {"world.laptop_preview", "world.laptop_handoff_preview"} <= names
    request = {"schema": "jeeves.world.tool_request.v1",
               "tool": "world.laptop_preview", "world_id": "lighthouse", "args": {}}
    response = invoke_world_tool(str(tmp_path), request)
    assert response["persisted"] is False
    assert response["result"]["source_digest"] == reviewed["source_digest"]
    assert response["result"]["reviewed"] is True
    request["tool"] = "world.laptop_handoff_preview"
    handoff = invoke_world_tool(str(tmp_path), request)
    assert handoff["persisted"] is False
    assert handoff["result"] == receipt
    assert handoff["result_digest"] == digest(receipt)


def test_existing_nine_plane_studio_engine_owner_bridge(tmp_path):
    from skeleton.testing.test_jeeves_world_studio_engine import fixture as engine_fixture
    engine_fixture(tmp_path)
    flow = LaptopFlow(tmp_path)
    source = flow.worlds.read("harbor")
    approved = flow.approve_current(
        "harbor", digest(source), "Existing canonical world explicitly reviewed.")
    assert approved["reviewed"] is True
    flow.compile("harbor", approved["source_digest"])
    preview = flow.engine_inspect("harbor", "eight_bit_tile_1983")
    assert preview["engine"]["source_digests"]["world"] == approved["source_digest"]
    stale = dict(preview["engine"]["source_digests"])
    stale["assets"] = "0" * 64
    reject("laptop_engine_stale_source", lambda: flow.engine_compile(
        "harbor", "eight_bit_tile_1983", stale))
    result = flow.engine_compile(
        "harbor", "eight_bit_tile_1983", preview["engine"]["source_digests"])
    assert flow.engine_verify("harbor") == result
    assert result["engine"]["qualification"] == (
        "source_verified_engine_recipe_not_release_certified")


def test_engine_bridge_never_synthesizes_missing_reviewed_planes(tmp_path):
    flow, _, _, _ = ready(tmp_path)
    reject("not_found", lambda: flow.engine_inspect(
        "lighthouse", "eight_bit_tile_1983"))
