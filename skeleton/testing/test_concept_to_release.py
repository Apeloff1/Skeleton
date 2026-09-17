"""Fail-closed tests for the concept-to-release benchmark arena."""
from __future__ import annotations

import copy

import pytest

from skeleton.eval.concept_to_release import (
    BENCHMARK_ID,
    BENCHMARK_SCHEMA_VERSION,
    DEFAULT_FRESHNESS_SECONDS,
    KIND_RAW,
    KIND_RUN,
    KIND_SUMMARY,
    MAX_EVIDENCE_BYTES,
    MAX_EVIDENCE_ITEMS,
    METRIC_SPECS,
    SCORE_DIMENSIONS,
    ConceptToReleaseError,
    EvidenceBundle,
    EvidenceItem,
    build_summary,
    canonical_digest,
    make_reproducible_fixture,
    retain_evidence,
    score_concept_to_release,
)
from skeleton.game.mechanics import (
    CombatStyle,
    CombatSystemSpec,
    GameMechanicsGenerator,
)
from skeleton.organism.quality_state import summarize_quality


def _replace_item(bundle: EvidenceBundle, item: EvidenceItem) -> EvidenceBundle:
    items = tuple(existing if existing.dimension != item.dimension else item for existing in bundle.items)
    if item.dimension not in {existing.dimension for existing in bundle.items}:
        items = bundle.items + (item,)
    return EvidenceBundle(
        schema_version=bundle.schema_version,
        source_commit=bundle.source_commit,
        evaluated_at=bundle.evaluated_at,
        items=items,
        freshness_seconds=bundle.freshness_seconds,
        metric_versions=bundle.metric_versions,
    )


def test_metrics_and_scoring_inputs_are_versioned_and_falsifiable() -> None:
    assert BENCHMARK_SCHEMA_VERSION == 1
    assert tuple(METRIC_SPECS) == SCORE_DIMENSIONS
    for dimension in SCORE_DIMENSIONS:
        spec = METRIC_SPECS[dimension]
        assert spec.version == 1
        assert spec.dimension == dimension
        assert spec.sources
        assert spec.required_inputs
        assert spec.description


def test_missing_dimensions_are_marked_missing_not_zero() -> None:
    bundle = make_reproducible_fixture(omit=("performance", "editability"))
    result = score_concept_to_release(bundle)
    run = result["run"]
    summary = run["summary"]

    assert summary["dimensions"]["performance"]["status"] == "missing"
    assert summary["dimensions"]["performance"]["value"] is None
    assert summary["dimensions"]["editability"]["status"] == "missing"
    assert summary["dimensions"]["editability"]["value"] is None
    assert "performance" not in run["raw_evidence_refs"]
    assert "editability" not in run["raw_evidence_refs"]
    assert "performance" in summary["missing"]
    assert "editability" in summary["missing"]
    assert summary["complete"] is False
    assert 0 not in (summary["dimensions"]["performance"]["value"], summary["dimensions"]["editability"]["value"])


def test_incomplete_metric_inputs_are_missing_not_guessed() -> None:
    bundle = make_reproducible_fixture()
    incomplete = retain_evidence(
        source="quality",
        dimension="correctness",
        observed_at=1_000_000,
        payload={"accepted": True, "reason": "accepted"},
    )
    result = score_concept_to_release(_replace_item(bundle, incomplete))
    row = result["run"]["summary"]["dimensions"]["correctness"]
    assert row["status"] == "missing"
    assert row["value"] is None
    assert row["evidence_digest"] == incomplete.digest
    assert incomplete.digest in result["raw_evidence"]


def test_stale_evidence_fails_closed() -> None:
    bundle = make_reproducible_fixture(
        observed_at=1_000_000,
        evaluated_at=1_000_000 + DEFAULT_FRESHNESS_SECONDS + 1,
    )
    with pytest.raises(ConceptToReleaseError, match="stale evidence"):
        score_concept_to_release(bundle)


def test_future_evidence_fails_closed() -> None:
    bundle = make_reproducible_fixture(observed_at=2_000_000, evaluated_at=1_000_000)
    with pytest.raises(ConceptToReleaseError, match="future"):
        score_concept_to_release(bundle)


def test_incompatible_benchmark_versions_fail_closed() -> None:
    bundle = make_reproducible_fixture()
    wrong_schema = EvidenceBundle(
        schema_version=BENCHMARK_SCHEMA_VERSION + 1,
        source_commit=bundle.source_commit,
        evaluated_at=bundle.evaluated_at,
        items=bundle.items,
        freshness_seconds=bundle.freshness_seconds,
        metric_versions=bundle.metric_versions,
    )
    with pytest.raises(ConceptToReleaseError, match="incompatible benchmark version"):
        score_concept_to_release(wrong_schema)

    wrong_metrics = {dimension: 99 if dimension == "security" else 1 for dimension in SCORE_DIMENSIONS}
    wrong_metric_bundle = EvidenceBundle(
        schema_version=bundle.schema_version,
        source_commit=bundle.source_commit,
        evaluated_at=bundle.evaluated_at,
        items=bundle.items,
        freshness_seconds=bundle.freshness_seconds,
        metric_versions=wrong_metrics,
    )
    with pytest.raises(ConceptToReleaseError, match="incompatible benchmark version"):
        score_concept_to_release(wrong_metric_bundle)


