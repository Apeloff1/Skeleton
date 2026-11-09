"""Scenario-driven Pack A admit depth tests."""

from __future__ import annotations

import pytest

from skeleton.api.admit_write import set_defaults
from skeleton.api.pack_a.admit_depth import admit_write_deep, reset_default_deep_admit_for_tests
from skeleton.api.pack_a.admit_scenarios import (
    SCENARIOS,
    sample_mutating,
    scenario_count,
    scenarios_for_method,
)
from skeleton.api.pack_a.path_catalog import catalog_count, synthetic_rows
from skeleton.kernel.adaptive_gate import AdaptiveGate
from skeleton.kernel.chaos import ChaosGovernor
from skeleton.kernel.pack_a.tiered_depth import AdmitDecision
from skeleton.kernel.pack_a import reset_default_caches_for_tests, reset_default_meter_for_tests
from skeleton.kernel.pack_a.buffer_arena import reset_default_pools_for_tests
from skeleton.kernel.pack_a.coalesce_depth import reset_default_board_for_tests


@pytest.fixture(autouse=True)
def _reset():
    reset_default_pools_for_tests()
    reset_default_board_for_tests()
    reset_default_caches_for_tests()
    reset_default_meter_for_tests()
    reset_default_deep_admit_for_tests()
    set_defaults(gate=AdaptiveGate(capacity=512, refill_per_sec=256), governor=ChaosGovernor())
    yield


def test_scenario_catalog_size():
    assert scenario_count() == len(SCENARIOS)
    assert scenario_count() > 1000


def test_get_scenarios_are_safe():
    for s in scenarios_for_method("GET")[:50]:
        result = admit_write_deep(method=s["method"], path=s["path"])
        assert result.decision is AdmitDecision.SAFE_METHOD


@pytest.mark.parametrize("s", sample_mutating(30))
def test_mutating_scenarios_admit(s):
    result = admit_write_deep(
        method=s["method"], path=s["path"], priority=s["priority"], use_decision_cache=False
    )
    assert result.decision is AdmitDecision.ADMITTED
    assert result.route_class == s["route_class"]


def test_path_catalog_synthetic_nonempty():
    assert catalog_count() > 1500
    assert len(synthetic_rows()) == 1500
