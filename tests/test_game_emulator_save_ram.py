"""Synthetic ABI byte-copy contracts for libretro save-RAM handling.

Uses real ctypes memory buffers and fake core methods, never runs a ROM/core.
Host contract checks exact SHA, firmware, registry and media lineage.
"""
from __future__ import annotations

import ctypes as C
import hashlib
import threading
import unittest
from types import SimpleNamespace

from skeleton.jeeves.game_emulator_host import EmulatorEnvironment, EmulatorHostError
from skeleton.jeeves.game_emulator_worker import MAX_SAVE_RAM, NativeCore


class FakeMemoryCore:
    def __init__(self, data=b"initial-user-save"):
        self.region = C.create_string_buffer(data, len(data))
        self.size = len(data)
    def retro_get_memory_size(self, region):
        return self.size if region == 0 else 0
    def retro_get_memory_data(self, region):
        return C.addressof(self.region) if region == 0 else 0


def worker(data=b"initial-user-save"):
    obj = NativeCore.__new__(NativeCore)
    obj.core = FakeMemoryCore(data)
    obj.error = None
    obj.shutdown = False
    return obj


def empty_host(data=b"initial-user-save"):
    obj = EmulatorEnvironment.__new__(EmulatorEnvironment)
    obj._lock = threading.RLock()
    obj._seed, obj._steps = None, 0
    obj._save_ram_imported = False
    obj.core = SimpleNamespace(core_id="pinned_core", library_sha256="a" * 64)
    obj._descriptor = {
        "content_digest": "b" * 64, "firmware_digest": "c" * 64,
        "registry_digest": "d" * 64,
    }
    obj.spec = SimpleNamespace(environment_digest="e" * 64)
    obj.close = lambda: None
    obj.native = worker(data)
    obj._exchange = lambda operation, payload, blocks=None: obj.native.command(
        operation, payload, {} if blocks is None else blocks
    )
    return obj


