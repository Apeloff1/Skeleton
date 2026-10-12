"""Mother-to-shadow integration uses actual canonical normalized scrutiny."""
from __future__ import annotations

from dataclasses import replace
import sqlite3
from hashlib import sha256

import pytest

from skeleton.ai.webcrawler.dragon_adversarial_review_worker import execute_adversarial_review
from skeleton.ai.webcrawler.dragon_analysis_chains import (
    AnalysisLayer, DEFAULT_CHAIN, LayerReceipt,
)
from skeleton.ai.webcrawler.dragon_analysis_execution import LayerDispatch
from skeleton.ai.webcrawler.dragon_human_review import DragonHumanReviewLedger
from skeleton.ai.webcrawler.dragon_knowledge_manifest import canonical_knowledge_id
from skeleton.ai.webcrawler.dragon_knowledge_normalization_worker import (
    NormalizedKnowledge, normalization_records_fingerprint,
)
from skeleton.ai.webcrawler.dragon_mother_shadow_handoff import run_mother_to_shadow
from skeleton.ai.webcrawler.dragon_nest_research_scheduler import (
    IdleResearchPlan, ResearchAssignment,
)
from skeleton.ai.webcrawler.dragon_resource_session import HardwareSample
from skeleton.ai.webcrawler.dragon_shadow_weight_automation import ShadowWeightAutomation
from skeleton.ai.webcrawler.dragon_shadow_weight_coordinator import ReviewedAcquisition

from test_ai_webcrawler_dragon_mother_glean_matrix import (
    OWNER, T0, T1, T2, scenario,
)


def staged_record():
    receipts = []
    for i, spec in enumerate(DEFAULT_CHAIN[:8]):
        before = () if i == 0 else (receipts[-1].output_fingerprint,)
        digest = sha256(f"stage:{i}:mother".encode()).hexdigest()
        receipts.append(LayerReceipt(spec.layer, before, digest, 3, True))
    raw = NormalizedKnowledge(
        "", "mother-hypothesis", "dragon.game-knowledge.v1", "supported",
        .98, "empirically_calibrated_probability", "a" * 64,
        receipts[-1].output_fingerprint, "resolved_support",
    )
    record = replace(raw, knowledge_id=canonical_knowledge_id(raw))
    normalized = LayerReceipt(
        AnalysisLayer.KNOWLEDGE_NORMALIZATION,
        (receipts[-1].output_fingerprint,),
        normalization_records_fingerprint(
            (receipts[-1].output_fingerprint,), (record,)
        ), 3, True,
    )
    receipts.append(normalized)
    dispatch = LayerDispatch(
        AnalysisLayer.ADVERSARIAL_REVIEW, (normalized.output_fingerprint,),
        "real_adversarial_replay_worker", "1",
    )
    adversarial = execute_adversarial_review(
        dispatch, (record,), normalization_receipt=normalized, authorized=True,
    )
    receipts.append(adversarial.receipt)
    return record, tuple(receipts), adversarial, dispatch


@pytest.fixture
def pipeline(scenario):
    library, nest, acquisitions, ledger, _ = scenario
    db = sqlite3.connect(":memory:")
    reviewers = DragonHumanReviewLedger(db)
    automation = ShadowWeightAutomation(
        db, library, reviewers,
        signing_key=b"mother-shadow-trust-store-key-32-byte-long",
        holdout_key=b"independent-mother-holdout-key-32-byte-long",
    )
    try:
        yield (library, nest, acquisitions, ledger, automation)
    finally:
        db.close()


def package(pipeline):
    library, nest, acquisitions, ledger, automation = pipeline
    item = acquisitions[0]
    record, receipts, adv, dispatch = staged_record()
    plan = IdleResearchPlan(
        OWNER, T2, (
            ResearchAssignment(
                "article", item.source_id, "https://alpha.example.org/research",
                "task", 125,
            ),
        ), "needs_canonical_worker_admission", 1, 0,
    )
    candidate = ReviewedAcquisition(
        "alpha", "note-alpha", "movement", record.knowledge_id,
        (record,), receipts, adv, dispatch,
    )
    hardware = HardwareSample(
        1024 * 1024 * 1024, 8, .1, .85, True, False, 1000.0,
    )
    options = dict(
        now=T2, idle_since=T1, hardware=hardware,
        hardware_now=1000, consented=True, background_allowed=True,
        owner_authorized=True, privacy_clear=True,
    )
    return plan, candidate, options


