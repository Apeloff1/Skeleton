from skeleton.frontier.gameforge_event_bus import BoundedEventBus


def test_event_bus_sequences_are_monotonic_and_fifo() -> None:
    bus = BoundedEventBus[int](capacity=3)
    first = bus.publish(10)
    second = bus.publish(20)
    assert first.sequence == 0
    assert second.sequence == 1
    assert [event.value for event in bus.since(0)] == [10, 20]


def test_event_bus_has_hard_retention_bound() -> None:
    bus = BoundedEventBus[int](capacity=2)
    bus.publish(1)
    bus.publish(2)
    bus.publish(3)
    assert len(bus) == 2
    assert [event.value for event in bus.since(0)] == [2, 3]


def test_event_bus_rejects_invalid_capacity() -> None:
    try:
        BoundedEventBus(capacity=0)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
