"""End-to-end source-bound narrative promise authoring, closure and handoff."""
from __future__ import annotations

import copy
import json
import os

import pytest

from skeleton.jeeves.worlds.promises import (
    PromiseStore, approve_promises, compile_promises, edit_promises,
    propose_promises, prove_promises, replay_promises, validate_promises,
)
from skeleton.jeeves.worlds.promises_cli import run
from skeleton.jeeves.worlds.review_editor import ReviewEditorStore
from skeleton.jeeves.worlds.session import SessionStore
from skeleton.jeeves.worlds.tools import SCHEMA, invoke_world_tool, manifest
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, canonical, digest, edit, propose, strict_json,
)


def world():
    source = propose(
        world_id="harbor", premise="A lighthouse keeper promises to return.",
        protagonist="Neri", region="Salt Reach", goal="Restore the beacon.",
    )
    return edit(source, {"action": "batch", "value": [
        {"action": "add_scene", "value": {
            "id": "bridge", "title": "The oath", "narrative": "A vow is spoken.",
        }},
        {"action": "add_choice", "value": {
            "id": "take_oath", "from": "opening", "to": "bridge",
            "label": "Promise to help", "requires": [], "grants": [],
        }},
        {"action": "add_choice", "value": {
            "id": "fulfill_oath", "from": "bridge", "to": "resolution",
            "label": "Keep the promise", "requires": [], "grants": [],
        }},
    ]})


def proposal(source=None):
    source = source or world()
    return propose_promises(
        source, prompt="Write an original obligation and explicit payoff.",
        promise_id="return_home", title="The return", setup="A promise is made.",
        payoff="The promise is kept.", trigger_choice="take_oath",
        resolve_choice="fulfill_oath", required=True,
    )


def request(name, args=None):
    return {"schema": SCHEMA, "tool": name, "world_id": "harbor",
            "args": args if args is not None else {}}


def test_proposal_is_typed_and_never_implicitly_approved():
    source = world()
    data = proposal(source)
    assert not data["approved"]
    assert data["world_digest"] == digest(source)
    assert validate_promises(data, source) == data
    with pytest.raises(CanonError, match="promise_review_required"):
        compile_promises(data, source)


def test_exhaustive_proof_and_actual_player_replay():
    source = world()
    data = approve_promises(proposal(source), source, "Reviewed original canon.")
    proof = prove_promises(data, source)
    assert proof["required_all_endings_closed"]
    assert proof["ending_witnesses"]["resolution"] == ["pursue_goal"]
    assert proof["states_explored"] >= 3
    initial = replay_promises(data, source, [])
    assert initial["open"] == []
    triggered = replay_promises(data, source, ["take_oath"])
    assert triggered["open_required"] == ["return_home"]
    assert not triggered["ending_continuity_satisfied"]
    done = replay_promises(data, source, ["take_oath", "fulfill_oath"])
    assert done["open"] == []
    assert done["resolved"] == ["return_home"]
    assert done["ending_continuity_satisfied"]
    assert done["events"] == [
        {"step": 1, "id": "return_home", "event": "triggered"},
        {"step": 2, "id": "return_home", "event": "resolved"},
    ]


def test_unresolved_branch_is_rejected_even_when_happy_path_passes():
    source = edit(world(), {"action": "add_choice", "value": {
        "id": "betray_oath", "from": "bridge", "to": "resolution",
        "label": "Abandon the vow", "requires": [], "grants": [],
    }})
    data = proposal(source)
    with pytest.raises(CanonError, match="unresolved_required_promise"):
        approve_promises(data, source, "I reviewed only the good ending.")
    with pytest.raises(CanonError, match="unresolved_required_promise"):
        prove_promises(data, source)


def test_optional_promise_can_remain_open_without_forging_resolution():
    source = edit(world(), {"action": "add_choice", "value": {
        "id": "betray_oath", "from": "bridge", "to": "resolution",
        "label": "Abandon the vow", "requires": [], "grants": [],
    }})
    data = proposal(source)
    data["promises"][0]["required"] = False
    approved = approve_promises(data, source, "Optional branch consequence.")
    proof = prove_promises(approved, source)
    assert proof["required_all_endings_closed"]
    result = replay_promises(approved, source, ["take_oath", "betray_oath"])
    assert result["open"] == ["return_home"]
    assert result["open_required"] == []


