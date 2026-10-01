from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "repo_machine_transaction",
    ROOT / "skeleton" / "repo_machine" / "transaction.py",
)
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M
SPEC.loader.exec_module(M)


class RepositoryTransactionTests(unittest.TestCase):
    def test_lease_registry_rejects_boolean_and_nonfinite_bounds(self) -> None:
        with self.assertRaises(TypeError):
            M.LeaseRegistry(max_leases=True)
        with self.assertRaises(TypeError):
            M.LeaseRegistry(max_ttl_s=float("nan"))

    def test_lease_acquire_rejects_boolean_and_nonfinite_ttl(self) -> None:
        leases = M.LeaseRegistry(clock=lambda: 100.0)
        with self.assertRaises(TypeError):
            leases.acquire("builder-a", ["pkg"], ttl_s=True)
        with self.assertRaises(TypeError):
            leases.acquire("builder-a", ["pkg"], ttl_s=float("inf"))

    def test_commit_is_path_scoped_and_optimistic(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target = root / "pkg/file.txt"
            target.parent.mkdir(parents=True)
            target.write_text("old", encoding="utf-8")
            old = hashlib.sha256(b"old").hexdigest()
            leases = M.LeaseRegistry(clock=lambda: 100.0)
            lease = leases.acquire("builder-a", ["pkg"], ttl_s=10)
            tx = M.WorkspaceTransaction(root, leases, lease, clock=lambda: 101.0)
            tx.stage_text("pkg/file.txt", "new", expected_sha256=old)
            receipt = tx.commit()
            self.assertEqual(target.read_text(encoding="utf-8"), "new")
            self.assertEqual(receipt.entries[0].before_sha256, old)

    def test_forged_broader_lease_receipt_is_rejected(self) -> None:
        leases = M.LeaseRegistry(clock=lambda: 100.0)
        lease = leases.acquire("builder-a", ["pkg/safe"], ttl_s=10)
        forged = M.EditLease(
            lease_id=lease.lease_id,
            owner_id=lease.owner_id,
            paths=("pkg",),
            acquired_at=lease.acquired_at,
            expires_at=lease.expires_at,
        )
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(
                M.RepositoryTransactionError,
                "does not match registry authority",
            ):
                M.WorkspaceTransaction(raw, leases, forged, clock=lambda: 101.0)

    def test_in_repo_target_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            actual = root / "pkg/actual.txt"
            actual.parent.mkdir(parents=True)
            actual.write_text("original", encoding="utf-8")
            link = root / "pkg/link.txt"
            try:
                link.symlink_to(actual.name)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks are unavailable on this platform")

            leases = M.LeaseRegistry(clock=lambda: 100.0)
            lease = leases.acquire("builder-a", ["pkg"], ttl_s=10)
            tx = M.WorkspaceTransaction(root, leases, lease, clock=lambda: 101.0)
            with self.assertRaisesRegex(
                M.RepositoryTransactionError,
                "target must not be a symlink",
            ):
                tx.stage_text("pkg/link.txt", "replacement")
            self.assertEqual(actual.read_text(encoding="utf-8"), "original")

    def test_conflicting_leases_fail_closed(self) -> None:
        leases = M.LeaseRegistry(clock=lambda: 100.0)
        leases.acquire("builder-a", ["pkg"], ttl_s=10)
        with self.assertRaises(M.LeaseConflictError):
            leases.acquire("builder-b", ["pkg/sub/file.py"], ttl_s=10)

    def test_stale_write_does_not_mutate(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target = root / "file.txt"
            target.write_text("live", encoding="utf-8")
            leases = M.LeaseRegistry(clock=lambda: 100.0)
            lease = leases.acquire("builder-a", ["file.txt"], ttl_s=10)
            tx = M.WorkspaceTransaction(root, leases, lease, clock=lambda: 101.0)
            tx.stage_text("file.txt", "replacement", expected_sha256="0" * 64)
            with self.assertRaises(M.StaleWriteError):
                tx.commit()
            self.assertEqual(target.read_text(encoding="utf-8"), "live")

    def test_lease_expiry_during_multi_file_commit_rolls_back(self) -> None:
        ticks = iter((100.0, 100.2, 100.4, 102.0))
        leases = M.LeaseRegistry(clock=lambda: next(ticks))
        lease = leases.acquire("builder-a", ["pkg"], ttl_s=1.0)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            first = root / "pkg/a.txt"
            second = root / "pkg/b.txt"
            first.parent.mkdir(parents=True)
            first.write_text("old-a", encoding="utf-8")
            second.write_text("old-b", encoding="utf-8")
            tx = M.WorkspaceTransaction(root, leases, lease, clock=lambda: 100.5)
            tx.stage_text("pkg/a.txt", "new-a")
            tx.stage_text("pkg/b.txt", "new-b")
            with self.assertRaises(M.LeaseExpiredError):
                tx.commit()
            self.assertEqual(first.read_text(encoding="utf-8"), "old-a")
            self.assertEqual(second.read_text(encoding="utf-8"), "old-b")

    def test_expired_lease_fences_commit(self) -> None:
        now = [100.0]
        leases = M.LeaseRegistry(clock=lambda: now[0])
        lease = leases.acquire("builder-a", ["file.txt"], ttl_s=1)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            tx = M.WorkspaceTransaction(root, leases, lease, clock=lambda: now[0])
            tx.stage_text("file.txt", "x")
            now[0] = 102.0
            with self.assertRaises(M.LeaseExpiredError):
                tx.commit()


if __name__ == "__main__":
    unittest.main()
