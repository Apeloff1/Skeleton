"""Executable Dragon IF/OR/AND/BUT and shadow-to-approved-weight workflow."""
from dataclasses import replace
import sqlite3

import pytest

from skeleton.ai.game_builder.reviewed_knowledge import (
    ReviewedDocument, ReviewedKnowledgeStore, ReviewedNote,
)
from skeleton.ai.webcrawler.dragon_adversarial_review_worker import (
    execute_adversarial_review,
)
from skeleton.ai.webcrawler.dragon_analysis_chains import (
    AnalysisLayer, LayerReceipt, DEFAULT_CHAIN,
)
from skeleton.ai.webcrawler.dragon_analysis_execution import LayerDispatch
from skeleton.ai.webcrawler.dragon_conditional_automation import (
    ConditionalRule, SHADOW_RULE, VETOES, evaluate_trigger,
)
from skeleton.ai.webcrawler.dragon_human_review import (
    DragonHumanReviewLedger, ReviewerPrincipal,
)
from skeleton.ai.webcrawler.dragon_knowledge_manifest import canonical_knowledge_id
from skeleton.ai.webcrawler.dragon_knowledge_normalization_worker import (
    NormalizedKnowledge, normalization_records_fingerprint,
)
from skeleton.ai.webcrawler.dragon_memory_promotion_worker import (
    execute_memory_promotion,
)
from skeleton.ai.webcrawler.dragon_resource_session import HardwareSample
from skeleton.ai.webcrawler.dragon_shadow_weight_automation import (
    BenchmarkCase, ShadowWeightAutomation, seal_holdout,
)

OWNER = "dragon-owner"
T0 = "2026-10-12T12:00:00Z"
T1 = "2026-10-12T12:10:00Z"
T2 = "2026-10-12T12:15:00Z"
T3 = "2026-10-12T12:20:00Z"


def digest(value):
    import hashlib
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def document(source, group, statement, *, at=T0, stance="supports"):
    return ReviewedDocument(
        OWNER, source, f"https://{source}.example.org/research",
        "Original reviewed game mechanics", "Movement enables controllers.",
        at, "licensed_design_reference", ("design_reference",), "reviewer-1",
        True,
        (ReviewedNote(
            f"note-{source}", "movement", statement, 0, 8,
            stance, 975000, group, ("movement",),
        ),),
    )


def scrutiny(label):
    """Produce a typed, linked 10-stage chain for a deterministic integration test.

    Real deployments use the executable workers; these minimal receipts model
    their outputs without pretending synthetic tests have run production AI.
    """
    receipts = []
    for i, spec in enumerate(DEFAULT_CHAIN[:8]):
        inputs = () if i == 0 else (receipts[-1].output_fingerprint,)
        receipts.append(LayerReceipt(
            spec.layer, inputs, digest(f"{label}:real-stage:{i}"), 2, True,
        ))
    identity = NormalizedKnowledge(
        "", "hypothesis-" + label, "dragon.game-knowledge.v1",
        "supported", .97, "empirically_calibrated_probability",
        "a" * 64, receipts[-1].output_fingerprint, "resolved_support",
    )
    record = replace(identity, knowledge_id=canonical_knowledge_id(identity))
    normalization = LayerReceipt(
        AnalysisLayer.KNOWLEDGE_NORMALIZATION,
        (receipts[-1].output_fingerprint,),
        normalization_records_fingerprint(
            (receipts[-1].output_fingerprint,), (record,),
        ), 2, True,
    )
    receipts.append(normalization)
    dispatched = LayerDispatch(
        AnalysisLayer.ADVERSARIAL_REVIEW,
        (normalization.output_fingerprint,), "adversarial_worker", "1",
    )
    adversarial = execute_adversarial_review(
        dispatched, (record,), normalization_receipt=normalization,
        authorized=True,
    )
    assert adversarial.receipt.passed
    receipts.append(adversarial.receipt)
    return record, tuple(receipts), adversarial


def adversarial_dispatch_for(receipts):
    return LayerDispatch(
        AnalysisLayer.ADVERSARIAL_REVIEW,
        (receipts[8].output_fingerprint,), "adversarial_worker", "1",
    )


