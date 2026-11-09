"""A negative episodic limit must not mark the weakest memories as accessed."""

import pytest

from skeleton.memory.mag import MAGStore


def test_negative_top_k_does_not_touch_episodes() -> None:
    store = MAGStore("user-1")
    episode_id = store.add_episode("alpha beta gamma", importance=1.0)
    before = store._episodes[episode_id].access_count
    with pytest.raises(ValueError):
        store.query("alpha", top_k=-1)
    assert store._episodes[episode_id].access_count == before
    assert store.query("alpha", top_k=0) == []
