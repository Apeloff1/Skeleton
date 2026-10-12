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
    BenchmarkCase, ShadowWeightAutomation,
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


@pytest.fixture
def setup(tmp_path):
    knowledge = ReviewedKnowledgeStore(tmp_path / "reviewed.sqlite")
    db = sqlite3.connect(":memory:")
    ledger = DragonHumanReviewLedger(db)
    automation = ShadowWeightAutomation(
        db, knowledge, ledger,
        signing_key=b"isolated-shadow-routing-secret-of-32bytes",
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
        receipts=receipts, at=T1, idle_since=T0,
        hardware=sample(), hardware_now=1000.0,
        consented=True, authorized=True, privacy_clear=True,
    )
    arguments.update(changes)
    result = automation.stage_shadow(
        OWNER, brief(library), source, "note-" + source, **arguments,
    )
    return result, record, receipts, adv


def suite(source="alpha"):
    if source == "alpha":
        cases = ("responsive jumping", "smooth climbing", "jump timing")
    else:
        cases = ("collision physics", "rigidbody constraints", "physics gameplay")
    return tuple(BenchmarkCase(str(i), q, source)
                 for i, q in enumerate(cases))


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
    result = automation.evaluate(OWNER, weight.candidate_id, suite(),
                                 at=T2, authorized=True)
    assert result.accepted
    outcome, review_id = reviewed_promotion(setup, record, adversarial)
    automation.promote(
        OWNER, weight.candidate_id, suite(),
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
        OWNER, weight.candidate_id, suite(), at=T2, authorized=True,
    )
    assert verdict.accepted and verdict.improved >= 1 and verdict.regressed == 0
    assert automation.route(OWNER, "responsive jumping", authorized=True)["source_id"] is None
    promotion, review_id = reviewed_promotion(setup, record, adversarial)
    approved = automation.promote(
        OWNER, weight.candidate_id, suite(),
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
    unrelated = tuple(BenchmarkCase(str(i), q, "alpha")
                      for i, q in enumerate(("castle", "music", "graphics")))
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
    automation.evaluate(OWNER, weight.candidate_id, suite(),
                        at=T2, authorized=True)
    promotion, review_id = reviewed_promotion(setup, record, adversarial)
    with pytest.raises((KeyError, ValueError, PermissionError)):
        automation.promote(
            "other-owner", weight.candidate_id, suite(),
            memory_promotion=promotion, review_id=review_id,
            at=T3, authorized=True,
        )
    with pytest.raises((PermissionError, ValueError)):
        automation.promote(
            OWNER, weight.candidate_id, suite(),
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
    tests = (
        BenchmarkCase("one", "collision physics", "beta"),
        BenchmarkCase("two", "rigidbody constraints", "beta"),
        BenchmarkCase("three", "responsive jumping", "alpha"),
        BenchmarkCase("four", "smooth climbing", "alpha"),
    )
    checked = automation.evaluate(
        OWNER, weight.candidate_id, tests, at="2026-10-12T12:25:00Z",
        authorized=True,
    )
    assert checked.accepted and checked.regressed == 0
    assert checked.before_hits == 2 and checked.after_hits == 4
    assert automation.route(OWNER, "collision physics", authorized=True)["source_id"] is None
