"""End-to-end reviewed forks, replay provenance, security and CLI acceptance."""
from __future__ import annotations

import copy
import json
import os

import pytest

from skeleton.jeeves.worlds.branching import (
    ForkStore, compare_sessions, propose_fork,
)
from skeleton.jeeves.worlds.branching_cli import run
from skeleton.jeeves.worlds.branching_editor import render_fork_editor
from skeleton.jeeves.worlds.session import SessionStore, _source_session, apply_choice, new_session
from skeleton.jeeves.worlds.tools import SCHEMA, invoke_world_tool, manifest
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, canonical, digest, propose, prove,
)


def world():
    w = propose(world_id="isles", premise="Two routes across an island.",
                protagonist="Ari", region="North Isle", goal="Reach the beacon.")
    w["scenes"].insert(1, {
        "id": "harbor", "title": "Harbor", "narrative": "Boats at anchor.",
    })
    w["scenes"].insert(2, {
        "id": "cliff", "title": "Cliff", "narrative": "A high path.",
    })
    w["choices"] = [
        {"id": "sail", "from": "opening", "to": "harbor",
         "label": "Sail", "requires": [], "grants": ["boat"]},
        {"id": "climb", "from": "opening", "to": "cliff",
         "label": "Climb", "requires": [], "grants": ["rope"]},
        {"id": "dock", "from": "harbor", "to": "resolution",
         "label": "Dock", "requires": ["boat"], "grants": []},
        {"id": "summit", "from": "cliff", "to": "resolution",
         "label": "Summit", "requires": ["rope"], "grants": []},
    ]
    prove(w)
    return w


def setup(tmp_path):
    source = world()
    WorldStore(tmp_path).publish(source, create=True)
    sessions = SessionStore(tmp_path)
    sessions.create("isles", "primary")
    first = sessions.read("isles", "primary")
    sessions.choose("isles", "primary", "sail", digest(first))
    return source, sessions, ForkStore(tmp_path)


def test_preview_is_pure_and_reviewed_publish_is_native_session(tmp_path):
    source, sessions, forks = setup(tmp_path)
    before = sessions.read("isles", "primary")
    proposal = forks.preview(
        "isles", parent_slot="primary", target_slot="alternate",
        prompt="What if Ari climbed instead?", at_revision=0, choice_id="climb")
    assert proposal["preview"]["scene"]["id"] == "cliff"
    assert proposal["preview"]["flags"] == ["rope"]
    assert sessions.read("isles", "primary") == before
    with pytest.raises(CanonError, match="not_found"):
        sessions.read("isles", "alternate")
    published = forks.publish("isles", proposal, digest(before))
    assert published["player"]["scene"]["id"] == "cliff"
    assert forks.inspect("isles", "alternate")["history_proven"]
    assert forks.compare("isles", "alternate")["common_revision"] == 0
    assert forks.compare("isles", "alternate")["left_only_flags"] == ["boat"]
    assert forks.compare("isles", "alternate")["right_only_flags"] == ["rope"]
    assert sessions.inspect("isles", "alternate")["playable"] is True
    child = sessions.read("isles", "alternate")
    sessions.choose("isles", "alternate", "summit", digest(child))
    assert forks.inspect("isles", "alternate")["player"]["ending"]
    assert forks.compare("isles", "alternate")["right_suffix"] == ["climb", "summit"]
    assert sessions.read("isles", "primary") == before
    handoff = forks.compile("isles", "alternate", digest(source))
    assert handoff["artifact"]["html_file"] == "isles.html"
    assert (tmp_path / "isles.html").is_file()


def test_proposal_is_bound_to_parent_lease_and_immutable_review(tmp_path):
    _, sessions, forks = setup(tmp_path)
    proposal = forks.preview(
        "isles", parent_slot="primary", target_slot="branch",
        prompt="Alternate crossing", at_revision=0, choice_id="climb")
    for key, value in (
        ("world_digest", "0" * 64),
        ("choice_id", "sail"),
        ("initial_session_digest", "1" * 64),
        ("prompt", "changed without re-review"),
    ):
        bad = copy.deepcopy(proposal)
        bad[key] = value
        with pytest.raises(CanonError, match="fork_proposal_mismatch"):
            forks.publish("isles", bad, proposal["parent_digest"])
    parent = sessions.read("isles", "primary")
    sessions.choose("isles", "primary", "dock", digest(parent))
    with pytest.raises(CanonError, match="fork_stale_parent"):
        forks.publish("isles", proposal, proposal["parent_digest"])


