"""Secrets at rest: repository behaviour and the plaintext->envelope / rewrap
migration on both the in-memory and SQLite stores. Test keys only."""
import pytest

from core.core_v1 import envelope, sqlite_store
from core.core_v1.keys import StaticKeyProvider
from core.core_v1.memory_store import MemorySecretRepository
from core.core_v1.secret_migration import JOB_ENCRYPT, MemoryCheckpointStore, SecretMigrator
from core.core_v1.secret_vault import (EncryptedSecretRepository, PlaintextSecretRepository,
                                       SecretDecryptError, classify_blob)
from core.core_v1.sqlite_store import SqliteCheckpointStore, SqliteSecretRepository, open_database

from ._support import ADMIN, memory_service

K1, K2 = b"\x01" * 32, b"\x02" * 32
P1 = StaticKeyProvider({"k1": K1}, "k1")
P12 = StaticKeyProvider({"k1": K1, "k2": K2}, "k2")


class Clock:
    t = 1000.0

    def __call__(self):
        Clock.t += 1
        return Clock.t


@pytest.fixture(params=["memory", "sqlite"])
def stores(request, tmp_path):
    if request.param == "memory":
        return MemorySecretRepository(), MemoryCheckpointStore()
    db = open_database(str(tmp_path / "s.db"))
    return SqliteSecretRepository(db), SqliteCheckpointStore(db)


def _seed_plain(store, n, tenant="t1"):
    for i in range(n):
        store.put(f"sec_{i:04d}", tenant, f"whsec_{i:04d}".encode(), float(i))


def test_classify():
    assert classify_blob(b"whsec_x") == "plaintext"
    assert classify_blob(envelope.seal(P1, b"whsec_x", b"a")) == "envelope"
    assert classify_blob(b"\x00junk") == "unknown"


def test_encrypted_repo_seals_on_put_and_opens_on_get(stores):
    store, _ = stores
    repo = EncryptedSecretRepository(store, P1)
    repo.put("sec_a", "t1", b"whsec_a", 1.0)
    raw = store.get("t1", "sec_a")
    assert envelope.is_envelope(raw) and b"whsec_a" not in raw
    assert repo.get("t1", "sec_a") == b"whsec_a"
    assert repo.get("t2", "sec_a") is None  # tenant scoped
    assert store.count_by_key() == {"k1": 1}


def test_duplicate_put_refused(stores):
    store, _ = stores
    store.put("sec_a", "t1", b"whsec_a", 1.0)
    with pytest.raises(Exception):
        store.put("sec_a", "t1", b"whsec_b", 1.0)


def test_plaintext_read_policy(stores):
    store, _ = stores
    _seed_plain(store, 1)
    assert EncryptedSecretRepository(store, P1).get("t1", "sec_0000") == b"whsec_0000"
    with pytest.raises(SecretDecryptError):
        EncryptedSecretRepository(store, P1, allow_plaintext_read=False).get("t1", "sec_0000")


def test_plaintext_repo_never_returns_ciphertext(stores):
    store, _ = stores
    EncryptedSecretRepository(store, P1).put("sec_a", "t1", b"whsec_a", 1.0)
    with pytest.raises(SecretDecryptError):
        PlaintextSecretRepository(store).get("t1", "sec_a")


def test_wrong_or_missing_key_raises(stores):
    store, _ = stores
    EncryptedSecretRepository(store, P12).put("sec_a", "t1", b"whsec_a", 1.0)  # under k2
    with pytest.raises(SecretDecryptError):
        EncryptedSecretRepository(store, P1).get("t1", "sec_a")


def test_encrypt_migration_resumable_and_idempotent(stores):
    store, cps = stores
    _seed_plain(store, 25)
    m = SecretMigrator(store, P1, cps, Clock())
    r1 = m.encrypt_plaintext(batch_size=10, max_batches=1)
    assert (r1.changed, r1.done) == (10, False)
    assert cps.get(JOB_ENCRYPT).cursor == "sec_0009"
    # "crash" and resume with a fresh migrator over the same checkpoint store
    r2 = SecretMigrator(store, P1, cps, Clock()).encrypt_plaintext(batch_size=10)
    assert r2.resumed_from == "sec_0009" and r2.changed == 15 and r2.done
    assert store.count_by_key() == {"k1": 25}
    repo = EncryptedSecretRepository(store, P1, allow_plaintext_read=False)
    assert all(repo.get("t1", f"sec_{i:04d}") == f"whsec_{i:04d}".encode() for i in range(25))
    # finished job is a no-op; force re-scans but changes nothing
    r3 = m.encrypt_plaintext()
    assert r3.done and r3.scanned == 0
    r4 = m.encrypt_plaintext(force=True)
    assert r4.done and r4.scanned == 25 and r4.changed == 0 and r4.skipped == 25


