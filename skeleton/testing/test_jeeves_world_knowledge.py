"""Deterministic, source-backed NPC knowledge and spoiler regression fixtures."""
from __future__ import annotations

import json

import pytest

from skeleton.jeeves.worlds.cast import (
    CastStore, approve_cast, propose_cast,
)
from skeleton.jeeves.worlds.knowledge import (
    KnowledgeStore, approve_knowledge, compile_knowledge,
    edit_knowledge, propose_knowledge, prove_knowledge,
    render_knowledge_html, validate_knowledge,
)
from skeleton.jeeves.worlds.knowledge_cli import run
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, digest, edit, propose,
)


def setup_world(tmp_path):
    world = propose(
        world_id="archive", premise="An original expedition",
        protagonist="Ari", region="The old observatory",
        goal="Restore the sky map",
    )
    WorldStore(tmp_path).publish(world, create=True)
    cast = propose_cast(
        world, npc_id="scribe", npc_name="Archivist",
        npc_line="The star chart is unfinished.",
    )
    cast = approve_cast(cast, world, "Original dialogue reviewed")
    CastStore(tmp_path).publish(world["id"], cast, create=True)
    return world, cast


def setup_knowledge(tmp_path):
    world, cast = setup_world(tmp_path)
    data = propose_knowledge(
        world, cast, prompt="Reveal a newly authored star map clue",
        fact_id="star_map", title="Lost constellation",
        detail="A map of seven invented stars.",
        choice="pursue_goal", speaker="scribe",
    )
    store = KnowledgeStore(tmp_path)
    store.publish(world["id"], data, create=True)
    return world, cast, data, store


def test_author_review_to_playable_receipt_and_replay(tmp_path):
    world, cast, data, store = setup_knowledge(tmp_path)
    assert not data["approved"]
    assert prove_knowledge(data, world, cast)["states_explored"] == 2
    with pytest.raises(CanonError, match="knowledge_review_required"):
        store.compile(world["id"], digest(data))
    reviewed = approve_knowledge(data, world, cast, "Original fact and reveal approved")
    lease = store.publish(world["id"], reviewed, expected_digest=digest(data))
    assert lease == digest(reviewed)
    receipt = store.compile(world["id"], lease)
    assert receipt == store.verify(world["id"])
    before = store.player(world["id"], [])
    after = store.player(world["id"], ["pursue_goal"])
    assert before["visible_facts"] == []
    assert [fact["id"] for fact in after["visible_facts"]] == ["star_map"]
    assert after["scene"] == "resolution"
    assert b"Content-Security-Policy" in render_knowledge_html(reviewed, world, cast)
    assert compile_knowledge(reviewed, world, cast)["proof"]["scope"] == (
        "declared_fact_claims_only"
    )


def test_invalid_replay_and_stale_write_rejected(tmp_path):
    world, cast, data, store = setup_knowledge(tmp_path)
    reviewed = approve_knowledge(data, world, cast, "Approved")
    store.publish(world["id"], reviewed, expected_digest=digest(data))
    with pytest.raises(CanonError, match="knowledge_invalid_replay"):
        store.player(world["id"], ["missing"])
    with pytest.raises(CanonError, match="knowledge_invalid_replay"):
        store.player(world["id"], ["pursue_goal", "pursue_goal"])
    with pytest.raises(CanonError, match="stale_knowledge"):
        store.publish(world["id"], reviewed, expected_digest=digest(data))
    with pytest.raises(CanonError, match="knowledge_already_exists"):
        store.publish(world["id"], reviewed, create=True)


def test_tampered_handoff_fails_closed(tmp_path):
    world, cast, data, store = setup_knowledge(tmp_path)
    reviewed = approve_knowledge(data, world, cast, "Approved")
    lease = store.publish(world["id"], reviewed, expected_digest=digest(data))
    store.compile(world["id"], lease)
    artifact = tmp_path / (world["id"] + ".knowledge.handoff.json")
    artifact.write_bytes(b'{"schema":"forged"}')
    with pytest.raises(CanonError, match="knowledge_artifact_mismatch"):
        store.verify(world["id"])


def test_symlink_custody_refuses_external_source(tmp_path):
    world, cast, data, store = setup_knowledge(tmp_path)
    target = tmp_path.parent / (tmp_path.name + "-external.json")
    target.write_text(json.dumps(data))
    path = tmp_path / (world["id"] + ".knowledge.json")
    path.unlink()
    path.symlink_to(target)
    with pytest.raises((CanonError, OSError)):
        store.read(world["id"])
    assert target.read_text() == json.dumps(data)


