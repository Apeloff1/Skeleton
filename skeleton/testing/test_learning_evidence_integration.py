"""Cross-contract regressions for Jeeves learning evidence."""

from __future__ import annotations

import pytest

from skeleton.jeeves.evidence_core import EvidenceJeevesCore, EvidenceResult
from skeleton.learning import (
    Feature,
    Hypothesis,
    LearningEvidenceStore,
    LearningService,
    Observation,
    canonical_fingerprint,
    make_provenance,
    make_provenance_from_evidence_envelope,
)


def _feature_payload(name: str, value: object, subject_id: str) -> dict:
    return {"name": name, "value": value, "subject_id": subject_id}


def _hypothesis_payload(claim: str, polarity: str, subject_id: str) -> dict:
    return {"claim": claim, "polarity": polarity, "subject_id": subject_id}


def test_newer_feature_value_is_longitudinal_not_contradictory() -> None:
    now = [1_000.0]
    subject = "skill-python"
    store = LearningEvidenceStore(
        clock=lambda: now[0],
        max_age_seconds=60.0,
    )

    first_observation = Observation(
        observation_id="obs-1",
        subject_id=subject,
        payload={"mastery": 0.25},
        provenance=make_provenance(
            {"mastery": 0.25},
            observed_at=1_000.0,
        ),
    )
    store.record_observation(first_observation)
    store.record_feature(
        Feature(
            feature_id="feat-1",
            subject_id=subject,
            name="mastery",
            value=0.25,
            observation_ids=("obs-1",),
            provenance=make_provenance(
                _feature_payload("mastery", 0.25, subject),
                observed_at=1_000.0,
                parent_ids=("obs-1",),
            ),
        )
    )

    now[0] = 1_010.0
    second_observation = Observation(
        observation_id="obs-2",
        subject_id=subject,
        payload={"mastery": 0.75},
        provenance=make_provenance(
            {"mastery": 0.75},
            observed_at=1_010.0,
        ),
    )
    store.record_observation(second_observation)
    store.record_feature(
        Feature(
            feature_id="feat-2",
            subject_id=subject,
            name="mastery",
            value=0.75,
            observation_ids=("obs-2",),
            provenance=make_provenance(
                _feature_payload("mastery", 0.75, subject),
                observed_at=1_010.0,
                parent_ids=("obs-2",),
            ),
        )
    )

    assert [feature.value for feature in store.features()] == [0.25, 0.75]


def test_opposite_polarity_unrelated_hypotheses_can_coexist() -> None:
    subject = "skill-python"
    store = LearningEvidenceStore(clock=lambda: 1_000.0)

    observation = Observation(
        observation_id="obs-1",
        subject_id=subject,
        payload={"score": 1, "latency": 2},
        provenance=make_provenance({"score": 1, "latency": 2}),
    )
    store.record_observation(observation)

    score_feature = Feature(
        feature_id="feat-score",
        subject_id=subject,
        name="score",
        value=1,
        observation_ids=("obs-1",),
        provenance=make_provenance(
            _feature_payload("score", 1, subject),
            parent_ids=("obs-1",),
        ),
    )
    latency_feature = Feature(
        feature_id="feat-latency",
        subject_id=subject,
        name="latency",
        value=2,
        observation_ids=("obs-1",),
        provenance=make_provenance(
            _feature_payload("latency", 2, subject),
            parent_ids=("obs-1",),
        ),
    )
    store.record_feature(score_feature)
    store.record_feature(latency_feature)

    first_claim = "learner answered the item correctly"
    second_claim = "learner did not answer within the target latency"
    store.record_hypothesis(
        Hypothesis(
            hypothesis_id="hyp-correct",
            subject_id=subject,
            claim=first_claim,
            feature_ids=("feat-score",),
            confidence=0.8,
            polarity="affirm",
            provenance=make_provenance(
                _hypothesis_payload(first_claim, "affirm", subject),
                parent_ids=("feat-score",),
            ),
        )
    )
    store.record_hypothesis(
        Hypothesis(
            hypothesis_id="hyp-latency",
            subject_id=subject,
            claim=second_claim,
            feature_ids=("feat-latency",),
            confidence=0.7,
            polarity="deny",
            provenance=make_provenance(
                _hypothesis_payload(second_claim, "deny", subject),
                parent_ids=("feat-latency",),
            ),
        )
    )

    assert {item.hypothesis_id for item in store.hypotheses()} == {
        "hyp-correct",
        "hyp-latency",
    }


