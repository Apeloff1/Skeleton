"""Policy revision and staged rollout regressions."""

from __future__ import annotations

import sys

import pytest

from skeleton.shells.policy_rollout import PolicyRolloutManager, RolloutPhase
from skeleton.shells.policy_store import PolicyConflict, PolicyStore
from skeleton.shells.runner import ShellPolicy


def policy(tmp_path, **changes):
    root = tmp_path / "root"
    root.mkdir(exist_ok=True)
    values = dict(
        executables={"python": sys.executable},
        cwd_roots=(root,),
        allowed_env=frozenset(),
        inherited_env=frozenset(),
        default_timeout=5.0,
        max_timeout=10.0,
        max_output_bytes=1024,
        max_input_bytes=1024,
        max_env_bytes=1024,
        max_args=16,
        max_arg_bytes=1024,
    )
    values.update(changes)
    return ShellPolicy(**values)


def test_policy_store_starts_at_revision_one(tmp_path):
    store = PolicyStore(policy(tmp_path))
    current = store.current()
    assert current.revision == 1
    assert current.fingerprint


def test_policy_store_compare_and_swap(tmp_path):
    store = PolicyStore(policy(tmp_path))
    second = store.compare_and_swap(1, policy(tmp_path, max_timeout=9.0))
    assert second.revision == 2
    assert store.current() == second


def test_policy_store_conflict(tmp_path):
    store = PolicyStore(policy(tmp_path))
    store.compare_and_swap(1, policy(tmp_path, max_timeout=9.0))
    with pytest.raises(PolicyConflict):
        store.compare_and_swap(1, policy(tmp_path, max_timeout=8.0))


def test_policy_store_replace_advances_revision(tmp_path):
    store = PolicyStore(policy(tmp_path))
    second = store.replace(policy(tmp_path, max_output_bytes=512))
    assert second.revision == 2


def test_policy_store_history(tmp_path):
    store = PolicyStore(policy(tmp_path))
    store.replace(policy(tmp_path, max_output_bytes=900))
    store.replace(policy(tmp_path, max_output_bytes=800))
    assert [item.revision for item in store.history()] == [1, 2, 3]


def test_policy_store_at_revision(tmp_path):
    first_policy = policy(tmp_path)
    store = PolicyStore(first_policy)
    store.replace(policy(tmp_path, max_output_bytes=900))
    assert store.at(1).policy == first_policy
    assert store.at(2).revision == 2


@pytest.mark.parametrize("revision", [0, -1, 99])
def test_policy_store_invalid_revision(tmp_path, revision):
    store = PolicyStore(policy(tmp_path))
    with pytest.raises(KeyError):
        store.at(revision)


def test_policy_fingerprint_changes_when_limit_changes(tmp_path):
    store = PolicyStore(policy(tmp_path))
    first = store.current().fingerprint
    second = store.replace(policy(tmp_path, max_timeout=9)).fingerprint
    assert first != second


def test_policy_rollout_prepare_creates_target_revision(tmp_path):
    store = PolicyStore(policy(tmp_path))
    manager = PolicyRolloutManager(store)
    rollout = manager.prepare("r1", policy(tmp_path, max_timeout=9))
    assert rollout.phase is RolloutPhase.PREPARED
    assert rollout.base_revision == 1
    assert rollout.target_revision == 2


def test_policy_rollout_cannot_duplicate_id(tmp_path):
    store = PolicyStore(policy(tmp_path))
    manager = PolicyRolloutManager(store)
    manager.prepare("r1", policy(tmp_path, max_timeout=9))
    with pytest.raises(RuntimeError):
        manager.prepare("r1", policy(tmp_path, max_timeout=8))


def test_policy_rollout_advance_sequence(tmp_path):
    store = PolicyStore(policy(tmp_path))
    manager = PolicyRolloutManager(store)
    manager.prepare("r1", policy(tmp_path, max_timeout=9))
    assert manager.advance("r1").phase is RolloutPhase.CANARY
    assert manager.advance("r1").phase is RolloutPhase.BROAD
    assert manager.advance("r1").phase is RolloutPhase.COMPLETE


def test_policy_rollout_complete_cannot_advance(tmp_path):
    store = PolicyStore(policy(tmp_path))
    manager = PolicyRolloutManager(store)
    manager.prepare("r1", policy(tmp_path, max_timeout=9))
    manager.advance("r1")
    manager.advance("r1")
    manager.advance("r1")
    with pytest.raises(RuntimeError):
        manager.advance("r1")


def test_policy_rollout_prepared_selects_nobody(tmp_path):
    store = PolicyStore(policy(tmp_path))
    manager = PolicyRolloutManager(store)
    manager.prepare("r1", policy(tmp_path, max_timeout=9), canary_percent=100)
    assert not manager.selected("r1", "p")


def test_policy_rollout_canary_is_deterministic(tmp_path):
    store = PolicyStore(policy(tmp_path))
    manager = PolicyRolloutManager(store)
    manager.prepare("r1", policy(tmp_path, max_timeout=9), canary_percent=50)
    manager.advance("r1")
    first = manager.selected("r1", "p")
    assert manager.selected("r1", "p") is first


def test_policy_rollout_broad_selects_everyone(tmp_path):
    store = PolicyStore(policy(tmp_path))
    manager = PolicyRolloutManager(store)
    manager.prepare("r1", policy(tmp_path, max_timeout=9))
    manager.advance("r1")
    manager.advance("r1")
    assert manager.selected("r1", "p")
    assert manager.selected("r1", "q")


def test_policy_rollout_rollback_restores_base_policy(tmp_path):
    base = policy(tmp_path, max_timeout=10)
    target = policy(tmp_path, max_timeout=9)
    store = PolicyStore(base)
    manager = PolicyRolloutManager(store)
    manager.prepare("r1", target)
    manager.advance("r1")
    rolled = manager.rollback("r1")
    assert rolled.phase is RolloutPhase.ROLLED_BACK
    assert store.current().policy == base


def test_policy_rollout_rolled_back_selects_nobody(tmp_path):
    store = PolicyStore(policy(tmp_path))
    manager = PolicyRolloutManager(store)
    manager.prepare("r1", policy(tmp_path, max_timeout=9))
    manager.rollback("r1")
    assert not manager.selected("r1", "p")


def test_policy_rollout_complete_cannot_rollback(tmp_path):
    store = PolicyStore(policy(tmp_path))
    manager = PolicyRolloutManager(store)
    manager.prepare("r1", policy(tmp_path, max_timeout=9))
    manager.advance("r1")
    manager.advance("r1")
    manager.advance("r1")
    with pytest.raises(RuntimeError):
        manager.rollback("r1")


def test_policy_rollout_snapshot_sorted(tmp_path):
    store = PolicyStore(policy(tmp_path))
    manager = PolicyRolloutManager(store)
    manager.prepare("b", policy(tmp_path, max_timeout=9))
    manager.prepare("a", policy(tmp_path, max_timeout=8))
    assert [item.rollout_id for item in manager.snapshot()] == ["a", "b"]
