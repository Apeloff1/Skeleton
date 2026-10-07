import pytest

from skeleton.frontier.gameforge_lifecycle import Lifecycle, ServiceLifecycle


def test_lifecycle_exposes_terminal_state():
    lifecycle = ServiceLifecycle()
    assert lifecycle.state is Lifecycle.NEW
    assert not lifecycle.can_accept
    assert lifecycle.ready() is Lifecycle.READY
    assert lifecycle.can_accept
    assert lifecycle.drain() is Lifecycle.DRAINING
    assert lifecycle.draining
    assert lifecycle.stop() is Lifecycle.STOPPED
    assert lifecycle.stopped


def test_lifecycle_rejects_ready_after_stop():
    lifecycle = ServiceLifecycle()
    lifecycle.stop()
    with pytest.raises(RuntimeError):
        lifecycle.ready()
