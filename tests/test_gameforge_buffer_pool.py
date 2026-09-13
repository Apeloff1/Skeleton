from skeleton.frontier.gameforge_buffer_pool import lease
from skeleton.frontier.gameforge_runtime import BufferClass, BufferPool


def test_lease_wraps_class_and_is_single_return() -> None:
    pool = BufferPool()
    handle = lease(pool, 4096)
    assert handle is not None
    assert handle.buffer_class is BufferClass.SMALL
    assert handle.return_to(pool) is True
    assert handle.return_to(pool) is False


def test_large_request_uses_large_class() -> None:
    pool = BufferPool()
    handle = lease(pool, 65537)
    assert handle is not None
    assert handle.buffer_class is BufferClass.LARGE
