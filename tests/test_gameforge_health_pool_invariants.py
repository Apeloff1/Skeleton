import pytest

from skeleton.frontier.gameforge_health import HealthPool


def test_pool_rejects_boolean_capacity_and_noncallable_factory():
    with pytest.raises(ValueError):
        HealthPool(lambda: object(), lambda _: True, capacity=True)
    with pytest.raises(TypeError):
        HealthPool(None, lambda _: True)  # type: ignore[arg-type]


def test_release_is_idempotent_and_requires_checkout():
    resource = object()
    pool = HealthPool(lambda: resource, lambda _: True)
    assert not pool.release(resource)
    leased = pool.checkout()
    assert leased is resource
    assert pool.release(leased)
    assert not pool.release(leased)
    assert pool.idle == 1


def test_unhealthy_release_is_dropped():
    healthy = {"ok": True}
    pool = HealthPool(lambda: healthy, lambda value: value["ok"])
    leased = pool.checkout()
    healthy["ok"] = False
    assert not pool.release(leased)
    assert pool.idle == 0
