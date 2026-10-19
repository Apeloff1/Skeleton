"""Host-only pre-delivery working-memory and evidence receipt regressions."""

from dataclasses import replace

import pytest

from skeleton.jeeves.agent.types import EvidenceKind, EvidenceRef, Goal, ToolObservation
from skeleton.jeeves.agent.working_context_cycle import (
    CycleReceipt,
    IntegrityVerifier,
    PageClicker,
    ScopeVerifier,
    WorkingContextCycle,
    is_no_found,
    verify_delivery,
)


def goal():
    return Goal("goal:working", "Find the current game build failure",
                success_criteria=("Identify blocker",), constraints=("Do not invent logs",))


def miss(call="search-1"):
    return ToolObservation(
        call_id=call, tool_name="search_repo", ok=True,
        payload={"status": "no_results", "query": "old engine module", "results": []},
    )


def hit(call="search-2"):
    return ToolObservation(
        call_id=call, tool_name="search_repo", ok=True,
        payload={"status": "ok", "query": "build failure", "results": [{"path": "issue.py"}]},
    )


def test_compacts_only_typed_misses_and_retains_successful_context():
    found = hit()
    missing = miss()
    audit = WorkingContextCycle().prepare(
        goal(), [missing, found], refill_text="Continue inspecting build evidence."
    )
    assert [item.call_id for item in audit.active_observations] == ["search-2"]
    assert len(audit.notes) == 1
    assert audit.notes[0].call_id == "search-1"
    assert "do not infer global nonexistence" in audit.notes[0].text
    assert audit.notes[0].scope == "old engine module"
    assert audit.page_count == 3
    assert audit.receipts[0].serial == "JVS-000001-P000001"
    assert audit.receipts[-1].action == "delivery_audit_pending"
    assert "current game build failure" not in audit.notes[0].text
    assert "Continue inspecting" in audit.prompt_note()
    assert len(verify_delivery(audit, goal(), (missing, found))) == 2


def test_404_compacted_but_denials_timeouts_and_unscoped_empty_payload_not():
    assert is_no_found(ToolObservation("m1", "lookup", False, error="404 Not Found"))
    assert not is_no_found(ToolObservation("m2", "lookup", False, error="403 permission denied; not found"))
    assert not is_no_found(ToolObservation("m3", "lookup", False, error="timeout; no results"))
    assert not is_no_found(ToolObservation("m4", "search_repo", True, payload={"results": []}))
    assert not is_no_found(ToolObservation("m5", "search_repo", True,
                                          payload={"status": "no_results", "partial": True}))
    assert not is_no_found(ToolObservation("m6", "search_repo", True,
                                          payload={"found": False, "complete": False}))
    assert is_no_found(ToolObservation("m7", "search_repo", True,
                                      payload={"found": False, "complete": True}))


def test_unabridged_source_is_unchanged_and_replayable():
    observed = [miss(), hit()]
    originals = [x.payload for x in observed]
    result = WorkingContextCycle().prepare(goal(), observed)
    assert [x.payload for x in observed] == originals
    assert len(result.original_digests) == 2
    IntegrityVerifier.verify(result, goal(), observed)
    assert len(result.active_observations) == 1
    with pytest.raises(ValueError, match="digest mismatch"):
        IntegrityVerifier.verify(result, goal(), [miss(), hit("changed")])


def test_dual_verifiers_detect_separate_receipt_and_scope_tampering():
    observed = (miss(), hit())
    result = WorkingContextCycle().prepare(goal(), observed)
    forged = replace(result, receipts=(replace(result.receipts[0], previous="bad"),) +
                     result.receipts[1:])
    with pytest.raises(ValueError, match="chained receipt"):
        IntegrityVerifier.verify(forged, goal(), observed)
    forged_note = replace(result.notes[0], scope="the entire repository")
    forged = replace(result, notes=(forged_note,))
    with pytest.raises(ValueError, match="scope"):
        ScopeVerifier.verify(forged, goal(), observed)
    with pytest.raises(ValueError, match="original goal"):
        verify_delivery(result, Goal("goal:working", "Invent a different task"), observed)


def test_scope_verifier_prevents_unqualified_global_nonexistence():
    observed = (miss(), hit())
    prepared = WorkingContextCycle().prepare(goal(), observed)
    with pytest.raises(ValueError, match="unqualified nonexistence"):
        verify_delivery(prepared, goal(), observed, answer="The game engine does not exist.")
    verify_delivery(prepared, goal(), observed,
                    answer="That search returned no matches; I used other build evidence.")


def test_no_misses_no_context_loss_or_invented_receipts():
    observed = (hit(),)
    prepared = WorkingContextCycle().prepare(goal(), observed, refill_text="ignored")
    assert prepared.active_observations == observed
    assert not prepared.notes and not prepared.receipts
    assert prepared.page_count == 0
    assert prepared.prompt_note() == ""
    verify_delivery(prepared, goal(), observed)


def test_capacity_fail_closed_and_serials_are_monotonic():
    with pytest.raises(ValueError, match="capacity"):
        WorkingContextCycle(max_notes=1).prepare(goal(), (miss("m1"), miss("m2")))
    pages = PageClicker()
    for _ in range(35):
        pages.click()
    assert pages.click() == "JVS-000010-P000036"
    assert pages.count == 36


def test_duplicate_ids_rejected_before_compaction():
    with pytest.raises(ValueError, match="duplicate"):
        WorkingContextCycle().prepare(goal(), (miss(), miss()))


