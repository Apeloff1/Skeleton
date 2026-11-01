"""Bounded and fail-closed percentile ingestion for untrusted generators."""
from itertools import repeat

import pytest

from skeleton.perf_profiler import _stats


def test_percentile_summary_rejects_unbounded_generator_without_exhausting_it(monkeypatch):
    monkeypatch.setattr(_stats, "MAX_SUMMARY_SAMPLES", 3)
    with pytest.raises(ValueError, match="sample count"):
        _stats.percentile_summary("frame", repeat(1.0))


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1, True, "2"])
def test_percentile_summary_rejects_invalid_samples(bad):
    with pytest.raises(ValueError, match="nonnegative finite"):
        _stats.percentile_summary("frame", [1.0, bad])


def test_percentile_summary_preserves_canonical_profiler_contract():
    result = _stats.percentile_summary("frame", [1.0, 2.0, 3.0])
    assert result["samples"] == 3