class NativeSaveRamWorkerContracts(unittest.TestCase):
    def test_export_returns_exact_bytes_and_hash(self):
        obj = worker()
        meta, blocks = obj.command("save_ram_export", {}, {})
        self.assertEqual(blocks["save_ram"], b"initial-user-save")
        self.assertEqual(meta["size"], 17)
        self.assertEqual(meta["memory_region"], 0)
        self.assertEqual(meta["sha256"], hashlib.sha256(blocks["save_ram"]).hexdigest())

    def test_exact_matching_import_roundtrip(self):
        obj = worker(b"abcdefghijklmnop")
        payload = b"another-save-ram!"
        sha = hashlib.sha256(payload).hexdigest()
        # A region must not be expanded or shortened silently.
        with self.assertRaisesRegex(ValueError, "native_save_ram_exact_size_mismatch"):
            obj.command("save_ram_import",
                        {"memory_region": 0, "size": len(payload), "sha256": sha},
                        {"save_ram": payload})
        data = b"replacement-1234"  # 16 bytes
        self.assertEqual(len(data), 16)
        meta, _ = obj.command(
            "save_ram_import", {
                "memory_region": 0, "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }, {"save_ram": data})
        self.assertTrue(meta["readback_verified"])
        _, blocks = obj.command("save_ram_export", {}, {})
        self.assertEqual(blocks["save_ram"], data)

    def test_tampered_buffer_cannot_write(self):
        obj = worker(b"x" * 16)
        with self.assertRaisesRegex(ValueError, "native_save_ram_source_corrupt"):
            obj.command("save_ram_import", {
                "memory_region": 0, "size": 16,
                "sha256": hashlib.sha256(b"a" * 16).hexdigest(),
            }, {"save_ram": b"b" * 16})
        self.assertEqual(obj.command("save_ram_export", {}, {})[1]["save_ram"], b"x" * 16)

    def test_unauthorized_region_is_rejected(self):
        obj = worker(b"x" * 16)
        with self.assertRaisesRegex(ValueError, "native_save_ram_region_forbidden"):
            obj.command("save_ram_import", {
                "memory_region": 1, "size": 16,
                "sha256": hashlib.sha256(b"x" * 16).hexdigest(),
            }, {"save_ram": b"x" * 16})

    def test_missing_save_memory_is_honestly_unavailable(self):
        obj = worker(b"x" * 16)
        obj.core.size = 0
        with self.assertRaisesRegex(ValueError, "native_save_ram_unavailable_or_oversized"):
            obj.command("save_ram_export", {}, {})

    def test_abnormally_large_region_rejected_before_reading_pointer(self):
        obj = worker(b"x")
        obj.core.size = MAX_SAVE_RAM + 1
        with self.assertRaisesRegex(ValueError, "native_save_ram_unavailable_or_oversized"):
            obj.command("save_ram_export", {}, {})

    def test_export_requires_no_arguments_or_media_blocks(self):
        obj = worker()
        with self.assertRaises(ValueError):
            obj.command("save_ram_export", {"path": "/private/save.srm"}, {})


class NativeSaveRamHostContracts(unittest.TestCase):
    def test_host_checkpoint_and_fresh_instance_byte_match(self):
        original = empty_host(b"x" * 16)
        checkpoint, data = original.export_save_ram()
        resumed = empty_host(b"0" * 16)
        old_digest = resumed.spec.environment_digest
        imported = resumed.import_save_ram(checkpoint, data)
        self.assertTrue(imported["native_ram_write_verified"])
        self.assertNotEqual(resumed.spec.environment_digest, old_digest)
        after, data_after = resumed.export_save_ram()
        self.assertEqual(data_after, data)
        self.assertEqual(after["save_ram_sha256"], checkpoint["save_ram_sha256"])

    def test_core_mismatch_rejected_without_memory_write(self):
        source = empty_host(b"a" * 16)
        meta, raw = source.export_save_ram()
        target = empty_host(b"x" * 16)
        target.core = SimpleNamespace(core_id="different_core", library_sha256="a" * 64)
        with self.assertRaisesRegex(EmulatorHostError, "different source, core or firmware"):
            target.import_save_ram(meta, raw)
        self.assertEqual(target.native.command("save_ram_export", {}, {})[1]["save_ram"], b"x" * 16)

    def test_media_firmware_registry_mismatch_all_rejected(self):
        original = empty_host(b"z" * 16)
        meta, raw = original.export_save_ram()
        for attr in ("content_digest", "firmware_digest", "registry_digest"):
            target = empty_host(b"x" * 16)
            target._descriptor[attr] = "f" * 64
            with self.subTest(attr=attr), self.assertRaises(EmulatorHostError):
                target.import_save_ram(meta, raw)
            self.assertFalse(target._save_ram_imported)

    def test_checkpoint_hash_and_bytes_reject_tampering(self):
        source = empty_host(b"b" * 16)
        meta, raw = source.export_save_ram()
        changed = dict(meta)
        changed["save_ram_sha256"] = "0" * 64
        with self.assertRaises(EmulatorHostError):
            empty_host(b"x" * 16).import_save_ram(changed, raw)
        with self.assertRaises(EmulatorHostError):
            empty_host(b"x" * 16).import_save_ram(meta, b"y" * 16)

    def test_import_only_once_and_before_reset(self):
        source = empty_host(b"b" * 16)
        meta, raw = source.export_save_ram()
        target = empty_host(b"x" * 16)
        target.import_save_ram(meta, raw)
        with self.assertRaisesRegex(EmulatorHostError, "Only one"):
            target.import_save_ram(meta, raw)
        another = empty_host(b"x" * 16)
        another._seed = 123
        with self.assertRaisesRegex(EmulatorHostError, "Only one"):
            another.import_save_ram(meta, raw)

    def test_core_claims_do_not_certify_game_save_compatibility(self):
        env = empty_host(b"x" * 16)
        checkpoint, _ = env.export_save_ram()
        self.assertFalse(checkpoint["hardware_save_fidelity_verified"])
        self.assertFalse(checkpoint["model_weights_updated"])


if __name__ == "__main__":
    unittest.main()
