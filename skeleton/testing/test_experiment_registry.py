from __future__ import annotations

import pytest

from skeleton.eval.experiment_registry import (
    ExperimentBudget,
    ExperimentEligibility,
    ExperimentManifest,
    ExperimentMetric,
    ExperimentRegistry,
    ExperimentRegistryError,
    MetricDirection,
    TrafficMode,
)


HEAD = "a" * 40


def _budget(**overrides) -> ExperimentBudget:
    values = {
        "max_samples": 1000,
        "max_tokens": 1_000_000,
        "max_cost_units": 25.0,
        "max_wall_time_s": 3600.0,
    }
    values.update(overrides)
    return ExperimentBudget(**values)


def _eligibility(**overrides) -> ExperimentEligibility:
    values = {
        "traffic_mode": TrafficMode.SHADOW,
        "max_traffic_fraction": 0.1,
        "allowed_data_classes": ("public", "internal"),
        "tenant_ids": ("tenant-test",),
        "external_side_effects_allowed": False,
    }
    values.update(overrides)
    return ExperimentEligibility(**values)


def _metric(metric_id: str = "quality.acceptance") -> ExperimentMetric:
    return ExperimentMetric(
        metric_id=metric_id,
        direction=MetricDirection.MAXIMIZE,
        minimum_samples=100,
        source="independent-eval",
    )


def _manifest(**overrides) -> ExperimentManifest:
    values = {
        "experiment_id": "exp.routing-quality.v1",
        "hypothesis": "A bounded routing candidate improves independent quality.",
        "owner": "p1-learning",
        "source_commit": HEAD,
        "environment_id": "staging.eval",
        "candidate_ref": "candidate:routing.v2",
        "eligibility": _eligibility(),
        "budget": _budget(),
        "metrics": (_metric(),),
        "parent_experiment_id": None,
        "tags": ("routing", "quality"),
    }
    values.update(overrides)
    return ExperimentManifest(**values)


def test_manifest_is_deterministic_and_non_authoritative() -> None:
    left = _manifest()
    right = _manifest(metrics=tuple(reversed(left.metrics)))

    assert left.manifest_digest == right.manifest_digest
    assert left.identity_payload()["production_authority"] is False
    evidence = left.registry_evidence_ref()
    assert evidence.category == "experiment_manifest"
    assert evidence.digest == left.manifest_digest


def test_shadow_traffic_is_bounded_and_side_effect_free() -> None:
    with pytest.raises(ExperimentRegistryError, match="external side effects"):
        _eligibility(external_side_effects_allowed=True)
    with pytest.raises(ExperimentRegistryError, match="positive bounded"):
        _eligibility(max_traffic_fraction=0.0)
    with pytest.raises(ExperimentRegistryError, match=r"\[0, 1\]"):
        _eligibility(max_traffic_fraction=1.1)


def test_offline_experiment_requires_zero_traffic() -> None:
    offline = _eligibility(
        traffic_mode=TrafficMode.OFFLINE,
        max_traffic_fraction=0.0,
        tenant_ids=(),
    )
    assert offline.max_traffic_fraction == 0.0

    with pytest.raises(ExperimentRegistryError, match="zero traffic"):
        _eligibility(
            traffic_mode=TrafficMode.OFFLINE,
            max_traffic_fraction=0.1,
        )


def test_registry_rejects_duplicate_and_unknown_lineage() -> None:
    manifest = _manifest()
    with pytest.raises(ExperimentRegistryError, match="unique"):
        ExperimentRegistry((manifest, manifest))

    child = _manifest(
        experiment_id="exp.routing-quality.v2",
        parent_experiment_id="missing",
    )
    with pytest.raises(ExperimentRegistryError, match="unknown parent"):
        ExperimentRegistry((child,))


def test_registry_accepts_acyclic_lineage_and_is_order_stable() -> None:
    parent = _manifest()
    child = _manifest(
        experiment_id="exp.routing-quality.v2",
        parent_experiment_id=parent.experiment_id,
        candidate_ref="candidate:routing.v3",
    )
    left = ExperimentRegistry((parent, child))
    right = ExperimentRegistry((child, parent))

    assert left.registry_digest == right.registry_digest
    assert left.get(child.experiment_id) == child


def test_registry_rejects_lineage_cycle() -> None:
    first = _manifest(
        experiment_id="exp.one",
        parent_experiment_id="exp.two",
    )
    second = _manifest(
        experiment_id="exp.two",
        parent_experiment_id="exp.one",
    )
    with pytest.raises(ExperimentRegistryError, match="cycle"):
        ExperimentRegistry((first, second))


def test_metrics_require_unique_ids_and_materialized_budget() -> None:
    metric = _metric()
    with pytest.raises(ExperimentRegistryError, match="unique"):
        _manifest(metrics=(metric, metric))
    with pytest.raises(ExperimentRegistryError, match="positive integer"):
        _budget(max_samples=0)
    with pytest.raises(ExperimentRegistryError, match="positive"):
        _budget(max_cost_units=0.0)


def test_source_commit_is_exact_and_hypothesis_is_normalized() -> None:
    with pytest.raises(ExperimentRegistryError, match="source_commit"):
        _manifest(source_commit="short")
    with pytest.raises(ExperimentRegistryError, match="hypothesis"):
        _manifest(hypothesis=" padded ")


def test_manifest_identity_changes_with_eligibility_budget_or_metrics() -> None:
    baseline = _manifest()
    changed_traffic = _manifest(
        eligibility=_eligibility(max_traffic_fraction=0.2),
    )
    changed_budget = _manifest(
        budget=_budget(max_samples=2000),
    )
    changed_metric = _manifest(
        metrics=(
            ExperimentMetric(
                metric_id="quality.acceptance",
                direction=MetricDirection.MINIMIZE,
                minimum_samples=100,
                source="independent-eval",
            ),
        ),
    )

    assert baseline.manifest_digest != changed_traffic.manifest_digest
    assert baseline.manifest_digest != changed_budget.manifest_digest
    assert baseline.manifest_digest != changed_metric.manifest_digest

def test_shadow_non_public_data_requires_tenant_scope() -> None:
    with pytest.raises(ExperimentRegistryError, match="require tenant scope"):
        _eligibility(
            allowed_data_classes=("internal",),
            tenant_ids=(),
        )

    public = _eligibility(
        allowed_data_classes=("public",),
        tenant_ids=(),
    )
    assert public.tenant_ids == ()


def test_candidate_cannot_self_certify_metrics() -> None:
    with pytest.raises(ExperimentRegistryError, match="independently produced"):
        ExperimentMetric(
            metric_id="quality.self",
            direction=MetricDirection.MAXIMIZE,
            minimum_samples=10,
            source="candidate-eval",
            independent=False,
        )

def test_empty_registry_is_valid_and_deterministic() -> None:
    left = ExperimentRegistry(())
    right = ExperimentRegistry(())

    assert left.registry_digest == right.registry_digest
    assert len(left.registry_digest) == 64
    with pytest.raises(KeyError):
        left.get("exp.missing")
