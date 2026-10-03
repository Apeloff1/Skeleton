"""Vault seal lifecycle: Shamir commitment, sealed store, recovery, quorum, unseal ceremony."""

from __future__ import annotations

import json

import pytest

from skeleton.kernel.errors import SealedVaultError
from skeleton.vault import (
    AuditLog,
    IntegrityError,
    QuorumError,
    QuorumGate,
    RecoveryError,
    RecoveryManager,
    RecoverySnapshot,
    SealedStore,
    SealState,
    ShamirSeal,
    UnsealError,
    VaultSeal,
)
from skeleton.vault.entropy import EntropyError, EntropyQuality, EntropyRegistry, EntropySource
from skeleton.vault.kms import EnvelopeKMS
from skeleton.vault.policies import PolicyRegistry, PolicyViolation, require_prefix
from skeleton.vault.rotation import RotationPolicy, RotationScheduler
from skeleton.vault.shamir import SealingError, Share
from skeleton.vault.store import slot_context


class Clock:
    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


# ---------------------------------------------------------------------------
# Shamir
# ---------------------------------------------------------------------------

class TestShamir:
    def test_round_trip_any_k_subset(self):
        secret = bytes(range(256))
        shares = ShamirSeal.split(secret, n=5, k=3)
        assert ShamirSeal.combine(shares[:3]) == secret
        assert ShamirSeal.combine([shares[4], shares[0], shares[2]]) == secret
        assert ShamirSeal.combine(shares) == secret

    def test_too_few_shares_do_not_reconstruct(self):
        secret = b"\x11" * 32
        shares = ShamirSeal.split(secret, n=5, k=3)
        assert ShamirSeal.combine(shares[:2]) != secret

    def test_commitment_verifies_and_rejects(self):
        secret = bytes(range(32))
        shares, commitment = ShamirSeal.split_with_commitment(secret, n=4, k=2)
        assert ShamirSeal.combine_verified(shares[1:3], commitment) == secret
        with pytest.raises(SealingError):
            ShamirSeal.combine_verified(shares[:1], commitment)
        bad = Share(shares[0].index, shares[0].nonce,
                    ((shares[0].values[0] + 1) % 257,) + shares[0].values[1:])
        with pytest.raises(SealingError):
            ShamirSeal.combine_verified([bad, shares[1]], commitment)

    def test_share_validation(self):
        shares = ShamirSeal.split(b"abc", n=3, k=2)
        with pytest.raises(SealingError):
            ShamirSeal.combine([shares[0], shares[0]])
        with pytest.raises(SealingError):
            ShamirSeal.combine([Share(0, shares[0].nonce, shares[0].values), shares[1]])
        with pytest.raises(SealingError):
            ShamirSeal.combine([Share(1, shares[0].nonce, (300, 1, 2)), shares[1]])
        other = ShamirSeal.split(b"abc", n=3, k=2)
        if other[0].nonce != shares[0].nonce:
            with pytest.raises(SealingError):
                ShamirSeal.combine([shares[0], other[1]])

    def test_share_dict_round_trip(self):
        shares = ShamirSeal.split(b"secret", n=3, k=2)
        restored = [Share.from_dict(json.loads(json.dumps(s.to_dict()))) for s in shares]
        assert ShamirSeal.combine(restored[:2]) == b"secret"

    @pytest.mark.parametrize("n,k", [(1, 1), (3, 1), (2, 3), (256, 2)])
    def test_invalid_parameters(self, n, k):
        with pytest.raises(SealingError):
            ShamirSeal.split(b"x", n=n, k=k)


# ---------------------------------------------------------------------------
# SealedStore
# ---------------------------------------------------------------------------