@pytest.fixture
def setup(tmp_path):
    knowledge = ReviewedKnowledgeStore(tmp_path / "reviewed.sqlite")
    db = sqlite3.connect(":memory:")
    ledger = DragonHumanReviewLedger(db)
    automation = ShadowWeightAutomation(
        db, knowledge, ledger,
        signing_key=b"isolated-shadow-routing-secret-of-32bytes",
        holdout_key=b"trusted-benchmark-evaluator-service-key-32b",
    )
    for args in (
        ("alpha", "independent-a",
         "Responsive jump timing and smooth climbing controls."),
        ("beta", "independent-b",
         "Collision physics and rigidbody constraints for gameplay."),
    ):
        knowledge.import_document(
            document(*args), expected_parent_digest=None, authorized=True,
        )
    try:
        yield automation, knowledge, db, ledger
    finally:
        knowledge.close()
        db.close()


def brief(knowledge):
    return knowledge.build_brief(
        OWNER, "movement", authorized=True, min_independent_groups=2,
    )


def sample(pressure=.1):
    return HardwareSample(1024 * 1024 * 1024, 8, pressure, .85,
                          True, False, 1000.0)


def offer(setup, source="alpha", **changes):
    automation, library, _, _ = setup
    record, receipts, adv = scrutiny(source)
    arguments = dict(
        normalized_knowledge_id=record.knowledge_id,
        normalized_records=(record,), adversarial_output=adv,
        adversarial_dispatch=adversarial_dispatch_for(receipts),
        receipts=receipts, at=T1, idle_since=T0,
        hardware=sample(), hardware_now=1000.0,
        consented=True, authorized=True, privacy_clear=True,
    )
    arguments.update(changes)
    result = automation.stage_shadow(
        OWNER, brief(library), source, "note-" + source, **arguments,
    )
    return result, record, receipts, adv


def suite(setup, source="alpha", *, controls=()):
    _, knowledge, _, _ = setup
    if source == "alpha":
        queries = ("responsive jumping", "smooth climbing", "jump timing")
    else:
        queries = ("collision physics", "rigidbody constraints", "physics gameplay")
    cases = tuple(BenchmarkCase(str(i), q, source)
                  for i, q in enumerate(queries))
    cases += (
        BenchmarkCase("abstain-a", "ocean currents satellite", "_abstain"),
        BenchmarkCase("abstain-b", "distant astronomy nebulae", "_abstain"),
    )
    cases += tuple(BenchmarkCase("control-" + str(i), q, sid)
                   for i, (q, sid) in enumerate(controls))
    return seal_holdout(
        OWNER, knowledge.snapshot_root(OWNER, authorized=True),
        "independent-evaluator", cases,
        created_at=T0, expires_at="2026-10-13T00:00:00Z",
        evaluator_key=b"trusted-benchmark-evaluator-service-key-32b",
    )


def reviewed_promotion(setup, record, adversarial):
    automation, _, _, ledger = setup
    principal = ReviewerPrincipal(
        "human-reviewer", "company-idp", "user-1", 100.0, "b" * 64,
    )
    decision, human = ledger.review(
        OWNER, adversarial, reviewer_id="human-reviewer",
        approved=True, reviewed_at=1200.0,
        rationale="Independent scrutiny and verified holdout utility.",
        authorized=True, records=(record,), reviewer_principal=principal,
        principal_verifier=lambda p: p == principal,
    )
    output = execute_memory_promotion(
        LayerDispatch(AnalysisLayer.MEMORY_PROMOTION,
                      (human.output_fingerprint,), "memory_worker", "1"),
        (record,), human_receipt=human, human_decision=decision,
        surviving_knowledge_ids=(record.knowledge_id,),
        authorized=True,
    )
    assert len(output.promoted) == 1
    return output, decision.review_id


def complete(setup):
    automation, *_ = setup
    weight, record, receipts, adversarial = offer(setup)
    result = automation.evaluate(OWNER, weight.candidate_id, suite(setup),
                                 at=T2, authorized=True)
    assert result.accepted
    outcome, review_id = reviewed_promotion(setup, record, adversarial)
    automation.promote(
        OWNER, weight.candidate_id, suite(setup),
        memory_promotion=outcome, review_id=review_id,
        at=T3, authorized=True,
    )
    return weight


