"""Actual libretro SET_INPUT_DESCRIPTORS ABI parsing and under-screen labels.

These tests use an in-memory ctypes C descriptor array, not a native game.
Core-reported labels remain unverified hardware descriptions.
"""
from __future__ import annotations

import ctypes as C
import unittest
from types import SimpleNamespace

from skeleton.jeeves.game_emulator_worker import InputDescriptor, NativeCore
from skeleton.jeeves.game_comparison_controllers import controller_layout_for_target


def descriptors(*entries):
    texts=[C.create_string_buffer(e[-1].encode("utf-8")+b"\x00") for e in entries]
    rowtype=InputDescriptor*(len(entries)+1)
    values=rowtype()
    for i,(port,device,index,key,name) in enumerate(entries):
        values[i]=InputDescriptor(port,device,index,key,C.addressof(texts[i]))
    return texts,values


class ActualLibretroInputDescriptorContracts(unittest.TestCase):
    def test_real_abi_descriptor_labels_preserve_masks(self):
        strings,values=descriptors(
            (0,1,0,8,"Jump / Confirm"),
            (0,1,0,0,"Action / Back"),
        )
        fixture=SimpleNamespace(input_descriptors=[],error=None)
        self.assertTrue(NativeCore._environment(fixture,11,C.addressof(values)))
        layout=controller_layout_for_target(
            "nes",["joypad"],core_input_descriptors=fixture.input_descriptors,
        )
        by_id={x["id"]:x for x in layout["ports"][0]["controls"]}
        self.assertEqual(by_id["a"]["legend"],"Jump / Confirm")
        self.assertEqual(by_id["a"]["mask"],256)
        self.assertEqual(by_id["b"]["legend"],"Action / Back")
        self.assertEqual(by_id["b"]["mask"],1)
        self.assertEqual(layout["core_reported_input_legend_count"],2)
        self.assertFalse(layout["physical_layout_certified"])
        self.assertFalse(layout["core_labels_independently_qualified"])

    def test_bad_core_descriptor_never_becomes_visible(self):
        strings,values=descriptors(
            (0,1,0,8,"Jump"),(0,1,0,8,"Duplicate Jump")
        )
        fixture=SimpleNamespace(input_descriptors=[],error=None)
        self.assertFalse(NativeCore._environment(fixture,11,C.addressof(values)))
        self.assertEqual(fixture.input_descriptors,[])

    def test_malformed_external_metadata_fails_closed(self):
        with self.assertRaises(ValueError):
            controller_layout_for_target(
                "nes",["joypad"],core_input_descriptors=[
                    {"port":0,"device":1,"index":0,"id":8,
                     "description":"bad\nlabel"},
                ],
            )

    def test_padded_offline_catalog_remains_generic_without_native_core(self):
        layout=controller_layout_for_target("nes",["joypad"])
        self.assertEqual(layout["core_reported_input_legend_count"],0)
        self.assertEqual(layout["ports"][0]["controls"][-1]["legend_source"],
                         "generic_or_hardware_style_label")


if __name__=="__main__":
    unittest.main()
