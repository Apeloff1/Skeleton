"""Tests for the adaptive policy engine."""
from __future__ import annotations

import pytest

from skeleton.intelligence.adaptive_policy import (
    _compute_surface_pressure,
    _suggest_threshold_adjustment,
    adapt_all_surfaces,
    adapt_surface,
    adaptive_policy_card,
    default_adaptive_config,
    load_adaptive_config,
    save_adaptive_config,
    set_adaptive_config,
    set_surface_adaptive_config,
)
from skeleton.organism.policy_state import load_policy, save_policy, set_threshold
from skeleton.organism.quality_state import append_quality


class TestAdaptiveConfig:
    def test_default_config(self):
        cfg = default_adaptive_config()
        assert cfg["enabled"] is True
        assert cfg["target_accept_rate"] == 0.85
        assert cfg["adjustment_rate"] == 0.05

    def test_load_save_roundtrip(self, tmp_path):
        cfg = default_adaptive_config()
        cfg["target_accept_rate"] = 0.90
        save_adaptive_config(cfg, root=tmp_path)
        loaded = load_adaptive_config(root=tmp_path)
        assert loaded["target_accept_rate"] == 0.90


class TestThresholdAdjustment:
    def test_suggest_lower_when_accept_rate_too_low(self):
        result = _suggest_threshold_adjustment(
            current_threshold=0.7,
            accept_rate=0.5,
            target_accept_rate=0.85,
            adjustment_rate=0.05,
            min_threshold=0.3,
            max_threshold=0.95,
        )
        assert result["adjustment"] < 0
        assert result["would_change"] is True
        assert result["suggested"] < 0.7

    def test_suggest_raise_when_accept_rate_too_high(self):
        result = _suggest_threshold_adjustment(
            current_threshold=0.7,
            accept_rate=0.95,
            target_accept_rate=0.85,
            adjustment_rate=0.05,
            min_threshold=0.3,
            max_threshold=0.95,
        )
        assert result["adjustment"] > 0
        assert result["would_change"] is True
        assert result["suggested"] > 0.7

    def test_no_change_when_within_tolerance(self):
        result = _suggest_threshold_adjustment(
            current_threshold=0.7,
            accept_rate=0.87,
            target_accept_rate=0.85,
            adjustment_rate=0.05,
            min_threshold=0.3,
            max_threshold=0.95,
        )
        assert result["would_change"] is False
        assert result["suggested"] == 0.7

    def test_respects_min_max(self):
        result = _suggest_threshold_adjustment(
            current_threshold=0.94,
            accept_rate=0.99,
            target_accept_rate=0.85,
            adjustment_rate=0.05,
            min_threshold=0.3,
            max_threshold=0.95,
        )
        assert result["suggested"] == 0.95  # capped at max


class TestSurfacePressure:
    def test_empty_history(self, tmp_path):
        info = _compute_surface_pressure("forge", 16, root=tmp_path)
        assert info["pressure"] == 0.0
        assert info["accept_rate"] == 1.0
        assert info["count"] == 0

    def test_with_quality_records(self, tmp_path):
        # Seed some quality records
        for i in range(5):
            append_quality({
                "kind": "quality",
                "surface": "forge",
                "accepted": i < 3,
                "reason": "test",
                "score": 0.8 if i < 3 else 0.4,
            }, root=tmp_path)
        info = _compute_surface_pressure("forge", 16, root=tmp_path)
        assert info["count"] == 5
        assert info["accept_rate"] == 0.6
        assert info["pressure"] == 0.4


class TestAdaptSurface:
    def test_insufficient_data(self, tmp_path):
        result = adapt_surface("forge", root=tmp_path)
        assert result["kind"] == "adaptive-policy-insufficient-data"
        assert result["count"] < 3

    def test_dry_run_no_change(self, tmp_path):
        # Seed enough data
        for i in range(5):
            append_quality({
                "kind": "quality",
                "surface": "forge",
                "accepted": True,
                "reason": "test",
                "score": 0.9,
            }, root=tmp_path)
        # Set initial threshold
        set_threshold("forge", 0.7, root=tmp_path)
        result = adapt_surface("forge", root=tmp_path, dry_run=True)
        assert result["kind"] == "adaptive-policy-analysis"
        assert result["dry_run"] is True
        assert result["applied"] is False

    def test_live_adjustment_low_accept_rate(self, tmp_path):
        # Seed data with low accept rate
        for i in range(10):
            append_quality({
                "kind": "quality",
                "surface": "forge",
                "accepted": i < 2,
                "reason": "test",
                "score": 0.9 if i < 2 else 0.4,
            }, root=tmp_path)
        set_threshold("forge", 0.7, root=tmp_path)
        result = adapt_surface("forge", root=tmp_path, dry_run=False)
        assert result["applied"] is True
        assert result["suggested_threshold"] < 0.7
        # Verify policy was updated
        policy = load_policy(root=tmp_path)
        assert policy["quality_thresholds"]["forge"] < 0.7

    def test_disabled_skips(self, tmp_path):
        set_adaptive_config(enabled=False, root=tmp_path)
        result = adapt_surface("forge", root=tmp_path)
        assert result["kind"] == "adaptive-policy-skip"


class TestAdaptAllSurfaces:
    def test_batch_analysis(self, tmp_path):
        # Seed data for multiple surfaces
        for surface in ["forge", "plan"]:
            for i in range(5):
                append_quality({
                    "kind": "quality",
                    "surface": surface,
                    "accepted": True,
                    "reason": "test",
                    "score": 0.9,
                }, root=tmp_path)
        result = adapt_all_surfaces(root=tmp_path, dry_run=True)
        assert result["kind"] == "adaptive-policy-batch"
        assert result["surfaces_analyzed"] >= 2


class TestConfigSetters:
    def test_set_adaptive_config(self, tmp_path):
        result = set_adaptive_config(
            target_accept_rate=0.90,
            adjustment_rate=0.10,
            root=tmp_path,
        )
        assert result["kind"] == "adaptive-config-set"
        cfg = load_adaptive_config(root=tmp_path)
        assert cfg["target_accept_rate"] == 0.90
        assert cfg["adjustment_rate"] == 0.10

    def test_set_surface_config(self, tmp_path):
        result = set_surface_adaptive_config(
            "forge",
            target_accept_rate=0.80,
            min_threshold=0.4,
            root=tmp_path,
        )
        assert result["kind"] == "adaptive-surface-config-set"
        assert result["surface"] == "forge"
        cfg = load_adaptive_config(root=tmp_path)
        assert cfg["surface_configs"]["forge"]["target_accept_rate"] == 0.80


class TestAdaptivePolicyCard:
    def test_card_structure(self, tmp_path):
        card = adaptive_policy_card(root=tmp_path)
        assert card["kind"] == "adaptive-policy-card"
        assert "surfaces" in card
        assert "enabled" in card