def test_if_or_and_but_has_strict_short_circuit_vetoes_and_unknown_fails_closed():
    fact = {name: False for name in VETOES}
    fact.update({
        "task_relevant": True, "adjacent_relevant": False,
        "revision_changed": False, "novel": True, "reviewed": True,
        "rights_checked": True, "source_current": True,
        "independent_groups": True, "analysis_passed": True,
        "adversarial_passed": True, "owner_authorized": True,
        "consented": True, "idle": True, "resource_admitted": True,
    })
    first = evaluate_trigger(SHADOW_RULE, fact)
    assert first.admitted
    assert first == evaluate_trigger(SHADOW_RULE, fact)
    denied = evaluate_trigger(SHADOW_RULE, {**fact, "privacy_risk": True})
    assert not denied.admitted
    assert "but_veto_or_unknown:privacy_risk" in denied.reasons
    unknown = evaluate_trigger(
        SHADOW_RULE, {k: v for k, v in fact.items() if k != "retracted"},
    )
    assert not unknown.admitted
    assert "but_veto_or_unknown:retracted" in unknown.reasons
    with pytest.raises(ValueError):
        evaluate_trigger(SHADOW_RULE, {**fact, "reviewed": 1})
    with pytest.raises(ValueError):
        ConditionalRule(("novel",), ("reviewed",), but_none=("reviewed",))


def test_verified_acquisition_enters_shadow_not_production_until_review(setup):
    automation, *_ = setup
    weight, record, _, adversarial = offer(setup)
    assert len(weight.terms) > 0
    assert automation.active_weights(OWNER, authorized=True) == ()
    assert automation.route(OWNER, "responsive jumping", authorized=True)["source_id"] is None
    history = automation.history(OWNER, weight.candidate_id, authorized=True)
    assert len(history) == 1
    assert history[0].after == "shadow"
    assert history[0].improvement.startswith("(")
    verdict = automation.evaluate(
        OWNER, weight.candidate_id, suite(setup), at=T2, authorized=True,
    )
    assert verdict.accepted and verdict.improved >= 1 and verdict.regressed == 0
    assert automation.route(OWNER, "responsive jumping", authorized=True)["source_id"] is None
    promotion, review_id = reviewed_promotion(setup, record, adversarial)
    approved = automation.promote(
        OWNER, weight.candidate_id, suite(setup),
        memory_promotion=promotion, review_id=review_id,
        at=T3, authorized=True,
    )
    assert approved == weight
    assert automation.route(OWNER, "responsive jumping", authorized=True) == {
        "schema": "skeleton.dragon.approved_sparse_routing.v1",
        "source_id": "alpha", "active_weights": 1,
        "neural_parameters_modified": False,
        "memory_promotion_authorized": False,
    }
    history = automation.history(OWNER, weight.candidate_id, authorized=True)
    assert [x.after for x in history] == ["shadow", "tested", "active"]
    assert all(x.improvement.startswith("(") for x in history)
    assert all(x.at.endswith("Z") for x in history)
    assert len({x.digest for x in history}) == 3


def test_failed_benchmark_does_not_leave_quarantine(setup):
    automation, *_ = setup
    weight, _, _, _ = offer(setup)
    unrelated = seal_holdout(
        OWNER, setup[1].snapshot_root(OWNER, authorized=True),
        "independent-evaluator",
        (BenchmarkCase("one", "castle", "alpha"),
         BenchmarkCase("two", "music", "alpha"),
         BenchmarkCase("abstain-a", "distant astronomy nebulae", "_abstain"),
         BenchmarkCase("abstain-b", "ocean currents satellite", "_abstain"),
         BenchmarkCase("five", "graphics", "_abstain")),
        created_at=T0, expires_at="2026-10-13T00:00:00Z",
        evaluator_key=b"trusted-benchmark-evaluator-service-key-32b",
    )
    poor = automation.evaluate(
        OWNER, weight.candidate_id, unrelated, at=T2, authorized=True,
    )
    assert not poor.accepted and poor.improved == 0
    assert len(automation.history(OWNER, weight.candidate_id, authorized=True)) == 1
    with pytest.raises(PermissionError, match="no evaluated"):
        automation.promote(
            OWNER, weight.candidate_id, unrelated,
            memory_promotion=None, review_id="0" * 64,
            at=T3, authorized=True,
        )


