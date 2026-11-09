import pytest
from skeleton.runtime.gpu_memory import *


def test_reservation_precedes_load_and_is_deterministic():
    pool, first = GPUMemoryPool(10).reserve("a", 4)
    pool, second = pool.reserve("b", 3)
    assert (first.start, second.start) == (0, 4)


def test_oom_fails_before_allocation():
    with pytest.raises(MemoryError):
        GPUMemoryPool(2).reserve("x", 3)


def test_duplicate_reservation_and_bool_size_rejected():
    pool, _ = GPUMemoryPool(10).reserve("r", 2)
    with pytest.raises(ValueError):
        pool.reserve("r", 1)
    with pytest.raises(ValueError):
        pool.reserve("x", True)


def test_release_reclaims_space():
    pool, _ = GPUMemoryPool(2).reserve("r", 2)
    pool = pool.release("r")
    pool, replacement = pool.reserve("x", 2)
    assert replacement.start == 0


def test_alignment_accounting_and_fragmentation_are_deterministic():
    pool, first = GPUMemoryPool(16).reserve("a", 3, alignment=4, owner="model-a")
    pool, second = pool.reserve("b", 4, alignment=4, owner="model-b")
    assert (first.start, second.start) == (0, 4)
    assert pool.used == 7
    assert pool.free == 9
    pool = pool.release("a")
    assert pool.largest_free_block == 8
    assert pool.fragmentation_bytes == 4


def test_allocation_requires_existing_reservation_and_boolean_commit():
    pool, reservation = GPUMemoryPool(8).reserve("a", 4)
    allocation = pool.allocation("a")
    assert allocation.reservation == reservation and allocation.committed
    with pytest.raises(KeyError):
        pool.allocation("missing")
    with pytest.raises(ValueError):
        pool.allocation("a", committed=1)
