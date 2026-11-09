import pytest

from skeleton.frontier.gameforge_traffic import TrafficClass, TrafficDecision, TrafficShaper


def test_traffic_pressure_tracks_remaining_capacity():
    shaper = TrafficShaper(interactive=2, background=1, bulk=1)
    assert shaper.limit(TrafficClass.INTERACTIVE) == 2
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
    with pytest.raises(TypeError):
        shaper.remaining("interactive")
    with pytest.raises(TypeError):
        shaper.limit("interactive")


def test_traffic_limits_reject_boolean_values():
    with pytest.raises(ValueError):
        TrafficShaper(interactive=True)


def test_traffic_decision_is_typed_and_nonempty():
    decision = TrafficDecision(True, "admitted")
    assert decision.admitted
    with pytest.raises(TypeError):
        TrafficDecision(1, "admitted")
    with pytest.raises(ValueError):
        TrafficDecision(True, "")
