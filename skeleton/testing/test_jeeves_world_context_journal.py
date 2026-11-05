"""Narrative context custody: typed append, private handoff, replay and forgery."""
from __future__ import annotations

import json
import os

import pytest

from skeleton.jeeves.worlds.context_cli import run
from skeleton.jeeves.worlds.context_editor import ContextEditorStore
from skeleton.jeeves.worlds.context_journal import (
    ContextStore, GENESIS, append_entry, compile_context, context_status,
    new_journal, validate_journal,
)
from skeleton.jeeves.worlds.tools import SCHEMA, invoke_world_tool
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, canonical, digest, edit, propose, strict_json,
)


def world():
    return propose(
        world_id="island", premise="A keeper maps a storm-lashed island.",
        protagonist="Ari", region="Beacon Isle", goal="Light the beacon.",
    )


def request(name):
    return {"schema": SCHEMA, "tool": name, "world_id": "island", "args": {}}


def test_empty_journal_is_deterministic_and_private():
    source = world()
    journal = new_journal(source)
    assert journal["head"] == GENESIS
    assert journal["revision"] == 0
    assert validate_journal(journal, source) == journal
    status = context_status(journal, source)
    assert status["note_text_exposed"] is False
    assert status["authenticity"] == "unkeyed_hash_chain_integrity_only"


def test_append_chain_replay_and_non_exposure():
    source = world()
    first = append_entry(
        new_journal(source), source, expected_head=GENESIS,
        kind="canon_rationale", text="The storm explains the beacon delay.",
    )
    assert first["revision"] == 1
    assert first["entries"][0]["prev"] == GENESIS
    second = append_entry(
        first, source, expected_head=first["head"],
        kind="playtest_observation", text="Players need a clearer route.",
    )
    assert second["revision"] == 2
    assert second["head"] != first["head"]
    assert validate_journal(second, source) == second
    assert "Players need a clearer route." not in json.dumps(
        compile_context(second, source))
    assert "The storm explains the beacon delay." not in json.dumps(
        context_status(second, source))
    with pytest.raises(CanonError, match="stale_context_head"):
        append_entry(first, source, expected_head=GENESIS,
                     kind="author_note", text="A new note.")


@pytest.mark.parametrize("change,code", [
    ({"seq": 2}, "context_sequence_invalid"),
    ({"kind": "system_prompt"}, "context_kind_invalid"),
    ({"text": "forged"}, "context_hash_mismatch"),
    ({"prev": "f" * 64}, "context_chain_mismatch"),
    ({"hash": "f" * 64}, "context_hash_mismatch"),
])
def test_forged_entries_fail_closed(change, code):
    source = world()
    data = append_entry(new_journal(source), source, expected_head=GENESIS,
                        kind="author_note", text="A review note.")
    data["entries"][0].update(change)
    with pytest.raises(CanonError, match=code):
        validate_journal(data, source)


