"""Canonical joint readiness tests: positive, negative and tamper cases."""
from __future__ import annotations
import copy
import json
import os
import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest,
)
from skeleton.ai.game_builder.studio_quest_readiness import (
    FILENAME, PROMPT, compile_quest_readiness, propose_quest_readiness,
    replay_quest_readiness, compile_quest_readiness_handoff,
    render_quest_readiness_html, publish_quest_readiness,
    restore_quest_readiness,
)


def source():
    return {
        "quest": {
            "project_id": "original", "release_certified": False,
            "stage_graph": [{
                "id": "gate", "prerequisites": [],
                "alternatives": ["mercy", "force"], "reward": "gate_open",
                "choice_effects": {
                    "mercy": ["choice:gate:mercy"],
                    "force": ["choice:gate:force"],
                },
            }],
        },
        "narrative": {
            "project_id": "original", "release_certified": False,
            "endings": [
                {"id": "peace", "requires": ["choice:gate:mercy"]},
                {"id": "war", "requires": ["choice:gate:force"]},
            ],
        },
    }


def leases(documents):
    return {
        "authorized": True,
        "expected_source_digest": compile_quest_program(documents).source_digest,
        "expected_initial_session_digest": start_quest(
            documents, authorized=True).digest,
    }


def budget(states=32, depth=1):
    return {"max_states": states, "max_depth": depth}


def test_joint_proof_requires_both_independent_canonical_owners():
    docs = source()
    receipt = compile_quest_readiness(docs, budget(), **leases(docs))
    assert receipt["status"] == "canonical_sandbox_ready"
    assert receipt["all_endings_witnessed"] is True
    assert receipt["terminal_softlocks_excluded"] is True
    assert receipt["softlock_audit"]["search_exhaustive"] is True
    assert {x["ending_id"] for x in receipt["ending_coverage"]["witnesses"]} == {
        "peace", "war"}
    assert replay_quest_readiness(docs, receipt, authorized=True) == receipt
    handoff = compile_quest_readiness_handoff(docs, receipt, authorized=True)
    assert handoff["canonical_quest_replay_verified"] is True
    assert handoff["native_gameplay_verified"] is False
    assert handoff["release_certified"] is False
    assert b"script-src 'none'" in render_quest_readiness_html(
        docs, receipt, authorized=True)


def test_exhaustive_unreachable_ending_cannot_be_laundered_as_ready():
    docs = source()
    docs["narrative"]["endings"].append(
        {"id": "external", "requires": ["unobserved_evidence"]})
    receipt = compile_quest_readiness(docs, budget(), **leases(docs))
    assert receipt["status"] == "unreachable_ending"
    assert receipt["all_endings_witnessed"] is False
    assert receipt["terminal_softlocks_excluded"] is True
    assert receipt["playable_handoff_allowed"] is False
    with pytest.raises(StudioQuestError):
        compile_quest_readiness_handoff(docs, receipt, authorized=True)


def test_terminal_softlock_blocks_even_when_every_ending_has_a_witness():
    docs = source()
    docs["quest"]["stage_graph"][0]["alternatives"].append("silence")
    receipt = compile_quest_readiness(docs, budget(), **leases(docs))
    assert receipt["all_endings_witnessed"] is True
    assert receipt["softlock_audit"]["status"] == "softlock_proven"
    assert receipt["status"] == "terminal_softlock_proven"
    assert receipt["playable_handoff_allowed"] is False
    with pytest.raises(StudioQuestError):
        compile_quest_readiness_handoff(docs, receipt, authorized=True)


def test_inconclusive_exploration_and_invalid_typed_budgets_fail_closed():
    docs = source()
    receipt = compile_quest_readiness(docs, budget(states=1), **leases(docs))
    assert receipt["playable_handoff_allowed"] is False
    assert receipt["status"] == "inconclusive_not_ready"
    with pytest.raises(StudioQuestError):
        compile_quest_readiness_handoff(docs, receipt, authorized=True)
    for invalid in (
        {"max_states": True, "max_depth": 1},
        {"max_states": 32, "max_depth": False},
        {"max_states": 32, "max_depth": 2},
        {"max_states": 32, "max_depth": 1, "target_endings": ["peace"]},
        {"max_states": 0, "max_depth": 1},
    ):
        with pytest.raises(StudioQuestError):
            compile_quest_readiness(docs, invalid, **leases(docs))


