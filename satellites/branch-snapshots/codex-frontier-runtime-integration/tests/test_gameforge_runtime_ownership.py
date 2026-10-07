import pytest

from skeleton.frontier.gameforge_runtime import BufferClass, BufferPool


def test_reclaim_rejects_foreign_lease():
    first = BufferPool()
    second = BufferPool()
    lease = first.lease(1)
    with pytest.raises(TypeError):
        first.reclaim(object())
    assert not second.reclaim(lease)
    assert first.reclaim(lease)


def test_available_requires_buffer_class():
    pool = BufferPool()
    with pytest.raises(TypeError):
        pool.available("small")
    assert pool.available(BufferClass.SMALL) == 0
