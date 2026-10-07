import pytest
from skeleton.runtime.gpu_interconnect import *


def test_collective_requires_measured_paths():
    with pytest.raises(ValueError):
        place_collective(
            ("g0", "g1"),
            (GPUInterconnect("g0", "g1", 10, False),),
        )


def test_heterogeneous_bandwidth_is_preserved():
    placement = place_collective(
        ("g0", "g1"),
        (GPUInterconnect("g0", "g1", 7, True),),
    )
    assert placement.evidence[0].bandwidth == 7
    assert placement.bottleneck == 7


def test_three_gpu_collective_requires_all_pairwise_measurements():
    links = (
        GPUInterconnect("a", "b", 1, True),
        GPUInterconnect("b", "c", 1, True),
    )
    with pytest.raises(ValueError):
        place_collective(("a", "b", "c"), links)


def test_conflicting_duplicate_link_evidence_rejected():
    links = (
        GPUInterconnect("a", "b", 10, True),
        GPUInterconnect("b", "a", 20, True),
    )
    with pytest.raises(ValueError):
        place_collective(("a", "b"), links)


def test_pairwise_evidence_order_is_deterministic():
    links = (
        GPUInterconnect("b", "c", 3, True),
        GPUInterconnect("a", "c", 2, True),
        GPUInterconnect("a", "b", 4, True),
    )
    placement = place_collective(("a", "b", "c"), links)
    assert [link.pair for link in placement.evidence] == [
        ("a", "b"),
        ("a", "c"),
        ("b", "c"),
    ]
    assert placement.bottleneck == 2
