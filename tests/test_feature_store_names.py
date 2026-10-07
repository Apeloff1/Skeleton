"""Feature names that contain a colon must still use their own TTL."""

import time

from skeleton.intelligence.feature_store import FeatureStore


def test_freshness_uses_the_full_feature_name() -> None:
    store = FeatureStore()
    store.register("player:score", "player", ttl_s=10.0)
    store.write("player:score", "ada", 3, timestamp_ns=time.time_ns())
    row = store.freshness()["player:score:ada"]
    assert row["stale"] is False
    assert row["values"] == 1
    assert store.online("player:score", "ada") == 3
