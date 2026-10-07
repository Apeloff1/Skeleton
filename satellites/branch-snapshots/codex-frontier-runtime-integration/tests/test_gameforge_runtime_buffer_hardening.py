import pytest

from skeleton.frontier.gameforge_runtime import BufferClass, BufferLease, BufferPool


def test_buffer_pool_reclaims_once_and_tracks_capacity():
    pool = BufferPool(1)
    lease = pool.lease(100)
    assert pool.leased == 1
    assert pool.reclaim(lease)
    assert pool.leased == 0
    assert pool.available(BufferClass.SMALL) == 1
    assert not pool.reclaim(lease)
    assert pool.available_total == 1


def test_buffer_pool_validates_sizes():
    pool = BufferPool()
    with pytest.raises(ValueError):
        pool.lease(-1)
    with pytest.raises(ValueError):
        pool.lease(1.5)


def test_buffer_pool_rejects_foreign_lease():
    pool = BufferPool()
    foreign = BufferLease(bytearray(16), BufferClass.SMALL)
    assert not pool.reclaim(foreign)
    assert pool.leased == 0


def test_buffer_pool_rejects_invalid_lease_type():
    pool = BufferPool()
    with pytest.raises(TypeError):
        pool.reclaim(object())


def test_buffer_pool_caps_each_class():
    pool = BufferPool(1)
    first = pool.lease(100)
    second = pool.lease(100)
    assert pool.reclaim(first)
    assert pool.reclaim(second)
    assert pool.available(BufferClass.SMALL) == 1
