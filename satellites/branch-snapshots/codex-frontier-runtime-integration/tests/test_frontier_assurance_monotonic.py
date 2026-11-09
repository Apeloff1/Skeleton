from skeleton.frontier.assurance.monotonic import MonotonicCounter


def test_counter_is_strictly_monotonic():
    counter = MonotonicCounter(4)
    assert counter.next() == 5
    assert counter.next() == 6
    assert counter.value == 6
