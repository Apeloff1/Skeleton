"""Narrative pacing: climax proof, review, replay, editor, CLI and source drift."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

import pytest

from skeleton.jeeves.worlds.pacing import (
    PacingStore, edit_pacing, prove_pacing, replay_pacing, render_pacing_html,
)
from skeleton.jeeves.worlds.pacing_cli import run
from skeleton.jeeves.worlds.tools import invoke_world_tool, manifest
from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore, digest, propose, prove


def fixture(tmp_path):
    world = propose(world_id="harbor", premise="An original harbor crisis",
                    protagonist="Mara", region="Glass Bay", goal="Save the beacon")
    world["scenes"].append({"id": "storm", "title": "Storm",
                            "narrative": "The beacon is threatened."})
    world["choices"][0]["to"] = "storm"
    world["choices"].append({"id": "save_beacon", "from": "storm", "to": "resolution",
                             "label": "Save the beacon", "requires": [], "grants": []})
    prove(world)
    WorldStore(tmp_path).publish(world, create=True)
    store = PacingStore(tmp_path)
    source = store.propose("harbor", prompt="Escalate to a real climax",
                           beats=[
                               {"scene": "opening", "phase": "setup", "intensity": 2,
                                "note": "Introduce the storm."},
                               {"scene": "resolution", "phase": "resolution", "intensity": 3,
                                "note": "Resolve the beacon."},
                               {"scene": "storm", "phase": "climax", "intensity": 9,
                                "note": "Face the strongest danger."},
                           ])
    return world, store, source


def reject(code, fn):
    with pytest.raises(CanonError) as exc:
        fn()
    assert exc.value.code == code


def test_climax_witness_and_replay(tmp_path):
    world, _, source = fixture(tmp_path)
    proof = prove_pacing(source, world)
    assert proof["climax_witnesses"]["storm"] == ["pursue_goal"]
    assert proof["ending_witnesses"]["resolution"] == ["pursue_goal", "save_beacon"]
    replay = replay_pacing(source, world, ["pursue_goal", "save_beacon"])
    assert replay["steps"][1]["beat"]["phase"] == "climax"
    reject("session_invalid_transition",
           lambda: replay_pacing(source, world, ["save_beacon"]))


def test_review_compile_receipt_and_tamper(tmp_path):
    _, store, source = fixture(tmp_path)
    source["approved"] = True
    first = store.publish("harbor", source, create=True)
    assert store.inspect("harbor")["pacing"]["approved"] is False
    reject("pacing_review_required", lambda: store.compile("harbor", first))
    approved = store.approve("harbor", expected_digest=first, review_note="Reviewed")
    receipt = store.compile("harbor", approved)
    assert store.verify("harbor") == receipt
    page = tmp_path / receipt["html_file"]
    assert sha256(page.read_bytes()).hexdigest() == receipt["html_sha256"]
    assert b"connect-src 'none'" in page.read_bytes()
    page.write_bytes(page.read_bytes() + b"<!-- modified -->")
    reject("pacing_playable_mismatch", lambda: store.verify("harbor"))


def test_missing_climax_and_phase_regression(tmp_path):
    world, _, source = fixture(tmp_path)
    bad = deepcopy(source)
    bad["beats"][2]["phase"] = "rising"
    bad["beats"][2]["intensity"] = 6
    reject("pacing_ending_without_climax", lambda: prove_pacing(bad, world))
    bad = deepcopy(source)
    bad["beats"][1]["phase"] = "setup"
    reject("pacing_ending_not_resolution", lambda: prove_pacing(bad, world))
    bad = deepcopy(source)
    bad["beats"][2]["intensity"] = 2
    reject("pacing_phase_intensity_mismatch", lambda: prove_pacing(bad, world))
    bad = deepcopy(source)
    bad["world_digest"] = "0" * 64
    reject("pacing_source_lease_mismatch", lambda: prove_pacing(bad, world))


def test_edit_cas_and_review_reset(tmp_path):
    world, store, source = fixture(tmp_path)
    first = store.publish("harbor", source, create=True)
    edited = edit_pacing(source, world, {
        "action": "replace_beat", "value": source["beats"][2]})
    assert not edited["approved"]
    reject("pacing_stale_edit", lambda: store.publish(
        "harbor", edited, expected_digest="0" * 64))
    assert store.publish("harbor", edited, expected_digest=first)


def test_editor_cli_and_readonly_tools(tmp_path, capsys):
    _, store, source = fixture(tmp_path)
    first = store.publish("harbor", source, create=True)
    editor = store.editor("harbor", first)
    page = (tmp_path / editor["html_file"]).read_bytes()
    assert b"Export unapproved pacing" in page
    assert b"connect-src 'none'" in page
    reject("pacing_stale_edit", lambda: store.editor("harbor", "0" * 64))
    assert run(["--store", str(tmp_path), "inspect", "--world-id", "harbor"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    names = {item["name"] for item in manifest()["tools"]}
    assert {"world.pacing_preview", "world.pacing_propose_preview"} <= names
    response = invoke_world_tool(str(tmp_path), {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.pacing_preview", "world_id": "harbor", "args": {},
    })
    assert response["persisted"] is False
    assert response["result_digest"] == digest(response["result"])
    proposal = invoke_world_tool(str(tmp_path), {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.pacing_propose_preview", "world_id": "harbor",
        "args": {"prompt": "Escalate the storm", "beats": source["beats"]},
    })
    assert proposal["review_required"] is True
    assert proposal["result"]["approved"] is False
