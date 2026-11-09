import pytest
from skeleton.runtime.research_queue import *


def test_research_never_consumes_production_reservation():
    queue = ResearchQueue((ResearchComputeJob("r", 10, 100, "p"),))
    assert queue.allocate(10, 8) == (ResearchAllocation("r", 2),)


def test_priority_is_deterministic():
    queue = ResearchQueue(
        (
            ResearchComputeJob("b", 1, 1, "p"),
            ResearchComputeJob("a", 2, 1, "p"),
        )
    )
    assert queue.allocate(1, 0)[0].job_id == "a"


def test_production_reservation_cannot_exceed_capacity():
    with pytest.raises(ValueError):
        ResearchQueue(()).allocate(1, 2)


def test_production_workload_cannot_enter_research_queue():
    with pytest.raises(ValueError):
        ResearchComputeJob("p", 1, 1, "prov", workload_class="production")


def test_research_classes_are_explicit_and_supported():
    queue = ResearchQueue(
        (
            ResearchComputeJob("e", 2, 1, "prov", workload_class="experiment"),
            ResearchComputeJob("r", 1, 1, "prov", workload_class="reproduction"),
        )
    )
    assert [item.job_id for item in queue.allocate(2, 0)] == ["e", "r"]


def test_duplicate_jobs_fail_before_scheduling():
    job = ResearchComputeJob("r", 1, 1, "p")
    with pytest.raises(ValueError):
        ResearchQueue((job, job))
