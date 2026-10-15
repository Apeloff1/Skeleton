"""Independent exact 2-/3-factor cubes, matched seeds and replay scrutiny."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.jeeves.game_studio_environment import make_studio_source
from skeleton.jeeves.game_studio_factorial_scrutiny import (
    FactorialScrutinyError, scrutinize_interactions, verify_factorial_receipt,
)


class FactorialScrutinyTests(unittest.TestCase):
    def setUp(self):
        self.original=make_studio_source(
            "economy",{"market_nodes":3,"goods":10},
            actions=("inspect","survey","wait","buy:1","sell:1","produce"),
        )
        original=self.original["settings"]
        self.axes=[
            {
                "id":"setting:goods","kind":"source_field","field":"goods",
                "levels":[original["goods"],original["goods"]+1],
            },
            {
                "id":"setting:trade_tax","kind":"source_field",
                "field":"trade_tax",
                "levels":[original["trade_tax"],original["trade_tax"]+1],
            },
            {
                "id":"action:buy:1","kind":"registered_action","field":None,
                "levels":[None,"buy:1"],
            },
        ]

    def test_every_eight_corner_three_way_interaction_is_replayed_twice(self):
        observed=scrutinize_interactions(
            self.original,self.axes,[1,1,1],
            seed=11,steps=3,seed_count=2,
        )
        self.assertEqual(observed["exact_cells_per_seed"],8)
        self.assertEqual(observed["source_replayed_corner_count"],16)
        self.assertEqual(observed["audited_checks_count"],160)
        self.assertEqual(observed["complete_seed_cubes"],2)
        self.assertTrue(observed["source_factorial_design_complete"])
        self.assertTrue(observed["whole_joint_variant_examined"])
        self.assertEqual(len(observed["seed_cubes"]),2)
        for cube in observed["seed_cubes"]:
            self.assertEqual([x["mask"] for x in cube["corners"]],list(range(8)))
            self.assertEqual(len(cube["main_effects"]),3)
            self.assertEqual(len(cube["interaction_effects"]),4)
            for cell in cube["corners"]:
                self.assertEqual(cell["checks_passed"],10)
                self.assertEqual(len(cell["trace_digest"]),64)
                self.assertEqual(len(cell["multispectral_audit_digest"]),64)
            self.assertEqual(cube["corners"][0]["interventions"][0]["active"],False)
            self.assertEqual(cube["corners"][-1]["interventions"][0]["active"],True)
        self.assertEqual(len(observed["sensitivity"]),7)
        self.assertTrue(verify_factorial_receipt(
            self.original,self.axes,[1,1,1],observed,steps=3,
        ))

    def test_all_four_corners_for_two_factor_subset_without_false_full_claim(self):
        output=scrutinize_interactions(
            self.original,self.axes,[1,1,1],
            selected_indices=[0,2],seed=19,steps=3,seed_count=2,
        )
        self.assertEqual(output["exact_cells_per_seed"],4)
        self.assertEqual(output["audited_checks_count"],80)
        self.assertTrue(output["source_factorial_design_complete"])
        self.assertFalse(output["whole_joint_variant_examined"])
        self.assertEqual(output["other_active_axes_not_examined"],
                         ["setting:trade_tax"])

    def test_inadmissible_cross_factor_corner_remains_inconclusive(self):
        invalid=deepcopy(self.axes)
        invalid[0]["levels"][1]=-999
        output=scrutinize_interactions(
            self.original,invalid,[1,1,0],
            selected_indices=[0,1],seed=4,steps=2,
        )
        self.assertEqual(output["complete_seed_cubes"],0)
        self.assertFalse(output["source_factorial_design_complete"])
        self.assertFalse(output["observed_joint_gain_proven"])
        self.assertTrue(output["constraint_violations"])
        self.assertIsNone(output["worst_seed_joint_return_delta"])
        self.assertTrue(verify_factorial_receipt(
            self.original,invalid,[1,1,0],output,steps=2,
        ))

    def test_stale_forged_unsupported_or_tampered_world_is_rejected(self):
        fake=deepcopy(self.axes)
        fake[0]["field"]="homebrew_only"
        with self.assertRaises(FactorialScrutinyError):
            scrutinize_interactions(
                self.original,fake,[1,1,0],
                selected_indices=[0,1],seed=10,
            )
        result=scrutinize_interactions(
            self.original,self.axes,[1,1,0],
            selected_indices=[0,1],seed=10,steps=2,
        )
        altered=deepcopy(result)
        altered["seed_cubes"][0]["corners"][1]["accepted_controls"]=9999
        with self.assertRaises(FactorialScrutinyError):
            verify_factorial_receipt(
                self.original,self.axes,[1,1,0],altered,steps=2,
            )
        with self.assertRaises(FactorialScrutinyError):
            scrutinize_interactions(
                self.original,self.axes,[1,1,1],
                seed=10,steps=30,
            )


if __name__=="__main__":
    unittest.main()