class TestSealedStore:
    def test_round_trip_and_access_hook(self):
        events = []
        store = SealedStore(EnvelopeKMS(), on_access=lambda sid, op: events.append((sid, op)))
        store.put("db/password", b"hunter2")
        assert store.get("db/password") == b"hunter2"
        assert store.names() == ("db/password",)
        assert "db/password" in store and len(store) == 1
        assert store.delete("db/password") is True
        assert store.delete("db/password") is False
        assert events == [("db/password", "write"), ("db/password", "read"), ("db/password", "delete")]

    def test_ciphertext_never_contains_plaintext_and_is_unique(self):
        store = SealedStore(EnvelopeKMS())
        store.put("a", b"same-secret-value")
        store.put("b", b"same-secret-value")
        env = store.export_envelopes()
        assert b"same-secret-value".hex() not in json.dumps(env)
        assert env["a"]["ciphertext"] != env["b"]["ciphertext"]
        assert env["a"]["context"] == slot_context("a")

    def test_tampered_ciphertext_rejected(self):
        store = SealedStore(EnvelopeKMS())
        store.put("k", b"value")
        envelope = store._slots["k"]
        ct = bytearray(bytes.fromhex(envelope["ciphertext"]))
        ct[0] ^= 1
        envelope["ciphertext"] = ct.hex()
        with pytest.raises(IntegrityError):
            store.get("k")

    def test_slot_swap_rejected(self):
        store = SealedStore(EnvelopeKMS())
        store.put("admin", b"root-token")
        store.put("guest", b"guest-token")
        store._slots["guest"] = store._slots["admin"]
        with pytest.raises(IntegrityError):
            store.get("guest")

    def test_unknown_and_invalid_ids(self):
        store = SealedStore(EnvelopeKMS())
        with pytest.raises(IntegrityError):
            store.get("missing")
        for bad in ("", " padded", None):
            with pytest.raises(IntegrityError):
                store.put(bad, b"x")  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            store.put("k", "not-bytes")  # type: ignore[arg-type]

    def test_detached_store_is_sealed(self):
        kms = EnvelopeKMS()
        store = SealedStore(kms)
        store.put("k", b"v")
        store.detach()
        assert store.sealed
        with pytest.raises(SealedVaultError):
            store.get("k")
        with pytest.raises(SealedVaultError):
            store.put("k2", b"v")
        assert store.names() == ("k",)
        with pytest.raises(IntegrityError):
            store.attach(EnvelopeKMS())  # wrong master: refuses to attach
        assert store.sealed
        store.attach(kms)
        assert store.get("k") == b"v"

    def test_reencrypt_is_atomic(self):
        kms = EnvelopeKMS()
        store = SealedStore(kms)
        store.put("a", b"1")
        store.put("b", b"2")
        new = EnvelopeKMS()
        assert store.reencrypt(new) == 2
        assert store.get("a") == b"1" and store.get("b") == b"2"
        store.detach()
        with pytest.raises(IntegrityError):
            store.attach(kms)  # old master no longer opens anything
        store.attach(new)
        store._slots["b"]["ciphertext"] = "00" * 8
        before = store.export_envelopes()
        with pytest.raises(IntegrityError):
            store.reencrypt(EnvelopeKMS())
        assert store.export_envelopes() == before

    def test_policies_enforced_on_write(self):
        policies = PolicyRegistry()
        policies.register(require_prefix("app/"))
        store = SealedStore(EnvelopeKMS(), policies=policies)
        store.put("app/key", b"v")
        with pytest.raises(PolicyViolation):
            store.put("other/key", b"v")
        assert store.names() == ("app/key",)

    def test_import_is_verified_and_atomic(self):
        kms = EnvelopeKMS()
        src = SealedStore(kms)
        src.put("a", b"1")
        env = src.export_envelopes()
        dst = SealedStore(kms)
        dst.put("keep", b"k")
        assert dst.import_envelopes(env) == 1
        assert dst.names() == ("a", "keep")
        foreign = SealedStore(EnvelopeKMS())
        foreign.put("z", b"9")
        mixed = {**env, **foreign.export_envelopes()}
        with pytest.raises(IntegrityError):
            dst.import_envelopes(mixed, replace=True)
        assert dst.names() == ("a", "keep")


