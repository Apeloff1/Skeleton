from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from skeleton.config.authority import (
    ConfigConflict,
    ConfigCorruption,
    ConfigSecretMaterialError,
    SQLiteConfigAuthority,
)


class ConfigAuthorityTests(unittest.TestCase):
    def test_proposal_does_not_activate_and_first_activation_is_fenced(self) -> None:
        with SQLiteConfigAuthority() as authority:
            candidate = authority.propose(
                {"model": {"temperature": 0.2}, "budget": 100},
                actor_id="operator-a",
                reason="initial runtime configuration",
                now_ns=100,
            )
            self.assertIsNone(authority.active_snapshot())
            self.assertEqual(authority.head().generation, 0)
            head = authority.activate(
                version=candidate.version,
                expected_head_generation=0,
                actor_id="operator-a",
                reason="approved initial configuration",
                now_ns=110,
            )
            self.assertEqual(head.generation, 1)
            self.assertEqual(head.active_version, 1)
            self.assertEqual(authority.active_snapshot().digest, candidate.digest)

    def test_stale_head_cannot_activate(self) -> None:
        with SQLiteConfigAuthority() as authority:
            first = authority.propose(
                {"value": 1},
                actor_id="operator",
                reason="first",
                now_ns=100,
            )
            authority.activate(
                version=first.version,
                expected_head_generation=0,
                actor_id="operator",
                reason="activate first",
                now_ns=110,
            )
            second = authority.propose(
                {"value": 2},
                actor_id="operator",
                reason="second",
                now_ns=120,
            )
            with self.assertRaisesRegex(ConfigConflict, "stale"):
                authority.activate(
                    version=second.version,
                    expected_head_generation=0,
                    actor_id="operator",
                    reason="stale activation",
                    now_ns=130,
                )
            self.assertEqual(authority.active_snapshot().version, 1)

    def test_sibling_candidate_cannot_replace_new_head_without_reproposal(self) -> None:
        with SQLiteConfigAuthority() as authority:
            first = authority.propose(
                {"value": 1}, actor_id="operator", reason="one", now_ns=100
            )
            authority.activate(
                version=first.version,
                expected_head_generation=0,
                actor_id="operator",
                reason="activate one",
                now_ns=110,
            )
            left = authority.propose(
                {"value": 2}, actor_id="operator", reason="left", now_ns=120
            )
            right = authority.propose(
                {"value": 3}, actor_id="operator", reason="right", now_ns=121
            )
            authority.activate(
                version=left.version,
                expected_head_generation=1,
                actor_id="operator",
                reason="choose left",
                now_ns=130,
            )
            with self.assertRaisesRegex(ConfigConflict, "does not descend"):
                authority.activate(
                    version=right.version,
                    expected_head_generation=2,
                    actor_id="operator",
                    reason="stale sibling",
                    now_ns=140,
                )

    def test_explicit_rollback_moves_head_without_mutating_snapshots(self) -> None:
        with SQLiteConfigAuthority() as authority:
            first = authority.propose(
                {"value": 1}, actor_id="operator", reason="one", now_ns=100
            )
            authority.activate(
                version=first.version,
                expected_head_generation=0,
                actor_id="operator",
                reason="activate one",
                now_ns=110,
            )
            second = authority.propose(
                {"value": 2}, actor_id="operator", reason="two", now_ns=120
            )
            authority.activate(
                version=second.version,
                expected_head_generation=1,
                actor_id="operator",
                reason="activate two",
                now_ns=130,
            )
            before = authority.read_snapshot(1)
            head = authority.rollback(
                version=1,
                expected_head_generation=2,
                actor_id="incident-commander",
                reason="rollback regression",
                now_ns=140,
            )
            after = authority.read_snapshot(1)
            self.assertEqual(before, after)
            self.assertEqual(head.generation, 3)
            self.assertEqual(authority.active_snapshot().version, 1)
            self.assertEqual(
                [row["action"] for row in authority.transition_log()],
                ["activate", "activate", "rollback"],
            )

    def test_snapshots_are_deep_immutable(self) -> None:
        with SQLiteConfigAuthority() as authority:
            snapshot = authority.propose(
                {"nested": {"items": [1, 2], "flag": True}},
                actor_id="operator",
                reason="immutable",
                now_ns=100,
            )
            with self.assertRaises(TypeError):
                snapshot.values["nested"] = {}  # type: ignore[index]
            nested = snapshot.values["nested"]
            with self.assertRaises(TypeError):
                nested["flag"] = False  # type: ignore[index]
            self.assertEqual(snapshot.get("nested.items"), (1, 2))

    def test_secret_shaped_material_is_rejected_before_persistence(self) -> None:
        with SQLiteConfigAuthority() as authority:
            for payload in (
                {"api_key": "plaintext"},
                {"provider": {"password": "plaintext"}},
                {"headers": {"authorization": "Bearer plaintext"}},
                {"refresh-token": "plaintext"},
            ):
                with self.assertRaises(ConfigSecretMaterialError):
                    authority.propose(
                        payload,
                        actor_id="operator",
                        reason="must reject",
                        now_ns=100,
                    )
            self.assertEqual(authority.card()["snapshot_count"], 0)

    def test_opaque_secret_reference_names_are_allowed_without_material(self) -> None:
        with SQLiteConfigAuthority() as authority:
            snapshot = authority.propose(
                {
                    "provider": {
                        "secret_ref": "vault://provider-key/version-7",
                        "endpoint": "https://provider.invalid",
                    }
                },
                actor_id="operator",
                reason="opaque reference",
                now_ns=100,
            )
            rendered = repr(snapshot.payload())
            self.assertIn("secret_ref", rendered)
            self.assertNotIn("plaintext-secret", rendered)
            self.assertFalse(snapshot.payload()["secret_material_present"])

    def test_restart_preserves_head_history_and_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.sqlite"
            with SQLiteConfigAuthority(path) as first:
                one = first.propose(
                    {"value": 1}, actor_id="operator", reason="one", now_ns=100
                )
                first.activate(
                    version=one.version,
                    expected_head_generation=0,
                    actor_id="operator",
                    reason="activate one",
                    now_ns=110,
                )
                two = first.propose(
                    {"value": 2}, actor_id="operator", reason="two", now_ns=120
                )
                first.activate(
                    version=two.version,
                    expected_head_generation=1,
                    actor_id="operator",
                    reason="activate two",
                    now_ns=130,
                )
            with SQLiteConfigAuthority(path) as reopened:
                self.assertEqual(reopened.head().generation, 2)
                self.assertEqual(reopened.active_snapshot().get("value"), 2)
                self.assertEqual(len(reopened.history()), 2)
                reopened.rollback(
                    version=1,
                    expected_head_generation=2,
                    actor_id="operator",
                    reason="restart rollback",
                    now_ns=140,
                )
                self.assertEqual(reopened.active_snapshot().get("value"), 1)

    def test_tampered_snapshot_is_not_returned(self) -> None:
        with SQLiteConfigAuthority() as authority:
            snapshot = authority.propose(
                {"value": 1}, actor_id="operator", reason="one", now_ns=100
            )
            authority._connection.execute(
                """
                UPDATE config_snapshot
                SET values_json = ?
                WHERE namespace = ? AND version = ?
                """,
                ('{"value":999}', authority.namespace, snapshot.version),
            )
            with self.assertRaises(ConfigCorruption):
                authority.read_snapshot(snapshot.version)

    def test_tampered_active_head_is_not_trusted(self) -> None:
        with SQLiteConfigAuthority() as authority:
            snapshot = authority.propose(
                {"value": 1}, actor_id="operator", reason="one", now_ns=100
            )
            authority.activate(
                version=snapshot.version,
                expected_head_generation=0,
                actor_id="operator",
                reason="activate",
                now_ns=110,
            )
            authority._connection.execute(
                """
                UPDATE config_head
                SET active_digest = ?
                WHERE namespace = ?
                """,
                ("0" * 64, authority.namespace),
            )
            with self.assertRaises(ConfigCorruption):
                authority.active_snapshot()

    def test_canonical_and_ai_mirror_are_byte_identical(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self.assertEqual(
            (root / "skeleton/config/authority.py").read_bytes(),
            (root / "skeleton/ai/runtime/config/authority.py").read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
