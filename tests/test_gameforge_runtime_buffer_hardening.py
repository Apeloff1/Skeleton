import pytest

from skeleton.frontier.gameforge_runtime import BufferClass, BufferPool


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