def test_reject_duplicate_json_keys_nonfinite_and_unbounded_text():
    with pytest.raises(CanonError, match="duplicate_json_key"):
        strict_json(b'{"kind":"a","kind":"b"}')
    with pytest.raises(CanonError, match="nonfinite_number"):
        strict_json(b'{"x":NaN}')
    with pytest.raises(CanonError, match="invalid_text"):
        append_entry(new_journal(world()), world(), expected_head=GENESIS,
                     kind="author_note", text="x" * 2049)
    with pytest.raises(CanonError, match="context_kind_invalid"):
        append_entry(new_journal(world()), world(), expected_head=GENESIS,
                     kind="private_chain_of_thought", text="Forbidden.")


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_store_create_append_compile_verify_and_private_handoff(tmp_path):
    root = tmp_path / "private"
    source = world()
    WorldStore(root).publish(source, create=True)
    store = ContextStore(root)
    initial = store.create("island")
    assert initial["head"] == GENESIS
    assert store.status("island") == initial
    with pytest.raises(CanonError, match="context_already_exists"):
        store.create("island")
    updated = store.append(
        "island", expected_head=GENESIS, kind="author_note",
        text="Only the operator should read this original note.",
    )
    assert updated["revision"] == 1
    with pytest.raises(CanonError, match="stale_context_head"):
        store.append("island", expected_head=GENESIS,
                     kind="author_note", text="Lost concurrent edit.")
    receipt = store.compile("island", updated["head"])
    assert store.verify("island") == receipt
    assert "Only the operator should read" in (
        root / "island.context.json").read_text()
    assert "Only the operator should read" not in (
        root / "island.context.handoff.json").read_text()
    assert "Only the operator should read" not in (
        root / "island.context.playable.html").read_text()
    assert (root / "island.context.playable.html").read_text().startswith(
        "<!doctype html>")
    assert strict_json((root / "island.context.handoff.json").read_bytes())[
        "private_text_included"] is False
    with pytest.raises(CanonError, match="stale_context_head"):
        store.compile("island", GENESIS)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_replay_detects_tampering_and_stale_world(tmp_path):
    root = tmp_path / "private"
    worlds = WorldStore(root)
    source = world()
    initial = worlds.publish(source, create=True)
    store = ContextStore(root)
    store.create("island")
    current = store.append("island", expected_head=GENESIS,
                           kind="author_note", text="Original note.")
    store.compile("island", current["head"])
    path = root / "island.context.json"
    forged = json.loads(path.read_text())
    forged["entries"][0]["text"] = "Edited without lease."
    path.write_text(json.dumps(forged))
    with pytest.raises(CanonError, match="context_hash_mismatch"):
        store.read("island")
    path.write_bytes(canonical(append_entry(
        new_journal(source), source, expected_head=GENESIS,
        kind="author_note", text="Original note.")))
    revised = edit(source, {"action": "replace_scene", "value": {
        "id": "opening", "title": "Revised beacon",
        "narrative": "The keeper arrives late.",
    }})
    worlds.publish(revised, expected_digest=initial)
    with pytest.raises(CanonError, match="context_world_lease_mismatch"):
        store.read("island")


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_artifact_and_editor_receipts_reject_forgery(tmp_path):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    store = ContextStore(root)
    store.create("island")
    editor = ContextEditorStore(root)
    receipt = editor.render("island", GENESIS)
    assert editor.verify("island") == receipt
    page = (root / "island.context.editor.html").read_text()
    assert "Content-Security-Policy" in page
    assert "connect-src 'none'" in page
    assert "author_note" in page
    assert "Original note." not in page
    compiled = store.compile("island", GENESIS)
    assert store.verify("island") == compiled
    artifact = root / "island.context.handoff.json"
    artifact.write_bytes(artifact.read_bytes() + b"forged")
    with pytest.raises(CanonError, match="context_artifact_mismatch"):
        store.verify("island")
    store.compile("island", GENESIS)
    receipt_file = root / "island.context.receipt.json"
    forged = json.loads(receipt_file.read_text())
    forged["qualification"] = "release_certified"
    receipt_file.write_text(json.dumps(forged))
    with pytest.raises(CanonError, match="context_receipt_mismatch"):
        store.verify("island")
    store.append("island", expected_head=GENESIS,
                 kind="author_note", text="A new note.")
    with pytest.raises(CanonError, match="context_editor_receipt_mismatch"):
        editor.verify("island")


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_symlink_and_fifo_are_not_read_as_context(tmp_path):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    store = ContextStore(root)
    store.create("island")
    source = root / "island.context.json"
    source.unlink()
    source.symlink_to(tmp_path / "missing")
    with pytest.raises((CanonError, OSError)):
        store.read("island")
    source.unlink()
    os.mkfifo(source)
    with pytest.raises(CanonError, match="unsafe_source_file"):
        store.read("island")


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_cli_and_read_only_jeeves_status(tmp_path, capsys):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    base = ["--store", str(root)]
    assert run(base + ["create", "--world-id", "island"]) == 0
    assert json.loads(capsys.readouterr().out)["status"]["head"] == GENESIS
    tool = invoke_world_tool(str(root), request("context.status"))
    assert tool["persisted"] is False
    assert tool["result"]["head"] == GENESIS
    assert "entries" not in tool["result"]
    assert run(base + ["editor", "--world-id", "island",
                       "--expected-head", GENESIS]) == 0
    assert json.loads(capsys.readouterr().out)["editor"]["head"] == GENESIS
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({
        "schema": "jeeves.world.context_append_request.v1",
        "world_id": "island", "expected_head": GENESIS,
        "kind": "canon_rationale", "text": "Original authored note.",
    }))
    assert run(base + ["append", "--world-id", "island",
                       "--operation-file", str(request_file)]) == 0
    updated = json.loads(capsys.readouterr().out)["status"]
    assert updated["revision"] == 1
    assert run(base + ["compile", "--world-id", "island",
                       "--expected-head", updated["head"]]) == 0
    assert json.loads(capsys.readouterr().out)["receipt"]["head"] == updated["head"]
    assert run(base + ["verify", "--world-id", "island"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    assert run(base + ["append", "--world-id", "island",
                       "--operation-file", str(request_file)]) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "stale_context_head"
