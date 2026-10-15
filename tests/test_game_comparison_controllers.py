"""Pure controller panel/receipt tests: not physical hardware certification."""
from __future__ import annotations
import unittest
from skeleton.jeeves.game_comparison_controllers import (
    controller_layout_for_target,supported_controller_layout_catalog
)
from skeleton.jeeves.game_emulator_host import _ACTIONS

class ControllerLayoutContractTests(unittest.TestCase):
    def test_catalog_one_panel_per_target(self):
        result=supported_controller_layout_catalog()
        self.assertGreaterEqual(result["target_count"],100)
        self.assertEqual(result["target_count"],len(result["targets"]))
        self.assertEqual(len({x["target_id"] for x in result["targets"]}),result["target_count"])
        self.assertEqual(result["real_controller_compatibility_verified"],0)

    def test_nes_retropad_masks_and_below_view(self):
        row=controller_layout_for_target("nes",["joypad"])
        self.assertEqual(row["mapping_kind"],"libretro_retropad_semantic_overlay_below_game_screen")
        self.assertFalse(row["physical_layout_certified"])
        a=next(x for x in row["ports"][0]["controls"] if x["id"]=="a")
        self.assertEqual(a["mask"],_ACTIONS["a"])
        self.assertGreater(a["x"],0)
        self.assertEqual(len(row["ports"]),4)
        self.assertEqual(row["ports"][1]["device"],"none")

    def test_multi_type_ports(self):
        row=controller_layout_for_target("ps1",["analog","keyboard","mouse","pointer"])
        self.assertEqual([x["device"] for x in row["ports"]],
                         ["analog","keyboard","mouse","pointer"])
        self.assertEqual(len(row["ports"][0]["analog_axes"]),4)
        self.assertEqual(next(x for x in row["ports"][1]["controls"] if x["id"]=="key_enter")["key_code"],13)
        self.assertEqual(row["ports"][3]["controls"][0]["pointer_index"],2)

    def test_unsupported_hardware_rejected(self):
        with self.assertRaises(ValueError):
            controller_layout_for_target("hardware_that_does_not_exist")

if __name__=="__main__":
    unittest.main()
