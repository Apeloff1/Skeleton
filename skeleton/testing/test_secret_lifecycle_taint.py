from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from skeleton.security.secret_handles import SecretRef
from skeleton.security.secret_lifecycle import (
    SQLiteSecretLifecycle,
    SecretLifecycleConflict,
    SecretLifecycleCorruption,
    SecretLifecycleError,
    SecretTaintStale,
    SecretTaintViolation,
    SecretVersionState,
    SecretVersionUnavailable,
)


def ref(version: str, handle: str = "provider-key") -> SecretRef:
    return SecretRef(
        handle_id=handle,
        provider_id="vault-primary",
        version_id=version,
    )


class SecretLifecycleTests(unittest.TestCase):
    def test_register_and_exact_active_use(self) -> None:
        with SQLiteSecretLifecycle() as registry:
            record = registry.register_version(
                tenant_id="tenant-a",
                owner_id="provider-runtime",
                secret_ref=ref("v1"),
                now_ns=100,
            )
            self.assertEqual(record.state, SecretVersionState.ACTIVE)
            self.assertEqual(record.identity.generation, 1)
            usable = registry.assert_usable(
                tenant_id="tenant-a",
                owner_id="provider-runtime",
                secret_ref=ref("v1"),
            )
            self.assertEqual(usable.identity, record.identity)
            self.assertNotIn("secret", repr(record.payload()).lower().replace("secret_material_present", ""))

    def test_register_is_idempotent_only_for_same_owner(self) -> None:
        with SQLiteSecretLifecycle() as registry:
            first = registry.register_version(
                tenant_id="tenant-a",
                owner_id="owner-a",
                secret_ref=ref("v1"),
                now_ns=100,
            )
            replay = registry.register_version(
                tenant_id="tenant-a",
                owner_id="owner-a",
                secret_ref=ref("v1"),
                now_ns=200,
            )
            self.assertEqual(replay, first)
            with self.assertRaisesRegex(SecretLifecycleConflict, "owner mismatch"):
                registry.register_version(
                    tenant_id="tenant-a",
                    owner_id="owner-b",
                    secret_ref=ref("v1"),
                    now_ns=300,
                )

    def test_rotation_is_atomic_and_old_version_immediately_unusable(self) -> None:
        with SQLiteSecretLifecycle() as registry:
            current = registry.register_version(
                tenant_id="tenant-a",
                owner_id="provider-runtime",
                secret_ref=ref("v1"),
                now_ns=100,
            )
            retired, successor = registry.rotate(
                tenant_id="tenant-a",
                owner_id="provider-runtime",
                current_ref=ref("v1"),
                new_ref=ref("v2"),
                expected_generation=current.identity.generation,
                now_ns=200,
            )
            self.assertEqual(retired.state, SecretVersionState.ROTATED)
            self.assertEqual(retired.superseded_by_version_id, "v2")
            self.assertEqual(successor.state, SecretVersionState.ACTIVE)
            self.assertEqual(successor.identity.generation, 2)
            with self.assertRaisesRegex(SecretVersionUnavailable, "rotated"):
                registry.assert_usable(
                    tenant_id="tenant-a",
                    owner_id="provider-runtime",
                    secret_ref=ref("v1"),
                )
            registry.assert_usable(
                tenant_id="tenant-a",
                owner_id="provider-runtime",
                secret_ref=ref("v2"),
            )

    def test_rotation_rejects_provider_handle_and_generation_drift(self) -> None:
        with SQLiteSecretLifecycle() as registry:
            registry.register_version(
                tenant_id="tenant-a",
                owner_id="provider-runtime",
                secret_ref=ref("v1"),
                now_ns=100,
            )
            with self.assertRaisesRegex(SecretLifecycleError, "handle_id"):
                registry.rotate(
                    tenant_id="tenant-a",
                    owner_id="provider-runtime",
                    current_ref=ref("v1"),
                    new_ref=ref("v2", handle="other"),
                    expected_generation=1,
                    now_ns=200,
                )
            with self.assertRaisesRegex(SecretLifecycleConflict, "stale"):
                registry.rotate(
                    tenant_id="tenant-a",
                    owner_id="provider-runtime",
                    current_ref=ref("v1"),
                    new_ref=ref("v2"),
                    expected_generation=2,
                    now_ns=200,
                )
            self.assertEqual(
                registry.read_version(
                    tenant_id="tenant-a",
                    secret_ref=ref("v1"),
                ).state,
                SecretVersionState.ACTIVE,
            )

    def test_revoke_then_destroy_survives_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "secret-lifecycle.sqlite"
            with SQLiteSecretLifecycle(path) as registry:
                record = registry.register_version(
                    tenant_id="tenant-a",
                    owner_id="provider-runtime",
                    secret_ref=ref("v1"),
                    now_ns=100,
                )
                revoked = registry.revoke(
                    tenant_id="tenant-a",
                    owner_id="provider-runtime",
                    secret_ref=ref("v1"),
                    expected_generation=record.identity.generation,
                    now_ns=200,
                )
                self.assertEqual(revoked.state, SecretVersionState.REVOKED)
            with SQLiteSecretLifecycle(path) as reopened:
                with self.assertRaisesRegex(SecretVersionUnavailable, "revoked"):
                    reopened.assert_usable(
                        tenant_id="tenant-a",
                        owner_id="provider-runtime",
                        secret_ref=ref("v1"),
                    )
                destroyed = reopened.destroy(
                    tenant_id="tenant-a",
                    owner_id="provider-runtime",
                    secret_ref=ref("v1"),
                    expected_generation=1,
                    now_ns=300,
                )
                self.assertEqual(destroyed.state, SecretVersionState.DESTROYED)

    def test_destroy_active_secret_fails_closed(self) -> None:
        with SQLiteSecretLifecycle() as registry:
            registry.register_version(
                tenant_id="tenant-a",
                owner_id="provider-runtime",
                secret_ref=ref("v1"),
                now_ns=100,
            )
            with self.assertRaisesRegex(SecretLifecycleConflict, "cannot transition"):
                registry.destroy(
                    tenant_id="tenant-a",
                    owner_id="provider-runtime",
                    secret_ref=ref("v1"),
                    expected_generation=1,
                    now_ns=200,
                )

    def test_direct_taint_blocks_untrusted_sink_and_allows_secret_aware_sink(self) -> None:
        with SQLiteSecretLifecycle() as registry:
            registry.register_version(
                tenant_id="tenant-a",
                owner_id="provider-runtime",
                secret_ref=ref("v1"),
                now_ns=100,
            )
            taint = registry.taint_from_secrets(
                tenant_id="tenant-a",
                value_id="auth-header",
                secret_refs=(ref("v1"),),
                owner_id="provider-runtime",
                transformation_id="bearer-header",
                now_ns=110,
            )
            self.assertEqual(len(taint.sources), 1)
            denied = registry.evaluate_sink(
                tenant_id="tenant-a",
                value_id="auth-header",
                sink_id="telemetry",
                secret_aware=False,
                now_ns=120,
            )
            self.assertFalse(denied.allowed)
            self.assertEqual(denied.reason_code, "secret-taint")
            with self.assertRaises(SecretTaintViolation):
                registry.assert_untainted(
                    tenant_id="tenant-a",
                    value_id="auth-header",
                    sink_id="logs",
                    now_ns=120,
                )
            allowed = registry.evaluate_sink(
                tenant_id="tenant-a",
                value_id="auth-header",
                sink_id="provider-auth-transport",
                secret_aware=True,
                now_ns=120,
            )
            self.assertTrue(allowed.allowed)
            self.assertEqual(allowed.reason_code, "secret-aware-sink")

    def test_taint_propagation_is_transitive_union_and_cannot_be_rebound(self) -> None:
        with SQLiteSecretLifecycle() as registry:
            registry.register_version(
                tenant_id="tenant-a",
                owner_id="provider-runtime",
                secret_ref=ref("v1", "a"),
                now_ns=100,
            )
            registry.register_version(
                tenant_id="tenant-a",
                owner_id="provider-runtime",
                secret_ref=ref("v1", "b"),
                now_ns=100,
            )
            registry.taint_from_secrets(
                tenant_id="tenant-a",
                value_id="left",
                secret_refs=(ref("v1", "a"),),
                owner_id="provider-runtime",
                transformation_id="left",
                now_ns=110,
            )
            registry.taint_from_secrets(
                tenant_id="tenant-a",
                value_id="right",
                secret_refs=(ref("v1", "b"),),
                owner_id="provider-runtime",
                transformation_id="right",
                now_ns=110,
            )
            combined = registry.propagate_taint(
                tenant_id="tenant-a",
                value_id="combined",
                parent_value_ids=("right", "left"),
                transformation_id="combine",
                now_ns=120,
            )
            self.assertEqual(
                [source.handle_id for source in combined.sources],
                ["a", "b"],
            )
            self.assertEqual(combined.parent_value_ids, ("left", "right"))
            with self.assertRaisesRegex(SecretLifecycleConflict, "cannot be rebound"):
                registry.propagate_taint(
                    tenant_id="tenant-a",
                    value_id="combined",
                    parent_value_ids=("left",),
                    transformation_id="different",
                    now_ns=130,
                )

    def test_rotation_makes_existing_taint_stale(self) -> None:
        with SQLiteSecretLifecycle() as registry:
            current = registry.register_version(
                tenant_id="tenant-a",
                owner_id="provider-runtime",
                secret_ref=ref("v1"),
                now_ns=100,
            )
            registry.taint_from_secrets(
                tenant_id="tenant-a",
                value_id="derived",
                secret_refs=(ref("v1"),),
                owner_id="provider-runtime",
                transformation_id="derive",
                now_ns=110,
            )
            registry.rotate(
                tenant_id="tenant-a",
                owner_id="provider-runtime",
                current_ref=ref("v1"),
                new_ref=ref("v2"),
                expected_generation=current.identity.generation,
                now_ns=120,
            )
            with self.assertRaises(SecretTaintStale):
                registry.read_taint(
                    tenant_id="tenant-a",
                    value_id="derived",
                )
            decision = registry.evaluate_sink(
                tenant_id="tenant-a",
                value_id="derived",
                sink_id="provider-auth-transport",
                secret_aware=True,
                now_ns=130,
            )
            self.assertFalse(decision.allowed)
            self.assertEqual(decision.reason_code, "stale-secret-lineage")

    def test_cross_tenant_taint_and_secret_access_fail_closed(self) -> None:
        with SQLiteSecretLifecycle() as registry:
            registry.register_version(
                tenant_id="tenant-a",
                owner_id="provider-runtime",
                secret_ref=ref("v1"),
                now_ns=100,
            )
            with self.assertRaises(SecretVersionUnavailable):
                registry.assert_usable(
                    tenant_id="tenant-b",
                    owner_id="provider-runtime",
                    secret_ref=ref("v1"),
                )
            registry.taint_from_secrets(
                tenant_id="tenant-a",
                value_id="value",
                secret_refs=(ref("v1"),),
                owner_id="provider-runtime",
                transformation_id="derive",
                now_ns=110,
            )
            self.assertFalse(
                registry.is_tainted(
                    tenant_id="tenant-b",
                    value_id="value",
                )
            )

    def test_persisted_corruption_is_not_interpreted_as_valid_lifecycle(self) -> None:
        with SQLiteSecretLifecycle() as registry:
            registry.register_version(
                tenant_id="tenant-a",
                owner_id="provider-runtime",
                secret_ref=ref("v1"),
                now_ns=100,
            )
            registry._connection.execute(
                """
                UPDATE secret_version_lifecycle
                SET state = 'invented'
                WHERE namespace = ? AND tenant_id = ?
                """,
                (registry.namespace, "tenant-a"),
            )
            with self.assertRaises(SecretLifecycleCorruption):
                registry.read_version(
                    tenant_id="tenant-a",
                    secret_ref=ref("v1"),
                )

    def test_status_card_contains_no_secret_material_and_ai_mirror_matches(self) -> None:
        with SQLiteSecretLifecycle() as registry:
            registry.register_version(
                tenant_id="tenant-a",
                owner_id="provider-runtime",
                secret_ref=ref("v1"),
                now_ns=100,
            )
            card = registry.card()
            self.assertFalse(card["secret_material_present"])
            self.assertEqual(card["version_states"]["active"], 1)
            self.assertEqual(card["taint_count"], 0)

        root = Path(__file__).resolve().parents[2]
        self.assertEqual(
            (root / "skeleton/security/secret_lifecycle.py").read_bytes(),
            (root / "skeleton/ai/runtime/security/secret_lifecycle.py").read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