def test_fork_limits_invalid_transition_and_existing_slot(tmp_path):
    source, sessions, forks = setup(tmp_path)
    parent = sessions.read("isles", "primary")
    for revision in (-1, 2, True):
        with pytest.raises(CanonError, match="fork_revision_invalid"):
            propose_fork(source, parent, parent_slot="primary",
                         target_slot="branch", prompt="review",
                         at_revision=revision, choice_id="climb")
    with pytest.raises(CanonError, match="session_invalid_transition"):
        forks.preview("isles", parent_slot="primary", target_slot="branch",
                      prompt="Impossible", at_revision=1, choice_id="climb")
    with pytest.raises(CanonError, match="fork_same_slot"):
        forks.preview("isles", parent_slot="primary", target_slot="primary",
                      prompt="Collision", at_revision=0, choice_id="climb")
    proposal = forks.preview("isles", parent_slot="primary", target_slot="branch",
                             prompt="Valid", at_revision=0, choice_id="climb")
    forks.publish("isles", proposal, proposal["parent_digest"])
    with pytest.raises(CanonError, match="fork_slot_exists"):
        forks.publish("isles", proposal, proposal["parent_digest"])


def test_forged_receipt_and_fork_history_rejected(tmp_path):
    _, sessions, forks = setup(tmp_path)
    proposal = forks.preview("isles", parent_slot="primary", target_slot="branch",
                             prompt="Alternative", at_revision=0, choice_id="climb")
    forks.publish("isles", proposal, proposal["parent_digest"])
    path = tmp_path / "isles.branch.fork.json"
    original = path.read_bytes()
    receipt = json.loads(original)
    receipt["choice_id"] = "sail"
    path.write_bytes(canonical(receipt))
    with pytest.raises(CanonError, match="fork_receipt_mismatch"):
        forks.inspect("isles", "branch")
    path.write_bytes(original)
    session_path = tmp_path / "isles.branch.session.json"
    child = sessions.read("isles", "branch")
    forged = apply_choice(new_session(world()), world(), "sail")
    session_path.write_bytes(canonical(forged))
    with pytest.raises(CanonError, match="fork_history_mismatch"):
        forks.inspect("isles", "branch")
    session_path.write_bytes(canonical(child))
    assert forks.inspect("isles", "branch")["history_proven"]


def test_symlinked_receipt_rejected_without_following(tmp_path):
    _, _, forks = setup(tmp_path)
    proposal = forks.preview("isles", parent_slot="primary", target_slot="branch",
                             prompt="Alternative", at_revision=0, choice_id="climb")
    forks.publish("isles", proposal, proposal["parent_digest"])
    receipt = tmp_path / "isles.branch.fork.json"
    receipt.unlink()
    target = tmp_path / "sentinel"
    target.write_text("do-not-read")
    receipt.symlink_to(target)
    with pytest.raises((CanonError, OSError)):
        forks.inspect("isles", "branch")
    assert target.read_text() == "do-not-read"


def test_tool_preview_is_read_only_and_manifested(tmp_path):
    _, sessions, _ = setup(tmp_path)
    request = {
        "schema": SCHEMA, "tool": "world.fork_preview",
        "world_id": "isles",
        "args": {"parent_slot": "primary", "target_slot": "alternate",
                 "prompt": "Try cliff", "at_revision": 0, "choice_id": "climb"},
    }
    assert "world.fork_preview" in {x["name"] for x in manifest()["tools"]}
    output = invoke_world_tool(str(tmp_path), request)
    assert output["persisted"] is False
    assert output["result"]["preview"]["scene"]["id"] == "cliff"
    assert sessions.read("isles", "primary")["choices"] == ["sail"]
    with pytest.raises(CanonError, match="not_found"):
        sessions.read("isles", "alternate")


