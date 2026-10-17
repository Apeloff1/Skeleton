"""SQLite online snapshot regressions for annual production (simulated jobs)."""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from skeleton.automation.annual_production import AnnualProductionStore
from skeleton.automation.annual_backup import (
    AnnualBackupError, snapshot_annual_production, verify_annual_snapshot,
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


if __name__ == "__main__":
    unittest.main()
