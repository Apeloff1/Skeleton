"""Focused regressions for Pack E runner hygiene / boundary / queue."""

from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.pr_automation.runner_hygiene import (
    BoundaryRegistry,
    QueuePressure,
    assess_queue_starvation,
    audit_live_service_boundaries,
    filter_before_cap,
    load_live_service_manifest,
)
from skeleton.pr_automation.runner_hygiene.queue_starvation import QueueCandidate
from skeleton.pr_automation.runner_hygiene.types import HygieneVerdict


ROOT = Path(__file__).resolve().parents[2]


def test_live_service_manifest_loads_and_is_nonempty():
    registry = load_live_service_manifest(ROOT / "backend/tests/live_service_tests.json")
    assert isinstance(registry, BoundaryRegistry)
    assert registry.version == 1
    assert registry.size >= 4
    assert registry.requires("test_galaxy_build_pipeline_regression.py")


def test_live_service_boundary_audit_passes_on_pack_e_tree():
    findings = audit_live_service_boundaries(root=ROOT)
    assert findings == ()


def test_filter_before_cap_does_not_let_disallowed_bases_starve_main():
    candidates = [
        QueueCandidate(number=1, base_ref="docs", head_sha="a" * 40, priority=99),
        QueueCandidate(number=2, base_ref="main", head_sha="b" * 40, priority=1),
        QueueCandidate(number=3, base_ref="main", head_sha="c" * 40, priority=5),
        QueueCandidate(number=4, base_ref="release", head_sha="d" * 40, priority=50),
    ]
    pressure = filter_before_cap(candidates, allowed_bases=("main",), max_targets=10)
    assert pressure.skipped_disallowed == 2
    assert [c.number for c in pressure.selected] == [3, 2]
    assert pressure.complete is True
    assert pressure.truncated is False
    assert assess_queue_starvation(pressure) is HygieneVerdict.ALLOW


def test_target_cap_truncation_is_fail_closed_incomplete():
    candidates = [
        QueueCandidate(number=i, base_ref="main", head_sha=f"{i:040d}", priority=i)
        for i in range(1, 6)
    ]
    pressure = filter_before_cap(candidates, allowed_bases=("main",), max_targets=2)
    assert isinstance(pressure, QueuePressure)
    assert pressure.truncated is True
    assert pressure.complete is False
    assert pressure.starved is True
    assert len(pressure.selected) == 2
    assert assess_queue_starvation(pressure) is HygieneVerdict.HOLD
    assert any(f.code == "queue.target_cap_truncation" for f in pressure.findings)


def test_no_eligible_after_base_filter_denies():
    candidates = [
        QueueCandidate(number=9, base_ref="feature", head_sha="e" * 40),
    ]
    pressure = filter_before_cap(candidates, allowed_bases=("main",), max_targets=5)
    assert pressure.selected == ()
    assert assess_queue_starvation(pressure) is HygieneVerdict.DENY
