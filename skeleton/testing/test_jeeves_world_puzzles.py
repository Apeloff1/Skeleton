"""Original puzzle gating, review, custody, HTML and adversarial contracts."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

import pytest

from skeleton.jeeves.worlds.puzzles import (
    PuzzleStore, compile_puzzles_html, edit_puzzles, prove_puzzles,
    validate_puzzles,
)
from skeleton.jeeves.worlds.puzzles_cli import run
from skeleton.jeeves.worlds.tools import invoke_world_tool, manifest
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, canonical, digest, edit, propose,
)


def setup(tmp_path):
    worlds = WorldStore(tmp_path)
    world = propose(
        world_id="clocktower", premise="An original clocktower mystery",
        protagonist="Edda", region="Marble Quay", goal="Repair the bells",
    )
    worlds.publish(world, create=True)
    store = PuzzleStore(str(tmp_path))
    source = store.propose(
        "clocktower", prompt="Solve the bellkeeper's original riddle",
        puzzle_id="bell_riddle", scene="opening",
        question="Which number follows two?", answer="three",
        hint="Count forward", unlock_choice="pursue_goal",
    )
    return worlds, store, world, source


def assert_code(code, callback):
    with pytest.raises(CanonError) as error:
        callback()
    assert error.value.code == code


def test_proposal_requires_review_and_proves_solve_then_travel(tmp_path):
    _, store, world, source = setup(tmp_path)
    proof = prove_puzzles(source, world)
    assert proof["puzzle_witnesses"]["bell_riddle"] == ["solve:bell_riddle"]
    assert proof["gate_witnesses"]["pursue_goal"] == [
        "solve:bell_riddle", "pursue_goal",
    ]
    assert proof["ending_witnesses"]["resolution"] == [
        "solve:bell_riddle", "pursue_goal",
    ]
    assert source["approved"] is False
    assert_code("puzzles_review_required",
                lambda: compile_puzzles_html(source, world))
    assert store.propose(
        "clocktower", prompt="Another riddle", puzzle_id="bell_riddle",
        scene="opening", question="Number after two?", answer="three",
        hint="Count", unlock_choice="pursue_goal",
    )["approved"] is False


def test_persist_approve_compile_verify(tmp_path):
    _, store, world, source = setup(tmp_path)
    first = store.publish("clocktower", source, create=True)
    assert store.inspect("clocktower")["proof"]["world_digest"] == digest(world)
    assert_code("puzzles_review_required",
                lambda: store.compile("clocktower", first))
    approved = store.approve(
        "clocktower", expected_digest=first, review_note="Original author reviewed",
    )
    receipt = store.compile("clocktower", approved)
    assert store.verify("clocktower") == receipt
    content = (tmp_path / receipt["html_file"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == receipt["html_sha256"]
    assert b"connect-src 'none'" in content
    assert b"bell_riddle" in content
    assert_code("puzzles_stale_edit",
                lambda: store.compile("clocktower", first))


def test_tamper_playable_and_receipt(tmp_path):
    _, store, _, source = setup(tmp_path)
    first = store.publish("clocktower", source, create=True)
    approved = store.approve(
        "clocktower", expected_digest=first, review_note="Author approved",
    )
    receipt = store.compile("clocktower", approved)
    html_file = tmp_path / receipt["html_file"]
    html_file.write_bytes(html_file.read_bytes() + b"<!-- altered -->")
    assert_code("puzzles_playable_mismatch", lambda: store.verify("clocktower"))
    store.compile("clocktower", approved)
    (tmp_path / "clocktower.puzzles.receipt.json").write_bytes(b'{"schema":"fake"}')
    assert_code("puzzles_receipt_mismatch", lambda: store.verify("clocktower"))


def test_forged_approval_is_removed_on_save(tmp_path):
    _, store, _, source = setup(tmp_path)
    source["approved"] = True
    source["review_note"] = "Forged"
    published = store.publish("clocktower", source, create=True)
    assert published != digest(source)
    assert store.inspect("clocktower")["puzzles"]["approved"] is False
    assert_code("puzzles_review_required",
                lambda: store.compile("clocktower", published))


def test_revisions_reset_approval_and_invalidate_receipt(tmp_path):
    _, store, world, source = setup(tmp_path)
    first = store.publish("clocktower", source, create=True)
    approved = store.approve(
        "clocktower", expected_digest=first, review_note="Author approved",
    )
    store.compile("clocktower", approved)
    updated = edit_puzzles(
        store.inspect("clocktower")["puzzles"], world,
        {"action": "replace_puzzle", "value": {
            "id": "bell_riddle", "scene": "opening",
            "question": "What is one plus two?", "answer": "three",
            "hint": "Add the numbers", "unlock_choice": "pursue_goal",
        }},
    )
    assert updated["approved"] is False
    revision = store.publish("clocktower", updated, expected_digest=approved)
    assert_code("puzzles_review_required",
                lambda: store.compile("clocktower", revision))
    second = store.approve(
        "clocktower", expected_digest=revision, review_note="Revision reviewed",
    )
    assert_code("puzzles_receipt_mismatch", lambda: store.verify("clocktower"))
    store.compile("clocktower", second)
    assert store.verify("clocktower")["puzzles_digest"] == second


def test_duplicate_id_duplicate_gate_and_bad_answer(tmp_path):
    _, _, world, source = setup(tmp_path)
    duplicate = deepcopy(source)
    duplicate["puzzles"].append(deepcopy(duplicate["puzzles"][0]))
    assert_code("puzzles_duplicate_id",
                lambda: validate_puzzles(duplicate, world))
    invalid = deepcopy(source)
    invalid["puzzles"][0]["answer"] = " three "
    assert_code("puzzles_invalid_answer",
                lambda: validate_puzzles(invalid, world))
    invalid = deepcopy(source)
    invalid["puzzles"][0]["unlock_choice"] = "not_a_choice"
    assert_code("puzzles_invalid_gate",
                lambda: validate_puzzles(invalid, world))


def test_world_revision_invalidates_source_lease(tmp_path):
    _, _, world, source = setup(tmp_path)
    changed = edit(world, {"action": "replace_scene", "value": {
        "id": "opening", "title": "Revised clocktower",
        "narrative": "The bell has been moved",
    }})
    assert_code("puzzles_source_lease_mismatch",
                lambda: prove_puzzles(source, changed))


def test_invalid_edit_and_empty_puzzles_fail_closed(tmp_path):
    _, _, world, source = setup(tmp_path)
    assert_code("puzzles_unsupported_edit",
                lambda: edit_puzzles(source, world, {
                    "action": "run_code", "value": {},
                }))
    assert_code("puzzles_empty",
                lambda: edit_puzzles(source, world, {
                    "action": "remove_puzzle", "value": {"id": "bell_riddle"},
                }))
    assert_code("expected_object",
                lambda: PuzzleStore(str(tmp_path)).publish(
                    "clocktower", [], create=True,
                ))


def test_cli_propose_save_approve_compile_verify(tmp_path, capsys):
    _, _, _, source = setup(tmp_path)
    def cli(*args):
        status = run(["--store", str(tmp_path), *args])
        response = json.loads(capsys.readouterr().out)
        return status, response
    status, proposed = cli(
        "propose", "--world-id", "clocktower",
        "--prompt", "Bellkeeper riddle", "--puzzle-id", "bell_riddle",
        "--scene", "opening", "--question", "Which number follows two?",
        "--answer", "three", "--hint", "Count forward",
        "--unlock-choice", "pursue_goal",
    )
    assert status == 0 and proposed["review_required"] is True
    status, saved = cli(
        "save", "--world-id", "clocktower", "--create",
        "--puzzles-json", json.dumps(source),
    )
    assert status == 0
    status, approved = cli(
        "approve", "--world-id", "clocktower",
        "--expected-digest", saved["puzzles_digest"],
        "--review-note", "Author reviewed",
    )
    assert status == 0
    status, compiled = cli(
        "compile", "--world-id", "clocktower",
        "--expected-digest", approved["puzzles_digest"],
    )
    assert status == 0
    status, verified = cli("verify", "--world-id", "clocktower")
    assert status == 0 and verified["receipt"] == compiled["receipt"]


def test_read_only_jeeves_puzzle_preview(tmp_path):
    _, store, _, source = setup(tmp_path)
    request = {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.puzzles_propose_preview",
        "world_id": "clocktower",
        "args": {
            "prompt": "Bellkeeper riddle", "puzzle_id": "bell_riddle",
            "scene": "opening", "question": "Which number follows two?",
            "answer": "three", "hint": "Count forward",
            "unlock_choice": "pursue_goal",
        },
    }
    preview = invoke_world_tool(str(tmp_path), request)
    assert preview["persisted"] is False and preview["review_required"] is True
    assert not (tmp_path / "clocktower.puzzles.json").exists()
    assert any(x["name"] == request["tool"] and x["read_only"]
               for x in manifest()["tools"])
    store.publish("clocktower", source, create=True)
    request["tool"] = "world.puzzles_preview"
    request["args"] = {}
    assert invoke_world_tool(str(tmp_path), request)["result"]["puzzles"]["approved"] is False


def test_symlink_source_fails_closed(tmp_path):
    _, store, _, source = setup(tmp_path)
    target = tmp_path / "outside.json"
    target.write_bytes(canonical(source))
    (tmp_path / "clocktower.puzzles.json").symlink_to(target)
    with pytest.raises((CanonError, OSError)):
        store.inspect("clocktower")
    assert target.read_bytes() == canonical(source)


def test_offline_puzzle_editor_exports_unapproved_json(tmp_path, capsys):
    _, store, _, source = setup(tmp_path)
    first = store.publish("clocktower", source, create=True)
    editor = store.editor("clocktower", first)
    html_bytes = (tmp_path / editor["html_file"]).read_bytes()
    assert hashlib.sha256(html_bytes).hexdigest() == editor["html_sha256"]
    assert b"connect-src 'none'" in html_bytes
    assert b"Export unapproved puzzle JSON" in html_bytes
    assert b"Review required after offline puzzle edit" in html_bytes
    assert_code("puzzles_stale_edit",
                lambda: store.editor("clocktower", "0" * 64))
    status = run([
        "--store", str(tmp_path), "editor", "--world-id", "clocktower",
        "--expected-digest", first,
    ])
    assert status == 0
    assert json.loads(capsys.readouterr().out)["editor"]["puzzles_digest"] == first
