"""Host-only pre-delivery working-memory and evidence receipt regressions."""

from dataclasses import replace

import pytest

from skeleton.jeeves.agent.types import Goal, ToolObservation
from skeleton.jeeves.agent.working_context_cycle import (
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
