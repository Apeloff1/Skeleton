"""Fail-closed regressions for the provider-neutral learning evidence contract."""

from __future__ import annotations

import pytest

from skeleton.learning import (
    Calibration,
    Curriculum,
    EvidenceProvenance,
    Feature,
    Hypothesis,
    LearningEvidenceError,
    LearningEvidenceStore,
    LearningService,
    Lesson,
    Observation,
    Outcome,
    Prediction,
    UpdateKind,
    canonical_fingerprint,
    empty_calibration,
    make_provenance,
)
from skeleton.retrieval.provenance import ProvenanceEntry

NOW = 1_000.0
SUBJECT = "skill-python"


def _store(**overrides) -> LearningEvidenceStore:
    values = {
        "clock": lambda: NOW,
        "clock_version": 1,
        "max_age_seconds": 60.0,
        "max_history": 8,
    }
    values.update(overrides)
    return LearningEvidenceStore(**values)


def _observation(
    observation_id: str = "obs-1",
    *,
    payload: dict | None = None,
    observed_at: float = NOW,
    clock_version: int = 1,
    source_kind: str = "fixture",
    subject_id: str = SUBJECT,
) -> Observation:
    body = payload if payload is not None else {"score": 1}
    return Observation(
        observation_id=observation_id,
        subject_id=subject_id,
        payload=body,
        provenance=make_provenance(
            body,
            observed_at=observed_at,
            clock_version=clock_version,
            source_kind=source_kind,
        ),
    )


def _feature_payload(name: str, value: object, subject_id: str = SUBJECT) -> dict:
    return {"name": name, "value": value, "subject_id": subject_id}


def _feature(
    *,
    feature_id: str = "feat-1",
    name: str = "score",
    value: object = 1,
    observation_ids: tuple[str, ...] = ("obs-1",),
) -> Feature:
    payload = _feature_payload(name, value)
    return Feature(
        feature_id=feature_id,
        subject_id=SUBJECT,
        name=name,
        value=value,
        observation_ids=observation_ids,
        provenance=make_provenance(
            payload,
            parent_ids=observation_ids,
        ),
    )


def _seed_observation(store: LearningEvidenceStore, **kwargs) -> Observation:
    observation = _observation(**kwargs)
    store.record_observation(observation)
    return observation


def _seed_feature(store: LearningEvidenceStore, **kwargs) -> Feature:
    if "obs-1" not in store.facts():
        _seed_observation(store)
    feature = _feature(**kwargs)
    store.record_feature(feature)
    return feature


def _hypothesis(
    *,
    hypothesis_id: str = "hyp-1",
    claim: str = "the learner has basic python fluency",
    feature_ids: tuple[str, ...] = ("feat-1",),
    polarity: str = "affirm",
    confidence: float = 0.8,
) -> Hypothesis:
    payload = {"claim": claim, "polarity": polarity, "subject_id": SUBJECT}
    return Hypothesis(
        hypothesis_id=hypothesis_id,
        subject_id=SUBJECT,
        claim=claim,
        feature_ids=feature_ids,
        confidence=confidence,
        polarity=polarity,
        provenance=make_provenance(payload, parent_ids=feature_ids),
    )


def _seed_hypothesis(store: LearningEvidenceStore, **kwargs) -> Hypothesis:
    if "feat-1" not in store.facts():
        _seed_feature(store)
    hypothesis = _hypothesis(**kwargs)
    store.record_hypothesis(hypothesis)
    return hypothesis


def _prediction(
    *,
    prediction_id: str = "pred-1",
    expected: object = "pass",
    confidence: float = 0.8,
    channel: str = "fixture",
) -> Prediction:
    payload = {"hypothesis_id": "hyp-1", "expected": expected}
    return Prediction(
        prediction_id=prediction_id,
        hypothesis_id="hyp-1",
        expected=expected,
        confidence=confidence,
        channel=channel,
        calibration=empty_calibration(channel, confidence),
        provenance=make_provenance(payload, parent_ids=("hyp-1",)),
    )


def _seed_prediction(store: LearningEvidenceStore, **kwargs) -> Prediction:
    if "hyp-1" not in store.analysis():
        _seed_hypothesis(store)
    prediction = _prediction(**kwargs)
    store.record_prediction(prediction)
    return prediction


