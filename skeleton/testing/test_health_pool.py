"""Tests for skeleton.kernel.health_pool (gameforge-rs pool::HealthPool port)."""

from __future__ import annotations

import threading
import time

from skeleton.kernel.health_pool import HealthPool


def test_checkout_creates_when_empty():
    made = {"n": 0}

    def make() -> dict:
        made["n"] += 1
        return {"id": made["n"], "ok": True}

    pool = HealthPool(make_fn=make, check_fn=lambda c: c["ok"], cap=4, max_age_sec=60.0)
    conn = pool.checkout()
    assert conn["id"] == 1
    assert made["n"] == 1
    assert pool.stats()["checkouts"] == 1
    assert pool.stats()["replaced"] == 0


def test_checkin_reuses_healthy():
    made = {"n": 0}

    def make() -> dict:
        made["n"] += 1
        return {"id": made["n"], "ok": True}

    pool = HealthPool(make_fn=make, check_fn=lambda c: c["ok"], cap=4, max_age_sec=60.0)
    a = pool.checkout()
    pool.checkin(a)
    assert pool.idle_count == 1
    b = pool.checkout()
    assert b is a
    assert made["n"] == 1
    assert pool.stats()["checkouts"] == 2
    assert pool.stats()["replaced"] == 0


def test_checkout_replaces_unhealthy():
    made = {"n": 0}

    def make() -> dict:
        made["n"] += 1
        return {"id": made["n"], "ok": True}

    pool = HealthPool(make_fn=make, check_fn=lambda c: c["ok"], cap=4, max_age_sec=60.0)
    bad = {"id": 0, "ok": False}
    pool.checkin(bad)
    conn = pool.checkout()
    assert conn["ok"] is True
    assert made["n"] == 1
    assert pool.stats()["replaced"] == 1
    assert pool.stats()["checkouts"] == 1


def test_checkout_replaces_aged():
    made = {"n": 0}

    def make() -> dict:
        made["n"] += 1
        return {"id": made["n"], "ok": True}

    pool = HealthPool(make_fn=make, check_fn=lambda c: True, cap=4, max_age_sec=0.05)
    old = pool.checkout()
    pool.checkin(old)
    time.sleep(0.06)
    fresh = pool.checkout()
    assert fresh is not old
    assert made["n"] == 2
    assert pool.stats()["replaced"] == 1


def test_checkin_respects_cap():
    made = {"n": 0}

    def make() -> int:
        made["n"] += 1
        return made["n"]

    pool = HealthPool(make_fn=make, check_fn=lambda _: True, cap=2, max_age_sec=60.0)
    items = [pool.checkout() for _ in range(4)]
    for item in items:
        pool.checkin(item)
    assert pool.idle_count == 2
    assert pool.stats()["checkouts"] == 4


def test_stats_counters():
    pool = HealthPool(
        make_fn=lambda: {"ok": True},
        check_fn=lambda c: c["ok"],
        cap=2,
        max_age_sec=60.0,
    )
    assert pool.stats() == {"checkouts": 0, "replaced": 0}
    a = pool.checkout()
    pool.checkin({"ok": False})
    b = pool.checkout()  # replaces unhealthy idle, then may reuse or make
    assert pool.stats()["checkouts"] == 2
    assert pool.stats()["replaced"] == 1
    pool.checkin(a)
    pool.checkin(b)


def test_concurrent_checkout_checkin():
    counter = {"n": 0}
    lock = threading.Lock()

    def make() -> dict:
        with lock:
            counter["n"] += 1
            return {"id": counter["n"], "ok": True}

    pool = HealthPool(make_fn=make, check_fn=lambda c: c["ok"], cap=8, max_age_sec=60.0)
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            for _ in range(30):
                conn = pool.checkout()
                pool.checkin(conn)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert pool.stats()["checkouts"] == 8 * 30
    assert pool.idle_count <= 8
