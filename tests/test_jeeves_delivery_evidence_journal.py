"""Evidence journal: actual source-bound replay, corruption, and delivery scope."""

from dataclasses import replace

import pytest

from skeleton.jeeves.agent.code_delivery_quality import (
    CodeDeliveryQualityReviewer, QualityCheckResult, required_checker_names,
)
from skeleton.jeeves.agent.delivery_evidence_journal import (
    ANSWER_PATH, EvidenceJournalEntry, EvidenceJournalError,
    build_release_evidence_journal, verify_journal_chain,
    verify_release_evidence_journal,
)
from skeleton.jeeves.agent.final_delivery_reviews import (
    ComparativeObjectiveFinalReviewer, ContentReviewResult,
    MeasuredCriterion, SourceProvenance,
)
from skeleton.jeeves.agent.types import Goal, ToolObservation, stable_fingerprint
from skeleton.jeeves.agent.working_context_cycle import WorkingContextCycle


ANSWER = "Implemented an original game component with review evidence."
CODE = {"src/level.py": "def tile(position):\n    return position * 2\n"}
CORE = (
    "modularity", "efficiency", "performance", "cleanliness",
    "maintainability", "machine_friendly",
)


def fixture(kind="code", extras=()):
    goal = Goal(
        "g:release", "Implement game feature" if kind == "game" else (
            "Write an original poem" if kind == "creative" else (
                "Explain why tests matter" if kind == "non_code" else
                "Implement Python code"
            )
        ),
        metadata=(
            {"delivery_kind": kind, "additional_quality_requirements": list(extras)}
            if kind in ("code", "game") else
            ({"delivery_kind": "creative"} if kind == "creative" else {})
        ),
    )
    observations = (
        ToolObservation("lookup:miss", "repository_lookup", True, payload={
            "status": "no_results", "complete": True,
            "query": "legacy path",
        }),
        ToolObservation("lookup:found", "repository_lookup", True, payload={
            "status": "ok", "results": ["src/level.py"],
        }),
    )
    prepared = WorkingContextCycle().prepare(
        goal, observations, refill_text="Continue with source evidence.",
    )
    return goal, observations, prepared


def make_quality(kind="code", *, extras=()):
    def checker(name):
        def check(files):
            return QualityCheckResult(
                name, stable_fingerprint(dict(files)), True,
                "host:" + name + ":" + stable_fingerprint(dict(files))[:16],
            )
        return check

    checkers = {
        name: checker(name)
        for name in required_checker_names(kind, extras)
    }
    receipt = CodeDeliveryQualityReviewer().inspect(
        kind, CODE, checkers=checkers,
        additional_requirements=extras,
    )
    assert receipt.releasable
    return receipt


def make_final(kind, quality=None, *, answer=ANSWER, code=CODE):
    sources = {**(code if kind in ("code", "game") else {}), ANSWER_PATH: answer}
    required = CORE if kind in ("code", "game") else ("originality", "coherence")
    metrics = tuple(MeasuredCriterion(
        axis=axis, unit="score", method="controlled-fixture-v1",
        direction="higher", observed=96, baseline=85, target=90,
        observed_evidence="host:observed:" + axis,
        baseline_evidence="host:baseline:" + axis,
        target_evidence="host:target:" + axis,
        sample_count=8, baseline_sample_count=8,
    ) for axis in required)
    rights = tuple(SourceProvenance(
        path=path, content_digest=stable_fingerprint(content),
        origin="original", rights_evidence="host:origin:" + path,
        permitted_use=True,
    ) for path, content in sources.items())

    def review(stage):
        def run(artifacts, inventory):
            dimensions = (
                ("provenance", "permissions", "license_conditions",
                 "source_similarity")
                if stage == "copyright" else
                ("originality", "substantive_transformation", "canon",
                 "author_voice")
            )
            return ContentReviewResult(
                stage=stage,
                source_digest=stable_fingerprint(dict(artifacts)),
                checker="host:" + stage,
                evidence_ref="host:review:" + stage,
                review_scope="original fixture sources only",
                covered_paths=tuple(artifacts),
                passed=True,
                checked_dimensions=dimensions,
            )
        return run

    report = ComparativeObjectiveFinalReviewer().inspect(
        kind, sources, metrics=metrics, provenance=rights,
        copyright_checker=review("copyright"),
        rewrite_checker=review("creative_rewrite"),
        upstream_quality_digest=quality.digest if quality else None,
    )
    return report, sources