def test_missing_provenance_is_rejected() -> None:
    with pytest.raises(LearningEvidenceError, match="provenance"):
        Observation(
            observation_id="obs-missing",
            subject_id=SUBJECT,
            payload={"score": 1},
            provenance=None,  # type: ignore[arg-type]
        )


def test_blank_source_id_is_missing_provenance() -> None:
    payload = {"score": 1}
    with pytest.raises(LearningEvidenceError) as caught:
        EvidenceProvenance(
            source_id=" ",
            source_kind="fixture",
            observed_at=NOW,
            clock_version=1,
            fingerprint=canonical_fingerprint(payload),
        )
    assert caught.value.context["reason"] == "invalid_identifier"


def test_fingerprint_mismatch_is_rejected() -> None:
    with pytest.raises(LearningEvidenceError) as caught:
        Observation(
            observation_id="obs-tampered",
            subject_id=SUBJECT,
            payload={"score": 1},
            provenance=EvidenceProvenance(
                source_id="fixture",
                source_kind="fixture",
                observed_at=NOW,
                clock_version=1,
                fingerprint="deadbeef",
            ),
        )
    assert caught.value.context["reason"] == "fingerprint_mismatch"


def test_stale_evidence_is_rejected_against_explicit_clock() -> None:
    store = _store(max_age_seconds=10.0)
    with pytest.raises(LearningEvidenceError) as caught:
        store.record_observation(_observation(observed_at=NOW - 11.0))
    assert caught.value.context["reason"] == "stale_evidence"


def test_stale_evidence_is_rejected_against_clock_version() -> None:
    store = _store(clock_version=2)
    with pytest.raises(LearningEvidenceError) as caught:
        store.record_observation(_observation(clock_version=1))
    assert caught.value.context["reason"] == "stale_evidence"


def test_advance_clock_version_makes_prior_epoch_stale() -> None:
    store = _store()
    _seed_observation(store)
    store.advance_clock_version()
    with pytest.raises(LearningEvidenceError) as caught:
        store.record_observation(_observation(observation_id="obs-2"))
    assert caught.value.context["reason"] == "stale_evidence"


def test_facts_are_stored_separately_from_derived_analysis() -> None:
    store = _store()
    observation = _seed_observation(store)
    feature = _seed_feature(store)
    hypothesis = _seed_hypothesis(store)
    prediction = _seed_prediction(store)

    assert observation.observation_id in store.facts()
    assert feature.feature_id in store.facts()
    assert hypothesis.hypothesis_id not in store.facts()
    assert prediction.prediction_id not in store.facts()
    assert hypothesis.hypothesis_id in store.analysis()
    assert prediction.prediction_id in store.analysis()
    assert observation.observation_id not in store.analysis()
    assert store.plane_of(observation.observation_id).value == "fact"
    assert store.plane_of(hypothesis.hypothesis_id).value == "analysis"


def test_contradictory_feature_signals_fail_closed_without_averaging() -> None:
    store = _store()
    _seed_observation(store, payload={"score": 0.9})
    store.record_observation(
        _observation(observation_id="obs-2", payload={"score": 0.1})
    )
    store.record_feature(
        Feature(
            feature_id="feat-high",
            subject_id=SUBJECT,
            name="score",
            value=0.9,
            observation_ids=("obs-1",),
            provenance=make_provenance(
                _feature_payload("score", 0.9),
                parent_ids=("obs-1",),
            ),
        )
    )

    with pytest.raises(LearningEvidenceError) as caught:
        store.record_feature(
            Feature(
                feature_id="feat-low",
                subject_id=SUBJECT,
                name="score",
                value=0.1,
                observation_ids=("obs-2",),
                provenance=make_provenance(
                    _feature_payload("score", 0.1),
                    parent_ids=("obs-2",),
                ),
            )
        )

    assert caught.value.context["reason"] == "contradictory_signal"
    assert store.features()[0].value == 0.9
    assert [item.value for item in store.features()] != [0.5]


