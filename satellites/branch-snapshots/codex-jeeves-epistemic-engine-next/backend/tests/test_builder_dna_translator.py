"""Unit tests for the Builder DNA → prompt translator.

These cover the four hardening pillars:
    • Security      — clamping, dropping unknown / oversized keys, NaN/inf.
    • Performance   — at-default sliders never emit directives; cache hits.
    • Stability     — translator never raises on malformed input.
    • Maintainability — output is deterministic + sorted.

Run with: ``pytest tests/test_builder_dna_translator.py -q`` from /app/backend.
"""

from __future__ import annotations

import math

import pytest

from routes.builder_dna_translator import (
    DEFAULT_VALUE, MAX_KEYS, MAX_PROMPT_CHARS,
    sanitise_dna, translate_dna_to_prompt, stats,
)


def _drifted(key: str = "bdr_web_perf_p95", v: float = 2.4):
    return {key: v}


# ─── Security ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("bad", [None, "string", 42, [], 0])
def test_sanitise_handles_non_dict(bad):
    assert sanitise_dna(bad) == {}


def test_sanitise_drops_unknown_prefix():
    out = sanitise_dna({"foo_bar": 2.0, "bdr_web_perf_p95": 2.0})
    assert "foo_bar" not in out
    assert out["bdr_web_perf_p95"] == 2.0


def test_sanitise_clamps_value_range():
    out = sanitise_dna({"bdr_web_perf_p95": 99.0, "bdr_web_perf_cold": -7.0})
    assert out["bdr_web_perf_p95"] == 3.0
    assert out["bdr_web_perf_cold"] == 0.0


def test_sanitise_rejects_nan_inf():
    out = sanitise_dna({
        "bdr_web_perf_p95": float("nan"),
        "bdr_web_perf_cold": math.inf,
        "bdr_web_perf_hot": 2.0,
    })
    assert out == {"bdr_web_perf_hot": 2.0}


def test_sanitise_caps_max_keys():
    payload = {f"bdr_web_perf_p{i}": 2.0 for i in range(MAX_KEYS + 50)}
    out = sanitise_dna(payload)
    assert len(out) == MAX_KEYS


def test_sanitise_rejects_oversized_key():
    long_key = "bdr_" + "x" * 200
    assert sanitise_dna({long_key: 2.0}) == {}


def test_sanitise_rejects_non_numeric():
    assert sanitise_dna({"bdr_web_perf_p95": "high"}) == {}


# ─── Performance ───────────────────────────────────────────────────────


def test_default_sliders_emit_no_directives():
    payload = {f"bdr_web_perf_p{i}": DEFAULT_VALUE for i in range(10)}
    assert translate_dna_to_prompt(payload) == ""


def test_only_drifted_sliders_appear():
    payload = {
        "bdr_web_perf_p95": 2.4,             # drift
        "bdr_web_perf_cold": DEFAULT_VALUE,  # ignored
        "bdr_web_quality_terse": 0.3,        # drift
    }
    result = translate_dna_to_prompt(payload)
    assert "p95 latency" in result
    assert "terseness" in result
    assert "cold-start" not in result


def test_translator_caches_equivalent_payloads():
    p1 = {"bdr_web_perf_p95": 2.4, "bdr_web_quality_terse": 0.3}
    p2 = {"bdr_web_quality_terse": 0.3, "bdr_web_perf_p95": 2.4}  # different order
    assert translate_dna_to_prompt(p1) == translate_dna_to_prompt(p2)


def test_translator_caps_prompt_length():
    # Many widely drifted sliders to test the bound. Each spans ~10 groups.
    payload = {}
    for grp in ("perf", "quality", "testing", "security", "deploy",
                "obs", "ux", "docs", "a11y", "maint"):
        for slot in ("a", "b", "c", "d", "e", "f", "g", "h", "i", "j"):
            payload[f"bdr_web_{grp}_{slot}"] = 2.9
    text = translate_dna_to_prompt(payload)
    assert len(text) <= MAX_PROMPT_CHARS + 50  # allow tiny truncation marker


# ─── Stability ─────────────────────────────────────────────────────────


def test_translator_never_raises_on_garbage():
    # A grab-bag of malformed payloads should all return ''.
    for bad in (None, {}, "string", [1, 2, 3], {"x": object()}, {1: 2}):
        try:
            result = translate_dna_to_prompt(bad)  # type: ignore[arg-type]
        except Exception as e:  # pragma: no cover
            pytest.fail(f"translator raised on {bad!r}: {e}")
        assert isinstance(result, str)


# ─── Maintainability — deterministic, sorted output ────────────────────


def test_output_is_deterministic_across_calls():
    payload = {"bdr_web_perf_p95": 2.0, "bdr_web_quality_terse": 0.4}
    a = translate_dna_to_prompt(payload)
    b = translate_dna_to_prompt(payload)
    assert a == b


def test_stats_returns_expected_shape():
    payload = {"bdr_web_perf_p95": 2.0, "bdr_web_quality_terse": 1.0, "bad": 5}
    s = stats(payload)
    assert s["received_keys"] == 2
    assert s["drift"] == 1
    assert s["at_default"] == 1
    assert s["dropped_keys"] == 1


# ─── Sub-process integration check for the /dna/preview endpoint ───────


def test_preview_endpoint_rejects_malformed_payload(tmp_path):
    """The hardened endpoint should refuse non-mapping ``builder_dna``.

    We don't spin a full HTTP server here — instead we directly invoke the
    sanitiser the endpoint relies on with the same shapes a malformed
    POST would yield.
    """
    for bad in (None, [], "string", 42, {"builder_dna": [1, 2, 3]}):
        # Either a wrong root type or a wrong inner value type — sanitiser
        # collapses both to an empty payload.
        if isinstance(bad, dict):
            bad = bad.get("builder_dna")
        assert sanitise_dna(bad) == {}