@pytest.mark.parametrize("changes", [
    {"consented": False},
    {"authorized": False},
    {"privacy_clear": False},
    {"idle_since": "2026-10-12T12:09:59Z"},
    {"hardware": sample(.99)},
    {"hardware_now": 1010.0},
])
def test_shadow_but_vetoes_genuinely_block_bad_acquisitions(setup, changes):
    automation, *_ = setup
    with pytest.raises((PermissionError, ValueError)):
        offer(setup, **changes)
    assert automation.active_weights(OWNER, authorized=True) == ()


def test_wrong_review_owner_or_record_cannot_approve_shadow(setup):
    automation, *_ = setup
    weight, record, _, adversarial = offer(setup)
    automation.evaluate(OWNER, weight.candidate_id, suite(setup),
                        at=T2, authorized=True)
    promotion, review_id = reviewed_promotion(setup, record, adversarial)
    with pytest.raises((KeyError, ValueError, PermissionError)):
        automation.promote(
            "other-owner", weight.candidate_id, suite(setup),
            memory_promotion=promotion, review_id=review_id,
            at=T3, authorized=True,
        )
    with pytest.raises((PermissionError, ValueError)):
        automation.promote(
            OWNER, weight.candidate_id, suite(setup),
            memory_promotion=promotion, review_id="a" * 64,
            at=T3, authorized=True,
        )


def test_active_weight_revokes_instantly_and_deletion_is_auditable(setup):
    automation, *_ = setup
    weight = complete(setup)
    automation.revoke(
        OWNER, weight.candidate_id, at="2026-10-12T12:25:00Z",
        reason="manual_rollback", authorized=True,
    )
    assert automation.route(OWNER, "responsive jumping", authorized=True)["source_id"] is None
    assert [x.after for x in automation.history(
        OWNER, weight.candidate_id, authorized=True,
    )] == ["shadow", "tested", "active", "revoked"]
    automation.revoke(
        OWNER, weight.candidate_id, at="2026-10-12T12:30:00Z",
        reason="manual_rollback", authorized=True,
    )
    assert len(automation.history(OWNER, weight.candidate_id, authorized=True)) == 4


def test_signed_row_tamper_fails_closed(setup):
    automation, _, db, _ = setup
    weight = complete(setup)
    db.execute(
        "UPDATE dragon_shadow_weights SET stage='shadow' "
        "WHERE owner=? AND candidate_id=?", (OWNER, weight.candidate_id),
    )
    db.commit()
    with pytest.raises(ValueError, match="integrity"):
        automation.active_weights(OWNER, authorized=True)


def test_signed_audit_history_tamper_fails_closed(setup):
    automation, _, db, _ = setup
    weight = complete(setup)
    db.execute(
        "DELETE FROM dragon_shadow_weight_events "
        "WHERE owner=? AND candidate_id=? AND seq=2",
        (OWNER, weight.candidate_id),
    )
    db.commit()
    with pytest.raises(ValueError):
        automation.history(OWNER, weight.candidate_id, authorized=True)


def test_new_source_revision_invalidates_active_routing_before_live_use(setup):
    automation, knowledge, _, _ = setup
    weight = complete(setup)
    parent = knowledge.history(OWNER, "alpha", authorized=True)[-1].revision_digest
    updated = document(
        "alpha", "independent-a", "Responsive jumping revamped.",
        at="2026-10-12T12:30:00Z",
    )
    knowledge.import_document(
        updated, expected_parent_digest=parent, authorized=True,
    )
    assert automation.route(OWNER, "responsive jumping", authorized=True)["source_id"] is None
    assert automation.active_weights(OWNER, authorized=True) == ()


def test_different_approved_baseline_must_be_rebenchmarked(setup):
    automation, *_ = setup
    complete(setup)
    weight, record, _, adversarial = offer(setup, "beta")
    tests = suite(setup, "beta", controls=(
        ("responsive jumping", "alpha"),
        ("smooth climbing", "alpha"),
    ))
    checked = automation.evaluate(
        OWNER, weight.candidate_id, tests, at="2026-10-12T12:25:00Z",
        authorized=True,
    )
    assert checked.accepted and checked.regressed == 0
    assert checked.before_hits == 4 and checked.after_hits == 7
    assert automation.route(OWNER, "collision physics", authorized=True)["source_id"] is None