def test_real_mother_insight_selects_child_for_shadow_not_active_weights(pipeline):
    library, nest, acquisitions, ledger, automation = pipeline
    plan, candidate, options = package(pipeline)
    handoff = run_mother_to_shadow(
        ledger, automation, library, nest, plan, (candidate,),
        (acquisitions[0],), **options,
    )
    assert handoff.mother.hypotheses
    assert handoff.insight_priority == ("alpha",)
    assert handoff.shadow is not None
    assert handoff.shadow.staged == 1
    assert handoff.shadow.activated == 0
    assert handoff.shadow.items[0].state == "shadow"
    assert handoff.neural_training_authorized is False
    state = automation.registry_health(OWNER, authorized=True)
    assert state["stages"]["shadow"] == 1
    assert state["stages"]["active"] == 0
    assert len(ledger.history(OWNER, authorized=True)) == 1


def test_duplicated_handoff_is_idempotent_and_cannot_activate_model(pipeline):
    library, nest, acquisitions, ledger, automation = pipeline
    plan, candidate, options = package(pipeline)
    initial = run_mother_to_shadow(
        ledger, automation, library, nest, plan, (candidate,),
        (acquisitions[0],), **options,
    )
    second = run_mother_to_shadow(
        ledger, automation, library, nest, plan, (candidate,),
        (acquisitions[0],), **options,
    )
    assert initial.mother == second.mother
    assert len(ledger.history(OWNER, authorized=True)) == 1
    assert len(automation.active_weights(OWNER, authorized=True)) == 0
    assert automation.registry_health(OWNER, authorized=True)["total"] == 1


def test_unauthorized_handoff_and_forged_plan_rejected(pipeline):
    library, nest, acquisitions, ledger, automation = pipeline
    plan, candidate, options = package(pipeline)
    with pytest.raises(PermissionError):
        run_mother_to_shadow(
            ledger, automation, library, nest, plan, (candidate,),
            (acquisitions[0],),
            **{**options, "owner_authorized": False},
        )
    poisoned = replace(plan, assignments=(
        replace(plan.assignments[0], source_id="other"),
    ))
    with pytest.raises(ValueError, match="scheduled hatchling"):
        run_mother_to_shadow(
            ledger, automation, library, nest, poisoned, (candidate,),
            (acquisitions[0],), **options,
        )
    misdated = replace(plan, at=T1)
    with pytest.raises(ValueError, match="same-owner"):
        run_mother_to_shadow(
            ledger, automation, library, nest, misdated, (candidate,),
            (acquisitions[0],), **options,
        )
    assert ledger.history(OWNER, authorized=True) == ()


def test_unconfirmed_single_publisher_insight_never_enters_shadow(pipeline):
    library, nest, acquisitions, ledger, automation = pipeline
    plan, candidate, options = package(pipeline)
    for sid in ("beta", "gamma"):
        rev = library.history(OWNER, sid, authorized=True)[-1]
        from test_ai_webcrawler_dragon_mother_glean_matrix import document
        library.import_document(
            document(
                sid, group="group-alpha", at="2026-10-12T12:15:00Z",
                text=f"Movement revised observations from {sid}.",
            ),
            expected_parent_digest=rev.revision_digest, authorized=True,
        )
    result = run_mother_to_shadow(
        ledger, automation, library, nest, plan, (candidate,),
        (acquisitions[0],), **options,
    )
    assert not result.mother.hypotheses
    assert result.shadow is None
    assert result.insight_priority == ()
    assert result.deferred_sources == ("alpha",)
    assert result.research_queries
    assert automation.registry_health(OWNER, authorized=True)["total"] == 0
