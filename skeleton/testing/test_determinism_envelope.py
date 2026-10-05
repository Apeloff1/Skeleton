from __future__ import annotations

import hashlib
import math

import pytest

from skeleton.contracts.canonical import canonical_json_bytes
from skeleton.eval.determinism import (
    DeterminismClass,
    DeterminismEnvelope,
    VariancePolicy,
    compare_replay,
)


def test_exact_envelope_identity_is_shared_canonical_bytes() -> None:
    envelope = DeterminismEnvelope(DeterminismClass.EXACT)
    assert envelope.identity == hashlib.sha256(canonical_json_bytes(envelope.canonical_payload())).hexdigest()
    assert compare_replay({"b": [2, 3], "a": 1}, {"a": 1, "b": [2, 3]}, envelope).equivalent


def test_exact_replay_reports_stable_paths() -> None:
    result = compare_replay({"b": 2, "a": [1, 2]}, {"a": [1, 9], "b": 3}, DeterminismEnvelope(DeterminismClass.EXACT))
    assert not result.equivalent
    assert result.mismatch_paths == ("$.a[1]", "$.b")


def test_seeded_requires_seed_and_exact_comparison() -> None:
    with pytest.raises(ValueError):
        DeterminismEnvelope(DeterminismClass.SEEDED)
    envelope = DeterminismEnvelope(DeterminismClass.SEEDED, seed=7)
    assert compare_replay(1.0, 1.0, envelope).equivalent
    assert not compare_replay(1.0, 1.000001, envelope).equivalent


def test_tolerant_comparison_requires_declared_source() -> None:
    with pytest.raises(ValueError):
        DeterminismEnvelope(DeterminismClass.TOLERANT, variance=VariancePolicy(absolute_tolerance=0.1))
    envelope = DeterminismEnvelope(
        DeterminismClass.TOLERANT,
        variance=VariancePolicy(absolute_tolerance=0.1, relative_tolerance=0.01),
        nondeterminism_sources=("gpu-reduction-order",),
    )
    assert compare_replay({"score": 10.05}, {"score": 10.0}, envelope).equivalent
    assert not compare_replay({"score": 10.2}, {"score": 10.0}, envelope).equivalent


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_observations_fail_closed(value: float) -> None:
    with pytest.raises(ValueError):
        compare_replay(value, value, DeterminismEnvelope(DeterminismClass.EXACT))


def test_non_string_mapping_keys_fail_closed() -> None:
    with pytest.raises(ValueError):
        compare_replay({1: "ambiguous"}, {1: "ambiguous"}, DeterminismEnvelope(DeterminismClass.EXACT))


def test_invalid_variance_policy_fails_closed() -> None:
    with pytest.raises(ValueError):
        VariancePolicy(absolute_tolerance=-1)
    with pytest.raises(ValueError):
        VariancePolicy(relative_tolerance=math.inf)


def test_exact_class_rejects_hidden_nondeterminism() -> None:
    with pytest.raises(ValueError):
        DeterminismEnvelope(DeterminismClass.EXACT, nondeterminism_sources=("clock",))
