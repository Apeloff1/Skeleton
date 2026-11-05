"""Source-leased clue discovery, spoiler suppression, authoring and replay."""
from __future__ import annotations

import json
import os

import pytest

from skeleton.jeeves.worlds.evidence import (
    EvidenceStore, approve_evidence, compile_evidence, edit_evidence,
    propose_evidence, replay_evidence, solve_evidence, validate_evidence,
)
from skeleton.jeeves.worlds.evidence_cli import run
from skeleton.jeeves.worlds.session import SessionStore
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, canonical, digest, propose, prove,
)


def world():
    data = propose(
        world_id="archive", premise="Find the missing archive key.",
        protagonist="Iris", region="Old library", goal="Open the archive.",
    )
    data["scenes"].insert(1, {
        "id": "library", "title": "Library", "narrative": "A note lies hidden.",
    })
    data["choices"] = [
        {"id": "search", "from": "opening", "to": "library",
         "label": "Search the shelves", "requires": [], "grants": ["note"]},
        {"id": "open", "from": "library", "to": "resolution",
         "label": "Open the archive", "requires": ["note"], "grants": []},
    ]
    prove(data)
    return data


def evidence():
    return propose_evidence(
        world(), prompt="The player must earn the secret clue.",
        clue_id="hidden_note", title="A hidden note",
        detail="The key lies under the clock.", unlock_choice="search",
    )


def test_prompt_review_compile_witness_and_spoiler_guard():
    data = evidence()
    assert replay_evidence(data, world(), [])["visible_clues"] == []
    assert replay_evidence(data, world(), ["search"])["collected"] == ["hidden_note"]
    assert solve_evidence(data, world()) == ("search", "open")
    with pytest.raises(CanonError, match="evidence_review_required"):
        compile_evidence(data, world())
    approved = approve_evidence(data, world(), "Original author reviewed.")
    handoff = compile_evidence(approved, world())
    assert handoff["outcome"]["complete"]
    assert handoff["choice_witness"] == ["search", "open"]


def test_unknown_choice_and_source_revision_rejected():
    data = evidence()
    data["clues"][0]["unlock_choice"] = "fabricated"
    with pytest.raises(CanonError, match="unknown_evidence_choice"):
        validate_evidence(data, world())
    changed = world()
    changed["scenes"][0]["narrative"] = "Changed."
    with pytest.raises(CanonError, match="evidence_world_lease_mismatch"):
        validate_evidence(evidence(), changed)


def test_unearned_transition_rejected():
    with pytest.raises(CanonError, match="session_invalid_transition"):
        replay_evidence(evidence(), world(), ["open"])


def test_dependency_closure_after_earlier_unlock():
    data = evidence()
    data["clues"].append({
        "id": "vault_code", "title": "Vault code",
        "detail": "Clock hands point to the answer.", "unlock_choice": "search",
        "depends_on": ["hidden_note"], "required": True,
    })
    assert validate_evidence(data, world()) is data
    result = replay_evidence(data, world(), ["search", "open"])
    assert result["collected"] == ["hidden_note", "vault_code"]
    assert result["complete"]


def test_cycles_and_missing_dependencies_fail_closed():
    data = evidence()
    data["clues"][0]["depends_on"] = ["missing"]
    with pytest.raises(CanonError, match="invalid_evidence_dependency"):
        validate_evidence(data, world())
    data["clues"][0]["depends_on"] = ["hidden_note"]
    with pytest.raises(CanonError, match="invalid_evidence_dependency"):
        validate_evidence(data, world())


def test_edit_batch_atomic_revokes_approval():
    data = approve_evidence(evidence(), world(), "Reviewed.")
    before = canonical(data)
    updated = edit_evidence(data, world(), {"action": "batch", "value": [
        {"action": "add", "value": {
            "id": "vault_code", "title": "Vault code", "detail": "A code.",
            "unlock_choice": "open", "depends_on": ["hidden_note"],
            "required": True,
        }},
    ]})
    assert updated["approved"] is False
    assert len(updated["clues"]) == 2
    assert canonical(data) == before
    with pytest.raises(CanonError, match="unsupported_evidence_edit"):
        edit_evidence(data, world(), {"action": "exec", "value": {}})


def test_mutually_exclusive_clue_branches_fail_closed():
    source = world()
    source["choices"].append({
        "id": "exit", "from": "opening", "to": "resolution",
        "label": "Leave without searching", "requires": [], "grants": [],
    })
    prove(source)
    data = evidence()
    data["world_digest"] = digest(source)
    data["clues"].append({
        "id": "other_path", "title": "Exit mark", "detail": "Seen on exit.",
        "unlock_choice": "exit", "depends_on": [], "required": True,
    })
    assert validate_evidence(data, source) is data
    with pytest.raises(CanonError, match="evidence_unreachable"):
        solve_evidence(data, source)
    with pytest.raises(CanonError, match="evidence_unreachable"):
        compile_evidence(approve_evidence(data, source, "Reviewed."), source)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_store_cas_compile_verify_player(tmp_path):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    store = EvidenceStore(root)
    first = store.publish("archive", evidence(), create=True)
    with pytest.raises(CanonError, match="stale_evidence"):
        store.publish("archive", evidence(), expected_digest="0" * 64)
    approved = approve_evidence(evidence(), world(), "Reviewed.")
    second = store.publish("archive", approved, expected_digest=first)
    receipt = store.compile("archive", second)
    assert store.verify("archive") == receipt
    session = SessionStore(root)
    session.create("archive", "one")
    assert store.player("archive", "one")["visible_clues"] == []
    old = session.read("archive", "one")
    session.choose("archive", "one", "search", digest(old))
    assert store.player("archive", "one")["visible_clues"][0]["detail"] == (
        "The key lies under the clock.")


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_tamper_receipt_and_source_lease(tmp_path):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    store = EvidenceStore(root)
    approved = approve_evidence(evidence(), world(), "Reviewed.")
    source_digest = store.publish("archive", approved, create=True)
    store.compile("archive", source_digest)
    (root / "archive.evidence.handoff.json").write_text("{}")
    with pytest.raises(CanonError, match="evidence_artifact_mismatch"):
        store.verify("archive")
    (root / "archive.json").write_text(json.dumps({
        **world(), "prompt": "The archive has moved.",
    }))
    with pytest.raises(CanonError, match="evidence_world_lease_mismatch"):
        store.read("archive")


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_cli_full_review_compile_verify(tmp_path, capsys):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    args = ["--store", str(root)]
    assert run(args + [
        "propose", "--world-id", "archive", "--prompt", "Find the clue.",
        "--clue-id", "hidden_note", "--title", "A hidden note",
        "--detail", "Under the clock.", "--unlock-choice", "search",
    ]) == 0
    first = json.loads(capsys.readouterr().out)["evidence_digest"]
    assert run(args + ["approve", "--world-id", "archive",
                       "--expected-digest", first, "--note", "Reviewed."]) == 0
    second = json.loads(capsys.readouterr().out)["evidence_digest"]
    assert run(args + ["compile", "--world-id", "archive",
                       "--expected-digest", second]) == 0
    capsys.readouterr()
    assert run(args + ["verify", "--world-id", "archive"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
