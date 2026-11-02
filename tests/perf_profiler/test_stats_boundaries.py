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


def test_percentile_summary_rejects_unrepresentable_int_without_overflow():
    with pytest.raises(ValueError, match="nonnegative finite"):
        _stats.percentile_summary("frame", [1.0, 10**1000])


def test_percentile_summary_rejects_numeric_subclasses():
    class PretendFloat(float):
        pass

    with pytest.raises(ValueError, match="nonnegative finite"):
        _stats.percentile_summary("frame", [PretendFloat(1.0)])


def test_percentile_summary_preserves_canonical_profiler_contract():
    result = _stats.percentile_summary("frame", [1.0, 2.0, 3.0])
    assert result["samples"] == 3


def test_percentile_summary_rejects_aggregate_overflow_and_unsafe_metric_names():
    # Upstream Profiler.stats sums samples; finite 1e308 values otherwise
    # overflow to infinity and create non-JSON performance evidence.
    with pytest.raises(ValueError, match="nonnegative finite"):
        _stats.percentile_summary("frame", [1e308, 1e308])
    for bad_name in ("", "x" * 129, "frame\nforged", "frame\x00hidden", True):
        with pytest.raises(ValueError, match="bounded and printable"):
            _stats.percentile_summary(bad_name, [1.0])
    assert _stats.percentile_summary("frame/render", [1.0, 2.0])["samples"] == 2


def test_percentile_summary_rejects_unicode_bidi_spoofed_metric_names():
    for bad_name in ("render\u202ereverse", "render\u2066isolated",
                     "render\u2028line", "render\u2029paragraph"):
        with pytest.raises(ValueError, match="bounded and printable"):
            _stats.percentile_summary(bad_name, [1.0])


def test_metric_names_reject_surrogates_and_whitespace_aliases():
    for name in (" frame", "frame ", "frame\ud800hidden"):
        with pytest.raises(ValueError, match="bounded and printable"):
            _stats.percentile_summary(name, [1.0])
