"""A pool with no usage is not idle, and one sample is not a flat trend."""

import pytest

from skeleton.intelligence.capacity_planner import CapacityPlanner


def test_unobserved_pool_has_no_usage() -> None:
    planner = CapacityPlanner()
    planner.define_pool("workers", 100, "slots")
    pool = planner._pools["workers"]
    assert pool.current_usage() is None
    assert pool.headroom() is None
    assert pool.utilization() is None
    assert planner.analyze() == []
    with pytest.raises(ValueError):
        planner.saturation_estimate("workers")
    with pytest.raises(ValueError):
        planner.record_usage("workers", True)
    with pytest.raises(KeyError):
        planner.saturation_estimate("missing")
    planner.record_usage("workers", 40)
    assert planner.card()["pools"]["workers"]["headroom"] == 60.0
