from skeleton.frontier.gameforge_sliding_window_v2 import SlidingWindowV2

def test_window_is_bounded_and_ordered():
    w = SlidingWindowV2(2)
    w.add(1); w.add(2); w.add(3)
    assert w.snapshot() == (2, 3)

def test_window_rejects_zero_capacity():
    try:
        SlidingWindowV2(0)
    except ValueError:
        pass
    else:
        raise AssertionError("zero capacity accepted")