def test_unreviewed_edit_cannot_preserve_approval(tmp_path):
    world, cast, data, store = setup_knowledge(tmp_path)
    reviewed = approve_knowledge(data, world, cast, "Approved")
    updated = edit_knowledge(reviewed, world, cast, {
        "action": "replace_fact",
        "value": {
            "id": "star_map", "title": "New constellation",
            "detail": "A newly reviewed authored star map.",
            "initial_knowers": ["scribe"],
        },
    })
    assert updated["approved"] is False
    with pytest.raises(CanonError, match="knowledge_review_required"):
        compile_knowledge(updated, world, cast)
    with pytest.raises(CanonError, match="knowledge_unknown_claim_reference"):
        validate_knowledge({**data, "claims": [
            {"line": "nonexistent", "fact": "star_map"}]}, world, cast)


def test_branch_specific_dialogue_leak_detected(tmp_path):
    world, cast = setup_world(tmp_path)
    branched = edit(world, {
        "action": "add_choice", "value": {
            "id": "alternate", "from": "opening", "to": "resolution",
            "label": "Take a different route", "requires": [], "grants": [],
        },
    })
    actor = dict(cast["characters"][0])
    actor["scenes"] = ["opening", "resolution"]
    new_line = {
        "id": "ending_line", "scene": "resolution", "speaker": "scribe",
        "order": 0, "text": "The map is here.", "requires_flags": [],
    }
    cast = {
        **cast, "world_digest": digest(branched),
        "characters": [actor], "lines": [*cast["lines"], new_line],
    }
    knowledge = propose_knowledge(
        branched, cast, prompt="Author an ending clue",
        fact_id="secret", title="Secret chart", detail="A fictional clue.",
        choice="pursue_goal", speaker="narrator", recipient="scribe",
    )
    knowledge["claims"] = [{"line": "ending_line", "fact": "secret"}]
    with pytest.raises(CanonError, match="knowledge_dialogue_leak"):
        prove_knowledge(knowledge, branched, cast)


def test_unearned_actor_disclosure_detected(tmp_path):
    world, cast = setup_world(tmp_path)
    data = propose_knowledge(
        world, cast, prompt="Reveal an original clue", fact_id="secret",
        title="Secret", detail="A newly invented clue",
        choice="pursue_goal", speaker="narrator",
    )
    data["disclosures"][0]["speaker"] = "scribe"
    with pytest.raises(CanonError, match="knowledge_unearned_disclosure"):
        prove_knowledge(data, world, cast)


def test_cli_roundtrip(tmp_path, capsys):
    world, cast = setup_world(tmp_path)
    command = [
        "--store", str(tmp_path), "propose", "--world-id", world["id"],
        "--prompt", "A clue", "--fact-id", "clue",
        "--title", "The clue", "--detail", "Original detail",
        "--choice", "pursue_goal", "--speaker", "narrator",
    ]
    assert run(command) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["review_required"] is True
    assert run(["--store", str(tmp_path), "approve",
                "--world-id", world["id"],
                "--expected-digest", result["knowledge_digest"],
                "--note", "Reviewed original fact"]) == 0
    lease = json.loads(capsys.readouterr().out)["knowledge_digest"]
    assert run(["--store", str(tmp_path), "compile",
                "--world-id", world["id"],
                "--expected-digest", lease]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert run(["--store", str(tmp_path), "verify",
                "--world-id", world["id"]]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_html_escapes_script_end_and_control_data(tmp_path):
    world, cast = setup_world(tmp_path)
    data = propose_knowledge(
        world, cast, prompt="A new clue", fact_id="script",
        title="A </script> clue", detail="Literal <script>alert(1)</script>",
        choice="pursue_goal", speaker="narrator",
    )
    reviewed = approve_knowledge(data, world, cast, "Reviewed")
    page = render_knowledge_html(reviewed, world, cast).decode()
    assert page.count("</script>") == 2
    assert "\\u003cscript>" in page
    assert "connect-src 'none'" in page


def test_operation_file_symlink_refused(tmp_path, capsys):
    world, cast, data, store = setup_knowledge(tmp_path)
    operation = tmp_path / "operation.json"
    operation.write_text('{"action":"remove_fact","value":{"id":"star_map"}}')
    link = tmp_path / "link.json"
    link.symlink_to(operation)
    assert run(["--store", str(tmp_path), "edit",
                "--world-id", world["id"],
                "--expected-digest", digest(data),
                "--operation-file", str(link)]) == 2
    assert json.loads(capsys.readouterr().out)["ok"] is False
