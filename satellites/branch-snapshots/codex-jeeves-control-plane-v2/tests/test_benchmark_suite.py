"""Tests for benchmark suite.

Covers benchmark execution, result aggregation, and reporting.
"""
from __future__ import annotations

import pytest

from skeleton.cortex.deck import CommandDeck


class TestBenchmarkSuite:
    def test_benchmark_card_initial(self):
        deck = CommandDeck()
        card = deck.benchmark_card()
        assert card["runs"] == 0

    def test_benchmark_metrics(self):
        deck = CommandDeck()
        card = deck.benchmark_card()
        assert "mean_latency_ms" in card
        assert "p99_latency_ms" in card
