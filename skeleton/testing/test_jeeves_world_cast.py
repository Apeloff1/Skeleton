"""NPC presence, dialogue preconditions, source custody and playable HTML."""
from __future__ import annotations

import copy
import json
import os

import pytest

from skeleton.jeeves.worlds.cast import (
    CastStore, approve_cast, compile_cast, edit_cast, propose_cast,
    render_cast_html, validate_cast,
)
from skeleton.jeeves.worlds.cast_cli import run
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, canonical, digest, propose, prove,
)


def world():
    source = propose(
        world_id="cinder", premise="A courier crosses the marsh.",
        protagonist="Iris", region="Lantern Marsh", goal="Deliver the message.",
    )
    source["scenes"].insert(1, {
        "id": "ferry", "title": "Old Ferry", "narrative": "The ferryman waits.",
    })
    source["choices"] = [
        {"id": "board", "from": "opening", "to": "ferry", "label": "Board",
         "requires": [], "grants": ["ticket"]},
        {"id": "deliver", "from": "ferry", "to": "resolution",
         "label": "Deliver", "requires": ["ticket"], "grants": []},
    ]
    prove(source)
    return source


def cast():
    return propose_cast(world(), npc_id="ferryman", npc_name="The Ferryman",
                        npc_line="The marsh remembers every promise.")


def line(*, line_id="ferry_reply", scene="ferry", flags=None):
    return {
        "id": line_id, "scene": scene, "speaker": "ferryman", "order": 1,
        "text": "Your ticket is valid.", "requires_flags": flags or [],
    }


def test_original_prompt_to_cast_and_reviewed_playable_handoff():
    source = world()
    data = cast()
    assert data["characters"][0]["name"] == "The Ferryman"
    assert data["approved"] is False
    with pytest.raises(CanonError, match="cast_review_required"):
        compile_cast(data, source)
    approved = approve_cast(data, source, "Original author reviewed dialogue.")
    manifest = compile_cast(approved, source)
    assert manifest["world_proof"]["source_digest"] == digest(source)
    html = render_cast_html(approved, source).decode()
    assert "default-src 'none'" in html
    assert "addEventListener" in html
    assert "eval(" not in html
    assert "innerHTML" not in html
    assert "The Ferryman" in html


def test_cast_edit_batch_preserves_source_and_requires_reapproval():
    source = world()
    data = cast()
    batch = {"action": "batch", "value": [
        {"action": "replace_actor", "value": {
            "id": "ferryman", "name": "The Ferryman", "role": "npc",
            "scenes": ["ferry", "opening"], "traits": ["watchful"],
        }},
        {"action": "add_line", "value": line(flags=["ticket"])},
    ]}
    before = canonical(data)
    updated = edit_cast(data, source, batch)
    assert canonical(data) == before
    assert len(updated["lines"]) == 2
    assert updated["approved"] is False
    assert updated["lines"][1]["requires_flags"] == ["ticket"]


def test_absent_actor_dialogue_rejected():
    source = world()
    data = cast()
    data["lines"].append(line())
    with pytest.raises(CanonError, match="absent_dialogue_speaker"):
        validate_cast(data, source)


def test_unearned_dialogue_flags_rejected():
    source = world()
    data = cast()
    data["lines"][0]["requires_flags"] = ["ticket"]
    with pytest.raises(CanonError, match="unreachable_dialogue_precondition"):
        validate_cast(data, source)


def test_order_collisions_rejected():
    source = world()
    data = cast()
    data["lines"].append({
        "id": "duplicate_order", "scene": "opening", "speaker": "ferryman",
        "order": 0, "text": "Another line.", "requires_flags": [],
    })
    with pytest.raises(CanonError, match="dialogue_order_collision"):
        validate_cast(data, source)


def test_unknown_role_and_unsafe_unicode_rejected():
    source = world()
    data = cast()
    data["characters"][0]["role"] = "system"
    with pytest.raises(CanonError, match="invalid_actor_role"):
        validate_cast(data, source)
    data = cast()
    data["lines"][0]["text"] = "e\u0301"
    with pytest.raises(CanonError, match="noncanonical_unicode"):
        validate_cast(data, source)


def test_duplicate_actor_and_line_ids_rejected():
    source = world()
    data = cast()
    data["characters"].append(copy.deepcopy(data["characters"][0]))
    with pytest.raises(CanonError, match="duplicate_actor"):
        validate_cast(data, source)
    data = cast()
    data["lines"].append(copy.deepcopy(data["lines"][0]))
    with pytest.raises(CanonError, match="duplicate_dialogue_line"):
        validate_cast(data, source)


