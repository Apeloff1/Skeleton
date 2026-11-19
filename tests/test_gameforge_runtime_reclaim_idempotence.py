from skeleton.frontier.gameforge_runtime import BufferPool


def test_buffer_reclaim_is_idempotent():
    pool = BufferPool(class_cap=1)
    lease = pool.lease(128)
    pool.reclaim(lease)
    pool.reclaim(lease)
    assert pool.leased == 0
    assert pool.available(lease.buffer_class) == 1