def test_contradictory_observations_cannot_be_collapsed_into_one_feature() -> None:
    store = _store()
    store.record_observation(_observation(payload={"score": 0.9}))
    store.record_observation(
        _observation(observation_id="obs-2", payload={"score": 0.1})
    )
    with pytest.raises(LearningEvidenceError) as caught:
        store.record_feature(
            Feature(
                feature_id="feat-avg",
                subject_id=SUBJECT,
                name="score",
                value=0.5,
                observation_ids=("obs-1", "obs-2"),
                provenance=make_provenance(
                    _feature_payload("score", 0.5),
                    parent_ids=("obs-1", "obs-2"),
                ),
            )
        )
    assert caught.value.context["reason"] == "contradictory_signal"


def test_contradictory_hypotheses_fail_closed() -> None:
    store = _store()
    _seed_feature(store)
    store.record_hypothesis(_hypothesis())
    with pytest.raises(LearningEvidenceError) as caught:
        store.record_hypothesis(
            _hypothesis(
                hypothesis_id="hyp-deny",
                claim="the learner lacks python fluency",
                polarity="deny",
            )
        )
    assert caught.value.context["reason"] == "contradictory_signal"


def test_rollback_restores_a_prior_version() -> None:
    store = _store()
    _seed_observation(store)
    version_after_fact = store.version
    _seed_feature(store)
    _seed_hypothesis(store)
    assert "hyp-1" in store.analysis()

    rolled = store.rollback(version_after_fact)

    assert rolled.kind is UpdateKind.ROLLBACK
    assert "feat-1" not in store.facts()
    assert "hyp-1" not in store.analysis()
    assert "obs-1" in store.facts()
    assert store.plane_of("obs-1").value == "fact"


def test_bounded_history_evicts_old_versions_and_refuses_their_rollback() -> None:
    store = _store(max_history=3)
    for index in range(4):
        store.record_observation(
            _observation(
                observation_id=f"obs-{index}",
                payload={"score": index},
            )
        )

    retained = [record.version for record in store.history()]
    assert retained == [2, 3, 4]
    assert len(store.history()) == store.max_history

    with pytest.raises(LearningEvidenceError) as caught:
        store.rollback(1)
    assert caught.value.context["reason"] == "rollback_unavailable"

    store.rollback(2)
    assert "obs-0" in store.facts()
    assert "obs-3" not in store.facts()


def test_calibration_metadata_is_updated_from_explicit_outcomes() -> None:
    store = _store()
    _seed_prediction(store, confidence=0.8, channel="tutor")
    payload = {"prediction_id": "pred-1", "actual": "pass", "correct": True}
    store.record_outcome(
        Outcome(
            outcome_id="out-1",
            prediction_id="pred-1",
            actual="pass",
            correct=True,
            provenance=make_provenance(payload, parent_ids=("pred-1",)),
        )
    )

    calibration = store.calibration("tutor")
    assert isinstance(calibration, Calibration)
    assert calibration.sample_count == 1
    assert calibration.stated_confidence == 0.8
    assert calibration.empirical_rate == 1.0
    assert calibration.expected_calibration_error == pytest.approx(0.2)
    assert calibration.last_outcome_id == "out-1"
    assert store.plane_of("out-1").value == "result"


def test_incorrect_outcome_flag_that_disagrees_with_actual_is_rejected() -> None:
    store = _store()
    _seed_prediction(store, expected="pass")
    with pytest.raises(LearningEvidenceError) as caught:
        store.record_outcome(
            Outcome(
                outcome_id="out-lie",
                prediction_id="pred-1",
                actual="fail",
                correct=True,
                provenance=make_provenance(
                    {"prediction_id": "pred-1", "actual": "fail", "correct": True},
                    parent_ids=("pred-1",),
                ),
            )
        )
    assert caught.value.context["reason"] == "contradictory_signal"