def test_cli_review_and_compile(tmp_path, capsys):
    source, _, forks = setup(tmp_path)
    store = str(tmp_path)
    args = ["--store", store, "preview", "--world-id", "isles",
            "--parent-slot", "primary", "--target-slot", "cli",
            "--prompt", "Try the cliff", "--at-revision", "0",
            "--choice-id", "climb"]
    assert run(args) == 0
    proposal = json.loads(capsys.readouterr().out)["result"]
    approved = tmp_path / "approved.json"
    approved.write_bytes(canonical(proposal))
    assert run(["--store", store, "publish", "--world-id", "isles",
                "--proposal-file", str(approved),
                "--expected-parent-digest", proposal["parent_digest"]]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert run(["--store", store, "compile", "--world-id", "isles",
                "--target-slot", "cli", "--expected-world-digest",
                digest(source)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["result"]["artifact"]["html_sha256"]
    assert forks.inspect("isles", "cli")["history_proven"]


def test_compare_rejects_unearned_or_forged_flags():
    source = world()
    left = apply_choice(new_session(source), source, "sail")
    right = apply_choice(new_session(source), source, "climb")
    assert compare_sessions(source, left, right)["common_revision"] == 0
    right["flags"] = ["unearned"]
    with pytest.raises(CanonError, match="session_replay_mismatch"):
        compare_sessions(source, left, right)


def test_forged_review_prompt_and_digest_are_detected(tmp_path):
    _, _, forks = setup(tmp_path)
    proposal = forks.preview("isles", parent_slot="primary", target_slot="branch",
                             prompt="Choose the cliff", at_revision=0, choice_id="climb")
    forks.publish("isles", proposal, proposal["parent_digest"])
    receipt_file = tmp_path / "isles.branch.fork.json"
    original = receipt_file.read_bytes()
    forged = json.loads(original)
    forged["prompt"] = "Unreviewed change"
    receipt_file.write_bytes(canonical(forged))
    with pytest.raises(CanonError, match="fork_receipt_mismatch"):
        forks.inspect("isles", "branch")
    receipt_file.write_bytes(original)
    forged = json.loads(original)
    forged["proposal_digest"] = "0" * 64
    receipt_file.write_bytes(canonical(forged))
    with pytest.raises(CanonError, match="fork_receipt_mismatch"):
        forks.inspect("isles", "branch")


def test_create_only_publish_rejects_symlink_collision(tmp_path):
    _, _, forks = setup(tmp_path)
    proposal = forks.preview("isles", parent_slot="primary", target_slot="branch",
                             prompt="Alternative", at_revision=0, choice_id="climb")
    target = tmp_path / "sentinel"
    target.write_text("untouched")
    (tmp_path / "isles.branch.session.json").symlink_to(target)
    with pytest.raises((CanonError, OSError)):
        forks.publish("isles", proposal, proposal["parent_digest"])
    assert target.read_text() == "untouched"


def test_editor_is_offline_csp_bound_and_source_leased(tmp_path):
    source, sessions, forks = setup(tmp_path)
    parent = sessions.read("isles", "primary")
    page = render_fork_editor(source, parent, "primary")
    assert b"Content-Security-Policy" in page
    assert b"connect-src 'none'" in page
    assert b"sha256-" in page
    assert b"Try the cliff" not in page
    assert b"fork-request.json" in page
    result = forks.editor("isles", "primary", digest(parent))
    assert result["review_required"] is True
    assert (tmp_path / result["html_file"]).read_bytes() == page
    with pytest.raises(CanonError, match="fork_stale_parent"):
        forks.editor("isles", "primary", "0" * 64)


def test_editor_request_to_cli_preview_then_reviewed_publish(tmp_path, capsys):
    _, sessions, forks = setup(tmp_path)
    request = {
        "world_id": "isles", "parent_slot": "primary",
        "target_slot": "from-editor", "prompt": "Ari explores the cliff",
        "at_revision": 0, "choice_id": "climb",
    }
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical(request))
    assert run(["--store", str(tmp_path), "preview-file",
                "--request-file", str(request_path)]) == 0
    proposal = json.loads(capsys.readouterr().out)["result"]
    assert proposal["preview"]["scene"]["id"] == "cliff"
    assert proposal["parent_digest"] == digest(sessions.read("isles", "primary"))
    reviewed = tmp_path / "reviewed.json"
    reviewed.write_bytes(canonical(proposal))
    assert run(["--store", str(tmp_path), "publish", "--world-id", "isles",
                "--proposal-file", str(reviewed),
                "--expected-parent-digest", proposal["parent_digest"]]) == 0
    assert forks.inspect("isles", "from-editor")["history_proven"]
    request["choice_id"] = "missing"
    request_path.write_bytes(canonical(request))
    assert run(["--store", str(tmp_path), "preview-file",
                "--request-file", str(request_path)]) == 2
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["ok"] is False


def test_editor_revision_budget_fails_closed():
    source = world()
    source["choices"].append({
        "id": "return", "from": "harbor", "to": "opening",
        "label": "Return to shore", "requires": [], "grants": [],
    })
    prove(source)
    parent = _source_session(source, ["sail", "return"] * 65)
    with pytest.raises(CanonError, match="fork_editor_revision_budget"):
        render_fork_editor(source, parent, "primary")


def test_editor_embedded_json_escapes_html_payload():
    source = world()
    source["choices"][0]["label"] = "</script><img src=x onerror=alert(1)>"
    prove(source)
    parent = new_session(source)
    page = render_fork_editor(source, parent, "primary")
    assert b"<img src=x" not in page
    assert b"Content-Security-Policy" in page