def test_scoring_is_deterministic_for_the_same_evidence_bundle() -> None:
    bundle = make_reproducible_fixture()
    first = score_concept_to_release(bundle)
    second = score_concept_to_release(bundle)
    assert first["run"] == second["run"]
    assert first["run"]["summary"]["digest"] == second["run"]["summary"]["digest"]
    assert dict(first["raw_evidence"]) == dict(second["raw_evidence"])

    reordered = EvidenceBundle(
        schema_version=bundle.schema_version,
        source_commit=bundle.source_commit,
        evaluated_at=bundle.evaluated_at,
        items=tuple(reversed(bundle.items)),
        freshness_seconds=bundle.freshness_seconds,
        metric_versions=bundle.metric_versions,
    )
    third = score_concept_to_release(reordered)
    assert third["run"]["summary"]["digest"] == first["run"]["summary"]["digest"]
    assert dict(third["run"]["raw_evidence_refs"]) == dict(first["run"]["raw_evidence_refs"])


def test_tampered_evidence_references_fail_closed() -> None:
    bundle = make_reproducible_fixture()
    original = bundle.items[0]
    with pytest.raises(ConceptToReleaseError, match="tampered evidence reference"):
        retain_evidence(
            source=original.source,
            dimension=original.dimension,
            observed_at=original.observed_at,
            payload=dict(original.payload),
            digest="d" * 64,
        )

    tampered = EvidenceItem(
        source=original.source,
        dimension=original.dimension,
        observed_at=original.observed_at,
        payload=original.payload,
        digest="d" * 64,
    )
    with pytest.raises(ConceptToReleaseError, match="tampered evidence reference"):
        score_concept_to_release(_replace_item(bundle, tampered))

    mutated_payload = dict(original.payload)
    if "score" in mutated_payload:
        mutated_payload["score"] = 0.11
    else:
        mutated_payload["tamper"] = True
    swapped = EvidenceItem(
        source=original.source,
        dimension=original.dimension,
        observed_at=original.observed_at,
        payload=mutated_payload,
        digest=original.digest,
    )
    with pytest.raises(ConceptToReleaseError, match="tampered evidence reference"):
        score_concept_to_release(_replace_item(bundle, swapped))


def test_self_certified_model_claims_are_refused() -> None:
    with pytest.raises(ConceptToReleaseError, match="self-certified model claims"):
        retain_evidence(
            source="quality",
            dimension="correctness",
            observed_at=1_000_000,
            payload={"accepted": True, "score": 0.99, "self_certified": True},
        )


def test_summary_cannot_be_produced_without_raw_evidence_refs() -> None:
    dimensions = {
        dimension: {"status": "missing", "value": None, "source": None}
        for dimension in SCORE_DIMENSIONS
    }
    dimensions["correctness"] = {"status": "scored", "value": 0.91, "source": "quality"}
    with pytest.raises(ConceptToReleaseError, match="raw evidence refs"):
        build_summary(
            schema_version=BENCHMARK_SCHEMA_VERSION,
            source_commit="a" * 40,
            raw_evidence_refs={},
            dimensions=dimensions,
        )


def test_raw_evidence_is_retained_separately_from_summaries() -> None:
    bundle = make_reproducible_fixture()
    result = score_concept_to_release(bundle)
    run = result["run"]
    summary = run["summary"]

    assert run["kind"] == KIND_RUN
    assert run["benchmark_id"] == BENCHMARK_ID
    assert run["schema_version"] == BENCHMARK_SCHEMA_VERSION
    assert run["source_commit"] == "a" * 40
    assert summary["kind"] == KIND_SUMMARY
    assert "payload" not in summary
    assert "payload" not in run
    dumped = str(dict(run))
    assert "attempted_edits" not in dumped
    assert "blocking_findings" not in dumped

    assert result["raw_evidence"]
    for digest, row in result["raw_evidence"].items():
        assert row["kind"] == KIND_RAW
        assert row["digest"] == digest
        assert "payload" in row
        assert digest in run["raw_evidence_refs"].values()

    rebound = build_summary(
        schema_version=run["schema_version"],
        source_commit=run["source_commit"],
        raw_evidence_refs=run["raw_evidence_refs"],
        dimensions={
            name: {"status": row["status"], "value": row["value"], "source": row["source"]}
            for name, row in summary["dimensions"].items()
        },
    )
    assert rebound["digest"] == summary["digest"]

    without_refs = copy.deepcopy(dict(run["raw_evidence_refs"]))
    without_refs.pop("correctness")
    with pytest.raises(ConceptToReleaseError, match="raw evidence refs"):
        build_summary(
            schema_version=run["schema_version"],
            source_commit=run["source_commit"],
            raw_evidence_refs=without_refs,
            dimensions={
                name: {"status": row["status"], "value": row["value"], "source": row["source"]}
                for name, row in summary["dimensions"].items()
            },
        )


