from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from skeleton.config.authority import (
    ConfigurationAuthorityError,
    ConfigurationConflict,
    ConfigurationCorruption,
    SQLiteConfigurationAuthority,
)


class ConfigurationAuthorityTests(unittest.TestCase):
    def test_commit_is_immutable_content_addressed_and_monotonic(self) -> None:
        source = {"routing": {"primary": "local"}, "budget": 8}
        with SQLiteConfigurationAuthority() as store:
            first = store.commit(
                tenant_id="tenant-a",
                namespace="runtime",
                expected_generation=0,
                actor_id="operator-a",
                reason="bootstrap",
                values=source,
                now_ns=100,
            )
            source["budget"] = 999
            self.assertEqual(first.generation, 1)
            self.assertEqual(first.values["budget"], 8)
            loaded = store.active(tenant_id="tenant-a", namespace="runtime")
            assert loaded is not None
            copy = loaded.values
            copy["budget"] = 123
            self.assertEqual(
                store.active(tenant_id="tenant-a", namespace="runtime").values["budget"],
                8,
            )

    def test_stale_compare_and_swap_fails_closed(self) -> None:
        with SQLiteConfigurationAuthority() as store:
            store.commit(
                tenant_id="tenant-a",
                namespace="runtime",
                expected_generation=0,
                actor_id="operator-a",
                reason="bootstrap",
                values={"v": 1},
                now_ns=100,
            )
            with self.assertRaisesRegex(ConfigurationConflict, "stale"):
                store.commit(
                    tenant_id="tenant-a",
                    namespace="runtime",
                    expected_generation=0,
                    actor_id="operator-b",
                    reason="stale",
                    values={"v": 2},
                    now_ns=101,
                )

    def test_rollback_creates_new_generation_instead_of_reactivating_history(self) -> None:
        with SQLiteConfigurationAuthority() as store:
            one = store.commit(
                tenant_id="tenant-a",
                namespace="runtime",
                expected_generation=0,
                actor_id="operator-a",
                reason="one",
                values={"v": 1},
                now_ns=100,
            )
            two = store.commit(
                tenant_id="tenant-a",
                namespace="runtime",
                expected_generation=1,
                actor_id="operator-a",
                reason="two",
                values={"v": 2},
                now_ns=101,
            )
            rolled = store.rollback(
                tenant_id="tenant-a",
                namespace="runtime",
                expected_generation=2,
                target_generation=1,
                actor_id="operator-b",
                reason="incident rollback",
                now_ns=102,
            )
            self.assertEqual(rolled.generation, 3)
            self.assertEqual(rolled.values, one.values)
            self.assertNotEqual(rolled.snapshot_digest, one.snapshot_digest)
            self.assertEqual(rolled.parent_snapshot_digest, two.snapshot_digest)
            self.assertEqual(len(store.verify_chain(tenant_id="tenant-a", namespace="runtime")), 3)

    def test_restart_preserves_active_authority_and_chain(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.sqlite3"
            with SQLiteConfigurationAuthority(path) as store:
                first = store.commit(
                    tenant_id="tenant-a",
                    namespace="runtime",
                    expected_generation=0,
                    actor_id="operator-a",
                    reason="bootstrap",
                    values={"feature": True},
                    now_ns=100,
                )
            with SQLiteConfigurationAuthority(path) as reopened:
                active = reopened.active(tenant_id="tenant-a", namespace="runtime")
                assert active is not None
                self.assertEqual(active.snapshot_digest, first.snapshot_digest)
                self.assertEqual(reopened.verify_chain(tenant_id="tenant-a", namespace="runtime"), (first.snapshot_digest,))

    def test_tenant_and_namespace_are_authority_boundaries(self) -> None:
        with SQLiteConfigurationAuthority() as store:
            a = store.commit(
                tenant_id="tenant-a",
                namespace="runtime",
                expected_generation=0,
                actor_id="operator-a",
                reason="a",
                values={"v": 1},
                now_ns=100,
            )
            self.assertIsNone(store.active(tenant_id="tenant-b", namespace="runtime"))
            self.assertIsNone(store.active(tenant_id="tenant-a", namespace="other"))
            with self.assertRaises(ConfigurationAuthorityError):
                store.read_snapshot(
                    tenant_id="tenant-b",
                    namespace="runtime",
                    snapshot_digest=a.snapshot_digest,
                )

    def test_non_finite_and_non_json_configuration_is_rejected(self) -> None:
        with SQLiteConfigurationAuthority() as store:
            with self.assertRaises(ConfigurationAuthorityError):
                store.commit(
                    tenant_id="tenant-a",
                    namespace="runtime",
                    expected_generation=0,
                    actor_id="operator-a",
                    reason="bad",
                    values={"x": float("nan")},
                    now_ns=100,
                )
            with self.assertRaises(ConfigurationAuthorityError):
                store.commit(
                    tenant_id="tenant-a",
                    namespace="runtime",
                    expected_generation=0,
                    actor_id="operator-a",
                    reason="bad",
                    values={"x": object()},
                    now_ns=100,
                )

    def test_payload_and_snapshot_corruption_fail_closed(self) -> None:
        with SQLiteConfigurationAuthority() as store:
            store.commit(
                tenant_id="tenant-a",
                namespace="runtime",
                expected_generation=0,
                actor_id="operator-a",
                reason="bootstrap",
                values={"v": 1},
                now_ns=100,
            )
            store._connection.execute(
                "UPDATE config_snapshot SET payload_json = ? WHERE tenant_id = ?",
                ('{"v":2}', "tenant-a"),
            )
            with self.assertRaisesRegex(ConfigurationCorruption, "payload digest"):
                store.active(tenant_id="tenant-a", namespace="runtime")

    def test_active_pointer_corruption_fails_closed(self) -> None:
        with SQLiteConfigurationAuthority() as store:
            store.commit(
                tenant_id="tenant-a",
                namespace="runtime",
                expected_generation=0,
                actor_id="operator-a",
                reason="bootstrap",
                values={"v": 1},
                now_ns=100,
            )
            store._connection.execute(
                "UPDATE config_active SET snapshot_digest = ? WHERE tenant_id = ?",
                ("0" * 64, "tenant-a"),
            )
            with self.assertRaisesRegex(ConfigurationCorruption, "does not match"):
                store.active(tenant_id="tenant-a", namespace="runtime")


if __name__ == "__main__":
    unittest.main()
