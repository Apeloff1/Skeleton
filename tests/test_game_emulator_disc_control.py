"""Libretro multi-disc ABI and host receipts, with fake native callbacks.

No ROM, proprietary BIOS, actual emulator core or native source used. The
callback fixture exercises ABI pointer shape, strict transaction order, and
failure paths. It is NOT proof that any PSX/Saturn/Dreamcast game boots.
"""
from __future__ import annotations

import ctypes as C
import threading
import unittest
from types import SimpleNamespace

from skeleton.jeeves.game_emulator_host import (
    EmulatorEnvironment, EmulatorHostError,
)
from skeleton.jeeves.game_emulator_worker import (
    DiskControlCallbacks, NativeCore,
)

SET_EJECT = C.CFUNCTYPE(C.c_bool, C.c_bool)
GET_EJECT = C.CFUNCTYPE(C.c_bool)
GET_INDEX = C.CFUNCTYPE(C.c_uint)
SET_INDEX = C.CFUNCTYPE(C.c_bool, C.c_uint)
GET_COUNT = C.CFUNCTYPE(C.c_uint)


class FakeDisc:
    def __init__(self, *, count=3, refuse_eject=False, refuse_select=False, sentinel_during_eject=False):
        self.count, self.index, self.ejected = count, 0, False
        self.calls = []
        self.refuse_eject, self.refuse_select = refuse_eject, refuse_select
        self.sentinel_during_eject = sentinel_during_eject
        def eject(value):
            self.calls.append(("eject", bool(value)))
            if value and self.refuse_eject:
                return False
            self.ejected = bool(value)
            return True
        def get_eject():
            return self.ejected
        def get_index():
            return 0xFFFFFFFF if self.ejected and self.sentinel_during_eject else self.index
        def select(index):
            self.calls.append(("select", index))
            if not self.ejected or self.refuse_select or index >= self.count:
                return False
            self.index = index
            return True
        def get_count():
            return self.count
        self.callbacks = [
            SET_EJECT(eject), GET_EJECT(get_eject), GET_INDEX(get_index),
            SET_INDEX(select), GET_COUNT(get_count),
        ]
        self.table = DiskControlCallbacks(
            *(C.cast(callback, C.c_void_p).value for callback in self.callbacks),
            None, None,
        )
        self.core = NativeCore.__new__(NativeCore)
        self.core.disk_callbacks = None
        self.core.disk_interface_version = None
        self.core.error = None
        self.core.shutdown = False

    def register(self, version=1):
        cmd = 58 if version else 13
        return self.core._environment(cmd, C.addressof(self.table))


class NativeDiskControlAbiContracts(unittest.TestCase):
    def test_v1_abi_negotiation_and_exact_eject_select_insert(self):
        core = FakeDisc()
        version = C.c_uint(999)
        self.assertTrue(core.core._environment(57, C.addressof(version)))
        self.assertEqual(version.value, 1)
        self.assertTrue(core.register(version=1))
        self.assertEqual(core.core.disk_status()["image_count"], 3)
        result = core.core.swap_disc(2)
        self.assertEqual(result["image_index"], 2)
        self.assertEqual(result["previous_image_index"], 0)
        self.assertFalse(result["ejected"])
        self.assertTrue(result["changed"])
        self.assertEqual(core.calls, [("eject", True), ("select", 2), ("eject", False)])

    def test_ejected_tray_can_report_uint_max_without_losing_actual_selection(self):
        fixture = FakeDisc(sentinel_during_eject=True)
        fixture.register()
        self.assertEqual(fixture.core.swap_disc(2)["image_index"], 2)
        self.assertFalse(fixture.ejected)
        self.assertEqual(fixture.calls, [
            ("eject", True), ("select", 2), ("eject", False),
        ])

    def test_legacy_v0_callback_is_supported(self):
        fixture = FakeDisc(count=2)
        self.assertTrue(fixture.register(version=0))
        self.assertEqual(fixture.core.disk_status()["interface_version"], 0)
        self.assertEqual(fixture.core.swap_disc(1)["image_index"], 1)

    def test_same_disc_has_no_side_effects(self):
        fixture = FakeDisc()
        fixture.register()
        result = fixture.core.swap_disc(0)
        self.assertFalse(result["changed"])
        self.assertEqual(fixture.calls, [])

    def test_no_registration_or_empty_registration_is_not_multidisc(self):
        fixture = FakeDisc(count=0)
        self.assertFalse(fixture.core.disk_status()["supported"])
        fixture.register()
        self.assertFalse(fixture.core.disk_status()["supported"])
        with self.assertRaisesRegex(ValueError, "native_multiple_discs_unavailable"):
            fixture.core.swap_disc(0)

    def test_unregistered_index_and_eject_failure_are_hard_errors(self):
        fixture = FakeDisc(count=2)
        fixture.register()
        with self.assertRaises(ValueError):
            fixture.core.swap_disc(8)
        self.assertFalse(fixture.ejected)
        failing = FakeDisc(refuse_eject=True)
        failing.register()
        with self.assertRaisesRegex(ValueError, "native_disc_eject_rejected"):
            failing.core.swap_disc(1)
        self.assertEqual(failing.index, 0)

    def test_partial_selection_failure_is_never_reported_as_success(self):
        fixture = FakeDisc(refuse_select=True)
        fixture.register()
        with self.assertRaisesRegex(ValueError, "native_disc_select_rejected"):
            fixture.core.swap_disc(1)
        self.assertTrue(fixture.ejected)
        self.assertEqual(fixture.index, 0)

    def test_core_can_unregister_disk_callback(self):
        fixture = FakeDisc()
        fixture.register()
        self.assertTrue(fixture.core._environment(13, 0))
        self.assertFalse(fixture.core.disk_status()["supported"])

    def test_unbounded_native_disk_count_rejected(self):
        fixture = FakeDisc(count=64)
        fixture.register()
        with self.assertRaisesRegex(ValueError, "native_disk_count_outside_bound"):
            fixture.core.disk_status()


