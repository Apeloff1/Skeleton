"""Tests for skeleton.kernel.background_lane (gameforge-rs BackgroundLane port)."""

from __future__ import annotations

import threading

from skeleton.kernel.background_lane import BackgroundLane, LanePermit


def test_default_max_concurrent_is_four():
    lane = BackgroundLane()
    assert lane.max_concurrent == 4
    permits = []
    for _ in range(4):
        p = lane.try_enter()
        assert p is not None
        permits.append(p)
    assert lane.open() == 4
    assert lane.try_enter() is None
    for p in permits:
        p.release()
    assert lane.open() == 0


def test_try_enter_returns_none_when_full():
    lane = BackgroundLane(max_concurrent=2)
    a = lane.try_enter()
    b = lane.try_enter()
    assert isinstance(a, LanePermit)
    assert isinstance(b, LanePermit)
    assert lane.try_enter() is None
    assert lane.open() == 2
    a.release()
    assert lane.open() == 1
    c = lane.try_enter()
    assert c is not None
    assert lane.open() == 2
    b.release()
    c.release()
    assert lane.open() == 0


def test_context_manager_releases():
    lane = BackgroundLane(max_concurrent=1)
    with lane.try_enter() as permit:
        assert isinstance(permit, LanePermit)
        assert lane.open() == 1
        assert lane.try_enter() is None
    assert lane.open() == 0
    again = lane.try_enter()
    assert again is not None
    again.release()


def test_release_is_idempotent():
    lane = BackgroundLane(max_concurrent=1)
    p = lane.try_enter()
    assert p is not None
    p.release()
    p.release()
    assert lane.open() == 0
    assert lane.try_enter() is not None


def test_open_tracks_currently_held():
    lane = BackgroundLane(max_concurrent=3)
    assert lane.open() == 0
    held = [lane.try_enter() for _ in range(3)]
    assert all(p is not None for p in held)
    assert lane.open() == 3
    held[1].release()
    assert lane.open() == 2
    held[0].release()
    held[2].release()
    assert lane.open() == 0


def test_zero_max_always_sheds():
    lane = BackgroundLane(max_concurrent=0)
    assert lane.try_enter() is None
    assert lane.open() == 0


def test_concurrent_try_enter():
    lane = BackgroundLane(max_concurrent=4)
    entered = []
    lock = threading.Lock()
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            for _ in range(50):
                p = lane.try_enter()
                if p is None:
                    continue
                with lock:
                    entered.append(1)
                    assert lane.open() <= 4
                p.release()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert lane.open() == 0
    assert sum(entered) > 0