def test_orchestration_stages_then_activates_only_after_human_ledger_review(setup):
    from skeleton.ai.webcrawler.dragon_nest_research_scheduler import (
        IdleResearchPlan, ResearchAssignment,
    )
    from skeleton.ai.webcrawler.dragon_shadow_weight_coordinator import (
        ReviewedAcquisition, run_shadow_automation,
    )
    automation, library, _, _ = setup
    record, receipts, adversarial = scrutiny("alpha")
    plan = IdleResearchPlan(
        OWNER, T1, (
            ResearchAssignment(
                "article", "alpha", "https://alpha.example.org/research",
                "task", 120,
            ),
        ), "worker_must_review", 1, 0,
    )
    candidate = ReviewedAcquisition(
        "alpha", "note-alpha", "movement", record.knowledge_id,
        (record,), receipts, adversarial,
        adversarial_dispatch_for(receipts), suite(setup),
    )
    first = run_shadow_automation(
        automation, library, plan, (candidate,),
        now=T1, idle_since=T0, hardware=sample(), hardware_now=1000,
        consented=True, authorized=True, privacy_clear=True,
    )
    assert first.staged == 1 and first.benchmarked == 1
    assert first.activated == 0
    assert first.items[0].state == "tested"
    assert first.items[0].reason == "awaiting_independent_human_promotion"
    assert automation.route(
        OWNER, "responsive jumping", authorized=True,
    )["source_id"] is None
    promoted_memory, review_id = reviewed_promotion(setup, record, adversarial)
    ready = replace(candidate, promoted_memory=promoted_memory,
                    human_review_id=review_id)
    second = run_shadow_automation(
        automation, library, plan, (ready,),
        now=T1, idle_since=T0, hardware=sample(), hardware_now=1000,
        consented=True, authorized=True, privacy_clear=True,
    )
    assert second.activated == 1
    assert second.items[0].state == "active"
    assert automation.route(
        OWNER, "responsive jumping", authorized=True,
    )["source_id"] == "alpha"
    assert second.neural_training_authorized is False
    assert second.execution_authorized is False


def test_orchestration_rejects_unscheduled_or_duplicate_reviewed_sources(setup):
    from skeleton.ai.webcrawler.dragon_nest_research_scheduler import (
        IdleResearchPlan, ResearchAssignment,
    )
    from skeleton.ai.webcrawler.dragon_shadow_weight_coordinator import (
        ReviewedAcquisition, run_shadow_automation,
    )
    automation, library, _, _ = setup
    record, receipts, adversarial = scrutiny("alpha")
    plan = IdleResearchPlan(
        OWNER, T1, (
            ResearchAssignment(
                "article", "alpha", "https://alpha.example.org/research",
                "task", 100,
            ),
        ), "needs_worker", 1, 0,
    )
    item = ReviewedAcquisition(
        "beta", "note-beta", "movement", record.knowledge_id,
        (record,), receipts, adversarial,
        adversarial_dispatch_for(receipts),
    )
    options = dict(now=T1, idle_since=T0, hardware=sample(),
                   hardware_now=1000, consented=True,
                   authorized=True, privacy_clear=True)
    with pytest.raises(PermissionError, match="unscheduled"):
        run_shadow_automation(
            automation, library, plan, (item,), **options,
        )
    item = replace(item, source_id="alpha", note_id="note-alpha")
    with pytest.raises(ValueError, match="duplicate"):
        run_shadow_automation(
            automation, library, plan, (item, item), **options,
        )
    with pytest.raises(ValueError, match="clock"):
        run_shadow_automation(
            automation, library, plan, (item,), **{**options, "now": T2},
        )
    swapped = replace(
        plan, assignments=(
            replace(plan.assignments[0],
                    url="https://beta.example.org/research"),
        ),
    )
    with pytest.raises(PermissionError, match="canonical reviewed source"):
        run_shadow_automation(
            automation, library, swapped, (item,), **options,
        )
    assert automation.active_weights(OWNER, authorized=True) == ()


