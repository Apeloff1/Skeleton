import pytest

from skeleton.frontier.gameforge_traffic import TrafficClass, TrafficShaper


def test_each_class_is_independently_bounded() -> None:
    shaper = TrafficShaper(interactive=2, background=1, bulk=1)
    assert shaper.acquire(TrafficClass.INTERACTIVE).admitted
    assert shaper.acquire(TrafficClass.INTERACTIVE).admitted
    assert not shaper.acquire(TrafficClass.INTERACTIVE).admitted
    assert shaper.acquire(TrafficClass.BACKGROUND).admitted
    assert shaper.active(TrafficClass.INTERACTIVE) == 2


def test_release_restores_capacity() -> None:
    shaper = TrafficShaper(bulk=1)
    assert shaper.acquire(TrafficClass.BULK).admitted
    assert not shaper.acquire(TrafficClass.BULK).admitted
    shaper.release(TrafficClass.BULK)
    assert shaper.acquire(TrafficClass.BULK).admitted


def test_release_without_active_request_fails() -> None:
    shaper = TrafficShaper()
    with pytest.raises(ValueError):
        shaper.release(TrafficClass.BACKGROUND)


def test_limits_must_be_positive() -> None:
    with pytest.raises(ValueError):
        TrafficShaper(interactive=0)
