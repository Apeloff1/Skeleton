"""Pack H admit pressure: sources, board caching, fail-closed behavior."""

from __future__ import annotations

import pytest

from skeleton.api.pack_h import admit_pressure as ap


class Clock:
    def __init__(self, t: float = 100.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def test_in_process_source_tracks_queue_and_active():
    src = ap.InProcessPressureSource(max_concurrency=2, max_queue_depth=4, max_tenant_queue_depth=2)
    src.enqueue("a")
    src.enqueue("a")
    raw = src.observe("a")
    assert raw.queued == 2 and raw.tenant_queued == 2
    assert ap.classify(raw).state is ap.PressureState.SHED  # tenant queue full
    src.start("a")
    raw = src.observe("a")
    assert raw.active == 1 and raw.queued == 1
    src.finish("a")
    src.abandon("a")
    raw = src.observe()
    assert raw.active == 0 and raw.queued == 0


def test_board_caches_within_ttl_and_fails_closed():
    calls = {"n": 0}

    class Flaky:
        def observe(self, tenant_id=None):
            calls["n"] += 1
            if calls["n"] > 1:
                raise ap.PressureSourceError("down")
            return ap.RawPressure(active=0, queued=0, max_concurrency=1, max_queue_depth=1)

    clock = Clock()
    board = ap.PressureBoard(Flaky(), ttl_s=1.0, clock=clock)
    assert board.snapshot().state is ap.PressureState.OPEN
    assert board.snapshot().state is ap.PressureState.OPEN
    assert calls["n"] == 1
    clock.t += 2
    snap = board.snapshot()
    assert snap.state is ap.PressureState.SHED and snap.reason == "source_unavailable"
    assert snap.retry_after_header() is not None


def test_install_board_overrides_module_snapshot():
    class Board:
        def snapshot(self, tenant_id=None):
            return ap.classify(ap.RawPressure(active=0, queued=0, max_concurrency=1, max_queue_depth=1))

    ap.install_board(Board())  # type: ignore[arg-type]
    try:
        assert ap.snapshot("x").state is ap.PressureState.OPEN
    finally:
        ap.install_board(None)


def test_snapshot_roundtrip_and_header():
    snap = ap.classify(ap.RawPressure(active=0, queued=80, max_concurrency=10, max_queue_depth=100))
    back = ap.PressureSnapshot.from_dict(snap.as_dict())
    assert back == snap
    assert int(snap.retry_after_header()) >= 1


def test_raw_pressure_rejects_negative():
    with pytest.raises(Exception):
        ap.RawPressure(active=-1, queued=0, max_concurrency=1, max_queue_depth=1)
