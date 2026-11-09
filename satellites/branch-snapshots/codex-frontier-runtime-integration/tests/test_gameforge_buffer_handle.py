from skeleton.frontier.gameforge_buffer_pool import lease
from skeleton.frontier.gameforge_runtime import BufferClass, BufferPool


def test_buffer_handle_returns_exact_runtime_lease_once():
    pool = BufferPool(1)
    handle = lease(pool, 100)
    assert handle.buffer_class is BufferClass.SMALL
    assert pool.leased == 1
    assert handle.return_to(pool)
    assert pool.leased == 0
    assert not handle.return_to(pool)