# ---------------------------------------------------------------------------
# Recovery
# ---------------------------------------------------------------------------

class TestRecovery:
    def test_snapshot_holds_ciphertext_and_restores(self):
        store = SealedStore(EnvelopeKMS())
        store.put("a", b"alpha")
        store.put("b", b"bravo")
        mgr = RecoveryManager(store, clock=Clock(42.0))
        snap = mgr.snapshot()
        assert snap.taken_at == 42.0
        assert b"alpha".hex() not in json.dumps(snap.to_dict())
        assert mgr.verify(snap)
        store.delete("a")
        store.put("b", b"changed")
        store.put("c", b"new")
        assert mgr.restore(snap) == 2
        assert store.names() == ("a", "b")
        assert store.get("b") == b"bravo"

    def test_tampered_snapshot_refused(self):
        store = SealedStore(EnvelopeKMS())
        store.put("a", b"alpha")
        mgr = RecoveryManager(store)
        raw = mgr.snapshot().to_dict()
        raw["slots"]["a"]["nonce"] = "00" * 12
        snap = RecoverySnapshot.from_dict(raw)
        assert not mgr.verify(snap)
        with pytest.raises(RecoveryError):
            mgr.restore(snap)
        assert store.get("a") == b"alpha"

    def test_snapshot_from_other_master_refused(self):
        other = SealedStore(EnvelopeKMS())
        other.put("a", b"x")
        snap = RecoveryManager(other).snapshot()
        store = SealedStore(EnvelopeKMS())
        with pytest.raises(RecoveryError):
            RecoveryManager(store).restore(snap)

    def test_restore_while_sealed_raises_sealed(self):
        store = SealedStore(EnvelopeKMS())
        store.put("a", b"x")
        mgr = RecoveryManager(store)
        snap = mgr.snapshot()
        store.detach()
        with pytest.raises(SealedVaultError):
            mgr.restore(snap)

    def test_from_dict_rejects_unknown_format(self):
        with pytest.raises(RecoveryError):
            RecoverySnapshot.from_dict({"format": "v0", "slots": {}})


# ---------------------------------------------------------------------------
# Quorum
# ---------------------------------------------------------------------------

class TestQuorum:
    def test_basic_threshold_backward_compatible(self):
        gate = QuorumGate(threshold=2)
        gate.propose("rotate")
        gate.approve("rotate", "alice")
        assert gate.check("rotate") is False
        gate.approve("rotate", "alice")  # idempotent per operator
        assert gate.check("rotate") is False
        gate.approve("rotate", "bob")
        assert gate.check("rotate") is True
        with pytest.raises(QuorumError):
            gate.check("rotate")  # consumed exactly once

    def test_repropose_does_not_wipe_approvals(self):
        gate = QuorumGate(threshold=2)
        gate.propose("a")
        gate.approve("a", "x")
        gate.propose("a")
        assert gate.status("a")["approvals"] == ["x"]

    def test_roster_and_four_eyes(self):
        gate = QuorumGate(threshold=2, operators={"alice", "bob", "carol"})
        with pytest.raises(QuorumError):
            QuorumGate(threshold=4, operators={"alice", "bob", "carol"})
        with pytest.raises(QuorumError):
            gate.propose("x", proposer="mallory")
        gate.propose("x", proposer="alice")
        with pytest.raises(QuorumError):
            gate.approve("x", "alice")
        with pytest.raises(QuorumError):
            gate.approve("x", "mallory")
        gate.approve("x", "bob")
        gate.approve("x", "carol")
        gate.revoke("x", "carol")
        assert gate.status("x")["remaining"] == 1
        gate.approve("x", "carol")
        assert gate.check("x") is True

    def test_expiry(self):
        clock = Clock()
        gate = QuorumGate(threshold=1, ttl_s=60, clock=clock)
        gate.propose("x")
        clock.t += 61
        with pytest.raises(QuorumError):
            gate.approve("x", "a")
        assert gate.pending() == ()
        gate.propose("y")
        gate.approve("y", "a")
        clock.t += 61
        assert gate.check("y") is False

    def test_invalid_construction(self):
        with pytest.raises(QuorumError):
            QuorumGate(threshold=0)
        with pytest.raises(QuorumError):
            QuorumGate(threshold=1, ttl_s=0)


