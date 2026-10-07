"""Security regression tests for the persistent Skeleton secret store."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import skeleton.organism.secret_manager as secret_module
from skeleton.organism.secret_manager import SecretManager


class TestSecretManagerSecurity(unittest.TestCase):
    def test_unconfigured_store_has_no_shared_fallback_key(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"SKELETON_MASTER_SECRET": ""}, clear=False
        ):
            manager = SecretManager(root=Path(tmp))
            self.assertEqual(manager.card()["storage_state"], "unconfigured")
            self.assertFalse(manager.card()["master_key_configured"])

            with self.assertRaisesRegex(RuntimeError, "SKELETON_MASTER_SECRET"):
                manager.set("api-token", "top-secret")

            self.assertFalse((Path(tmp) / "secrets.json").exists())
            self.assertIsNone(manager.get("api-token"))

    @unittest.skipIf(secret_module.Fernet is None, "cryptography.Fernet unavailable")
    def test_explicit_master_secret_round_trips_without_plaintext_at_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = SecretManager(root=root, master_secret="deployment-specific-master-key")
            manager.set("api-token", "top-secret-value")

            self.assertEqual(manager.get("api-token"), "top-secret-value")
            raw = (root / "secrets.json").read_bytes()
            self.assertNotIn(b"top-secret-value", raw)
            self.assertNotIn(b"api-token", raw)
            self.assertEqual(manager.card()["storage_state"], "ready")

            reopened = SecretManager(root=root, master_secret="deployment-specific-master-key")
            self.assertEqual(reopened.get("api-token"), "top-secret-value")

    @unittest.skipIf(secret_module.Fernet is None, "cryptography.Fernet unavailable")
    def test_existing_store_is_locked_without_its_master_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            SecretManager(root=root, master_secret="correct-key").set("token", "classified")

            with patch.dict(os.environ, {"SKELETON_MASTER_SECRET": ""}, clear=False):
                locked = SecretManager(root=root)

            self.assertEqual(locked.card()["storage_state"], "locked")
            self.assertFalse(locked.card()["master_key_configured"])
            self.assertIsNone(locked.get("token"))
            with self.assertRaises(RuntimeError):
                locked.set("another", "value")

    @unittest.skipIf(secret_module.Fernet is None, "cryptography.Fernet unavailable")
    def test_wrong_master_secret_does_not_overwrite_existing_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = SecretManager(root=root, master_secret="correct-key")
            original.set("token", "classified")
            before = (root / "secrets.json").read_bytes()

            wrong = SecretManager(root=root, master_secret="wrong-key")
            self.assertEqual(wrong.card()["storage_state"], "locked")
            self.assertIsNone(wrong.get("token"))
            with self.assertRaisesRegex(RuntimeError, "locked"):
                wrong.set("token", "replacement")

            self.assertEqual((root / "secrets.json").read_bytes(), before)
            self.assertEqual(
                SecretManager(root=root, master_secret="correct-key").get("token"),
                "classified",
            )

    @unittest.skipIf(secret_module.Fernet is None, "cryptography.Fernet unavailable")
    def test_legacy_cleartext_document_requires_key_and_migrates_on_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            file = root / "secrets.json"
            file.write_text(json.dumps({"secrets": {}}), encoding="utf-8")

            with patch.dict(os.environ, {"SKELETON_MASTER_SECRET": ""}, clear=False):
                unconfigured = SecretManager(root=root)
            self.assertEqual(unconfigured.card()["storage_state"], "locked")

            configured = SecretManager(root=root, master_secret="migration-key")
            self.assertEqual(configured.card()["storage_state"], "legacy_cleartext")
            configured.set("migrated", "secret-value")

            raw = file.read_bytes()
            self.assertNotIn(b"secret-value", raw)
            self.assertNotEqual(raw[:1], b"{")
            self.assertEqual(configured.card()["storage_state"], "ready")

    @unittest.skipIf(secret_module.Fernet is None, "cryptography.Fernet unavailable")
    def test_status_card_never_exposes_secret_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = SecretManager(root=Path(tmp), master_secret="status-card-key")
            manager.set("database-password", "do-not-display")
            rendered = repr(manager.card())

            self.assertNotIn("do-not-display", rendered)
            self.assertNotIn("status-card-key", rendered)
            self.assertEqual(manager.card()["secrets"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