def build(kind="code", *, extras=()):
    goal, observations, prepared = fixture(kind, extras)
    quality = make_quality(kind, extras=extras) if kind in ("code", "game") else None
    final, source = (
        make_final(kind, quality)
        if kind in ("code", "game", "creative") else (None, None)
    )
    ledger = build_release_evidence_journal(
        "run:release", goal, observations, prepared, ANSWER,
        quality=quality, final=final, final_sources=source,
    )
    return ledger, (goal, observations, prepared, ANSWER), (quality, final, source)


@pytest.mark.parametrize("kind,stage_count", (
    ("non_code", 5), ("creative", 10), ("code", 12), ("game", 12),
))
def test_typed_deliveries_have_exact_ordered_replayable_receipts(kind, stage_count):
    journal, context, approvals = build(kind)
    assert journal.kind == kind
    assert journal.milestone_count == stage_count
    assert journal.stages[0].stage == "context"
    assert journal.stages[-1].stage == "release"
    assert len(journal.fingerprint) == 64
    assert len(journal.release_digest) == 64
    assert journal.stages[0].serial == "JEL-000001-P000000001"
    assert journal.stages[-1].sequence == stage_count
    assert [e["stage"] for e in journal.exported_receipts()] == list(journal.stage_names)
    verify_journal_chain(journal)
    verify_release_evidence_journal(
        journal, *context, quality=approvals[0],
        final=approvals[1], final_sources=approvals[2],
    )


def test_exactly_same_valid_inputs_create_reproducible_release_fingerprint():
    first, _, _ = build("code")
    second, _, _ = build("code")
    assert first == second
    assert first.fingerprint == second.fingerprint
    assert first.exported_receipts() == second.exported_receipts()


def test_requested_additional_checker_cannot_disappear_in_replay():
    journal, context, approvals = build("code", extras=("memory_safety",))
    assert journal.milestone_count == 12
    verify_release_evidence_journal(
        journal, *context, quality=approvals[0],
        final=approvals[1], final_sources=approvals[2],
    )
    stronger_goal = replace(
        context[0],
        metadata={"delivery_kind": "code",
                  "additional_quality_requirements": [
                      "memory_safety", "offline_resume",
                  ]},
    )
    with pytest.raises(ValueError):
        verify_release_evidence_journal(
            journal, stronger_goal, *context[1:],
            quality=approvals[0], final=approvals[1],
            final_sources=approvals[2],
        )


def test_code_cannot_skip_quality_or_final_review():
    goal, obs, prepared = fixture("code")
    with pytest.raises(EvidenceJournalError, match="quality receipt"):
        build_release_evidence_journal(
            "r1", goal, obs, prepared, ANSWER,
        )
    quality = make_quality()
    with pytest.raises(EvidenceJournalError, match="copyright/rewrite"):
        build_release_evidence_journal(
            "r1", goal, obs, prepared, ANSWER, quality=quality,
        )


def test_creative_requires_rights_review_even_without_code_quality():
    goal, obs, prepared = fixture("creative")
    with pytest.raises(EvidenceJournalError, match="copyright/rewrite"):
        build_release_evidence_journal(
            "r2", goal, obs, prepared, ANSWER,
        )


def test_non_code_cannot_launder_unrelated_quality_or_creative_receipts():
    goal, obs, prepared = fixture("non_code")
    with pytest.raises(EvidenceJournalError, match="unrequested"):
        build_release_evidence_journal(
            "r3", goal, obs, prepared, ANSWER,
            quality=make_quality(),
        )


