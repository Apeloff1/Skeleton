import pytest

from skeleton.frontier.gameforge_runtime import BufferPool


def test_buffer_pool_rejects_invalid_cap_and_size():
    with pytest.raises(ValueError):
        BufferPool(0)
    pool = BufferPool()
    with pytest.raises(ValueError):
        pool.lease(-1)
