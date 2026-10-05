from skeleton.frontier.resilience import DegradationLevel, ResilienceController


def test_resilience_degrades_monotonically_and_recovers():
    controller = ResilienceController()
    assert controller.decide().allow_write
    assert controller.degrade(2) == DegradationLevel.SHED_BACKGROUND
    decision = controller.decide()
    assert not decision.allow_background
    assert not decision.allow_stale_reads
    assert controller.degrade(2) == DegradationLevel.READ_ONLY
    assert not controller.decide().allow_write
    assert controller.recover(99) == DegradationLevel.NORMAL


def test_invalid_step_is_rejected():
    controller = ResilienceController()
    for method in (controller.degrade, controller.recover):
        try:
            method(0)
        except ValueError:
            pass
        else:
            raise AssertionError("non-positive steps must fail")