@pytest.mark.parametrize("edit", (
    lambda j: replace(j, run_id="different"),
    lambda j: replace(j, kind="creative"),
    lambda j: replace(j, answer_digest="0" * 64),
    lambda j: replace(j, goal_digest="0" * 64),
    lambda j: replace(j, source_digest="0" * 64),
    lambda j: replace(j, release_digest="0" * 64),
    lambda j: replace(j, stages=tuple(reversed(j.stages))),
    lambda j: replace(j, stages=j.stages[:-1]),
))
def test_corrupted_checkpoint_fails_replay_even_if_chain_is_well_formed(edit):
    journal, context, approvals = build("code")
    with pytest.raises(EvidenceJournalError):
        verify_release_evidence_journal(
            edit(journal), *context,
            quality=approvals[0], final=approvals[1],
            final_sources=approvals[2],
        )


@pytest.mark.parametrize("attribute", (
    "serial", "sequence", "stage", "subject_digest",
    "previous_digest", "digest", "evidence_ref",
))
def test_every_entry_field_is_tamper_evident(attribute):
    journal, _, _ = build("code")
    first = journal.stages[0]
    modification = {
        "serial": "JEL-CHANGED",
        "sequence": 2,
        "stage": "copyright",
        "subject_digest": "a" * 64,
        "previous_digest": "a" * 64,
        "digest": "a" * 64,
        "evidence_ref": "host:fake",
    }[attribute]
    forged = replace(journal, stages=(
        replace(first, **{attribute: modification}), *journal.stages[1:],
    ))
    with pytest.raises(EvidenceJournalError):
        verify_journal_chain(forged)


def test_sha_validator_and_page_serial_guard():
    with pytest.raises(EvidenceJournalError, match="64-digit"):
        EvidenceJournalEntry.create(1, "quality", "not-a-hash",
                                    "host:verified", "0" * 64)
    with pytest.raises(EvidenceJournalError, match="bounded"):
        EvidenceJournalEntry.create(1, "quality", "a" * 64,
                                    " ", "0" * 64)
    with pytest.raises(EvidenceJournalError, match="counter"):
        EvidenceJournalEntry.create(1_000_000_000, "quality", "a" * 64,
                                    "host:verified", "0" * 64)


def test_stale_quality_files_cannot_be_replaced_inside_final_review():
    journal, context, approvals = build("code")
    source = dict(approvals[2])
    source["src/level.py"] = "def tile(position):\n    return 999\n"
    with pytest.raises(ValueError):
        verify_release_evidence_journal(
            journal, *context, quality=approvals[0],
            final=approvals[1], final_sources=source,
        )


def test_final_answer_edit_invalidates_originality_and_release_chain():
    journal, context, approvals = build("creative")
    altered_answer = context[-1] + " UNREVIEWED"
    with pytest.raises(EvidenceJournalError, match="exact answer"):
        verify_release_evidence_journal(
            journal, *context[:-1], altered_answer,
            final=approvals[1], final_sources=approvals[2],
        )


def test_context_observation_mutation_invalidates_journal_replay():
    journal, context, approvals = build("code")
    altered = replace(context[1][-1], payload={"status": "ok", "forged": True})
    with pytest.raises(ValueError):
        verify_release_evidence_journal(
            journal, context[0], (context[1][0], altered), *context[2:],
            quality=approvals[0], final=approvals[1],
            final_sources=approvals[2],
        )


def test_reordered_source_evidence_does_not_produce_false_green():
    journal, context, approvals = build("code")
    forged_prepared = replace(
        context[2],
        original_digests=tuple(reversed(context[2].original_digests)),
    )
    with pytest.raises(ValueError, match="observation digest mismatch"):
        verify_release_evidence_journal(
            journal, context[0], context[1], forged_prepared, context[3],
            quality=approvals[0], final=approvals[1],
            final_sources=approvals[2],
        )
