import pytest

from skeleton.frontier.gameforge_traffic import TrafficClass, TrafficShaper


def test_traffic_pressure_tracks_remaining_capacity():
    shaper = TrafficShaper(interactive=2, background=1, bulk=1)
    assert shaper.remaining(TrafficClass.INTERACTIVE) == 2
    assert shaper.acquire(TrafficClass.INTERACTIVE).admitted
    assert shaper.remaining(TrafficClass.INTERACTIVE) == 1
    assert shaper.acquire(TrafficClass.INTERACTIVE).admitted
    assert shaper.saturated(TrafficClass.INTERACTIVE)
    assert not shaper.acquire(TrafficClass.INTERACTIVE).admitted
    shaper.release(TrafficClass.INTERACTIVE)
    assert not shaper.saturated(TrafficClass.INTERACTIVE)


def test_traffic_rejects_invalid_class():
    shaper = TrafficShaper()
    with pytest.raises(TypeError):
        shaper.acquire("interactive")