class NativeDiskHostContracts(unittest.TestCase):
    @staticmethod
    def host():
        env = EmulatorEnvironment.__new__(EmulatorEnvironment)
        env._lock = threading.RLock()
        env._seed, env._steps, env.max_steps = 7, 1, 20
        env._disc_chain = "0" * 64
        env._disc_receipts = []
        env._disc_sequence = 0
        env._chain = "9" * 64
        env._descriptor = {"content_digest": "3" * 64}
        env.core = SimpleNamespace(library_sha256="4" * 64)
        env.spec = SimpleNamespace(environment_digest="5" * 64)
        env._fake_disc = {
            "supported": True, "interface_version": 1,
            "image_count": 3, "image_index": 0, "ejected": False,
        }
        env.closed_by_error = False
        env.close = lambda: setattr(env, "closed_by_error", True)
        def exchange(op, payload):
            if op == "disc_status":
                return dict(env._fake_disc), {}
            if op == "disc_swap":
                before = env._fake_disc["image_index"]
                env._fake_disc["image_index"] = payload["image_index"]
                return {**env._fake_disc, "previous_image_index": before, "changed": True}, {}
            raise AssertionError("Unexpected mocked native operation")
        env._exchange = exchange
        return env

    def test_swap_emits_chained_media_but_not_fake_frame(self):
        env = self.host()
        result = env.swap_disc(1)
        self.assertTrue(result["changed"])
        self.assertFalse(result["native_emulation_advanced"])
        self.assertEqual(result["receipt"]["selected_image_index"], 1)
        self.assertFalse(result["receipt"]["rendered_frame_after_swap"])
        self.assertEqual(env.disc_receipts()["receipts"][0]["receipt_sha256"],
                         result["event_chain_sha256"])
        self.assertEqual(env.disc_status()["image_index"], 1)

    def test_repeated_selection_is_noop_and_no_extra_receipt(self):
        env = self.host()
        env.swap_disc(1)
        second = env.swap_disc(1)
        self.assertFalse(second["changed"])
        self.assertEqual(len(env._disc_receipts), 1)

    def test_invalid_selection_rejected_without_mutation(self):
        env = self.host()
        with self.assertRaises(EmulatorHostError):
            env.swap_disc(10)
        self.assertEqual(env._fake_disc["image_index"], 0)
        self.assertEqual(env._disc_sequence, 0)

    def test_savestate_wrong_disc_chain_rejected_before_native_restore(self):
        env = self.host()
        fields = {
            "schema_version": "skeleton.libretro_environment.v1",
            "environment_digest": "5" * 64,
            "seed": 7, "steps": 1, "controls": [], "observation": {},
            "transition_digest": "9" * 64,
            "lifetime_audio_frames": 0, "audio_generation": 0,
            "state_sha256": "1" * 64, "state_size": 1,
            "state_base64": "AA==", "frame": {},
            "pixels_base64": "", "snapshot_digest": "1" * 64,
            "disc_context": {
                "status": dict(env._fake_disc),
                "disc_event_chain_sha256": "f" * 64,
            },
        }
        with self.assertRaisesRegex(EmulatorHostError, "Savestate and current disc provenance differ"):
            env.restore(fields)


if __name__ == "__main__":
    unittest.main()