def test_fact_payload_and_rollback_snapshot_are_immutable() -> None:
    store = LearningEvidenceStore(clock=lambda: 1_000.0)
    observation = Observation(
        observation_id="obs-1",
        subject_id="skill-python",
        payload={"score": 1},
        provenance=make_provenance({"score": 1}),
    )
    store.record_observation(observation)
    version_one = store.version
    fingerprint = store.facts()["obs-1"].provenance.fingerprint

    with pytest.raises(TypeError):
        store.facts()["obs-1"].payload["score"] = 2  # type: ignore[index]

    store.record_observation(
        Observation(
            observation_id="obs-2",
            subject_id="skill-python",
            payload={"score": 2},
            provenance=make_provenance({"score": 2}),
        )
    )
    store.rollback(version_one)

    restored = store.facts()["obs-1"]
    assert restored.payload["score"] == 1
    assert restored.provenance.fingerprint == fingerprint
    assert restored.provenance.fingerprint == canonical_fingerprint({"score": 1})


def test_first_commit_can_rollback_to_version_zero() -> None:
    store = LearningEvidenceStore(clock=lambda: 1_000.0)
    update = store.record_observation(
        Observation(
            observation_id="obs-1",
            subject_id="skill-python",
            payload={"score": 1},
            provenance=make_provenance({"score": 1}),
        )
    )

    assert update.previous_version == 0
    rolled = store.rollback(0)

    assert rolled.target_id == "v0"
    assert store.observations() == ()


class _Provider:
    name = "fixture"
    supports_system_prompt = True

    def complete(self, prompt, context=None, system=None):
        return "ok"


def test_evidence_core_envelope_roundtrips_without_digest_substitution() -> None:
    core = EvidenceJeevesCore(
        provider=_Provider(),
        evidence_clock=lambda: 1_000.0,
    )
    session = core.open_session("learner")
    core.register_evidence_tool(
        "fixture",
        lambda payload: EvidenceResult(
            data={"score": 1},
            observed_at=1_050.0,
            revision="r7",
        ),
        source_id="fixture.learning",
        max_age_seconds=60.0,
    )

    result = core.ask_with_evidence(
        session.session_id,
        "Use fixture evidence.",
        context={"tool_calls": [{"name": "fixture"}]},
        allowed_tools=["fixture"],
    )
    envelope = result["evidence"][0]["result"]

    translated = make_provenance_from_evidence_envelope(
        envelope["data"],
        envelope["provenance"],
    )
    store = LearningEvidenceStore(
        clock=lambda: 1_000.0,
        max_age_seconds=60.0,
        future_skew_seconds=60.0,
    )
    store.record_observation(
        Observation(
            observation_id="obs-core",
            subject_id="skill-python",
            payload=envelope["data"],
            provenance=translated,
        )
    )

    assert translated.source_id == "fixture.learning"
    assert translated.observed_at == 1_050.0
    assert translated.retrieved_at == 1_000.0
    assert translated.revision == "r7"
    assert translated.source_digest == envelope["provenance"]["sha256"]
    assert translated.source_digest != translated.fingerprint


def test_learning_subject_id_accepts_full_assessment_width() -> None:
    skill_id = "s" * 129
    service = LearningService()
    service.record(skill_id, correct=True)

    store = LearningEvidenceStore(clock=lambda: 1_000.0)
    store.record_observation(
        Observation(
            observation_id="obs-wide-skill",
            subject_id=skill_id,
            payload={"score": 1},
            provenance=make_provenance({"score": 1}),
        )
    )

    assert service.mastery(skill_id) is not None
    assert store.observations()[0].subject_id == skill_id
