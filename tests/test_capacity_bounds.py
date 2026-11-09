"""A pool cannot be defined with zero capacity and then look idle."""

import pytest

from skeleton.intelligence.capacity_planner import CapacityPlanner, ResourcePool


def test_capacity_must_be_positive() -> None:
    planner = CapacityPlanner()
    with pytest.raises(ValueError):
        planner.define_pool("workers", 0, "slots")
    pool = ResourcePool("workers", 0, "slots")
    pool.usage.append(4)
    assert pool.utilization() == 1.0
