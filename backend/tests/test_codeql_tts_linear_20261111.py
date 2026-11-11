"""Regression for the four historical CodeQL TTS polynomial-ReDoS alerts.

The shaping path must be O(n) in caller text (bounded by TTS_LIMIT), without
nested repeated whole-string casefolds or backtracking regex heuristics.
"""
from __future__ import annotations

import inspect

import pytest

from core import expressive_tts as tts


def test_multiword_connectives_preserve_useful_cadence_and_case():
    for source, expected in (
        ("Hello but really.", "Hello, but really."),
        ("See however this works.", "See, however this works."),
        ("Ready finally here.", "Ready, finally here."),
    ):
        assert expected == tts.shape_cadence(source, tone="butler")
    result = tts.shape_cadence("Straße and yet progress.", tone="butler")
    assert result.startswith("Straße, and")
    assert result.endswith("progress.")


def test_repeated_connectives_have_bounded_output_and_terminate():
    # This pattern formerly forced repeated O(n) casefold + slice edits
    # inside a loop, giving quadratic effort across many matches.
    payload = ("word but " * 600) + "finish."
    first = tts.shape_cadence(payload, tone="storyteller")
    second = tts.shape_cadence(payload, tone="storyteller")
    assert first == second
    assert 1 <= len(first) <= tts.TTS_LIMIT
    assert "word" in first


def test_caller_text_is_sliced_before_unbounded_strip_or_normalization():
    long_text = "hello but world." + (" " * 4_000_000)
    result = tts.shape_cadence(long_text)
    assert result == "hello, but world."
    assert len(result) <= tts.TTS_LIMIT


@pytest.mark.parametrize("bad", [None, True, 5, {}, ["text"]])
def test_invalid_types_fail_before_expensive_text_processing(bad):
    with pytest.raises(ValueError, match="text"):
        tts.shape_cadence(bad)


def test_cadence_source_has_no_unbounded_search_and_rewrite_loop():
    body = inspect.getsource(tts.shape_cadence)
    assert "while True:" not in body
    assert "folded = s.casefold()\n                index = folded.find" not in body
    assert "text[:TTS_LIMIT].strip()" in body
