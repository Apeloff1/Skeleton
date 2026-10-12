"""Actual original fixture-ID collision custody for source-to-NPC evidence."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_physics_runtime import default_layout
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    AdvancedRuntimeError,run_advanced_session,verify_advanced_session,
)
from skeleton.ai.game_builder.system_editors import make_editor_document
from skeleton.ai.game_builder.advanced_physics_interop import (
    rehearse_physics_encounter,verify_physics_encounter,
)


class ActualFixtureContactCustodyTests(unittest.TestCase):
    @staticmethod
    def original(*,mask=1,second=False):
        settings={"dimension":"2d","max_bodies":1,"collision_geometry":"aabb",
                  "gravity":0,"air_drag":0,"speed_limit":400,
                  "impulse_strength":500,"wall_restitution":0}
        cfg=make_editor_document("physics",settings)["settings"]
        layout=default_layout(cfg,2)
        layout["fixtures"]=[{"position":[430,900,0],
                             "half_size":[10,100,40],"layer":3}]
        if second:
            layout["fixtures"].append({
                "position":[1200,900,0],"half_size":[10,100,40],"layer":3})
        layout["bodies"][0]["mask"]=mask
        scene=make_advanced_scene("physics",settings,seed=2,layout=layout)
        report=run_advanced_session("physics",settings,
                       ("push:east","push:east"),seed=2,scene=scene)
        assert verify_advanced_session(report,settings)
        return report,settings

    def test_real_source_fixture_index_and_physical_body_receipts(self):
        session,settings=self.original()
        physical=session["state"]
        self.assertGreater(physical["contacts"],0)
        self.assertEqual(len(physical["fixture_contact_counts"]),1)
        self.assertGreater(physical["fixture_contact_counts"][0],0)
        self.assertEqual(sum(physical["fixture_contact_counts"]),
                         sum(event in ("fixture_contact","swept_fixture_contact")
                             for frame in session["trace"] for event in frame["events"]))
        self.assertTrue(physical["fixture_contact_events"])
        for item in physical["fixture_contact_events"]:
            self.assertEqual(item["fixture_index"],0)
            self.assertEqual(item["body_id"],"payload")
            self.assertIn(item["kind"],("swept_fixture_contact","fixture_contact"))
            self.assertEqual(len(item["position"]),3)

    def test_multiple_authored_fixtures_preserve_each_index_with_no_guessed_hits(self):
        session,_=self.original(second=True)
        state=session["state"]
        self.assertEqual(len(state["fixture_contact_counts"]),2)
        self.assertGreater(state["fixture_contact_counts"][0],0)
        self.assertEqual(state["fixture_contact_counts"][1],0)
        self.assertTrue(all(x["fixture_index"]==0 for x in
                            state["fixture_contact_events"]))

    def test_unmasked_original_solid_has_no_contact_receipt(self):
        settings={"dimension":"2d","max_bodies":1,"collision_geometry":"aabb",
                  "gravity":0,"air_drag":0,"speed_limit":400,
                  "impulse_strength":500,"wall_restitution":0}
        cfg=make_editor_document("physics",settings)["settings"]
        layout=default_layout(cfg,3)
        layout["fixtures"]=[{"position":[430,900,0],
                             "half_size":[10,100,40],"layer":2}]
        layout["bodies"][0]["mask"]=1
        scene=make_advanced_scene("physics",settings,seed=3,layout=layout)
        record=run_advanced_session("physics",settings,
                   ("push:east","push:east"),seed=3,scene=scene)
        self.assertEqual(record["state"]["fixture_contact_counts"],[0])
        self.assertEqual(record["state"]["fixture_contact_events"],[])
        self.assertTrue(verify_advanced_session(record,settings))

    def test_no_original_fixture_means_empty_canonical_receipts(self):
        report,settings=self.original()
        empty=deepcopy(report["scene"]["layout"])
        empty["fixtures"]=[]
        scene=make_advanced_scene("physics",settings,seed=2,layout=empty)
        cleared=run_advanced_session("physics",settings,
                       ("inspect",),seed=2,scene=scene)
        self.assertEqual(cleared["state"]["fixture_contact_counts"],[])
        self.assertEqual(cleared["state"]["fixture_contact_events"],[])
        self.assertTrue(verify_advanced_session(cleared,settings))

    def test_fixture_receipt_forgery_denied_by_full_replay(self):
        good,settings=self.original()
        for change in (
            lambda result:result["state"]["fixture_contact_counts"].__setitem__(0,999),
            lambda result:result["state"]["fixture_contact_events"][0].update(
                fixture_index=999),
            lambda result:result["state"]["fixture_contact_events"][0].update(
                body_id="phantom"),
            lambda result:result["state"]["fixture_contact_events"].clear(),
        ):
            modified=deepcopy(good)
            change(modified)
            with self.assertRaises(AdvancedRuntimeError):
                verify_advanced_session(modified,settings)

    def test_physics_interop_proof_records_source_object_and_hit_index(self):
        world=make_advanced_scene("racing",seed=1)
        racing=run_advanced_session("racing",scene=world,seed=1)
        proof=rehearse_physics_encounter(racing)
        self.assertTrue(proof["source_fixture_impacts"])
        physical=proof["physics_session"]["state"]
        self.assertEqual(
            sum(hit["impacts"] for hit in proof["source_fixture_impacts"]),
            proof["observed_fixture_impacts"])
        self.assertEqual(physical["fixture_contact_counts"][0],
                         proof["source_fixture_impacts"][0]["impacts"])
        self.assertTrue(verify_physics_encounter(proof,racing))
        forged=deepcopy(proof)
        forged["source_fixture_impacts"][0]["source_id"]=999
        from skeleton.ai.game_builder.advanced_physics_interop import PhysicsInteropError
        with self.assertRaises(PhysicsInteropError):
            verify_physics_encounter(forged,racing)


if __name__=="__main__":
    unittest.main()
