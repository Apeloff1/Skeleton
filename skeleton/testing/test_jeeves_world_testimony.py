"""NPC testimony proof, review, replay, CLI, tool, editor and hostile-input fixtures."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

import pytest

from skeleton.jeeves.worlds.cast import CastStore, approve_cast, propose_cast
from skeleton.jeeves.worlds.testimony import (
    TestimonyStore, edit_testimony, prove_testimony, replay_testimony,
    render_testimony_html,
)
from skeleton.jeeves.worlds.testimony_cli import run
from skeleton.jeeves.worlds.tools import invoke_world_tool, manifest
from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore, digest, propose


def fixture(tmp_path):
    world = propose(world_id="harbor", premise="An original harbor mystery",
                    protagonist="Mara", region="Glass Bay", goal="Find the missing ledger")
    WorldStore(tmp_path).publish(world, create=True)
    cast = propose_cast(world, npc_id="tala", npc_name="Tala",
                        npc_line="I watched the ledger cross the bridge.")
    cast["characters"][0]["scenes"] = ["opening", "resolution"]
    cast = approve_cast(cast, world, "Original witness reviewed")
    CastStore(tmp_path).publish("harbor", cast, create=True)
    store = TestimonyStore(tmp_path)
    source = store.propose(
        "harbor", prompt="Tala witnesses the ledger", statement_id="tala_ledger",
        actor="tala", scene="resolution", choice="pursue_goal", claim="ledger_moved",
        stance="supports", text="I saw the ledger carried across the bridge.",
        provenance="firsthand")
    return world, cast, store, source


def reject(code, fn):
    with pytest.raises(CanonError) as exc:
        fn()
    assert exc.value.code == code


def test_proof_replay_and_unearned_choice(tmp_path):
    world, cast, _, source = fixture(tmp_path)
    proof = prove_testimony(source, world, cast)
    assert proof["statement_witnesses"]["tala_ledger"] == ["pursue_goal"]
    replay = replay_testimony(source, world, cast, ["pursue_goal"])
    assert replay["revealed_ids"] == ["tala_ledger"]
    assert replay["steps"][-1]["statements"][0]["actor"] == "tala"
    reject("session_invalid_transition",
           lambda: replay_testimony(source, world, cast, ["forged"]))


def test_review_compile_and_tamper(tmp_path):
    _, _, store, source = fixture(tmp_path)
    source["approved"] = True
    source["review_note"] = "Forged approval"
    first = store.publish("harbor", source, create=True)
    assert store.inspect("harbor")["testimony"]["approved"] is False
    reject("testimony_review_required", lambda: store.compile("harbor", first))
    approved = store.approve("harbor", expected_digest=first, review_note="Reviewed")
    receipt = store.compile("harbor", approved)
    assert store.verify("harbor") == receipt
    page = tmp_path / receipt["html_file"]
    assert sha256(page.read_bytes()).hexdigest() == receipt["html_sha256"]
    assert b"connect-src 'none'" in page.read_bytes()
    page.write_bytes(page.read_bytes() + b"<!-- modified -->")
    reject("testimony_playable_mismatch", lambda: store.verify("harbor"))


def test_invalid_lease_actor_trigger_and_contradiction(tmp_path):
    world, cast, _, source = fixture(tmp_path)
    bad = deepcopy(source)
    bad["cast_digest"] = "0" * 64
    reject("testimony_source_lease_mismatch", lambda: prove_testimony(bad, world, cast))
    bad = deepcopy(source)
    bad["statements"][0]["actor"] = "unknown"
    reject("testimony_actor_absent", lambda: prove_testimony(bad, world, cast))
    bad = deepcopy(source)
    bad["statements"][0]["scene"] = "opening"
    reject("testimony_trigger_not_arrival", lambda: prove_testimony(bad, world, cast))
    bad = deepcopy(source)
    denial = deepcopy(bad["statements"][0])
    denial["id"] = "z_denial"
    denial["stance"] = "denies"
    bad["statements"].append(denial)
    reject("testimony_coexisting_contradiction", lambda: prove_testimony(bad, world, cast))
    bad["statements"][1]["claim"] = "another_claim"
    assert len(prove_testimony(bad, world, cast)["statement_witnesses"]) == 2


def test_edit_cas_and_approval_revocation(tmp_path):
    world, cast, store, source = fixture(tmp_path)
    first = store.publish("harbor", source, create=True)
    updated = edit_testimony(source, world, cast, {
        "action": "replace_statement", "value": source["statements"][0]})
    assert not updated["approved"]
    reject("testimony_stale_edit", lambda: store.publish(
        "harbor", updated, expected_digest="0" * 64))
    reject("testimony_unknown_edit", lambda: edit_testimony(
        source, world, cast, {"action": "remove_statement", "value": {"id": "missing"}}))
    assert store.publish("harbor", updated, expected_digest=first)


def test_editor_cli_tools_read_only(tmp_path, capsys):
    _, _, store, source = fixture(tmp_path)
    first = store.publish("harbor", source, create=True)
    editor = store.editor("harbor", first)
    page = (tmp_path / editor["html_file"]).read_bytes()
    assert b"Export unapproved testimony" in page
    assert b"connect-src 'none'" in page
    reject("testimony_stale_edit", lambda: store.editor("harbor", "0" * 64))
    assert run(["--store", str(tmp_path), "inspect", "--world-id", "harbor"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    names = {item["name"] for item in manifest()["tools"]}
    assert {"world.testimony_preview", "world.testimony_propose_preview"} <= names
    result = invoke_world_tool(str(tmp_path), {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.testimony_preview", "world_id": "harbor", "args": {},
    })
    assert result["persisted"] is False
    assert result["result_digest"] == digest(result["result"])
    proposal = invoke_world_tool(str(tmp_path), {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.testimony_propose_preview", "world_id": "harbor",
        "args": {"prompt": "A witnessed ledger", "statement_id": "tala_ledger",
                 "actor": "tala", "scene": "resolution", "choice": "pursue_goal",
                 "claim": "ledger_moved", "stance": "supports",
                 "text": "The ledger crossed the bridge.", "provenance": "record"},
    })
    assert proposal["review_required"] is True
    assert proposal["result"]["approved"] is False


def test_invalid_schema_and_unapproved_playable(tmp_path):
    world, cast, _, source = fixture(tmp_path)
    reject("testimony_review_required",
           lambda: render_testimony_html(source, world, cast))
    bad = deepcopy(source)
    bad["statements"][0]["id"] = "../escape"
    reject("invalid_identifier", lambda: prove_testimony(bad, world, cast))
    bad = deepcopy(source)
    bad["statements"][0]["text"] = "\u0000"
    reject("control_character", lambda: prove_testimony(bad, world, cast))
