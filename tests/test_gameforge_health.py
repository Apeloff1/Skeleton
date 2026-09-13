import pytest

from skeleton.frontier.gameforge_health import HealthPool


def test_pool_reuses_only_healthy_resources() -> None:
    values = iter(["first", "second"])
    healthy = {"first": True, "second": False}
    pool = HealthPool(lambda: next(values), lambda value: healthy[value], capacity=2)

    assert pool.checkout() == "first"
    assert pool.release("first") is True
    assert pool.checkout() == "first"
    assert pool.release("second") is False
    assert pool.stats().rejected == 1


def test_pool_has_hard_idle_capacity() -> None:
    pool = HealthPool(lambda: "new", lambda _: True, capacity=2)
    assert pool.release("a") is True
    assert pool.release("b") is True
    assert pool.release("c") is False
    assert pool.idle == 2


def test_pool_expires_resources_by_age() -> None:
    now = [100.0]
    pool = HealthPool(lambda: "fresh", lambda _: True, max_age_seconds=5, clock=lambda: now[0])
    assert pool.release("old") is True
    now[0] = 106.0
    assert pool.checkout() == "fresh"
    assert pool.idle == 0


def test_pool_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError):
        HealthPool(lambda: object(), lambda _: True, capacity=0)
    with pytest.raises(ValueError):
        HealthPool(lambda: object(), lambda _: True, max_age_seconds=0)


def test_unhealthy_factory_fails_closed() -> None:
    pool = HealthPool(lambda: "bad", lambda _: False)
    with pytest.raises(RuntimeError, match="unhealthy"):
        pool.checkout()
    assert pool.stats().rejected == 1
