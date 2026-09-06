"""Tests for resilience patterns.

Covers circuit breaker, retry, bulkhead, load shedder,
health probes, and rate limiter integration.
"""
from __future__ import annotations

import pytest

from skeleton.cortex.deck import CommandDeck


class TestResiliencePatterns:
    def test_circuit_card(self):
        deck = CommandDeck()
        card = deck.circuit_card()
        assert card["state"] == "closed"

    def test_retry_card(self):
        deck = CommandDeck()
        card = deck.retry_card()
        assert "total_retries" in card

    def test_bulkhead_card(self):
        deck = CommandDeck()
        card = deck.bulkhead_card()
        assert "active_threads" in card

    def test_load_shedder_card(self):
        deck = CommandDeck()
        card = deck.load_shedder_card()
        assert card["kind"] == "load-shedder-card"

    def test_health_probe_card(self):
        deck = CommandDeck()
        card = deck.health_probe_card()
        assert card["kind"] == "health-probe-card"

    def test_rate_limiter_card(self):
        deck = CommandDeck()
        card = deck.rate_limiter_card()
        assert card["kind"] == "rate-limiter-card"
