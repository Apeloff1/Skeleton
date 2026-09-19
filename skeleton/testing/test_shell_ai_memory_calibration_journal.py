"""AI outcome memory, calibration, trust, provenance, journal, and replay tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.calibration import AICalibration
from skeleton.shells.ai.journal import AIDecisionJournal
from skeleton.shells.ai.memory import AIOutcomeMemory
from skeleton.shells.ai.provenance import AIDecisionProvenance
from skeleton.shells.ai.replay import AIDecisionReplay
from skeleton.shells.ai.trust import ModelTrustRegistry


def fingerprint(char):
    return char * 64


def test_outcome_memory_record_and_query():
    memory = AIOutcomeMemory()
    item = memory.record(
        intent_fingerprint=fingerprint("a"),
        proposal_fingerprint=fingerprint("b"),
        risk_score=5,
        success=True,
        duration_ms=10,
        verified=True,
        command_count=1,
        model_id="m",
    )
    assert memory.by_intent(fingerprint("a")) == (item,)
    assert memory.by_model("m") == (item,)


def test_outcome_memory_bounded_eviction():
    memory = AIOutcomeMemory(max_items=1)
    memory.record(
        intent_fingerprint=fingerprint("a"),
        proposal_fingerprint=fingerprint("b"),
        risk_score=1,
        success=True,
        duration_ms=1,
        verified=True,
        command_count=1,
    )
    second = memory.record(
        intent_fingerprint=fingerprint("c"),
        proposal_fingerprint=fingerprint("d"),
        risk_score=2,
        success=False,
        duration_ms=2,
        verified=False,
        command_count=1,
    )
    assert memory.snapshot() == (second,)


def test_outcome_memory_success_rate_prior():
    assert AIOutcomeMemory().success_rate() == 0.5


def test_outcome_memory_success_rate():
    memory = AIOutcomeMemory()
    for success in (True, True, False):
        memory.record(
            intent_fingerprint=fingerprint("a"),
            proposal_fingerprint=fingerprint("b"),
            risk_score=1,
            success=success,
            duration_ms=1,
            verified=success,
            command_count=1,
            model_id="m",
        )
    assert memory.success_rate(model_id="m") == pytest.approx(2 / 3)


def test_calibration_beta_smoothed_success():
    calibration = AICalibration()
    snapshot = calibration.record(
        "m",
        predicted_confidence=0.9,
        success=True,
        verified=True,
        latency_ms=5,
    )
    assert snapshot.attempts == 1
    assert snapshot.successes == 1
    assert snapshot.predicted_success == pytest.approx(2 / 3)


def test_calibration_confidence_error():
    calibration = AICalibration()
    snapshot = calibration.record(
        "m",
        predicted_confidence=0.9,
        success=False,
        verified=False,
        latency_ms=5,
    )
    assert snapshot.confidence_error == pytest.approx(0.9)


def test_calibration_averages_latency():
    calibration = AICalibration()
    calibration.record(
        "m",
        predicted_confidence=0.5,
        success=True,
        verified=True,
        latency_ms=10,
    )
    snapshot = calibration.record(
        "m",
        predicted_confidence=0.5,
        success=True,
        verified=False,
        latency_ms=30,
    )
    assert snapshot.avg_latency_ms == 20
    assert snapshot.verified_successes == 1


def test_calibration_capacity():
    calibration = AICalibration(max_keys=1)
    calibration.record(
        "a",
        predicted_confidence=0.5,
        success=True,
        verified=True,
        latency_ms=1,
    )
    with pytest.raises(RuntimeError):
        calibration.record(
            "b",
            predicted_confidence=0.5,
            success=True,
            verified=True,
            latency_ms=1,
        )


def test_trust_profile_is_advisory_and_bounded():
    calibration = AICalibration()
    calibration.record(
        "m",
        predicted_confidence=0.8,
        success=True,
        verified=True,
        latency_ms=5,
    )
    trust = ModelTrustRegistry(calibration)
    trust.record_verification("m", verified=True)
    profile = trust.profile("m")
    assert 0 <= profile.trust_score <= 1
    assert profile.observations == 1


def provenance():
    return AIDecisionProvenance(
        intent_fingerprint=fingerprint("a"),
        proposal_fingerprint=fingerprint("b"),
        tool_catalog_digest=fingerprint("c"),
        effect_digest=fingerprint("d"),
        policy_fingerprint=fingerprint("e"),
        schema_digest=fingerprint("f"),
        model_id="m",
        risk_score=7,
        receipt_root=fingerprint("1"),
    )


def test_provenance_digest_stable():
    item = provenance()
    assert len(item.digest) == 64
    assert item.digest == item.digest


def test_provenance_rejects_bad_fingerprint():
    with pytest.raises(ValueError):
        AIDecisionProvenance(
            intent_fingerprint="short",
            proposal_fingerprint=fingerprint("b"),
            tool_catalog_digest=fingerprint("c"),
            effect_digest=fingerprint("d"),
            policy_fingerprint=fingerprint("e"),
            schema_digest=fingerprint("f"),
            model_id="m",
            risk_score=1,
        )


def test_journal_append_verify_root():
    journal = AIDecisionJournal()
    first = journal.append(
        "ai.plan.proposed",
        session_id="s",
        intent_id="i",
        proposal_id="p",
        summary="proposal created",
    )
    second = journal.append(
        "ai.plan.reviewed",
        session_id="s",
        intent_id="i",
        proposal_id="p",
        summary="proposal reviewed",
    )
    assert journal.verify()
    assert second.previous_hash == first.event_hash
    assert journal.root_hash() == second.event_hash


def test_journal_tamper_detected():
    journal = AIDecisionJournal()
    journal.append(
        "ai.plan.proposed",
        session_id="s",
        intent_id="i",
        summary="x",
    )
    item = journal._items[0]
    journal._items[0] = replace(item, summary="tampered")
    assert not journal.verify()


def test_journal_capacity_fails_closed():
    journal = AIDecisionJournal(max_events=1)
    journal.append("a", session_id="s", intent_id="i")
    with pytest.raises(RuntimeError):
        journal.append("b", session_id="s", intent_id="i")


def test_replay_validates_expected_digests():
    journal = AIDecisionJournal()
    journal.append("a", session_id="s", intent_id="i")
    item = provenance()
    report = AIDecisionReplay().verify(
        journal,
        item,
        expected_policy_fingerprint=item.policy_fingerprint,
        expected_effect_digest=item.effect_digest,
        expected_tool_catalog_digest=item.tool_catalog_digest,
    )
    assert report.valid


def test_replay_detects_policy_mismatch():
    journal = AIDecisionJournal()
    item = provenance()
    report = AIDecisionReplay().verify(
        journal,
        item,
        expected_policy_fingerprint=fingerprint("9"),
    )
    assert not report.valid
    assert "policy fingerprint mismatch" in report.reasons