def test_unsafe_edit_is_pure_and_denied():
    source = world()
    data = cast()
    before = canonical(data)
    with pytest.raises(CanonError, match="unsupported_cast_edit"):
        edit_cast(data, source, {"action": "execute_python", "value": {}})
    assert canonical(data) == before


def test_source_lease_invalidates_after_world_revision():
    source = world()
    data = cast()
    source["scenes"][0]["title"] = "A different marsh"
    with pytest.raises(CanonError, match="cast_world_lease_mismatch"):
        validate_cast(data, source)


def test_html_escapes_hostile_npc_text_and_is_deterministic():
    source = world()
    data = cast()
    data["lines"][0]["text"] = "</script><img src=x onerror=alert(1)>"
    approved = approve_cast(data, source, "Reviewed")
    html = render_cast_html(approved, source).decode()
    assert "</script><img" not in html
    assert "\\u003c/script>" in html
    assert render_cast_html(approved, source) == render_cast_html(
        copy.deepcopy(approved), copy.deepcopy(source))


@pytest.mark.skipif(os.name != "posix", reason="descriptor anchored POSIX custody")
def test_persist_edit_review_compile_verify(tmp_path):
    root = tmp_path / "private"
    worlds = WorldStore(root)
    worlds.publish(world(), create=True)
    store = CastStore(root)
    first = store.publish("cinder", cast(), create=True)
    assert first == digest(store.read("cinder"))
    with pytest.raises(CanonError, match="cast_review_required"):
        store.compile("cinder", first)
    reviewed = approve_cast(cast(), world(), "Reviewed by original author.")
    second = store.publish("cinder", reviewed, expected_digest=first)
    receipt = store.compile("cinder", second)
    assert store.verify("cinder") == receipt
    assert (root / "cinder.cast.playable.html").exists()
    assert (root / "cinder.cast.manifest.json").exists()


@pytest.mark.skipif(os.name != "posix", reason="descriptor anchored POSIX custody")
def test_tampered_playable_is_rejected(tmp_path):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    store = CastStore(root)
    reviewed = approve_cast(cast(), world(), "Reviewed")
    lease = store.publish("cinder", reviewed, create=True)
    store.compile("cinder", lease)
    (root / "cinder.cast.playable.html").write_text("tampered")
    with pytest.raises(CanonError, match="cast_artifact_mismatch"):
        store.verify("cinder")


@pytest.mark.skipif(os.name != "posix", reason="descriptor anchored POSIX custody")
def test_symlinked_cast_file_and_busy_lock_fail_closed(tmp_path):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    outside = tmp_path / "outside"
    outside.write_text(json.dumps(cast()))
    (root / "cinder.cast.json").symlink_to(outside)
    with pytest.raises((CanonError, OSError)):
        CastStore(root).read("cinder")
    (root / "cinder.cast.json").unlink()
    (root / "cinder.lock").write_text("held")
    with pytest.raises(CanonError, match="lease_busy"):
        CastStore(root).publish("cinder", cast(), create=True)


@pytest.mark.skipif(os.name != "posix", reason="descriptor anchored POSIX custody")
def test_cli_author_edit_review_compile_verify(tmp_path, capsys):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    args = ["--store", str(root)]
    assert run(args + ["propose", "--world-id", "cinder",
                       "--npc-id", "ferryman", "--npc-name", "Ferryman",
                       "--npc-line", "Welcome to the marsh."]) == 0
    first = json.loads(capsys.readouterr().out)
    op = tmp_path / "edit.json"
    op.write_text(json.dumps({"action": "replace_line", "value": {
        "id": "opening_line", "scene": "opening", "speaker": "ferryman",
        "order": 0, "text": "A reviewed original line.", "requires_flags": [],
    }}))
    assert run(args + ["edit", "--world-id", "cinder",
                       "--expected-digest", first["cast_digest"],
                       "--operation-file", str(op)]) == 0
    edited = json.loads(capsys.readouterr().out)
    assert edited["review_required"] is True
    assert run(args + ["approve", "--world-id", "cinder",
                       "--expected-digest", edited["cast_digest"],
                       "--note", "Original author approved."]) == 0
    approved = json.loads(capsys.readouterr().out)
    assert run(args + ["compile", "--world-id", "cinder",
                       "--expected-digest", approved["cast_digest"]]) == 0
    receipt = json.loads(capsys.readouterr().out)["receipt"]
    assert run(args + ["verify", "--world-id", "cinder"]) == 0
    assert json.loads(capsys.readouterr().out)["receipt"] == receipt

def test_malformed_actor_role_list_is_a_typed_failure():
    source = world()
    data = cast()
    data["characters"][0]["role"] = ["npc"]
    with pytest.raises(CanonError, match="invalid_actor_role"):
        validate_cast(data, source)
