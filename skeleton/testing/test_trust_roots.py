from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.kernel.keyholder import Keyholder
from skeleton.security.trust_roots import (
    TrustRootError,
    TrustRootStore,
)

SEED1 = bytes(range(32))
SEED2 = bytes(range(32, 64))
SEED3 = bytes(range(64, 96))


def test_clean_machine_bootstrap_is_deterministic() -> None:
    first = TrustRootStore.clean_bootstrap(SEED1)
    second = TrustRootStore.clean_bootstrap(SEED1)

    assert first.generation == second.generation == 1
    assert first.active_root_id == second.active_root_id
    assert first.history == (Keyholder.mint(SEED1).public_hex,)


def test_rotation_requires_old_and_new_root_signatures() -> None:
    store = TrustRootStore.clean_bootstrap(SEED1)
    proof = store.propose_rotation(SEED2)
    old = store.active_root_id

    store.apply_rotation(proof, new_seed=SEED2)

    assert store.generation == 2
    assert store.active_root_id == Keyholder.mint(SEED2).public_hex
    assert store.history == (old, store.active_root_id)
    assert len(proof.proof_digest) == 64


def test_faulted_rotation_is_atomic_and_leaves_old_root_active() -> None:
    store = TrustRootStore.clean_bootstrap(SEED1)
    proof = store.propose_rotation(SEED2)
    before = store.snapshot()

    tampered = replace(proof, previous_signature="0" * 64)
    with pytest.raises(TrustRootError, match="previous trust-root signature"):
        store.apply_rotation(tampered, new_seed=SEED2)

    assert store.snapshot() == before


def test_wrong_replacement_seed_fails_before_mutation() -> None:
    store = TrustRootStore.clean_bootstrap(SEED1)
    proof = store.propose_rotation(SEED2)
    before = store.snapshot()

    with pytest.raises(TrustRootError, match="does not match proposed root"):
        store.apply_rotation(proof, new_seed=SEED3)

    assert store.snapshot() == before


def test_recovery_drill_restores_seed_free_root_history() -> None:
    store = TrustRootStore.clean_bootstrap(SEED1)
    first_id = store.active_root_id
    proof = store.propose_rotation(SEED2)
    store.apply_rotation(proof, new_seed=SEED2)
    second_id = store.active_root_id

    snapshot = store.snapshot()
    assert SEED1.hex() not in repr(snapshot)
    assert SEED2.hex() not in repr(snapshot)

    restored = TrustRootStore.restore(
        snapshot,
        seeds_by_root_id={first_id: SEED1, second_id: SEED2},
    )

    assert restored.snapshot() == snapshot
    next_proof = restored.propose_rotation(SEED3)
    restored.apply_rotation(next_proof, new_seed=SEED3)
    assert restored.generation == 3


def test_recovery_rejects_missing_or_wrong_root_seed() -> None:
    store = TrustRootStore.clean_bootstrap(SEED1)
    root_id = store.active_root_id
    snapshot = store.snapshot()

    with pytest.raises(TrustRootError, match="missing recovery seed"):
        TrustRootStore.restore(snapshot, seeds_by_root_id={})

    with pytest.raises(TrustRootError, match="does not match"):
        TrustRootStore.restore(snapshot, seeds_by_root_id={root_id: SEED2})


def test_reusing_root_identity_is_rejected() -> None:
    store = TrustRootStore.clean_bootstrap(SEED1)
    store.apply_rotation(store.propose_rotation(SEED2), new_seed=SEED2)

    with pytest.raises(TrustRootError, match="already exists"):
        store.propose_rotation(SEED1)
