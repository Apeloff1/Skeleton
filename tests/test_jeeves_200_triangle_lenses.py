"""Actual authored 200-lens Jeeves routing, audit and custodied corpus admission.

These are source-bound routing tests; no transformer checkpoint or real ROM is
installed here. Runtime inference remains a separate, explicit live gate.
"""
from __future__ import annotations

import json

import pytest

from skeleton.jeeves.agent.semantic_maximal import MaximalSemanticRegistry
from skeleton.jeeves.game_emulator_triangle_semantics import (
    SEMANTIC_LENS_BUDGET, EXTENDED_SEMANTIC_LENS_BUDGET,
    TriangleSemanticError, route_episode_semantic_lenses,
    verify_episode_semantic_lenses,
)
from skeleton.jeeves.game_emulator_triangle_lens_coverage import (
    audit_43_lens_coverage, verify_43_lens_coverage,
)
from skeleton.jeeves.game_emulator_triangle import (
    build_training_triangle,
)
from tests.test_emulator_training_triangle import _report


def _evidence():
    report = _report(count=2)
    return report, build_training_triangle(report)


def test_200_real_jeeves_lenses_are_canonical_governed_and_unique():
    evidence, triangle = _evidence()
    registry = MaximalSemanticRegistry()
    native = triangle["episode_lens_references"][0]
    result = route_episode_semantic_lenses(
        native, max_lenses=EXTENDED_SEMANTIC_LENS_BUDGET,
    )
    verify_episode_semantic_lenses(native, result)
    assert EXTENDED_SEMANTIC_LENS_BUDGET == 200
    assert SEMANTIC_LENS_BUDGET == 43
    assert len(registry.all()) >= 200
    assert result["actually_routed_lenses"] == 200
    assert len(result["routes"]) == 200
    keys = [r["lens_key"] for r in result["routes"]]
    assert len(keys) == len(set(keys)) == 200
    assert set(keys) <= {lens.key for lens in registry.all()}
    assert all(not row["training_ground_truth_label_available"]
               and not row["factual_claims_allowed"]
               and not row["causal_claims_allowed"]
               and row["new_independent_evidence"] == 0
               and row["governance_fingerprint"]
               for row in result["routes"])
    assert result["additional_native_training_examples"] == 0
    assert result["selection_is_dynamic_not_a_claim_of_exactly_43_catalog_lenses"]


def test_200_ledger_distinguishes_measured_cues_from_unverified_lens_hypotheses():
    evidence, triangle = _evidence()
    audit = audit_43_lens_coverage(
        evidence, triangle, limit=2,
        lens_budget=EXTENDED_SEMANTIC_LENS_BUDGET,
    )
    verify_43_lens_coverage(evidence, triangle, audit)
    assert audit["schema_version"].endswith("200_lens_coverage.v1")
    assert audit["lens_budget"] == 200
    assert audit["episodes_audited"] == 2
    for item in audit["episode_coverage"]:
        assert item["routed_lens_count"] == 200
        assert len(item["cue_supported_lens_keys"]) + len(
            item["hypothesis_only_lens_keys"]
        ) == 200
        assert item["additional_independent_native_training_examples"] == 0
    assert audit["semantic_model_generations_executed"] == 0
    assert audit["production_jeeves_weight_updates"] == 0


def test_200_lens_operator_manifest_is_distinct_and_versioned(tmp_path):
    from skeleton.ai.training.rom_triangle_campaign import (
        load_operator_semantic_lens_set,
    )
    _, triangle = _evidence()
    route = route_episode_semantic_lenses(
        triangle["episode_lens_references"][0], max_lenses=200,
    )
    keys = [row["lens_key"] for row in route["routes"]]
    path = tmp_path / "200-lenses.json"
    path.write_text(json.dumps({
        "schema_version": "skeleton.jeeves.semantic_lens_set.v2",
        "lens_keys": keys,
    }), encoding="utf-8")
    assert load_operator_semantic_lens_set(path) == tuple(keys)
    path.write_text(json.dumps({
        "schema_version": "skeleton.jeeves.semantic_lens_set.v1",
        "lens_keys": keys,
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="43 or 200"):
        load_operator_semantic_lens_set(path)


def test_cli_surfaces_200_routing_review_and_campaign():
    from scripts.training.rom_study import parser
    p = parser()
    args = p.parse_args([
        "triangle-lenses", "--receipt", "/x/rom.json",
        "--source-sha256", "f" * 64, "--lens-count", "200",
    ])
    assert args.lens_count == 200
    args = p.parse_args([
        "execute-200-lenses", "--receipt", "/x/rom.json",
        "--review-receipt", "/x/crit.json", "--source-sha256", "f" * 64,
        "--critic-checkpoint", "/x/critic", "--semantic-checkpoint", "/x/semantic",
        "--output-dir", "/x/results",
    ])
    assert args.operation == "execute-200-lenses"
    args = p.parse_args([
        "triangle-lens-audit", "--receipt", "/x/rom.json",
        "--source-sha256", "f" * 64, "--lens-count", "200",
    ])
    assert args.lens_count == 200
    args = p.parse_args([
        "train-triangle", "--root", "/x/roms", "--approvals", "/x/approve",
        "--snapshot", "/x/snapshot", "--output-dir", "/x/receipts",
        "--reviewer-checkpoint", "/x/critic",
        "--semantic-checkpoint", "/x/semantic", "--semantic-lens-count", "200",
    ])
    assert args.semantic_lens_count == 200


def test_200_route_rejects_201_and_duplicate_requested_keys():
    _, triangle = _evidence()
    native = triangle["episode_lens_references"][0]
    with pytest.raises(TriangleSemanticError, match="1..200"):
        route_episode_semantic_lenses(native, max_lenses=201)
    selected = [r["lens_key"] for r in route_episode_semantic_lenses(
        native, max_lenses=200,
    )["routes"]]
    selected[-1] = selected[0]
    with pytest.raises(TriangleSemanticError, match="unique"):
        route_episode_semantic_lenses(
            native, max_lenses=200, requested_keys=selected,
        )
