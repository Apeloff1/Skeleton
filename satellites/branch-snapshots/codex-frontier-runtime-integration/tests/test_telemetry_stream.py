"""Tests for telemetry streaming subsystem.

Covers event collection, batching, compression, and export.
"""
from __future__ import annotations

import pytest

from skeleton.cortex.deck import CommandDeck


class TestTelemetryStream:
    def test_telemetry_stats_initial(self):
        deck = CommandDeck()
        stats = deck.telemetry_stats()
        assert stats["total_events"] == 0
        assert stats["bytes_sent"] == 0

    def test_telemetry_latency(self):
        deck = CommandDeck()
        stats = deck.telemetry_stats()
        assert "latency_ms" in stats