# ---------------------------------------------------------------------------
# Entropy + rotation hardening
# ---------------------------------------------------------------------------

class TestEntropyAndRotation:
    def test_stuck_source_rejected(self):
        reg = EntropyRegistry()
        reg.register(EntropySource("stuck", EntropyQuality.USER, lambda n: b"\x00" * n))
        with pytest.raises(EntropyError):
            reg.gather(32, source="stuck")
        assert len(reg.gather(32)) == 32
        assert reg.audit()[-1] == {"source": "urandom", "bytes": 32}

    def test_short_read_rejected(self):
        reg = EntropyRegistry()
        reg.register(EntropySource("short", EntropyQuality.USER, lambda n: b"\x01"))
        with pytest.raises(EntropyError):
            reg.gather(4, source="short")

    def test_default_rotation_material_is_unguessable(self):
        clock = Clock()
        policy = RotationPolicy(clock=clock)
        policy.register("api", "v1", max_age_s=10, grace_s=5)
        clock.t += 11
        sched = RotationScheduler(policy)
        assert sched.tick() == ["api"]
        material = policy._secrets["api"].active.material
        assert "api" not in material and len(material) >= 40
        assert policy.validate("api", material)
        assert policy.validate("api", "v1")  # still in grace
        clock.t += 6
        sched.tick()
        assert not policy.validate("api", "v1")


# ---------------------------------------------------------------------------
# VaultSeal lifecycle
# ---------------------------------------------------------------------------

