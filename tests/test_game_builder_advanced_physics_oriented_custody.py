"""Source-ID custody for real oriented SAT and temporally swept collider impacts."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_physics_runtime import start,default_layout
from skeleton.ai.game_builder.advanced_physics_oriented import oriented_static
from skeleton.ai.game_builder.advanced_physics_rotational_sweep import swept_fixtures
from skeleton.ai.game_builder.advanced_physics_contact_custody import (
    record_fixture_contact,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    AdvancedRuntimeError,run_advanced_session,verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.system_editors import make_editor_document


class OriginalOrientedFixtureIDTests(unittest.TestCase):
    @staticmethod
    def config(**overrides):
        return make_editor_document("physics",{
            "collision_geometry":"oriented_box","gravity":0,
            "air_drag":0,**overrides,
        })["settings"]

    @classmethod
    def sample(cls, **overrides):
        cfg=cls.config(**overrides)
        state=start(cfg,0)
        state["fixtures"]=[]
        state["fixture_contact_counts"]=[]
        state["fixture_contact_events"]=[]
        return cfg,state

    def test_discrete_sat_contact_attributes_real_source_fixture_index(self):
        cfg,state=self.sample()
        body=state["bodies"][0]
        body["position"]=[300,600,0]
        body["orientation"]=45000
        state["fixtures"]=[
            {"position":[300,600,0],"half_size":[20,20,40],
             "orientation":0,"layer":3},
            {"position":[900,600,0],"half_size":[20,20,40],
             "orientation":0,"layer":3},
        ]
        state["fixture_contact_counts"]=[0,0]
        events=[]
        oriented_static(body,state,cfg,events)
        self.assertEqual(state["fixture_contact_counts"][0],1)
        self.assertEqual(state["fixture_contact_counts"][1],0)
        receipt=state["fixture_contact_events"][0]
        self.assertEqual(receipt["fixture_index"],0)
        self.assertEqual(receipt["body_id"],"payload")
        self.assertEqual(receipt["kind"],"oriented_fixture")
        self.assertIn("oriented_fixture_manifold_resolved",events)

    def test_non_colliding_layers_and_world_boundaries_are_not_fixture_hits(self):
        cfg,state=self.sample()
        body=state["bodies"][0]
        body["position"]=[300,600,0]
        body["mask"]=1
        state["fixtures"]=[{"position":[300,600,0],
                            "half_size":[20,20,40],
                            "orientation":0,"layer":2}]
        state["fixture_contact_counts"]=[0]
        events=[]
        oriented_static(body,state,cfg,events)
        self.assertEqual(state["fixture_contact_counts"],[0])
        self.assertEqual(state["fixture_contact_events"],[])
        self.assertNotIn("oriented_fixture_manifold_resolved",events)

    def test_temporal_rotation_source_fixture_id_not_end_position_guess(self):
        cfg,state=self.sample()
        body=state["bodies"][0]
        body["position"]=[300,600,0]
        body["shape_half"]=[40,10]
        body["orientation"]=90000
        state["fixtures"]=[
            {"position":[300,640,0],"half_size":[25,10,40],
             "orientation":0,"layer":3},
            {"position":[800,640,0],"half_size":[25,10,40],
             "orientation":0,"layer":3},
        ]
        state["fixture_contact_counts"]=[0,0]
        events=[]
        self.assertTrue(swept_fixtures(
            body,state,cfg,[300,600,0],0,[0,1],events))
        self.assertEqual(state["fixture_contact_counts"],[1,0])
        self.assertEqual(state["fixture_contact_events"][0]["fixture_index"],0)
        self.assertEqual(state["fixture_contact_events"][0]["kind"],
                         "rotating_swept_fixture")
        self.assertIn("oriented_rotating_swept_fixture_manifold_resolved",events)

    def test_swept_collision_with_wrong_mask_cannot_fabricate_source(self):
        cfg,state=self.sample()
        body=state["bodies"][0]
        body["shape_half"]=[40,10]
        body["position"]=[300,600,0]
        body["orientation"]=90000
        body["mask"]=1
        state["fixtures"]=[{"position":[300,640,0],
                            "half_size":[25,10,40],
                            "orientation":0,"layer":2}]
        state["fixture_contact_counts"]=[0]
        # Candidate discovery is responsible for excluding masked fixtures;
        # direct swept calls accept caller-supplied indices, so exercise the
        # actual audited solver instead of bypassing that admission gate.
        from skeleton.ai.game_builder.advanced_physics_rotational_sweep import candidates
        pairs,fixtures=candidates(state,{"payload":[300,600,0],
                            "counterweight":state["bodies"][1]["position"][:]},cfg)
        self.assertEqual(fixtures,())
        self.assertEqual(state["fixture_contact_counts"],[0])

    def test_complete_bounded_fixture_history_keeps_global_counts(self):
        _,state=self.sample()
        body=state["bodies"][0]
        state["fixtures"]=[{"position":[300,640,0],
                            "half_size":[20,20,40],
                            "orientation":0,"layer":3}]
        state["fixture_contact_counts"]=[0]
        for _ in range(100):
            record_fixture_contact(state,body,0,"oriented_fixture")
        self.assertEqual(state["fixture_contact_counts"],[100])
        self.assertEqual(len(state["fixture_contact_events"]),96)
        self.assertEqual(state["fixture_contact_events"][0]["fixture_index"],0)

    def test_fixture_receipt_disallows_nonauthed_index_or_kind(self):
        _,state=self.sample()
        state["fixtures"]=[{"position":[300,640,0],
                            "half_size":[20,20,40],
                            "orientation":0,"layer":3}]
        state["fixture_contact_counts"]=[0]
        body=state["bodies"][0]
        for index,kind in ((3,"oriented_fixture"),(-1,"oriented_fixture"),
                           (True,"oriented_fixture"),(0,"world_collision"),
                           (0,"rotating_dynamic")):
            with self.assertRaises(ValueError):
                record_fixture_contact(state,body,index,kind)
        self.assertEqual(state["fixture_contact_counts"],[0])

    def test_signed_oriented_source_scene_and_full_canonical_replay(self):
        settings={"collision_geometry":"oriented_box","gravity":0,
                  "air_drag":0,"impulse_strength":500,"speed_limit":400}
        cfg=make_editor_document("physics",settings)["settings"]
        scene_layout=default_layout(cfg,1)
        scene_layout["fixtures"]=[{"position":[430,900,0],
                                  "half_size":[10,100,40],
                                  "orientation":0,"layer":3}]
        scene=make_advanced_scene("physics",settings,seed=1,layout=scene_layout)
        game=run_advanced_session("physics",settings,
             ("push:east","push:east"),seed=1,scene=scene)
        self.assertTrue(verify_advanced_session(game,settings))
        self.assertEqual(len(game["state"]["fixture_contact_counts"]),1)
        self.assertGreater(game["state"]["fixture_contact_counts"][0],0)
        self.assertEqual(sum(game["state"]["fixture_contact_counts"]),
                         len(game["state"]["fixture_contact_events"]))
        self.assertTrue(all(e["fixture_index"]==0
                            for e in game["state"]["fixture_contact_events"]))

    def test_forged_oriented_source_id_and_contact_kind_fail_replay(self):
        settings={"collision_geometry":"oriented_box","gravity":0,
                  "air_drag":0,"impulse_strength":500,"speed_limit":400}
        cfg=make_editor_document("physics",settings)["settings"]
        layout=default_layout(cfg,1)
        layout["fixtures"]=[{"position":[430,900,0],
                             "half_size":[10,100,40],
                             "orientation":0,"layer":3}]
        scene=make_advanced_scene("physics",settings,seed=1,layout=layout)
        good=run_advanced_session("physics",settings,
             ("push:east","push:east"),seed=1,scene=scene)
        self.assertTrue(good["state"]["fixture_contact_events"])
        for kind in ("index","kind","count"):
            forged=deepcopy(good)
            state=forged["state"]
            if kind=="index":
                state["fixture_contact_events"][0]["fixture_index"]=99
            elif kind=="kind":
                state["fixture_contact_events"][0]["kind"]="client_fake"
            else:
                state["fixture_contact_counts"][0]=123
            with self.assertRaises(AdvancedRuntimeError):
                verify_advanced_session(forged,settings)


if __name__=="__main__":
    unittest.main()
