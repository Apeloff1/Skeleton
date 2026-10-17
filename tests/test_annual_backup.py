"""SQLite online snapshot regressions for annual production (simulated jobs)."""
from __future__ import annotations

import json
import sqlite3
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from skeleton.automation.annual_production import AnnualProductionStore
from skeleton.automation.annual_backup import (
    AnnualBackupError, restore_annual_snapshot,
    snapshot_annual_production, verify_annual_snapshot,
)


def digest(s: str) -> str:
    return sha256(s.encode()).hexdigest()


class AnnualSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = AnnualProductionStore(self.root / "live.db")
        self.store.enroll(
            production_id="original-game", system="jeeves",
            objective_digest=digest("objective"),
            authority_digest=digest("authority"),
            authority_expires_at=2_000_000_000,
            horizon_days=366, now=1_800_000_000,
        )

    def test_snapshot_contains_real_rows_and_survives_new_live_work(self):
        result = snapshot_annual_production(self.store, self.root, label="day-001")
        self.assertTrue(result["verified"])
        self.assertEqual(result["table_counts"]["annual_productions"], 1)
        self.assertEqual(result, verify_annual_snapshot(self.root, "day-001"))
        self.store.enroll(
            production_id="dragon-observation", system="dragon",
            objective_digest=digest("new objective"),
            authority_digest=digest("new authority"),
            authority_expires_at=2_000_000_000,
            horizon_days=183, now=1_800_000_000,
        )
        self.assertEqual(
            verify_annual_snapshot(self.root, "day-001")["table_counts"][
                "annual_productions"], 1)
        self.assertEqual(
            snapshot_annual_production(self.store, self.root, label="day-002")[
                "table_counts"]["annual_productions"], 2)

    def test_never_overwrite_a_sealed_snapshot(self):
        snapshot_annual_production(self.store, self.root, label="week-1")
        with self.assertRaises(AnnualBackupError):
            snapshot_annual_production(self.store, self.root, label="week-1")

    def test_detects_mutated_manifest_and_mutated_db_bytes(self):
        snapshot_annual_production(self.store, self.root, label="baseline")
        manifest = self.root / "baseline.json"
        document = json.loads(manifest.read_text())
        document["table_counts"]["annual_productions"] = 999
        manifest.write_text(json.dumps(document))
        with self.assertRaises(AnnualBackupError):
            verify_annual_snapshot(self.root, "baseline")

        snapshot_annual_production(self.store, self.root, label="baseline2")
        with (self.root / "baseline2.db").open("ab") as out:
            out.write(b"tamper")
        with self.assertRaises(AnnualBackupError):
            verify_annual_snapshot(self.root, "baseline2")

    def test_no_traversal_or_symlinked_manifest(self):
        for name in ("../escape", "a/b", "", "x" * 81):
            with self.subTest(name=name):
                with self.assertRaises(AnnualBackupError):
                    snapshot_annual_production(self.store, self.root, label=name)
        snapshot_annual_production(self.store, self.root, label="original")
        (self.root / "original.json").unlink()
        (self.root / "original.json").symlink_to(self.root / "live.db")
        with self.assertRaises(AnnualBackupError):
            verify_annual_snapshot(self.root, "original")


    def _reseal_after_db_mutation(self, label):
        """Simulate an actor who rewrote both a SQLite image and its SHA manifest."""
        path = self.root / (label + ".db")
        manifest = self.root / (label + ".json")
        record = json.loads(manifest.read_text())
        record["sha256"] = sha256(path.read_bytes()).hexdigest()
        record["bytes"] = path.stat().st_size
        manifest.write_text(json.dumps(record))

    def test_rehashed_tampered_checkpoint_still_fails_receipt_chain_audit(self):
        claim = self.store.claim(
            "original-game", worker="host-1", authority_digest=digest("authority"),
            now=1_800_000_000, lease_seconds=120,
        )
        self.store.checkpoint(
            claim, sequence=1, state_digest=digest("state"),
            evidence_digest=digest("evidence"), now=1_800_000_001,
        )
        snapshot_annual_production(self.store, self.root, label="checkpointed")
        image = self.root / "checkpointed.db"
        with sqlite3.connect(image) as db:
            db.execute(
                "UPDATE annual_checkpoint_receipts SET evidence_digest=?",
                (digest("forged"),),
            )
            db.commit()
            # Flush the modified WAL into the sealed main-file image so this
            # tests the hash chain, not only an unsealed SQLite sidecar.
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            db.execute("PRAGMA journal_mode=DELETE")
        self._reseal_after_db_mutation("checkpointed")
        with self.assertRaisesRegex(AnnualBackupError, "checkpoint chain"):
            verify_annual_snapshot(self.root, "checkpointed")

    def test_rehashed_tampered_grant_still_fails_authority_chain_audit(self):
        self.store.renew_authority(
            "original-game", expected_authority_digest=digest("authority"),
            new_authority_digest=digest("renewed"),
            approval_digest=digest("approved-by-test-double"),
            new_expires_at=2_100_000_000,
            verify_approval=lambda *args: True,
            now=1_800_000_001,
        )
        snapshot_annual_production(self.store, self.root, label="grant-rotated")
        image = self.root / "grant-rotated.db"
        with sqlite3.connect(image) as db:
            db.execute(
                "UPDATE annual_authority_rotations SET approval_digest=?",
                (digest("substituted-approval"),),
            )
            db.commit()
            # Flush the modified WAL into the sealed main-file image so this
            # tests the hash chain, not only an unsealed SQLite sidecar.
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            db.execute("PRAGMA journal_mode=DELETE")
        self._reseal_after_db_mutation("grant-rotated")
        with self.assertRaisesRegex(AnnualBackupError, "authority chain"):
            verify_annual_snapshot(self.root, "grant-rotated")


    def test_unsealed_wal_sidecar_is_rejected_even_if_manifest_is_unchanged(self):
        snapshot_annual_production(self.store, self.root, label="offline")
        sidecar = self.root / "offline.db-wal"
        sidecar.write_bytes(b"unsealed after-snapshot SQLite log")
        with self.assertRaisesRegex(AnnualBackupError, "sidecars"):
            verify_annual_snapshot(self.root, "offline")
        sidecar.unlink()
        self.assertTrue(verify_annual_snapshot(self.root, "offline")["verified"])


    def test_recovery_is_new_independent_db_and_fences_old_worker_tokens(self):
        claim = self.store.claim(
            "original-game", worker="worker-1",
            authority_digest=digest("authority"),
            now=1_800_000_000, lease_seconds=120,
        )
        self.store.checkpoint(
            claim, sequence=1, state_digest=digest("checkpoint"),
            evidence_digest=digest("proof"), now=1_800_000_001,
        )
        snapshot_annual_production(self.store, self.root, label="sealed")
        recovered_path = self.root / "recovered.db"
        summary = restore_annual_snapshot(self.root, "sealed", recovered_path)
        self.assertTrue(summary["historic_leases_and_grants_fenced"])
        self.assertTrue(summary["independent_database_copy"])
        self.assertFalse(summary["workers_started"])
        self.assertNotEqual(
            self.root.joinpath("sealed.db").stat().st_ino,
            recovered_path.stat().st_ino,
        )
        restored = AnnualProductionStore(recovered_path)
        self.assertEqual(restored.verify_chain("original-game"), 1)
        self.assertEqual(restored.verify_authority_chain("original-game"), 0)
        self.assertEqual(restored.read("original-game").authority_expires_at, 0)
        self.assertIsNone(restored.read("original-game").lease_expires_at)
        with self.assertRaises(PermissionError):
            restored.claim(
                "original-game", worker="worker-2",
                authority_digest=digest("authority"), now=1_800_000_002,
            )
        # Previously authorized grant cannot be used again. Reopening
        # requires a NEW independently verified operator approval.
        reauthorized = restored.renew_authority(
            "original-game",
            expected_authority_digest=digest("authority"),
            new_authority_digest=digest("new-authority"),
            approval_digest=digest("operator-reviewed"),
            new_expires_at=2_100_000_000,
            verify_approval=lambda *args: True,
            now=1_800_000_002,
        )
        self.assertEqual(reauthorized.authority_expires_at, 2_100_000_000)
        self.assertEqual(restored.verify_chain("original-game"), 1)
        with self.assertRaises(AnnualBackupError):
            restore_annual_snapshot(self.root, "sealed", recovered_path)
        self.assertTrue(verify_annual_snapshot(self.root, "sealed")["verified"])

    def test_restore_refuses_tampered_archive_and_existing_database(self):
        snapshot_annual_production(self.store, self.root, label="clean")
        backup_path = self.root / "clean.db"
        restored = self.root / "target.db"
        backup_path.write_bytes(backup_path.read_bytes() + b"x")
        with self.assertRaises(AnnualBackupError):
            restore_annual_snapshot(self.root, "clean", restored)
        self.assertFalse(restored.exists())
        snapshot_annual_production(self.store, self.root, label="clean2")
        restored.write_bytes(b"cannot replace existing")
        with self.assertRaises(AnnualBackupError):
            restore_annual_snapshot(self.root, "clean2", restored)
        self.assertEqual(restored.read_bytes(), b"cannot replace existing")

if __name__ == "__main__":
    unittest.main()
