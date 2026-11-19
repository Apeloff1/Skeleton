from skeleton.frontier.gameforge_window import SlidingWindow


def test_window_tracks_capacity_and_clear():
    window = SlidingWindow(2)
    assert window.capacity == 2
    assert not window.full
    window.add("a")
    window.add("b")
    assert window.full
    window.add("c")
    assert window.values() == ("b", "c")
    window.clear()
    assert len(window) == 0
    assert not window.full