def test_refill_is_bounded():
    prepared = WorkingContextCycle(max_refill_chars=128).prepare(
        goal(), (miss(),), refill_text="x" * 4096
    )
    assert len(prepared.refill) == 128
    verify_delivery(prepared, goal(), (miss(),))

def test_long_sequence_rolls_older_notes_out_of_prompt_but_keeps_receipts():
    observations = tuple(miss(f"miss-{i}") for i in range(40))
    prepared = WorkingContextCycle().prepare(goal(), observations)
    active_note = prepared.prompt_note()
    assert len(prepared.notes) == 40
    assert len(prepared.receipts) == 42
    assert '"older_note_count":24' in active_note
    assert '"total_note_count":40' in active_note
    assert "miss-0" not in active_note
    assert "miss-39" not in active_note  # Raw IDs remain in typed retained notes.
    assert prepared.notes[0].call_id == "miss-0"
    assert prepared.notes[-1].call_id == "miss-39"
    verify_delivery(prepared, goal(), observations)

def test_rehashed_but_false_receipt_event_is_rejected():
    observations = (miss(), hit())
    original = WorkingContextCycle().prepare(goal(), observations)
    receipts = []
    previous = "0" * 64
    for prior in original.receipts:
        action = "wrong_action" if not receipts else prior.action
        updated = CycleReceipt.issue(
            prior.sequence, prior.serial, action, prior.subject_digest, previous
        )
        receipts.append(updated)
        previous = updated.digest
    forged = replace(original, receipts=tuple(receipts))
    with pytest.raises(ValueError, match="bind the declared event"):
        IntegrityVerifier.verify(forged, goal(), observations)


def test_retained_observation_payload_and_evidence_cannot_be_replaced_by_id():
    source = hit()
    scoped = (miss(), source)
    prepared = WorkingContextCycle().prepare(goal(), scoped)
    swapped = replace(source, payload={"status": "ok", "results": ["forged"]})
    altered = replace(prepared, active_observations=(swapped,))
    with pytest.raises(ValueError, match="active evidence"):
        IntegrityVerifier.verify(altered, goal(), scoped)
    with pytest.raises(ValueError, match="retained observation source"):
        ScopeVerifier.verify(altered, goal(), scoped)

    citation = EvidenceRef(
        evidence_id="ev:123", kind=EvidenceKind.TOOL, source="git:commit",
        fingerprint="a" * 64, observed_at=10.0, confidence=0.9,
    )
    witnessed = replace(source, evidence=(citation,))
    evidence_scope = (miss(), witnessed)
    checked = WorkingContextCycle().prepare(goal(), evidence_scope)
    forged_citation = replace(citation, fingerprint="b" * 64)
    corrupted = replace(checked, active_observations=(
        replace(witnessed, evidence=(forged_citation,)),
    ))
    with pytest.raises(ValueError, match="active evidence"):
        IntegrityVerifier.verify(corrupted, goal(), evidence_scope)
    with pytest.raises(ValueError, match="retained observation source"):
        ScopeVerifier.verify(corrupted, goal(), evidence_scope)


def test_original_goal_metadata_is_authoritative_for_delivery_gates():
    original = Goal(
        "goal:working", "Build a game", metadata={"delivery_kind": "game"},
    )
    prepared = WorkingContextCycle().prepare(original, (miss(),))
    verify_delivery(prepared, original, (miss(),))
    lowered = replace(original, metadata={"delivery_kind": "non_code"})
    with pytest.raises(ValueError, match="original goal"):
        verify_delivery(prepared, lowered, (miss(),))


@pytest.mark.parametrize("negative", (
    {"status": "no_results", "results": [{"path": "found.py"}]},
    {"status": "no_results", "next_cursor": "page-2", "results": []},
    {"status": "no_matches", "has_more": True},
    {"found": False, "complete": False},
    {"status": "not_found", "complete": False},
    {"status": "no_results", "items": [{"id": 1}]},
    {"status": "no_results", "results": "invalid collection"},
))
def test_incomplete_or_contradictory_negative_results_cannot_be_compacted(negative):
    observation = ToolObservation(
        "search-partial", "search_repo", True, payload=negative,
    )
    assert not is_no_found(observation)
    prepared = WorkingContextCycle().prepare(goal(), (observation,))
    assert not prepared.notes
    assert prepared.active_observations == (observation,)
    verify_delivery(prepared, goal(), (observation,))
    # A forged note for a contradictory result is rejected by the separate
    # source-scope verifier even when the tool says 'no_results'.
    prior = WorkingContextCycle().prepare(goal(), (miss(),))
    forged = replace(prepared, notes=(
        replace(prior.notes[0], call_id="search-partial"),
    ))
    with pytest.raises(ValueError, match="independently confirmed no-found"):
        ScopeVerifier.verify(forged, goal(), (observation,))


def test_compaction_savings_and_input_types_cannot_be_forged():
    observed = (miss(), hit())
    prepared = WorkingContextCycle().prepare(goal(), observed)
    with pytest.raises(ValueError, match="space accounting"):
        IntegrityVerifier.verify(
            replace(prepared, freed_chars=prepared.freed_chars + 9999),
            goal(), observed,
        )
    with pytest.raises(TypeError, match="ToolObservation"):
        WorkingContextCycle().prepare(goal(), (object(),))