@pytest.mark.parametrize("change,code", [
    ({"trigger_choice": "unknown"}, "promise_unknown_choice"),
    ({"resolve_choice": "take_oath"}, "promise_same_trigger_and_resolution"),
    ({"required": 1}, "promise_required_invalid"),
    ({"setup": ""}, "invalid_text"),
])
def test_invalid_author_proposals_fail_closed(change, code):
    data = proposal()
    data["promises"][0].update(change)
    with pytest.raises(CanonError, match=code):
        validate_promises(data, world())


def test_atomic_edits_revoke_approval_and_reject_duplicate_ids():
    source = world()
    approved = approve_promises(proposal(source), source, "Reviewed.")
    edited = edit_promises(approved, source, {"action": "replace", "value": {
        **approved["promises"][0], "payoff": "A new ending was authored.",
    }})
    assert edited["approved"] is False
    assert edited["review_note"] == ""
    assert approved["approved"] is True
    assert edited["promises"][0]["payoff"] == "A new ending was authored."
    with pytest.raises(CanonError, match="promise_duplicate"):
        edit_promises(approved, source, {"action": "add", "value":
                                         approved["promises"][0]})
    with pytest.raises(CanonError, match="promise_unsupported_edit"):
        edit_promises(approved, source, {"action": "exec", "value": {}})
    assert canonical(approved) == canonical(copy.deepcopy(approved))


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_persist_approve_compile_verify_player_and_editor(tmp_path):
    root = tmp_path / "private"
    source = world()
    WorldStore(root).publish(source, create=True)
    store = PromiseStore(root)
    draft = proposal(source)
    first = store.publish("harbor", draft, create=True)
    assert first == digest(store.read("harbor"))
    editor = ReviewEditorStore(root)
    editor_receipt = editor.render("harbor", "promises", first)
    assert editor.verify("harbor", "promises") == editor_receipt
    html = (root / "harbor.promises.editor.html").read_text()
    assert "Content-Security-Policy" in html
    assert "connect-src 'none'" in html
    assert "<script" in html
    with pytest.raises(CanonError, match="promise_review_required"):
        store.compile("harbor", first)
    approved = approve_promises(draft, source, "Reviewed original vow.")
    second = store.publish("harbor", approved, expected_digest=first)
    assert second != first
    with pytest.raises(CanonError, match="stale_promises"):
        store.publish("harbor", draft, expected_digest=first)
    with pytest.raises(CanonError, match="stale_review_editor"):
        editor.render("harbor", "promises", first)
    receipt = store.compile("harbor", second)
    assert store.verify("harbor") == receipt
    assert (root / "harbor.promises.playable.html").read_text().startswith("<!doctype")
    assert strict_json((root / "harbor.promises.handoff.json").read_bytes())["proof"][
        "required_all_endings_closed"]
    sessions = SessionStore(root)
    sessions.create("harbor", "player")
    assert store.player("harbor", "player")["open"] == []
    sessions.choose("harbor", "player", "take_oath",
                    digest(sessions.read("harbor", "player")))
    assert store.player("harbor", "player")["open_required"] == ["return_home"]
    sessions.choose("harbor", "player", "fulfill_oath",
                    digest(sessions.read("harbor", "player")))
    assert store.player("harbor", "player")["ending_continuity_satisfied"]


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_receipt_and_html_tampering_are_rejected(tmp_path):
    root = tmp_path / "private"
    source = world()
    WorldStore(root).publish(source, create=True)
    store = PromiseStore(root)
    approved = approve_promises(proposal(source), source, "Reviewed.")
    sha = store.publish("harbor", approved, create=True)
    store.compile("harbor", sha)
    path = root / "harbor.promises.playable.html"
    path.write_bytes(path.read_bytes() + b"forged")
    with pytest.raises(CanonError, match="promise_artifact_mismatch"):
        store.verify("harbor")
    store.compile("harbor", sha)
    receipt = root / "harbor.promises.receipt.json"
    forged = json.loads(receipt.read_text())
    forged["qualification"] = "device_certified"
    receipt.write_text(json.dumps(forged))
    with pytest.raises(CanonError, match="promise_receipt_mismatch"):
        store.verify("harbor")


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_symlink_source_and_world_revision_fail_closed(tmp_path):
    root = tmp_path / "private"
    source = world()
    worlds = WorldStore(root)
    before = worlds.publish(source, create=True)
    store = PromiseStore(root)
    draft = proposal(source)
    store.publish("harbor", draft, create=True)
    name = root / "harbor.promises.json"
    name.unlink()
    name.symlink_to(tmp_path / "missing")
    with pytest.raises((CanonError, OSError)):
        store.read("harbor")
    name.unlink()
    store.publish("harbor", draft, create=True)
    revised = edit(source, {"action": "replace_scene", "value": {
        "id": "bridge", "title": "Changed oath", "narrative": "A new vow.",
    }})
    worlds.publish(revised, expected_digest=before)
    with pytest.raises(CanonError, match="promises_world_lease_mismatch"):
        store.read("harbor")


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_typed_jeeves_preview_and_read_only_player(tmp_path):
    root = tmp_path / "private"
    source = world()
    WorldStore(root).publish(source, create=True)
    args = {
        "prompt": "Original vow.", "promise_id": "return_home",
        "title": "The return", "setup": "A promise is made.",
        "payoff": "The promise is kept.", "trigger_choice": "take_oath",
        "resolve_choice": "fulfill_oath", "required": True,
    }
    preview = invoke_world_tool(str(root), request("promises.propose_preview", args))
    assert preview["persisted"] is False
    assert preview["review_required"] is True
    assert preview["result"]["approved"] is False
    assert not (root / "harbor.promises.json").exists()
    assert "promises.player" in {item["name"] for item in manifest()["tools"]}
    with pytest.raises(CanonError, match="unknown_world_tool"):
        invoke_world_tool(str(root), request("promises.approve"))
    data = approve_promises(proposal(source), source, "Reviewed.")
    PromiseStore(root).publish("harbor", data, create=True)
    SessionStore(root).create("harbor", "one")
    assert invoke_world_tool(str(root), request("promises.player", {"slot": "one"}))[
        "result"]["open"] == []
    assert invoke_world_tool(str(root), request("promises.proof"))[
        "result"]["required_all_endings_closed"]


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_cli_full_operator_path(tmp_path, capsys):
    root = tmp_path / "private"
    source = world()
    WorldStore(root).publish(source, create=True)
    base = ["--store", str(root)]
    assert run(base + [
        "propose", "--world-id", "harbor", "--prompt", "Original vow.",
        "--promise-id", "return_home", "--title", "The return",
        "--setup", "A promise is made.", "--payoff", "The promise is kept.",
        "--trigger-choice", "take_oath", "--resolve-choice", "fulfill_oath",
    ]) == 0
    proposed = json.loads(capsys.readouterr().out)
    sha = proposed["promises_digest"]
    assert run(base + ["editor", "--world-id", "harbor",
                       "--expected-digest", sha]) == 0
    assert json.loads(capsys.readouterr().out)["editor"]["source_digest"] == sha
    assert run(base + ["approve", "--world-id", "harbor",
                       "--expected-digest", sha, "--note", "Reviewed."]) == 0
    approved = json.loads(capsys.readouterr().out)["promises_digest"]
    assert run(base + ["compile", "--world-id", "harbor",
                       "--expected-digest", approved]) == 0
    assert json.loads(capsys.readouterr().out)["receipt"]["world_id"] == "harbor"
    assert run(base + ["verify", "--world-id", "harbor"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    assert run(base + ["edit", "--world-id", "harbor",
                       "--expected-digest", sha,
                       "--operation-json", '{"action":"exec","value":{}}']) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "stale_promises"