def test_fixture_is_reproducible_and_bounded() -> None:
    first = make_reproducible_fixture()
    second = make_reproducible_fixture()
    assert [item.digest for item in first.items] == [item.digest for item in second.items]
    assert len(first.items) == len(SCORE_DIMENSIONS) <= MAX_EVIDENCE_ITEMS
    for item in first.items:
        encoded = canonical_digest(dict(item.payload))
        assert len(encoded) == 64
        assert len(str(dict(item.payload)).encode("utf-8")) <= MAX_EVIDENCE_BYTES

    scored = score_concept_to_release(first)
    assert scored["run"]["summary"]["complete"] is True
    assert scored["run"]["summary"]["missing"] == []
    assert set(scored["run"]["summary"]["scored"]) == set(SCORE_DIMENSIONS)
    assert scored["run"]["summary"]["dimensions"]["correctness"]["value"] == 0.91
    assert scored["run"]["summary"]["dimensions"]["iteration_latency"]["value"] == 0.75
    assert scored["run"]["summary"]["dimensions"]["editability"]["value"] == 0.75
    assert scored["run"]["summary"]["dimensions"]["determinism_replay"]["value"] == 1.0
    assert scored["run"]["summary"]["dimensions"]["security"]["value"] == 1.0
    assert scored["run"]["summary"]["dimensions"]["provenance"]["value"] == 1.0
    assert scored["run"]["summary"]["dimensions"]["performance"]["value"] == 0.8
    assert scored["run"]["summary"]["dimensions"]["creator_control"]["value"] == 1.0
    assert scored["run"]["summary"]["dimensions"]["release_completeness"]["value"] == 1.0


def test_scored_zero_is_distinct_from_missing() -> None:
    bundle = make_reproducible_fixture(
        overlay={"determinism_replay": {"live_digest": "d" * 64}},
    )
    result = score_concept_to_release(bundle)
    row = result["run"]["summary"]["dimensions"]["determinism_replay"]
    assert row["status"] == "scored"
    assert row["value"] == 0.0
    assert "determinism_replay" not in result["run"]["summary"]["missing"]


def test_quality_and_release_shapes_are_consumed_without_mutation() -> None:
    quality_rows = [
        {"accepted": True, "score": 0.91, "reason": "accepted", "surface": "forge"},
        {"accepted": False, "score": 0.2, "reason": "low_score", "surface": "npc"},
    ]
    rollup = summarize_quality(quality_rows)
    assert rollup["count"] == 2
    assert quality_rows[0]["accepted"] is True

    mechanics = GameMechanicsGenerator.generate_combat_system(
        CombatSystemSpec(style=CombatStyle.TURN_BASED)
    )
    assert mechanics["style"] == "turn_based"

    bundle = make_reproducible_fixture(
        overlay={
            "correctness": {
                "accepted": quality_rows[0]["accepted"],
                "score": quality_rows[0]["score"],
                "reason": quality_rows[0]["reason"],
                "surface": quality_rows[0]["surface"],
            },
            "performance": {"elapsed_ms": 10, "budget_ms": 100, "mechanic_style": mechanics["style"]},
        }
    )
    result = score_concept_to_release(bundle)
    assert result["run"]["summary"]["dimensions"]["correctness"]["value"] == 0.91
    assert result["run"]["summary"]["dimensions"]["performance"]["value"] == 0.9


def test_model_source_and_duplicate_dimensions_fail_closed() -> None:
    with pytest.raises(ConceptToReleaseError, match="stabilized contract"):
        retain_evidence(
            source="model",
            dimension="correctness",
            observed_at=1_000_000,
            payload={"accepted": True, "score": 0.9},
        )
    bundle = make_reproducible_fixture()
    duplicate = EvidenceBundle(
        schema_version=bundle.schema_version,
        source_commit=bundle.source_commit,
        evaluated_at=bundle.evaluated_at,
        items=bundle.items + bundle.items[:1],
        freshness_seconds=bundle.freshness_seconds,
        metric_versions=bundle.metric_versions,
    )
    with pytest.raises(ConceptToReleaseError, match="duplicate evidence"):
        score_concept_to_release(duplicate)


def test_contradictory_security_evidence_fails_closed() -> None:
    with pytest.raises(ConceptToReleaseError, match="contradictory"):
        score_concept_to_release(
            make_reproducible_fixture(
                overlay={"security": {"blocking_findings": 2, "passed": True}},
            )
        )