def test_forged_memory_promotion_fingerprint_cannot_activate_shadow(setup):
    from skeleton.ai.webcrawler.dragon_memory_promotion_worker import (
        MemoryPromotionOutput,
    )
    from skeleton.ai.webcrawler.dragon_analysis_chains import LayerReceipt, AnalysisLayer
    from skeleton.ai.webcrawler.dragon_memory_promotion_worker import PromotedKnowledge
    from skeleton.ai.game_builder.contracts import canonical_digest
    automation, *_ = setup
    weight, record, _, adversarial = offer(setup)
    automation.evaluate(OWNER, weight.candidate_id, suite(setup),
                        at=T2, authorized=True)
    output, review_id = reviewed_promotion(setup, record, adversarial)
    genuine = output.promoted[0]
    fake = replace(genuine, promotion_fingerprint="f" * 64)
    forged_output = replace(
        output,
        promoted=(fake,),
        receipt=replace(
            output.receipt,
            output_fingerprint=canonical_digest([vars(fake)]),
        ),
    )
    with pytest.raises(PermissionError, match="approval/knowledge"):
        automation.promote(
            OWNER, weight.candidate_id, suite(setup),
            memory_promotion=forged_output, review_id=review_id,
            at=T3, authorized=True,
        )
    assert automation.active_weights(OWNER, authorized=True) == ()
    assert automation.history(
        OWNER, weight.candidate_id, authorized=True,
    )[-1].after == "tested"


def test_invalid_holdout_signature_or_baseline_controls_cannot_grant_approval(setup):
    automation, *_ = setup
    weight, _, _, _ = offer(setup)
    original = suite(setup)
    forged = replace(original, seal="f" * 64)
    with pytest.raises(ValueError, match="signature"):
        automation.evaluate(
            OWNER, weight.candidate_id, forged, at=T2, authorized=True,
        )
    contaminated = replace(
        original,
        cases=original.cases[:-1] + (
            BenchmarkCase("abstain-b", "movement", "_abstain"),
        ),
    )
    with pytest.raises(ValueError, match="signature"):
        automation.evaluate(
            OWNER, weight.candidate_id, contaminated, at=T2, authorized=True,
        )
    assert automation.history(
        OWNER, weight.candidate_id, authorized=True,
    )[-1].after == "shadow"


def test_holdout_expiry_denies_promotion_even_after_initial_usefulness(setup):
    automation, *_ = setup
    weight, record, _, adversarial = offer(setup)
    signed = suite(setup)
    accepted = automation.evaluate(
        OWNER, weight.candidate_id, signed, at=T2, authorized=True,
    )
    assert accepted.accepted
    promotion, review_id = reviewed_promotion(setup, record, adversarial)
    with pytest.raises(ValueError, match="timing"):
        automation.promote(
            OWNER, weight.candidate_id, signed,
            memory_promotion=promotion, review_id=review_id,
            at="2026-10-13T00:00:00Z", authorized=True,
        )
    assert automation.active_weights(OWNER, authorized=True) == ()


def test_negative_canaries_detect_noise_poisoning_in_shadow_retrieval(setup):
    automation, library, _, _ = setup
    weight, _, _, _ = offer(setup)
    cases = (
        BenchmarkCase("a", "responsive jumping", "alpha"),
        BenchmarkCase("b", "smooth climbing", "alpha"),
        BenchmarkCase("c", "jump timing", "alpha"),
        BenchmarkCase("d", "movement", "_abstain"),
        BenchmarkCase("e", "distant galaxy astronomy", "_abstain"),
    )
    poisoned = seal_holdout(
        OWNER, library.snapshot_root(OWNER, authorized=True),
        "independent-evaluator", cases,
        created_at=T0, expires_at="2026-10-13T00:00:00Z",
        evaluator_key=b"trusted-benchmark-evaluator-service-key-32b",
    )
    result = automation.evaluate(
        OWNER, weight.candidate_id, poisoned, at=T2, authorized=True,
    )
    assert not result.accepted
    assert result.regressed == 1
    assert result.improved >= 1
    assert automation.active_weights(OWNER, authorized=True) == ()


def test_unreviewed_ontology_mismatch_cannot_advance_stage(setup):
    automation, library, _, _ = setup
    record, receipts, adversarial = scrutiny("alpha")
    forged = replace(record, ontology_version="incompatible.ontology")
    with pytest.raises(ValueError, match="normalized evidence|calibrated|bound"):
        automation.stage_shadow(
            OWNER, brief(library), "alpha", "note-alpha",
            normalized_knowledge_id=record.knowledge_id,
            normalized_records=(forged,),
            receipts=receipts, adversarial_output=adversarial,
            adversarial_dispatch=adversarial_dispatch_for(receipts),
            at=T1, idle_since=T0, hardware=sample(), hardware_now=1000,
            consented=True, authorized=True, privacy_clear=True,
        )
    assert automation.active_weights(OWNER, authorized=True) == ()


