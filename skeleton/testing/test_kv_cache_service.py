import pytest
from skeleton.kv.cache_service import *


def key(tenant="a", session="s", model="m", config="c", prefix="p", scope="private"):
    return KVCacheKey(tenant, session, model, config, prefix, scope)


def test_cross_tenant_or_model_reuse_rejected():
    entry = KVCacheEntry(key(), "alloc")
    lease = KVCacheLease(entry, "h", 0, 10)
    with pytest.raises(PermissionError):
        reuse(entry, key(tenant="b"), 1, lease, "h")
    with pytest.raises(PermissionError):
        reuse(entry, key(model="other"), 1, lease, "h")


def test_expired_and_future_lease_rejected():
    entry = KVCacheEntry(key(), "a")
    with pytest.raises(PermissionError):
        reuse(entry, key(), 10, KVCacheLease(entry, "h", 0, 10), "h")
    with pytest.raises(PermissionError):
        reuse(entry, key(), 0, KVCacheLease(entry, "h", 1, 10), "h")


def test_wrong_holder_and_privacy_scope_rejected():
    entry = KVCacheEntry(key(), "a")
    lease = KVCacheLease(entry, "h", 0, 10)
    with pytest.raises(PermissionError):
        reuse(entry, key(), 1, lease, "other")
    with pytest.raises(PermissionError):
        reuse(entry, key(scope="shared"), 1, lease, "h")


def test_session_config_and_prefix_identity_are_cache_boundaries():
    entry = KVCacheEntry(key(), "a")
    lease = KVCacheLease(entry, "h", 0, 10)
    for candidate in (
        key(session="other"),
        key(config="other"),
        key(prefix="other"),
    ):
        with pytest.raises(PermissionError):
            reuse(entry, candidate, 1, lease, "h")


def test_lease_must_bind_entry_and_time_type_is_strict():
    entry = KVCacheEntry(key(), "a")
    other = KVCacheEntry(key(), "b")
    lease = KVCacheLease(other, "h", 0, 10)
    with pytest.raises(PermissionError):
        reuse(entry, key(), 1, lease, "h")
    with pytest.raises(ValueError):
        reuse(entry, key(), True, KVCacheLease(entry, "h", 0, 10), "h")