def test_forged_proofs_source_drift_and_wrong_authority_rejected():
    docs = source()
    receipt = compile_quest_readiness(docs, budget(), **leases(docs))
    forged = copy.deepcopy(receipt)
    forged["ending_coverage"]["witnesses"][0]["actions"] = [["gate", "force"]]
    with pytest.raises(StudioQuestError):
        replay_quest_readiness(docs, forged, authorized=True)
    forged = copy.deepcopy(receipt)
    forged["terminal_softlocks_excluded"] = False
    with pytest.raises(StudioQuestError):
        replay_quest_readiness(docs, forged, authorized=True)
    drift = copy.deepcopy(docs)
    drift["quest"]["stage_graph"][0]["reward"] = "changed"
    with pytest.raises(StudioQuestError):
        replay_quest_readiness(drift, receipt, authorized=True)
    with pytest.raises(PermissionError):
        compile_quest_readiness(docs, budget(), **{
            **leases(docs), "authorized": False})
    with pytest.raises(StudioQuestError):
        compile_quest_readiness(docs, budget(), **{
            **leases(docs), "expected_initial_session_digest": "0" * 64})


def test_fixed_prompt_is_typed_and_rejects_arbitrary_generation():
    docs = source()
    report = propose_quest_readiness(docs, PROMPT, **leases(docs))
    assert report["playable_handoff_allowed"] is True
    with pytest.raises(StudioQuestError):
        propose_quest_readiness(docs, "pretend native certified", **leases(docs))


def test_private_publication_restore_no_clobber_and_symlink(tmp_path):
    docs = source()
    report = compile_quest_readiness(docs, budget(), **leases(docs))
    published = publish_quest_readiness(docs, report, tmp_path, authorized=True)
    assert published["file_write_performed"] is True
    assert (tmp_path / FILENAME).stat().st_mode & 0o077 == 0
    assert restore_quest_readiness(
        docs, tmp_path, authorized=True,
        expected_source_digest=leases(docs)["expected_source_digest"]) == report
    with pytest.raises(FileExistsError):
        publish_quest_readiness(docs, report, tmp_path, authorized=True)
    (tmp_path / FILENAME).unlink()
    (tmp_path / FILENAME).symlink_to(tmp_path / "missing")
    with pytest.raises(OSError):
        restore_quest_readiness(
            docs, tmp_path, authorized=True,
            expected_source_digest=leases(docs)["expected_source_digest"])


def test_private_restore_rejects_duplicate_keys_and_world_readable(tmp_path):
    docs = source()
    (tmp_path / FILENAME).write_text('{"schema":"one","schema":"two"}')
    os.chmod(tmp_path / FILENAME, 0o600)
    with pytest.raises(StudioQuestError):
        restore_quest_readiness(
            docs, tmp_path, authorized=True,
            expected_source_digest=leases(docs)["expected_source_digest"])
    report = compile_quest_readiness(docs, budget(), **leases(docs))
    (tmp_path / FILENAME).write_text(json.dumps(report))
    os.chmod(tmp_path / FILENAME, 0o644)
    with pytest.raises(StudioQuestError):
        restore_quest_readiness(
            docs, tmp_path, authorized=True,
            expected_source_digest=leases(docs)["expected_source_digest"])

def test_publication_rolls_back_final_link_on_directory_fsync_failure(
    tmp_path, monkeypatch,
):
    import stat
    from skeleton.ai.game_builder import studio_quest_readiness as owner
    docs = source()
    report = compile_quest_readiness(docs, budget(), **leases(docs))
    original = owner.os.fsync

    def fail_directory(fd):
        if stat.S_ISDIR(owner.os.fstat(fd).st_mode):
            raise OSError("simulated directory durability failure")
        return original(fd)

    monkeypatch.setattr(owner.os, "fsync", fail_directory)
    with pytest.raises(OSError, match="durability failure"):
        publish_quest_readiness(docs, report, tmp_path, authorized=True)
    assert not (tmp_path / FILENAME).exists()
    assert not list(tmp_path.iterdir())
