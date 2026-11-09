import tracemalloc

import pytest

from skeleton.perf_profiler.alloc import AllocationTracker

MB = 1024 * 1024


@pytest.fixture(autouse=True)
def _no_leaked_tracing():
    was = tracemalloc.is_tracing()
    yield
    if not was and tracemalloc.is_tracing():
        tracemalloc.stop()


def test_retained_allocation_counts_in_alloc_bytes():
    keep = []
    with AllocationTracker() as tracker:
        with tracker.scope("retain") as result:
            keep.append(bytearray(2 * MB))
    assert result.alloc_bytes >= 2 * MB
    assert result.peak_bytes >= 2 * MB
    assert tracker.totals()["alloc_bytes"] == result.alloc_bytes
    del keep


def test_transient_allocation_shows_in_peak_not_net():
    with AllocationTracker() as tracker:
        with tracker.scope("transient") as result:
            buf = bytearray(4 * MB)
            del buf
    assert result.peak_bytes >= 4 * MB
    assert result.alloc_bytes < MB


def test_child_reset_does_not_hide_parent_peak():
    with AllocationTracker() as tracker:
        with tracker.scope("outer") as outer:
            big = bytearray(6 * MB)
            del big
            with tracker.scope("inner") as inner:
                small = bytearray(MB)
                del small
    assert inner.peak_bytes >= MB
    assert inner.peak_bytes < 6 * MB
    assert outer.peak_bytes >= 6 * MB
    assert outer.children == [inner]
    assert tracker.results == [outer]


def test_top_n_reports_locations():
    with AllocationTracker(top_n=3) as tracker:
        with tracker.scope("top") as result:
            data = [bytearray(MB)]
    assert result.top
    assert any("test_alloc.py" in d.location for d in result.top)
    assert result.to_dict()["top"][0].keys() == {"location", "size_diff", "count_diff"}
    del data


def test_tracker_stops_tracing_it_started_and_respects_existing():
    assert not tracemalloc.is_tracing()
    tracker = AllocationTracker()
    assert tracemalloc.is_tracing()
    tracker.close()
    assert not tracemalloc.is_tracing()

    tracemalloc.start()
    try:
        AllocationTracker().close()
        assert tracemalloc.is_tracing()
    finally:
        tracemalloc.stop()


def test_closing_with_open_scope_fails_and_closed_tracker_refuses_scopes():
    tracker = AllocationTracker()
    cm = tracker.scope("open")
    cm.__enter__()
    with pytest.raises(RuntimeError):
        tracker.close()
    cm.__exit__(None, None, None)
    tracker.close()
    with pytest.raises(RuntimeError):
        with tracker.scope("after-close"):
            pass


def test_negative_top_n_rejected():
    with pytest.raises(ValueError):
        AllocationTracker(top_n=-1)
