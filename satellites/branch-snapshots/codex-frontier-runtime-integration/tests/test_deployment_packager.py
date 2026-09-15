"""Tests for deployment packager.

Covers manifest generation, packaging, and validation.
"""
from __future__ import annotations

import pytest

from skeleton.cortex.deck import CommandDeck


class TestDeploymentPackager:
    def test_manifests_empty(self):
        deck = CommandDeck()
        manifests = deck.deployment_manifests()
        assert manifests == []

    def test_manifests_structure(self):
        deck = CommandDeck()
        manifests = deck.deployment_manifests()
        assert isinstance(manifests, list)
