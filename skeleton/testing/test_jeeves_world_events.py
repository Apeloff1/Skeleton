"""End-to-end source review, deterministic event closure and hostile inputs."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

import pytest

from skeleton.jeeves.worlds.events import (
    EventStore, compile_events_html, edit_events, prove_events,
)
from skeleton.jeeves.worlds.events_cli import run
from skeleton.jeeves.worlds.tools import invoke_world_tool, manifest
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, digest, propose,
)


def fixture(tmp_path):
    world = propose(
        world_id="bells", premise="An original town of living bells",
        protagonist="Mara", region="North Pier", goal="Wake the tower",
    )
    WorldStore(tmp_path).publish(world, create=True)
    store = EventStore(str(tmp_path))
    source = store.propose(
        "bells", prompt="The clock rings when Mara enters",
        event_id="first_chime", scene="opening",
        description="The brass bells stir", requires=[], grants=["bell_awake"],
    )
    return world, store, source


def reject(code, callback):
    with pytest.raises(CanonError) as exc:
        callback()
    assert exc.value.code == code


def test_typed_prompt_proof_and_review(tmp_path):
    world, store, source = fixture(tmp_path)
    proof = prove_events(source, world)
    assert proof["event_witnesses"]["first_chime"] == ["event:first_chime"]
    assert proof["ending_witnesses"]["resolution"] == [
        "event:first_chime", "pursue_goal",
    ]
    assert source["approved"] is False
    reject("events_review_required", lambda: compile_events_html(source, world))
    assert store.propose(
        "bells", prompt="Again", event_id="first_chime", scene="opening",
        description="The bell rings", requires=[], grants=["bell_awake"],
    )["approved"] is False


def test_cascading_event_order_and_flag_proof(tmp_path):
    world, _, source = fixture(tmp_path)
    second = {
        "id": "a_second", "scene": "opening",
        "description": "The second bell answers",
        "requires": ["bell_awake"], "grants": ["answer_heard"],
    }
    source["events"] = [second, source["events"][0]]
    proof = prove_events(source, world)
    assert proof["event_witnesses"]["a_second"] == [
        "event:first_chime", "event:a_second",
    ]
    assert proof["ending_witnesses"]["resolution"] == [
        "event:first_chime", "event:a_second", "pursue_goal",
    ]


def test_publish_approve_compile_and_verify(tmp_path):
    _, store, source = fixture(tmp_path)
    first = store.publish("bells", source, create=True)
    assert store.inspect("bells")["proof"]["events_digest"] == first
    reject("events_review_required", lambda: store.compile("bells", first))
    approved = store.approve(
        "bells", expected_digest=first, review_note="Author reviewed",
    )
    receipt = store.compile("bells", approved)
    assert store.verify("bells") == receipt
    content = (tmp_path / receipt["html_file"]).read_bytes()
    assert sha256(content).hexdigest() == receipt["html_sha256"]
    assert b"connect-src 'none'" in content
    assert b"event:first_chime" not in content  # trace constructed at runtime
    reject("events_stale_edit", lambda: store.compile("bells", first))


def test_forged_approval_and_stale_edit_fail_closed(tmp_path):
    world, store, source = fixture(tmp_path)
    source["approved"] = True
    source["review_note"] = "Forged"
    first = store.publish("bells", source, create=True)
    assert store.inspect("bells")["events"]["approved"] is False
    reject("events_review_required", lambda: store.compile("bells", first))
    approved = store.approve(
        "bells", expected_digest=first, review_note="Author approved",
    )
    changed = edit_events(
        store.inspect("bells")["events"], world,
        {"action": "replace", "value": {
            "id": "first_chime", "scene": "opening",
            "description": "A different original chime",
            "requires": [], "grants": ["bell_awake"],
        }},
    )
    assert changed["approved"] is False
    reject("events_stale_edit", lambda: store.publish(
        "bells", changed, expected_digest=first,
    ))
    new_digest = store.publish("bells", changed, expected_digest=approved)
    reject("events_review_required", lambda: store.compile("bells", new_digest))


def test_unreachable_event_duplicate_and_invalid_flags(tmp_path):
    world, _, source = fixture(tmp_path)
    invalid = deepcopy(source)
    invalid["events"][0]["requires"] = ["impossible"]
    reject("events_unreachable_events", lambda: prove_events(invalid, world))
    invalid = deepcopy(source)
    invalid["events"].append(deepcopy(invalid["events"][0]))
    reject("events_ids_not_canonical", lambda: prove_events(invalid, world))
    invalid = deepcopy(source)
    invalid["events"][0]["grants"] = ["z", "a"]
    reject("flags_not_canonical", lambda: prove_events(invalid, world))
    invalid = deepcopy(source)
    invalid["events"][0]["scene"] = "unknown"
    reject("events_unknown_scene", lambda: prove_events(invalid, world))


def test_playable_and_receipt_tampering(tmp_path):
    _, store, source = fixture(tmp_path)
    first = store.publish("bells", source, create=True)
    approved = store.approve("bells", expected_digest=first, review_note="Reviewed")
    receipt = store.compile("bells", approved)
    playable = tmp_path / receipt["html_file"]
    playable.write_bytes(playable.read_bytes() + b"<!-- injected -->")
    reject("events_playable_mismatch", lambda: store.verify("bells"))
    store.compile("bells", approved)
    (tmp_path / "bells.events.receipt.json").write_bytes(b'{"schema":"fake"}')
    reject("events_receipt_mismatch", lambda: store.verify("bells"))


def test_editor_lease_cli_and_readonly_jeeves(tmp_path, capsys):
    _, store, source = fixture(tmp_path)
    first = store.publish("bells", source, create=True)
    editor = store.editor("bells", first)
    assert (tmp_path / editor["html_file"]).exists()
    reject("events_stale_edit", lambda: store.editor("bells", "0" * 64))
    args = ["--store", str(tmp_path), "inspect", "--world-id", "bells"]
    assert run(args) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    names = {item["name"] for item in manifest()["tools"]}
    assert {"world.events_preview", "world.events_propose_preview"} <= names
    response = invoke_world_tool(str(tmp_path), {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.events_preview", "world_id": "bells", "args": {},
    })
    assert response["persisted"] is False
    assert response["result"]["events"]["approved"] is False
    assert response["result_digest"] == digest(response["result"])


def test_symlink_source_is_rejected(tmp_path):
    _, store, source = fixture(tmp_path)
    store.publish("bells", source, create=True)
    name = tmp_path / "bells.events.json"
    target = tmp_path / "other.json"
    target.write_bytes(name.read_bytes())
    name.unlink()
    name.symlink_to(target)
    with pytest.raises((CanonError, OSError)):
        store.inspect("bells")


def test_non_object_source_and_script_breakout(tmp_path):
    world, store, source = fixture(tmp_path)
    reject("expected_object", lambda: store.publish("bells", [], create=True))
    source["events"][0]["description"] = "</script><script>alert(1)</script>"
    first = store.publish("bells", source, create=True)
    approved = store.approve("bells", expected_digest=first, review_note="Reviewed")
    receipt = store.compile("bells", approved)
    content = (tmp_path / receipt["html_file"]).read_bytes()
    assert b"</script><script>alert(1)" not in content
    assert b"\\u003c/script>" in content
    assert store.verify("bells") == receipt


def test_reject_duplicate_json_keys_and_nonfinite_cli(tmp_path, capsys):
    _, store, _ = fixture(tmp_path)
    command = ["--store", str(tmp_path), "save", "--world-id", "bells",
               "--create", "--events-json", '{"schema":"a","schema":"b"}']
    assert run(command) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "duplicate_json_key"
    command[-1] = '{"n":1e999}'
    assert run(command) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "nonfinite_number"