def test_provenance_survives_feature_hypothesis_outcome_flow() -> None:
    store = _store()
    _seed_observation(store)
    _seed_feature(store)
    _seed_hypothesis(store)
    _seed_prediction(store)
    store.record_outcome(
        Outcome(
            outcome_id="out-1",
            prediction_id="pred-1",
            actual="pass",
            correct=True,
            provenance=make_provenance(
                {"prediction_id": "pred-1", "actual": "pass", "correct": True},
                parent_ids=("pred-1",),
            ),
        )
    )

    chain = store.lineage("out-1")
    assert chain == ("obs-1", "feat-1", "hyp-1", "pred-1", "out-1")
    fingerprints = [
        store.facts()["obs-1"].provenance.fingerprint,
        store.facts()["feat-1"].provenance.fingerprint,
        store.analysis()["hyp-1"].provenance.fingerprint,
        store.analysis()["pred-1"].provenance.fingerprint,
        store.results()["out-1"].provenance.fingerprint,
    ]
    assert all(fingerprints)
    assert fingerprints == list(dict.fromkeys(fingerprints))
    assert all(len(item) == len(ProvenanceEntry.hash_data("x")) for item in fingerprints)


def test_feature_without_parent_provenance_is_rejected() -> None:
    store = _store()
    _seed_observation(store)
    with pytest.raises(LearningEvidenceError) as caught:
        Feature(
            feature_id="feat-orphan",
            subject_id=SUBJECT,
            name="score",
            value=1,
            observation_ids=("obs-1",),
            provenance=make_provenance(_feature_payload("score", 1), parent_ids=()),
        )
    assert caught.value.context["reason"] == "missing_provenance"


def test_unknown_observation_parent_is_rejected() -> None:
    store = _store()
    with pytest.raises(LearningEvidenceError) as caught:
        store.record_feature(_feature(observation_ids=("obs-missing",)))
    assert caught.value.context["reason"] == "unknown_parent"


def test_live_model_source_cannot_self_modify_the_store() -> None:
    store = _store()
    with pytest.raises(LearningEvidenceError) as caught:
        store.record_observation(_observation(source_kind="llm"))
    assert caught.value.context["reason"] == "blocked_source"
    assert not hasattr(LearningEvidenceStore, "ingest_model_output")
    assert not hasattr(LearningEvidenceStore, "self_update")
    assert store.observations() == ()


def test_deterministic_offline_fixtures_replay_identically() -> None:
    first = _store()
    second = _store()
    for store in (first, second):
        _seed_observation(store)
        _seed_feature(store)
        _seed_hypothesis(store)
        _seed_prediction(store)

    assert first.lineage("pred-1") == second.lineage("pred-1")
    assert [record.kind for record in first.history()] == [
        record.kind for record in second.history()
    ]
    assert first.facts()["obs-1"].provenance.fingerprint == second.facts()["obs-1"].provenance.fingerprint
    assert first.analysis()["hyp-1"].claim == second.analysis()["hyp-1"].claim


def test_learning_package_still_exports_curriculum_service() -> None:
    service = LearningService()
    service.add_lesson(Lesson("intro", "Intro", "skill-intro"))
    snapshot = service.snapshot()
    assert snapshot.ready_lesson_ids == ("intro",)
    assert isinstance(Curriculum(), Curriculum)



def test_record_observation_uses_one_clock_sample_for_validation_and_commit() -> None:
    ticks = iter([NOW, float("nan")])
    store = _store(clock=lambda: next(ticks))

    update = store.record_observation(_observation())

    assert update.version == 1
    assert update.timestamp == NOW
    assert store.version == 1
    assert [record.version for record in store.history()] == [1]
    assert store.observations()[0].observation_id == "obs-1"


def test_failed_rollback_clock_leaves_store_version_and_history_unchanged() -> None:
    store = _store()
    _seed_observation(store)
    version_after_fact = store.version
    _seed_feature(store)
    before_version = store.version
    before_history = store.history()
    before_facts = store.facts()

    store._clock = lambda: float("nan")  # type: ignore[method-assign]

    with pytest.raises(LearningEvidenceError, match="clock"):
        store.rollback(version_after_fact)

    assert store.version == before_version
    assert store.history() == before_history
    assert store.facts() == before_facts
    assert "feat-1" in store.facts()


def test_commit_timestamp_matches_staleness_clock_sample() -> None:
    ticks = iter([NOW])
    store = _store(clock=lambda: next(ticks))

    update = store.record_observation(_observation(observed_at=NOW))

    assert update.timestamp == NOW
    assert update.previous_version is None