def test_encrypt_reports_unknown_rows(stores):
    store, cps = stores
    _seed_plain(store, 2)
    store.put("sec_bad", "t1", b"\x00garbage", 5.0)
    r = SecretMigrator(store, P1, cps, Clock()).encrypt_plaintext()
    assert r.failed == ["sec_bad"] and r.changed == 2 and not r.done
    assert cps.get(JOB_ENCRYPT).cursor == "sec_0001"
    assert store.compare_and_set("sec_bad", b"\x00garbage", b"whsec_fixed", "")
    resumed = SecretMigrator(store, P1, cps, Clock()).encrypt_plaintext()
    assert resumed.changed == 1 and resumed.done and not resumed.failed


def test_cas_conflict_is_not_clobbered(stores):
    store, cps = stores
    _seed_plain(store, 1)
    row = store.scan("", 10)[0]
    assert store.compare_and_set(row.secret_id, b"not-current", b"x", "k1") is False
    assert store.get("t1", row.secret_id) == b"whsec_0000"


def test_rewrap_rotation(stores):
    store, cps = stores
    _seed_plain(store, 12)
    SecretMigrator(store, P1, cps, Clock()).encrypt_plaintext()
    m = SecretMigrator(store, P12, cps, Clock())
    st = m.status()
    assert st["active_key_id"] == "k2" and st["stale_key_rows"] == 12 and st["plaintext_rows"] == 0
    r1 = m.rewrap(batch_size=5, max_batches=1)
    assert r1.changed == 5 and not r1.done
    r2 = m.rewrap(batch_size=5)
    assert r2.changed == 7 and r2.done
    assert store.count_by_key() == {"k2": 12}
    # k1 can now be retired: provider with only k2 still reads everything
    only2 = StaticKeyProvider({"k2": K2}, "k2")
    repo = EncryptedSecretRepository(store, only2)
    assert repo.get("t1", "sec_0007") == b"whsec_0007"
    assert m.status()["rewrap_job"]["done"] is True


def test_rewrap_skips_plaintext(stores):
    store, cps = stores
    _seed_plain(store, 3)
    r = SecretMigrator(store, P12, cps, Clock()).rewrap()
    assert r.changed == 0 and r.skipped == 3 and store.count_by_key() == {"": 3}


def test_sqlite_upgrade_from_v3_keeps_plaintext_rows(tmp_path, monkeypatch):
    path = str(tmp_path / "old.db")
    monkeypatch.setattr(sqlite_store, "MIGRATIONS", sqlite_store.MIGRATIONS[:3])
    old = open_database(path)
    with old.tx() as c:
        c.execute("INSERT INTO core_v1_webhook_secrets (secret_id, tenant_id, secret, created_at) "
                  "VALUES ('sec_old', 't1', ?, 1.0)", (b"whsec_legacy",))
    monkeypatch.undo()
    db = open_database(path)
    versions = [r[0] for r in db.query("SELECT version FROM core_v1_migrations ORDER BY version")]
    assert versions == [1, 2, 3, 4]
    assert sqlite_store.migrate(db) == []  # idempotent
    store = SqliteSecretRepository(db)
    assert store.count_by_key() == {"": 1}
    r = SecretMigrator(store, P1, SqliteCheckpointStore(db), Clock()).encrypt_plaintext()
    assert r.changed == 1 and store.count_by_key() == {"k1": 1}
    assert EncryptedSecretRepository(store, P1).get("t1", "sec_old") == b"whsec_legacy"


def test_service_signs_with_decrypted_secret_and_retries_when_key_missing():
    svc, clock, transport = memory_service()
    raw = svc.secrets
    svc.secrets = EncryptedSecretRepository(raw, P1)
    from core.core_v1.models import SubscriptionDraft
    created = svc.create(ADMIN, SubscriptionDraft("https://h.example.com/x", ()))
    assert envelope.is_envelope(raw.get("t1", created.subscription.secret_ids[0]))
    svc.publish(ADMIN, "a.b", {"x": 1})
    assert svc.dispatch_due().succeeded == 1
    sig = transport.calls[0].headers["Skeleton-Signature"]
    from core.core_v1.signing import secret_bytes, verify
    assert verify(sig, transport.calls[0].body, secret_bytes(created.secret), clock.now())
    # keyring lost -> retry (operational), never dead-letter, never sign with ciphertext
    svc.secrets = EncryptedSecretRepository(raw, StaticKeyProvider({"k9": K2}, "k9"))
    svc.publish(ADMIN, "a.c", {"x": 2})
    rep = svc.dispatch_due()
    assert rep.retried == 1 and len(transport.calls) == 1


def test_secret_migration_rejects_unbounded_batch_parameters(stores):
    store, cps = stores
    m = SecretMigrator(store, P1, cps, Clock())
    for bad in (0, True, 1001, -1):
        with pytest.raises(ValueError, match="batch_size"):
            m.encrypt_plaintext(batch_size=bad)
        with pytest.raises(ValueError, match="max_batches"):
            m.encrypt_plaintext(max_batches=bad)