def test_health_counts_active_and_detects_source_root_drift(setup):
    automation, knowledge, _, _ = setup
    weight = complete(setup)
    healthy = automation.registry_health(OWNER, authorized=True)
    assert healthy["total"] == 1
    assert healthy["stages"]["active"] == 1
    assert healthy["routable_active"] == 1
    assert healthy["stale_candidate_ids"] == ()
    assert healthy["neural_training_authorized"] is False
    history_digest = healthy["history_digest"]
    parent = knowledge.history(OWNER, "alpha", authorized=True)[-1].revision_digest
    knowledge.import_document(
        document("alpha", "independent-a",
                 "Responsive jumping revised with new controls.",
                 at="2026-10-12T12:30:00Z"),
        expected_parent_digest=parent, authorized=True,
    )
    stale = automation.registry_health(OWNER, authorized=True)
    assert stale["stages"]["active"] == 1
    assert stale["routable_active"] == 0
    assert weight.candidate_id in stale["stale_candidate_ids"]
    assert stale["history_digest"] == history_digest
    with pytest.raises(PermissionError):
        automation.registry_health(OWNER, authorized=False)


def test_compiled_sparse_postings_equal_original_integer_scoring(setup):
    from collections import Counter
    from skeleton.ai.webcrawler.dragon_almanac_weights import WORD
    from skeleton.ai.webcrawler.dragon_shadow_weight_automation import (
        _compile_postings, _rank_postings, _route,
    )
    automation, *_ = setup
    complete(setup)
    active = automation.active_weights(OWNER, authorized=True)
    index = _compile_postings(active)
    for query in (
        "movement jumping", "responsive movement climbing",
        "distant astronomy", "smooth climbing", "MIXED movement timing",
        "motion unrelated",
    ):
        scores = Counter()
        tokens = set(WORD.findall(query.casefold()))
        for item in active:
            total = sum(value for term, value in item.terms if term in tokens)
            if total:
                scores[item.source_id] += total
        expected = min(scores, key=lambda sid: (-scores[sid], sid)) if scores else None
        assert _route(active, query) == expected
        assert _rank_postings(index, query) == expected


def test_signed_audit_cannot_be_rewritten_to_illegal_transition(setup):
    import hmac
    import json
    from hashlib import sha256
    from skeleton.ai.game_builder.contracts import canonical_json
    from skeleton.ai.webcrawler.dragon_shadow_weight_automation import _audit
    automation, _, db, _ = setup
    weight = complete(setup)
    record = db.execute(
        "SELECT payload,stage,benchmark,approval_id,head,mac "
        "FROM dragon_shadow_weights WHERE owner=? AND candidate_id=?",
        (OWNER, weight.candidate_id),
    ).fetchone()
    raw, stage, benchmark, approval_id, head, mac = record
    events = [
        json.loads(row[0]) for row in db.execute(
            "SELECT payload FROM dragon_shadow_weight_events "
            "WHERE owner=? AND candidate_id=? ORDER BY seq",
            (OWNER, weight.candidate_id),
        )
    ]
    assert len(events) == 3
    first_digest = events[0]["digest"]
    # A database writer with even the HMAC key cannot create an impossible
    # shadow->active transition and disguise it as routine progression.
    second = _audit(
        OWNER, weight.candidate_id, 2, events[1]["at"],
        "shadow", "active", "transition",
        "(illegally skipped benchmark)", first_digest,
    )
    third = _audit(
        OWNER, weight.candidate_id, 3, events[2]["at"],
        "active", "active", "transition",
        "(fabricated continuation)", second.digest,
    )
    for seq, value in ((2, second), (3, third)):
        db.execute(
            "UPDATE dragon_shadow_weight_events SET payload=? "
            "WHERE owner=? AND candidate_id=? AND seq=?",
            (canonical_json(vars(value)), OWNER, weight.candidate_id, seq),
        )
    forged_mac = automation._mac(
        OWNER, weight.candidate_id, raw, stage, benchmark,
        approval_id, third.digest,
    )
    db.execute(
        "UPDATE dragon_shadow_weights SET head=?,mac=? "
        "WHERE owner=? AND candidate_id=?",
        (third.digest, forged_mac, OWNER, weight.candidate_id),
    )
    db.commit()
    with pytest.raises(ValueError, match="verified|transition"):
        automation.registry_health(OWNER, authorized=True)
