from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import tempfile
import unittest

from skeleton.persistence.authority_consistency import (
    AuthorityConflict,
    AuthorityConsistencyError,
    AuthorityCorruption,
    ProjectionStale,
    SQLiteAuthorityConsistency,
    SourceBinding,
)


BASE = datetime(2026, 10, 4, 19, 0, tzinfo=timezone.utc)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class AuthorityConsistencyTests(unittest.TestCase):
    def test_authoritative_compare_and_commit_is_owner_and_content_bound(self) -> None:
        with SQLiteAuthorityConsistency() as ledger:
            first = ledger.open_authority(
                tenant_id="tenant-a",
                domain_id="conversation",
                resource_id="thread-1",
                owner_id="application-api",
                content_digest=digest("v1"),
                now=BASE,
            )
            self.assertEqual(first.generation, 1)
            second = ledger.compare_and_commit(
                tenant_id="tenant-a",
                domain_id="conversation",
                resource_id="thread-1",
                expected_generation=1,
                owner_id="application-api",
                expected_content_digest=digest("v1"),
                content_digest=digest("v2"),
                now=BASE + timedelta(seconds=1),
            )
            self.assertEqual(second.generation, 2)
            self.assertEqual(
                ledger.read_authority(
                    tenant_id="tenant-a",
                    domain_id="conversation",
                    resource_id="thread-1",
                ).content_digest,
                digest("v2"),
            )

    def test_stale_generation_and_implicit_owner_switch_fail_closed(self) -> None:
        with SQLiteAuthorityConsistency() as ledger:
            ledger.open_authority(
                tenant_id="tenant-a",
                domain_id="memory",
                resource_id="m-1",
                owner_id="memory",
                content_digest=digest("v1"),
                now=BASE,
            )
            with self.assertRaisesRegex(AuthorityConflict, "stale"):
                ledger.compare_and_commit(
                    tenant_id="tenant-a",
                    domain_id="memory",
                    resource_id="m-1",
                    expected_generation=0,
                    owner_id="memory",
                    content_digest=digest("v2"),
                    now=BASE + timedelta(seconds=1),
                )
            with self.assertRaisesRegex(AuthorityConflict, "explicit transfer"):
                ledger.compare_and_commit(
                    tenant_id="tenant-a",
                    domain_id="memory",
                    resource_id="m-1",
                    expected_generation=1,
                    owner_id="shadow-memory",
                    content_digest=digest("v2"),
                    now=BASE + timedelta(seconds=1),
                )

    def test_owner_transfer_is_explicit_and_invalidates_old_token(self) -> None:
        with SQLiteAuthorityConsistency() as ledger:
            first = ledger.open_authority(
                tenant_id="tenant-a",
                domain_id="operation",
                resource_id="op-1",
                owner_id="orchestration",
                content_digest=digest("stable"),
                now=BASE,
            )
            transferred = ledger.transfer_authority(
                tenant_id="tenant-a",
                domain_id="operation",
                resource_id="op-1",
                expected_generation=1,
                current_owner_id="orchestration",
                new_owner_id="orchestration-v2",
                expected_content_digest=digest("stable"),
                now=BASE + timedelta(seconds=1),
            )
            self.assertEqual(transferred.generation, 2)
            self.assertEqual(transferred.owner_id, "orchestration-v2")
            with self.assertRaisesRegex(AuthorityConflict, "current authority owner"):
                ledger.transfer_authority(
                    tenant_id="tenant-a",
                    domain_id="operation",
                    resource_id="op-1",
                    expected_generation=2,
                    current_owner_id="orchestration",
                    new_owner_id="orchestration-v3",
                    expected_content_digest=digest("stable"),
                    now=BASE + timedelta(seconds=2),
                )
            self.assertNotEqual(first.digest, transferred.digest)

    def test_projection_becomes_unreadable_when_source_advances(self) -> None:
        with SQLiteAuthorityConsistency() as ledger:
            source = ledger.open_authority(
                tenant_id="tenant-a",
                domain_id="memory",
                resource_id="m-1",
                owner_id="memory",
                content_digest=digest("canonical-v1"),
                now=BASE,
            )
            projection = ledger.register_projection(
                tenant_id="tenant-a",
                projection_id="vector:m-1",
                kind="derived",
                payload_digest=digest("embedding-v1"),
                sources=[source],
                now=BASE,
            )
            self.assertEqual(
                ledger.read_projection(
                    tenant_id="tenant-a",
                    projection_id="vector:m-1",
                ).digest,
                projection.digest,
            )
            ledger.compare_and_commit(
                tenant_id="tenant-a",
                domain_id="memory",
                resource_id="m-1",
                expected_generation=1,
                owner_id="memory",
                content_digest=digest("canonical-v2"),
                now=BASE + timedelta(seconds=1),
            )
            with self.assertRaisesRegex(ProjectionStale, "stale"):
                ledger.read_projection(
                    tenant_id="tenant-a",
                    projection_id="vector:m-1",
                )

    def test_multisource_projection_requires_every_exact_source(self) -> None:
        with SQLiteAuthorityConsistency() as ledger:
            a = ledger.open_authority(
                tenant_id="tenant-a",
                domain_id="conversation",
                resource_id="thread-1",
                owner_id="application-api",
                content_digest=digest("a1"),
                now=BASE,
            )
            b = ledger.open_authority(
                tenant_id="tenant-a",
                domain_id="memory",
                resource_id="m-1",
                owner_id="memory",
                content_digest=digest("b1"),
                now=BASE,
            )
            ledger.register_projection(
                tenant_id="tenant-a",
                projection_id="context-1",
                kind="cache",
                payload_digest=digest("compiled"),
                sources=[b, a],
                now=BASE,
            )
            current = ledger.read_projection(
                tenant_id="tenant-a",
                projection_id="context-1",
            )
            self.assertEqual(
                [(s.domain_id, s.resource_id) for s in current.sources],
                [("conversation", "thread-1"), ("memory", "m-1")],
            )
            ledger.compare_and_commit(
                tenant_id="tenant-a",
                domain_id="conversation",
                resource_id="thread-1",
                expected_generation=1,
                owner_id="application-api",
                content_digest=digest("a2"),
                now=BASE + timedelta(seconds=1),
            )
            with self.assertRaises(ProjectionStale):
                ledger.read_projection(
                    tenant_id="tenant-a",
                    projection_id="context-1",
                )

    def test_projection_rejects_cross_tenant_duplicate_and_forged_sources_atomically(self) -> None:
        with SQLiteAuthorityConsistency() as ledger:
            a = ledger.open_authority(
                tenant_id="tenant-a",
                domain_id="memory",
                resource_id="m-1",
                owner_id="memory",
                content_digest=digest("a"),
                now=BASE,
            )
            b = ledger.open_authority(
                tenant_id="tenant-b",
                domain_id="memory",
                resource_id="m-1",
                owner_id="memory",
                content_digest=digest("b"),
                now=BASE,
            )
            with self.assertRaisesRegex(AuthorityConsistencyError, "cross-tenant"):
                ledger.register_projection(
                    tenant_id="tenant-a",
                    projection_id="bad-cross-tenant",
                    kind="derived",
                    payload_digest=digest("x"),
                    sources=[a, b],
                )
            with self.assertRaisesRegex(AuthorityConsistencyError, "duplicate"):
                ledger.register_projection(
                    tenant_id="tenant-a",
                    projection_id="bad-duplicate",
                    kind="derived",
                    payload_digest=digest("x"),
                    sources=[a, a],
                )
            forged = replace(
                SourceBinding.from_token(a),
                token_digest=digest("forged"),
            )
            with self.assertRaisesRegex(AuthorityConsistencyError, "token digest mismatch"):
                ledger.register_projection(
                    tenant_id="tenant-a",
                    projection_id="bad-forged",
                    kind="derived",
                    payload_digest=digest("x"),
                    sources=[forged],
                )
            self.assertEqual(ledger.card()["projection_count"], 0)

    def test_projection_registration_checks_source_freshness_before_mutation(self) -> None:
        with SQLiteAuthorityConsistency() as ledger:
            old = ledger.open_authority(
                tenant_id="tenant-a",
                domain_id="artifact",
                resource_id="a-1",
                owner_id="artifact-plane",
                content_digest=digest("v1"),
                now=BASE,
            )
            ledger.compare_and_commit(
                tenant_id="tenant-a",
                domain_id="artifact",
                resource_id="a-1",
                expected_generation=1,
                owner_id="artifact-plane",
                content_digest=digest("v2"),
                now=BASE + timedelta(seconds=1),
            )
            with self.assertRaises(ProjectionStale):
                ledger.register_projection(
                    tenant_id="tenant-a",
                    projection_id="stale",
                    kind="cache",
                    payload_digest=digest("payload"),
                    sources=[old],
                )
            self.assertEqual(ledger.card()["projection_count"], 0)

    def test_malformed_digest_and_predating_commit_fail_closed(self) -> None:
        with SQLiteAuthorityConsistency() as ledger:
            with self.assertRaisesRegex(AuthorityConsistencyError, "SHA-256"):
                ledger.open_authority(
                    tenant_id="tenant-a",
                    domain_id="memory",
                    resource_id="m-1",
                    owner_id="memory",
                    content_digest="A" * 64,
                )
            ledger.open_authority(
                tenant_id="tenant-a",
                domain_id="memory",
                resource_id="m-1",
                owner_id="memory",
                content_digest=digest("v1"),
                now=BASE + timedelta(seconds=2),
            )
            with self.assertRaisesRegex(AuthorityConflict, "predate"):
                ledger.compare_and_commit(
                    tenant_id="tenant-a",
                    domain_id="memory",
                    resource_id="m-1",
                    expected_generation=1,
                    owner_id="memory",
                    content_digest=digest("v2"),
                    now=BASE,
                )

    def test_persisted_projection_corruption_is_not_returned(self) -> None:
        with SQLiteAuthorityConsistency() as ledger:
            source = ledger.open_authority(
                tenant_id="tenant-a",
                domain_id="memory",
                resource_id="m-1",
                owner_id="memory",
                content_digest=digest("v1"),
                now=BASE,
            )
            ledger.register_projection(
                tenant_id="tenant-a",
                projection_id="p-1",
                kind="derived",
                payload_digest=digest("p"),
                sources=[source],
                now=BASE,
            )
            ledger._connection.execute(
                """
                UPDATE state_projection
                SET sources_json = ?
                WHERE namespace = ? AND tenant_id = ? AND projection_id = ?
                """,
                ("[]", ledger.namespace, "tenant-a", "p-1"),
            )
            with self.assertRaises(AuthorityCorruption):
                ledger.read_projection(
                    tenant_id="tenant-a",
                    projection_id="p-1",
                )

    def test_file_backed_reopen_preserves_authority_and_staleness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "authority.sqlite"
            with SQLiteAuthorityConsistency(path) as ledger:
                source = ledger.open_authority(
                    tenant_id="tenant-a",
                    domain_id="operation",
                    resource_id="op-1",
                    owner_id="orchestration",
                    content_digest=digest("v1"),
                    now=BASE,
                )
                ledger.register_projection(
                    tenant_id="tenant-a",
                    projection_id="op-view",
                    kind="cache",
                    payload_digest=digest("view"),
                    sources=[source],
                    now=BASE,
                )
            with SQLiteAuthorityConsistency(path) as reopened:
                self.assertEqual(
                    reopened.read_authority(
                        tenant_id="tenant-a",
                        domain_id="operation",
                        resource_id="op-1",
                    ).generation,
                    1,
                )
                reopened.compare_and_commit(
                    tenant_id="tenant-a",
                    domain_id="operation",
                    resource_id="op-1",
                    expected_generation=1,
                    owner_id="orchestration",
                    content_digest=digest("v2"),
                    now=BASE + timedelta(seconds=1),
                )
                with self.assertRaises(ProjectionStale):
                    reopened.read_projection(
                        tenant_id="tenant-a",
                        projection_id="op-view",
                    )

    def test_canonical_and_governed_ai_files_are_byte_identical(self) -> None:
        root = Path(__file__).resolve().parents[2]
        canonical = root / "skeleton/persistence/authority_consistency.py"
        mirror = root / "skeleton/ai/runtime/persistence/authority_consistency.py"
        self.assertEqual(canonical.read_bytes(), mirror.read_bytes())


if __name__ == "__main__":
    unittest.main()