def test_migrator_rejects_corrupt_or_cross_job_checkpoints_before_skipping(stores):
    from core.core_v1.secret_migration import Checkpoint

    store, cps = stores
    _seed_plain(store, 1)
    migrator = SecretMigrator(store, P1, cps, Clock())
    for cp in (
        Checkpoint("wrong-job", "", True, 1.0),
        Checkpoint(JOB_ENCRYPT, "x" * 257, False, 1.0),
        Checkpoint(JOB_ENCRYPT, "", True, float("nan")),
        Checkpoint(JOB_ENCRYPT, "", True, 10**1000),
        Checkpoint(JOB_ENCRYPT, "", 1, 1.0),
    ):
        cps.save(cp if cp.job == JOB_ENCRYPT else Checkpoint(JOB_ENCRYPT, "", False, 1.0))
        if cp.job != JOB_ENCRYPT:
            class WrongJobStore:
                def get(self, job):
                    return cp

            check = SecretMigrator(store, P1, WrongJobStore(), Clock())
        else:
            check = migrator
        with pytest.raises(ValueError, match="checkpoint"):
            check.encrypt_plaintext()
    assert store.count_by_key() == {"": 1}


def test_force_migration_invalid_bounds_preserve_durable_resume_checkpoint(stores):
    store, checkpoints = stores
    _seed_plain(store, 3)
    migrator = SecretMigrator(store, P1, checkpoints, Clock())
    migrator.encrypt_plaintext(batch_size=1, max_batches=1)
    encrypted_checkpoint = checkpoints.get(JOB_ENCRYPT)
    assert encrypted_checkpoint is not None and not encrypted_checkpoint.done
    for kwargs in ({"batch_size": 0}, {"max_batches": True}, {"batch_size": 1001}):
        with pytest.raises(ValueError):
            migrator.encrypt_plaintext(force=True, **kwargs)
        assert checkpoints.get(JOB_ENCRYPT) == encrypted_checkpoint

    migrator.rewrap(batch_size=1, max_batches=1)
    rewrap_job = "secrets.rewrap:k1"
    rewrap_checkpoint = checkpoints.get(rewrap_job)
    assert rewrap_checkpoint is not None and not rewrap_checkpoint.done
    for kwargs in ({"batch_size": False}, {"max_batches": 1001}):
        with pytest.raises(ValueError):
            migrator.rewrap(force=True, **kwargs)
        assert checkpoints.get(rewrap_job) == rewrap_checkpoint


@pytest.mark.parametrize("bad_clock", [float("nan"), float("inf"), -1, True, 10**1000])
def test_invalid_migration_clock_cannot_erase_resume_checkpoint(stores, bad_clock):
    store, checkpoints = stores
    _seed_plain(store, 3)
    SecretMigrator(store, P1, checkpoints, Clock()).encrypt_plaintext(
        batch_size=1, max_batches=1,
    )
    before = checkpoints.get(JOB_ENCRYPT)
    assert before is not None and not before.done
    invalid = SecretMigrator(store, P1, checkpoints, lambda: bad_clock)
    with pytest.raises(ValueError, match="checkpoint clock"):
        invalid.encrypt_plaintext(force=True, batch_size=1, max_batches=1)
    assert checkpoints.get(JOB_ENCRYPT) == before


def test_invalid_migration_clock_never_persists_bad_checkpoint(stores):
    store, checkpoints = stores
    invalid = SecretMigrator(store, P1, checkpoints, lambda: float("nan"))
    with pytest.raises(ValueError, match="checkpoint clock"):
        invalid.encrypt_plaintext()
    assert checkpoints.get(JOB_ENCRYPT) is None


def test_secret_checkpoint_monotonicity_survives_concurrent_stale_writer(stores):
    """A slower worker must not rewind a completed or advanced checkpoint."""
    from core.core_v1.secret_migration import Checkpoint

    _, checkpoints = stores
    checkpoints.save(Checkpoint(JOB_ENCRYPT, "sec_0010", False, 100.0))
    for stale in (
        Checkpoint(JOB_ENCRYPT, "sec_0009", False, 101.0),
        Checkpoint(JOB_ENCRYPT, "sec_0010", False, 99.0),
    ):
        with pytest.raises(ValueError, match="checkpoint regression"):
            checkpoints.save(stale)
    assert checkpoints.get(JOB_ENCRYPT).cursor == "sec_0010"
    checkpoints.save(Checkpoint(JOB_ENCRYPT, "sec_0010", True, 102.0))
    with pytest.raises(ValueError, match="checkpoint regression"):
        checkpoints.save(Checkpoint(JOB_ENCRYPT, "sec_0011", False, 103.0))
    assert checkpoints.get(JOB_ENCRYPT).done is True

    # Explicit force-reset is a separate operator action, not an implicit
    # rewind permitted by a stale worker.
    checkpoints.reset(JOB_ENCRYPT)
    checkpoints.save(Checkpoint(JOB_ENCRYPT, "", False, 104.0))
    assert checkpoints.get(JOB_ENCRYPT).cursor == ""
    assert checkpoints.get(JOB_ENCRYPT).done is False
