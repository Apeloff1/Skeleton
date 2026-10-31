"""Adversarial time/size bound tests for local regex delivery."""

import pytest

from skeleton.context.delivery_regex import match_delivery_regex, validate_delivery_regex
from skeleton.context.sealed_sandwich import (
    SealedContextError, SealedContextLimitError,
)


def test_small_fullmatch_is_allowed():
    validate_delivery_regex(r"[0-9]{1,4}")
    match_delivery_regex("1234", r"[0-9]{1,4}")


def test_partial_match_is_denied():
    with pytest.raises(SealedContextError):
        match_delivery_regex("1234X", r"[0-9]{1,4}")


def test_malformed_pattern_is_rejected_before_sampling():
    with pytest.raises(SealedContextError):
        validate_delivery_regex("(unclosed")


def test_pattern_budget_is_strict():
    with pytest.raises(SealedContextLimitError):
        validate_delivery_regex("a" * 2049)


def test_long_output_fails_without_attempting_catastrophic_match():
    with pytest.raises(SealedContextLimitError):
        match_delivery_regex("a" * (64 * 1024 + 1), r"(a+)+$")


def test_catastrophic_backtracking_times_out_instead_of_hanging():
    with pytest.raises(SealedContextLimitError, match="time limit"):
        match_delivery_regex("a" * 5000 + "!", r"(a+)+$")


def test_surrogate_unicode_is_never_delivered():
    with pytest.raises(SealedContextError):
        match_delivery_regex("\ud800", r".*")
