"""Original accessible narration, exact coverage, proof, review and playable custody."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import pytest

from skeleton.jeeves.worlds.accessibility import (
    AccessibilityStore, edit_accessibility, accessible_replay,
    prove_accessibility, render_accessibility_html,
)
from skeleton.jeeves.worlds.accessibility_cli import run
from skeleton.jeeves.worlds.tools import invoke_world_tool, manifest
from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore, digest, propose


def fixture(tmp_path):
    world = propose(world_id="harbor", premise="An original harbor journey",
                    protagonist="Mara", region="Glass Bay", goal="Restore the beacon")
    WorldStore(tmp_path).publish(world, create=True)
    store = AccessibilityStore(tmp_path)
    source = store.propose(
        "harbor", prompt="Accessible original harbor experience",
        scenes=[{"id": row["id"], "summary": "Description of " + row["title"],
                 "landmark": "main"}
                for row in sorted(world["scenes"], key=lambda row: row["id"])],
        choices=[{"id": row["id"], "action": "Action: " + row["label"]}
                 for row in sorted(world["choices"], key=lambda row: row["id"])],
        endings=[{"scene": row["scene"], "summary": "Outcome: " + row["label"]}
                 for row in sorted(world["endings"], key=lambda row: row["scene"])])
    return world, store, source


def reject(code, fn):
    with pytest.raises(CanonError) as exc:
        fn()
    assert exc.value.code == code


def test_coverage_and_replay(tmp_path):
    world, _, source = fixture(tmp_path)
    proof = prove_accessibility(source, world)
    assert proof["scene_count"] == 2
    assert proof["choice_count"] == 1
    player = accessible_replay(source, world, ["pursue_goal"])
    assert player["ending"].startswith("Outcome:")
    assert player["steps"][-1]["accessible_action"].startswith("Action:")
    reject("session_invalid_transition",
           lambda: accessible_replay(source, world, ["forged"]))


def test_review_compile_and_tamper(tmp_path):
    _, store, source = fixture(tmp_path)
    source["approved"] = True
    first = store.publish("harbor", source, create=True)
    assert store.inspect("harbor")["accessibility"]["approved"] is False
    reject("accessibility_review_required", lambda: store.compile("harbor", first))
    approved = store.approve("harbor", expected_digest=first, review_note="Reviewed")
    receipt = store.compile("harbor", approved)
    assert store.verify("harbor") == receipt
    page = tmp_path / receipt["html_file"]
    assert sha256(page.read_bytes()).hexdigest() == receipt["html_sha256"]
    assert b"aria-live" in page.read_bytes()
    assert b"connect-src 'none'" in page.read_bytes()
    page.write_bytes(page.read_bytes() + b"<!-- tampered -->")
    reject("accessibility_playable_mismatch", lambda: store.verify("harbor"))


def test_missing_coverage_and_invalid_lease(tmp_path):
    world, _, source = fixture(tmp_path)
    bad = deepcopy(source)
    bad["scenes"].pop()
    reject("accessibility_scene_coverage", lambda: prove_accessibility(bad, world))
    bad = deepcopy(source)
    bad["choices"][0]["id"] = "missing"
    reject("accessibility_unknown_choice", lambda: prove_accessibility(bad, world))
    bad = deepcopy(source)
    bad["world_digest"] = "0" * 64
    reject("accessibility_source_lease_mismatch",
           lambda: prove_accessibility(bad, world))
    bad = deepcopy(source)
    bad["scenes"][0]["summary"] = "\u0000"
    reject("control_character", lambda: prove_accessibility(bad, world))


def test_edit_stale_lease_and_review_reset(tmp_path):
    world, store, source = fixture(tmp_path)
    first = store.publish("harbor", source, create=True)
    edited = edit_accessibility(source, world, {
        "action": "replace_scene", "value": source["scenes"][0]})
    assert not edited["approved"]
    reject("accessibility_stale_edit", lambda: store.publish(
        "harbor", edited, expected_digest="0" * 64))
    assert store.publish("harbor", edited, expected_digest=first)


def test_editor_cli_tools_read_only(tmp_path, capsys):
    _, store, source = fixture(tmp_path)
    first = store.publish("harbor", source, create=True)
    editor = store.editor("harbor", first)
    page = (tmp_path / editor["html_file"]).read_bytes()
    assert b"Export unapproved accessible narrative" in page
    assert b"connect-src 'none'" in page
    reject("accessibility_stale_edit", lambda: store.editor("harbor", "0" * 64))
    assert run(["--store", str(tmp_path), "inspect", "--world-id", "harbor"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    names = {item["name"] for item in manifest()["tools"]}
    assert {"world.accessibility_preview", "world.accessibility_propose_preview"} <= names
    response = invoke_world_tool(str(tmp_path), {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.accessibility_preview", "world_id": "harbor", "args": {},
    })
    assert response["persisted"] is False
    assert response["result_digest"] == digest(response["result"])
    proposal = invoke_world_tool(str(tmp_path), {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.accessibility_propose_preview", "world_id": "harbor",
        "args": {"prompt": "Accessible harbor",
                 "scenes": source["scenes"], "choices": source["choices"],
                 "endings": source["endings"]},
    })
    assert proposal["review_required"] is True
    assert proposal["result"]["approved"] is False
