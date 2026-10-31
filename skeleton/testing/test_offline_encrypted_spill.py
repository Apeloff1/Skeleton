"""Source-backed offline encrypted spill integration and abuse regressions."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skeleton.app.offline_encrypted_spill import (
    EncryptedSpillStore, SpillError, SpillIdentity, SpillPolicy,
)
from skeleton.app.offline_spill_cli import main

MODEL = "a" * 64
TOKENIZER = "b" * 64
IDENTITY = SpillIdentity(MODEL, TOKENIZER, "test-context", 0)


class TestOfflineEncryptedSpill(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "spool"
        self.key = b"\x12" * 32
        self.store = EncryptedSpillStore(self.root, self.key)
        self.temp = Path(temp.name)

    def test_restart_round_trip(self):
        data = b"binary-local-context:\x00\xff" * 64
        receipt = self.store.put(data, IDENTITY)
        self.assertEqual(EncryptedSpillStore(self.root, self.key).read(receipt["record_id"], IDENTITY), data)
        self.assertEqual(self.store.verify()["verified"], 1)
        self.assertNotIn(b"binary-local-context", (self.root / (receipt["record_id"] + ".bin")).read_bytes())

    def test_wrong_key_and_identity(self):
        receipt = self.store.put(b"private", IDENTITY)
        with self.assertRaisesRegex(SpillError, "authentication"):
            EncryptedSpillStore(self.root, b"\x13" * 32).read(receipt["record_id"], IDENTITY)
        for wrong in (
            SpillIdentity("c" * 64, TOKENIZER, "test-context", 0),
            SpillIdentity(MODEL, TOKENIZER, "another", 0),
            SpillIdentity(MODEL, TOKENIZER, "test-context", 1),
        ):
            with self.assertRaisesRegex(SpillError, "mismatch"):
                self.store.read(receipt["record_id"], wrong)

    def test_ciphertext_tamper(self):
        receipt = self.store.put(b"private", IDENTITY)
        path = self.root / (receipt["record_id"] + ".bin")
        data = bytearray(path.read_bytes())
        data[-1] ^= 1
        path.write_bytes(data)
        with self.assertRaisesRegex(SpillError, "authentication"):
            self.store.verify()

    def test_manifest_tamper(self):
        receipt = self.store.put(b"private", IDENTITY)
        path = self.root / (receipt["record_id"] + ".json")
        manifest = json.loads(path.read_text())
        manifest["created_ns"] += 1
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(SpillError, "authentication"):
            self.store.read(receipt["record_id"], IDENTITY)

    def test_list_requires_authenticated_manifest(self):
        receipt = self.store.put(b"private", IDENTITY)
        self.assertEqual(self.store.records()[0]["record_id"], receipt["record_id"])
        with self.assertRaisesRegex(SpillError, "authentication"):
            EncryptedSpillStore(self.root, bytes([0x13]) * 32).records()
        path = self.root / (receipt["record_id"] + ".json")
        manifest = json.loads(path.read_text())
        manifest["context_id"] = "forged-context"
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(SpillError, "authentication"):
            self.store.records()

    def test_missing_manifest_mac_rejected(self):
        receipt = self.store.put(b"private", IDENTITY)
        path = self.root / (receipt["record_id"] + ".json")
        manifest = json.loads(path.read_text())
        manifest.pop("manifest_mac")
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(SpillError, "fields"):
            self.store.records()

    def test_unknown_manifest_fields(self):
        receipt = self.store.put(b"private", IDENTITY)
        path = self.root / (receipt["record_id"] + ".json")
        manifest = json.loads(path.read_text())
        manifest["untrusted"] = True
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(SpillError, "fields"):
            self.store.records()

    def test_quota(self):
        policy = SpillPolicy(max_entry_bytes=32, max_total_bytes=48,
                             min_free_bytes=64 * 1024 * 1024, max_entries=1)
        store = EncryptedSpillStore(self.root, self.key, policy=policy)
        with self.assertRaises(SpillError):
            store.put(b"x" * 33, IDENTITY)
        store.put(b"x" * 20, IDENTITY)
        with self.assertRaisesRegex(SpillError, "quota"):
            store.put(b"x", IDENTITY)

    def test_disk_reserve(self):
        usage = type("Usage", (), {"free": 1})()
        with patch.object(self.store, "_free_bytes", return_value=usage.free):
            with self.assertRaisesRegex(SpillError, "reserve"):
                self.store.put(b"payload", IDENTITY)

    def test_crash_prune(self):
        (self.root / ("f" * 32 + ".bin")).write_bytes(b"orphan")
        (self.root / (".tmp-" + "a" * 32 + "-" + "b" * 16)).write_bytes(b"temporary")
        self.assertEqual(self.store.prune_orphans(),
                         {"orphan_data_removed": 1, "temp_files_removed": 1})
        self.assertEqual(self.store.verify()["verified"], 0)

    def test_delete_authenticates(self):
        receipt = self.store.put(b"private", IDENTITY)
        with self.assertRaises(SpillError):
            self.store.delete(receipt["record_id"],
                              SpillIdentity(MODEL, TOKENIZER, "wrong", 0))
        self.store.delete(receipt["record_id"], IDENTITY)
        self.assertEqual(self.store.records(), [])

    def test_symlink_and_traversal_rejected(self):
        if hasattr(os, "symlink"):
            link = self.temp / "link"
            try:
                link.symlink_to(self.root, target_is_directory=True)
            except OSError:
                self.skipTest("symlinks require privilege")
            with self.assertRaisesRegex(SpillError, "symlink"):
                EncryptedSpillStore(link, self.key)
        with self.assertRaises(SpillError):
            self.store.read("../escape", IDENTITY)
        with self.assertRaises(SpillError):
            SpillIdentity(MODEL, TOKENIZER, "../escape", 0)
        with self.assertRaises(SpillError):
            SpillIdentity(MODEL, TOKENIZER, "valid", True)

    def test_replaced_store_directory_fails_closed(self):
        if os.name != "posix":
            self.skipTest("POSIX directory-descriptor pinning")
        receipt = self.store.put(b"private", IDENTITY)
        moved = self.temp / "moved-store"
        self.root.rename(moved)
        self.root.mkdir(mode=0o700)
        with self.assertRaisesRegex(SpillError, "identity changed"):
            self.store.read(receipt["record_id"], IDENTITY)
        self.assertEqual((moved / (receipt["record_id"] + ".bin")).is_file(), True)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_ancestor_symlink_swap_rejected(self):
        if os.name != "posix":
            self.skipTest("POSIX nofollow directory traversal")
        parent = self.temp / "anchor"
        parent.mkdir()
        root = parent / "store"
        pinned = EncryptedSpillStore(root, self.key)
        receipt = pinned.put(b"private", IDENTITY)
        renamed = self.temp / "renamed-anchor"
        parent.rename(renamed)
        parent.symlink_to(renamed, target_is_directory=True)
        with self.assertRaisesRegex(SpillError, "symlinked or unsafe"):
            pinned.read(receipt["record_id"], IDENTITY)
        self.assertTrue((renamed / "store" / (receipt["record_id"] + ".bin")).is_file())

    def test_cli_round_trip_and_no_clobber(self):
        keyfile = self.temp / "key"
        keyfile.write_bytes(self.key)
        if os.name == "posix":
            keyfile.chmod(0o600)
        source = self.temp / "source"
        source.write_bytes(b"offline-cli")
        base = ["--store", str(self.root), "--key-file", str(keyfile)]
        identity = ["--model-sha256", MODEL, "--tokenizer-sha256", TOKENIZER,
                    "--context-id", "test-context", "--chunk-index", "0"]
        self.assertEqual(main(base + ["put", "--input", str(source)] + identity), 0)
        record_id = self.store.records()[0]["record_id"]
        self.assertEqual(main(base + ["verify"]), 0)
        output = self.temp / "output"
        self.assertEqual(main(base + ["get", "--id", record_id, "--output", str(output)] + identity), 0)
        self.assertEqual(output.read_bytes(), b"offline-cli")
        self.assertEqual(main(base + ["get", "--id", record_id, "--output", str(output)] + identity), 1)
        self.assertEqual(main(base + ["delete", "--id", record_id] + identity), 0)

    def test_key_file_ancestor_symlink_rejected(self):
        if os.name != "posix":
            self.skipTest("POSIX directory-descriptor traversal")
        parent = self.temp / "private-key-directory"
        parent.mkdir(mode=0o700)
        keyfile = parent / "key"
        keyfile.write_bytes(self.key)
        keyfile.chmod(0o600)
        link = self.temp / "key-directory-link"
        link.symlink_to(parent, target_is_directory=True)
        self.assertEqual(
            main(["--store", str(self.root), "--key-file", str(link / "key"), "list"]), 1
        )

    def test_insecure_key_file(self):
        if os.name != "posix":
            self.skipTest("POSIX-only permissions")
        keyfile = self.temp / "insecure"
        keyfile.write_bytes(self.key)
        keyfile.chmod(0o644)
        self.assertEqual(main(["--store", str(self.root), "--key-file", str(keyfile), "list"]), 1)


    def test_lockfile_replacement_cannot_bypass_directory_lock(self):
        if os.name != "posix":
            self.skipTest("POSIX directory flock contract")
        from threading import Event, Thread
        entered, acquired = Event(), Event()
        other = EncryptedSpillStore(self.root, self.key)

        def contender():
            entered.set()
            with other._lock():
                acquired.set()

        with self.store._lock():
            (self.root / ".lock").unlink()
            worker = Thread(target=contender, daemon=True)
            worker.start()
            self.assertTrue(entered.wait(1))
            self.assertFalse(acquired.wait(0.15), "replaced lock bypassed custody")
        self.assertTrue(acquired.wait(2), "store lock was not released")
        worker.join(timeout=2)

    def test_manifest_publication_never_clobbers_existing_record(self):
        original = self.store._new_member
        sentinel = b"independent-existing-manifest"
        targets = []

        def inject_collision(name, payload):
            original(name, payload)
            if name.startswith(".tmp-") and payload.startswith(b'{"'):
                target = self.root / (name.split("-")[1] + ".json")
                target.write_bytes(sentinel)
                targets.append(target)

        with patch.object(self.store, "_new_member", side_effect=inject_collision):
            with self.assertRaises(FileExistsError):
                self.store.put(b"no-clobber", IDENTITY)
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0].read_bytes(), sentinel)

    def test_disk_full_before_manifest_keeps_only_pruneable_orphan(self):
        import errno
        original = self.store._new_member

        def fail_manifest(name, payload):
            if name.startswith(".tmp-") and payload.startswith(b'{"'):
                raise OSError(errno.ENOSPC, "simulated disk full")
            original(name, payload)

        with patch.object(self.store, "_new_member", side_effect=fail_manifest):
            with self.assertRaises(OSError):
                self.store.put(b"interrupted", IDENTITY)
        self.assertEqual(self.store.verify(),
                         {"verified": 0, "orphan_data": 1, "temp_files": 0})
        self.assertEqual(self.store.prune_orphans()["orphan_data_removed"], 1)
        self.assertEqual(self.store.verify()["verified"], 0)

if __name__ == "__main__":
    unittest.main()
