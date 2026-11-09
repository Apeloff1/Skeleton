"""Tests for skeleton.kernel.coalesce (gameforge-rs coalesce::Coalescer port)."""

from __future__ import annotations

import threading
import time

from skeleton.kernel.coalesce import Coalescer


def test_single_get_returns_fetch():
    c = Coalescer()
    assert c.get("k", lambda: 42) == 42


def test_same_key_concurrent_callers_share_one_fetch():
    c = Coalescer()
    calls = {"n": 0}
    started = threading.Barrier(9)  # 8 workers + main
    hold = threading.Event()

    def fetch() -> str:
        calls["n"] += 1
        hold.wait(timeout=1.0)
        return "shared"

    results: list[str] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            started.wait(timeout=1.0)
            results.append(c.get("same", fetch))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    started.wait(timeout=1.0)
    # All 8 have entered get(); give the leader time to claim in-flight.
    time.sleep(0.05)
    hold.set()
    for t in threads:
        t.join()
    assert errors == []
    assert calls["n"] == 1
    assert results == ["shared"] * 8


def test_errors_propagate_to_all_waiters():
    c = Coalescer()
    started = threading.Barrier(7)  # 6 workers + main
    hold = threading.Event()

    def fetch() -> str:
        hold.wait(timeout=1.0)
        raise RuntimeError("boom")

    errors: list[BaseException] = []

    def worker() -> None:
        try:
            started.wait(timeout=1.0)
            c.get("err", fetch)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    started.wait(timeout=1.0)
    time.sleep(0.05)
    hold.set()
    for t in threads:
        t.join()
    assert len(errors) == 6
    assert all(isinstance(e, RuntimeError) and str(e) == "boom" for e in errors)


def test_different_keys_do_not_share():
    c = Coalescer()
    calls: list[str] = []
    gate = threading.Barrier(2)

    def fetch_a() -> str:
        calls.append("a")
        gate.wait(timeout=1.0)
        return "A"

    def fetch_b() -> str:
        calls.append("b")
        gate.wait(timeout=1.0)
        return "B"

    out: dict[str, str] = {}

    def wa() -> None:
        out["a"] = c.get("ka", fetch_a)

    def wb() -> None:
        out["b"] = c.get("kb", fetch_b)

    ta = threading.Thread(target=wa)
    tb = threading.Thread(target=wb)
    ta.start()
    tb.start()
    ta.join()
    tb.join()
    assert sorted(calls) == ["a", "b"]
    assert out == {"a": "A", "b": "B"}


def test_sequential_gets_refetch():
    c = Coalescer()
    n = {"v": 0}

    def fetch() -> int:
        n["v"] += 1
        return n["v"]

    assert c.get("k", fetch) == 1
    assert c.get("k", fetch) == 2
    assert n["v"] == 2
