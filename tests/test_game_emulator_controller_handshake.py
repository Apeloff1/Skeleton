"""Core-announced libretro controller evidence, without executing native ROMs."""

from __future__ import annotations

import ctypes as C
import unittest

from skeleton.jeeves.game_emulator_host import EmulatorHostError, _native_controller_profile
from skeleton.jeeves.game_emulator_worker import (
    ControllerDescription,
    ControllerInfo,
    InputDescriptor,
    NativeCore,
)


class TestCoreControllerHandshake(unittest.TestCase):
    def _worker(self) -> NativeCore:
        worker = NativeCore.__new__(NativeCore)
        worker.controller_capabilities = None
        worker.input_descriptors = []
        worker.error = None
        return worker

    def test_native_callback_captures_real_port_options(self):
        worker = self._worker()
        legend = C.create_string_buffer(b"Standard Pad")
        rows = (ControllerDescription * 1)(
            ControllerDescription(C.addressof(legend), 1)
        )
        ports = (ControllerInfo * 2)(
            ControllerInfo(rows, 1), ControllerInfo(None, 0)
        )
        self.assertTrue(worker._environment(35, C.addressof(ports)))
        self.assertEqual(
            worker.controller_capabilities,
            [[{"device_id": 1, "description": "Standard Pad"}]],
        )

    def test_native_input_descriptors_preserve_core_labels(self):
        worker = self._worker()
        legend = C.create_string_buffer(b"Primary Fire")
        rows = (InputDescriptor * 2)(
            InputDescriptor(0, 1, 0, 8, C.addressof(legend)),
            InputDescriptor(0, 0, 0, 0, None),
        )
        self.assertTrue(worker._environment(11, C.addressof(rows)))
        self.assertEqual(worker.input_descriptors, [{
            "port": 0, "device": 1, "index": 0, "id": 8, "label": "Primary Fire"
        }])

    def test_profile_validates_exact_selected_devices_and_verdict(self):
        system_info = {
            "controller_port_devices": ["joypad", "none", "none", "none"],
            "controller_capabilities": [[{
                "device_id": 1, "description": "Standard Pad"
            }]],
            "input_descriptors": [{
                "port": 0, "device": 1, "index": 0,
                "id": 8, "label": "Primary Fire"
            }],
            "controller_routing_evidence": [
                "core_advertised", "disconnected", "disconnected", "disconnected"
            ],
        }
        profile = _native_controller_profile(
            system_info, ("joypad", "none", "none", "none")
        )
        self.assertEqual(profile["port_status"][0], "core_advertised")
        self.assertEqual(profile["core_input_descriptors"][0]["label"], "Primary Fire")
        self.assertFalse(profile["hardware_input_verified"])
        system_info["controller_routing_evidence"][0] = "not_advertised"
        with self.assertRaises(EmulatorHostError):
            _native_controller_profile(system_info, ("joypad", "none", "none", "none"))

    def test_absent_native_announcement_is_not_certified(self):
        profile = _native_controller_profile(
            {
                "controller_port_devices": ["joypad"] * 4,
                "controller_capabilities": None,
                "input_descriptors": [],
                "controller_routing_evidence": ["not_advertised"] * 4,
            },
            ("joypad",) * 4,
        )
        self.assertIsNone(profile["core_advertised_types"])
        self.assertEqual(profile["port_status"], ["not_advertised"] * 4)
        self.assertFalse(profile["hardware_input_verified"])


if __name__ == "__main__":
    unittest.main()
