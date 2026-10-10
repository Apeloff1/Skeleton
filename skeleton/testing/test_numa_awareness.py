import pytest
from skeleton.runtime.numa import *


def test_locality_preferred_when_valid():
    assert place(
        (NUMANode(0, frozenset({1}), 10),),
        NUMAAffinity(1, 0),
        5,
    ) == NUMAPlacement(0, False)


def test_unknown_or_insufficient_locality_has_explicit_fallback():
    assert place(
        (NUMANode(1, frozenset({2}), 10),),
        NUMAAffinity(1, 0),
        5,
    ).fallback


def test_negative_memory_and_duplicate_node_rejected():
    node = NUMANode(0, frozenset({0}), 1)
    with pytest.raises(ValueError):
        place((node, node), NUMAAffinity(0, 0), 1)
    with pytest.raises(ValueError):
        place((node,), NUMAAffinity(0, 0), -1)


def test_fallback_prefers_cpu_owner_before_unrelated_low_node():
    nodes = (
        NUMANode(0, frozenset({0}), 16),
        NUMANode(2, frozenset({7}), 16),
    )
    placement = place(nodes, NUMAAffinity(7, 9), 4)
    assert placement == NUMAPlacement(2, True)


def test_cpu_cannot_belong_to_multiple_numa_nodes():
    nodes = (
        NUMANode(0, frozenset({1}), 8),
        NUMANode(1, frozenset({1}), 8),
    )
    with pytest.raises(ValueError):
        place(nodes, NUMAAffinity(1, 0), 1)
