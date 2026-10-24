"""GF-P0-16: exact environments, deterministic replay, holdout isolation, bounded buffers."""

from __future__ import annotations

import pytest

from skeleton.provider_environment import (
    DeterministicReplayBuffer, EnvironmentIdentity, EnvironmentMismatchError,
    ExactEnvironmentRegistry, HoldoutBuffer, HoldoutLeakError, HoldoutSplit,
    make_record, replay_episode, route_records,
)


class _Env:
    def __init__(self, simulation_id="g", seed=7):
        self.simulation_id, self.seed = simulation_id, seed
        self._x = 0

    @property
    def state(self):
        return {"x": self._x}

    def reset(self):
        self._x = self.seed
        return self.state

    def step(self, action):
        self._x += int(action["dx"])
        return None


ID = EnvironmentIdentity("g", "build1", 7)
SPLIT = HoldoutSplit(salt="s", holdout_fraction=0.3)


def test_exact_environment_resolution():
    reg = ExactEnvironmentRegistry()
    env = _Env()
    reg.register(ID, env)
    assert reg.resolve(ID) is env
    with pytest.raises(EnvironmentMismatchError):
        reg.resolve(EnvironmentIdentity("g", "build2", 7))
    with pytest.raises(EnvironmentMismatchError):
        reg.register(EnvironmentIdentity("g", "b", 8), _Env())


def test_environment_registry_capped():
    reg = ExactEnvironmentRegistry(max_environments=1)
    reg.register(ID, _Env())
    with pytest.raises(RuntimeError):
        reg.register(EnvironmentIdentity("g", "b2", 7), _Env())


def test_replay_is_deterministic():
    actions = [{"dx": 1}, {"dx": 2}]
    assert replay_episode(_Env(), actions) == replay_episode(_Env(), actions)
    assert replay_episode(_Env(), actions) != replay_episode(_Env(), [{"dx": 3}])


def _records(n):
    return [make_record(f"e{i}", ID, {"i": i}) for i in range(n)]


def test_holdout_isolation():
    replay, hold = DeterministicReplayBuffer(SPLIT, max_items=1000), HoldoutBuffer(SPLIT, max_items=1000)
    route_records(_records(200), replay, hold)
    train_ids = {r.example_id for r in replay.records()}
    hold_ids = {r.example_id for r in hold.records()}
    assert hold_ids and train_ids and not (train_ids & hold_ids)
    leak = next(r for r in _records(200) if SPLIT.is_holdout(r.example_id))
    with pytest.raises(HoldoutLeakError):
        replay.add(leak)


def test_seeded_sampling_reproducible():
    a, b = DeterministicReplayBuffer(SPLIT, max_items=500), DeterministicReplayBuffer(SPLIT, max_items=500)
    for buf in (a, b):
        for r in _records(100):
            if not SPLIT.is_holdout(r.example_id):
                buf.add(r)
    assert a.sample(10, seed=1) == b.sample(10, seed=1)


def test_bounded_memory_replay_and_holdout():
    replay, hold = DeterministicReplayBuffer(SPLIT, max_items=16), HoldoutBuffer(SPLIT, max_items=8)
    route_records(_records(5000), replay, hold)
    assert len(replay) == 16 and len(hold) == 8
    assert replay.evicted > 0 and hold.evicted > 0