class TestVaultSeal:
    def _init(self, **kw):
        vault = VaultSeal(**kw)
        keys = vault.initialize(shares=5, threshold=3, actor="root")
        return vault, keys

    def test_initialize_starts_sealed_and_never_exposes_master(self):
        vault, keys = self._init()
        assert vault.state is SealState.SEALED
        assert len(keys.shares) == 5 and keys.threshold == 3
        assert "values" not in repr(keys)
        with pytest.raises(SealedVaultError):
            vault.store.put("k", b"v")
        with pytest.raises(UnsealError):
            vault.initialize(shares=5, threshold=3, actor="root")

    def test_progressive_unseal_and_seal(self):
        vault, keys = self._init()
        assert vault.submit_share(keys.shares[4], actor="c5").progress == 1
        assert vault.submit_share(keys.shares[1], actor="c2").progress == 2
        status = vault.submit_share(keys.shares[0], actor="c1")
        assert status.state is SealState.UNSEALED and status.progress == 0
        vault.store.put("db", b"pw")
        vault.seal(actor="root")
        assert vault.sealed
        with pytest.raises(SealedVaultError):
            vault.store.get("db")
        vault.unseal(keys.shares[2:5], actor="ops")
        assert vault.store.get("db") == b"pw"

    def test_duplicate_foreign_and_wrong_length_shares(self):
        vault, keys = self._init()
        other, other_keys = self._init()
        vault.submit_share(keys.shares[0], actor="a")
        with pytest.raises(UnsealError):
            vault.submit_share(keys.shares[0], actor="a")
        if other_keys.shares[1].nonce != keys.shares[0].nonce:
            with pytest.raises(UnsealError):
                vault.submit_share(other_keys.shares[1], actor="b")
        with pytest.raises(UnsealError):
            vault.submit_share(Share(9, keys.shares[0].nonce, (1, 2, 3)), actor="b")
        assert vault.status().progress == 1
        vault.reset_progress(actor="root")
        assert vault.status().progress == 0

    def test_corrupted_share_fails_commitment_and_resets(self):
        vault, keys = self._init()
        s0 = keys.shares[0]
        bad = Share(s0.index, s0.nonce, ((s0.values[0] + 7) % 257,) + s0.values[1:])
        vault.submit_share(bad, actor="a")
        vault.submit_share(keys.shares[1], actor="b")
        with pytest.raises(UnsealError):
            vault.submit_share(keys.shares[2], actor="c")
        assert vault.sealed and vault.status().progress == 0
        vault.unseal(keys.shares[:3], actor="ops")
        assert not vault.sealed

    def test_rekey_requires_quorum_and_invalidates_old_shares(self):
        quorum = QuorumGate(threshold=2, operators={"alice", "bob", "carol"})
        vault, keys = self._init(quorum=quorum)
        vault.unseal(keys.shares[:3], actor="ops")
        vault.store.put("api", b"token")
        with pytest.raises(UnsealError):
            vault.rekey(shares=3, threshold=2, actor="alice")
        quorum.propose("vault.rekey", proposer="alice")
        quorum.approve("vault.rekey", "bob")
        quorum.approve("vault.rekey", "carol")
        new_keys = vault.rekey(shares=3, threshold=2, actor="alice")
        assert vault.status().generation == 2
        assert vault.store.get("api") == b"token"
        vault.seal(actor="root")
        with pytest.raises(UnsealError):
            vault.unseal(keys.shares[:3], actor="ops")
        vault.unseal(new_keys.shares[1:], actor="ops")
        assert vault.store.get("api") == b"token"

    def test_rekey_invalid_params_leave_vault_intact(self):
        vault, keys = self._init()
        vault.unseal(keys.shares[:3], actor="ops")
        vault.store.put("k", b"v")
        with pytest.raises(UnsealError):
            vault.rekey(shares=2, threshold=3, actor="root")
        vault.seal(actor="root")
        vault.unseal(keys.shares[:3], actor="ops")
        assert vault.store.get("k") == b"v"

    def test_rekey_while_sealed_refused(self):
        vault, _ = self._init()
        with pytest.raises(SealedVaultError):
            vault.rekey(shares=3, threshold=2, actor="root")

    def test_recovery_snapshot_survives_seal_cycle(self):
        vault, keys = self._init()
        vault.unseal(keys.shares[:3], actor="ops")
        vault.store.put("a", b"1")
        mgr = RecoveryManager(vault.store)
        snap = mgr.snapshot()
        vault.store.delete("a")
        vault.seal(actor="root")
        vault.unseal(keys.shares[1:4], actor="ops")
        mgr.restore(snap)
        assert vault.store.get("a") == b"1"

    def test_audit_chain_records_lifecycle_without_secrets(self, tmp_path):
        log = AuditLog.open(tmp_path / "worm.jsonl")
        vault, keys = self._init(audit=log)
        vault.unseal(keys.shares[:3], actor="ops")
        vault.seal(actor="root")
        actions = [e.action for e in log.query(limit=100)]
        assert "vault.initialize" in actions and "vault.unseal" in actions and "vault.seal" in actions
        log.verify_chain_or_refuse()
        text = (tmp_path / "worm.jsonl").read_text()
        assert keys.commitment not in text
        for share in keys.shares:
            assert json.dumps(list(share.values)) not in text
        assert AuditLog.open(tmp_path / "worm.jsonl").report()["chain_intact"] is True

    def test_status_dict(self):
        vault = VaultSeal()
        assert vault.status().to_dict()["state"] == "uninitialized"
        with pytest.raises(UnsealError):
            vault.submit_share(Share(1, 1, (0,) * 32), actor="x")
        with pytest.raises(UnsealError):
            VaultSeal(SealedStore(EnvelopeKMS()))

    def test_bad_initialize_parameters(self):
        with pytest.raises(UnsealError):
            VaultSeal().initialize(shares=2, threshold=3, actor="root")
