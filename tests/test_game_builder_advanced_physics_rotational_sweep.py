"""Advanced rotating collision trajectories, broadphase and stable-rest behavior.

Tests prove actual physics effects, not only editor schema presence. All signed
game results are independently replayed by the canonical session verifier.
"""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_physics_rotational_sweep import (
    candidates, _samples, swept_fixtures, solve_oriented_sweep,
)
from skeleton.ai.game_builder.advanced_physics_stability import (
    has_support, is_sleeping,
)
from skeleton.ai.game_builder.advanced_physics_runtime import default_layout, start
from skeleton.ai.game_builder.advanced_level_scenes import (
    make_advanced_scene, validate_advanced_scene,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    AdvancedRuntimeError, run_advanced_session, verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_gameplay_save import (
    export_advanced_savegame, import_advanced_savegame,
)
from skeleton.ai.game_builder.system_editors import make_editor_document, SystemEditorError


class OriginalRotatingSweepTests(unittest.TestCase):
    @staticmethod
    def cfg(**kwargs):
        return make_editor_document("physics", {"collision_geometry":"oriented_box",
                                                 **kwargs})["settings"]

    @classmethod
    def authored(cls, settings=None, change=None):
        rules={"collision_geometry":"oriented_box", **(settings or {})}
        layout=default_layout(cls.cfg(**(settings or {})),0)
        if change:
            change(layout)
        return make_advanced_scene("physics",rules,layout=layout)

    @staticmethod
    def crossing(layout):
        layout["bodies"][0]["position"]=[250,900,0]
        layout["bodies"][0]["velocity"]=[260,0,0]
        layout["bodies"][0]["break_threshold"]=1000
        layout["bodies"][1]["position"]=[600,900,0]
        layout["bodies"][1]["velocity"]=[-260,0,0]
        layout["bodies"][1]["break_threshold"]=1000

    def test_new_settings_are_real_bounded_source_axes(self):
        cfg=self.cfg()
        self.assertTrue(cfg["rotating_sweep_enabled"])
        self.assertGreaterEqual(cfg["oriented_sweep_budget"],8)
        self.assertEqual(cfg["broadphase_cell_size"],240)
        for key in ("rest_speed","rest_spin","sleep_frames"):
            self.assertIn(key,cfg)
        for invalid in (
            {"oriented_sweep_budget":4096},
            {"broadphase_cell_size":0},
            {"sleep_frames":0},
            {"rotating_sweep_enabled":"yes"},
        ):
            with self.assertRaises(SystemEditorError):
                make_editor_document("physics",invalid)

    def test_fast_opposing_oriented_boxes_have_real_midframe_contact(self):
        settings={"speed_limit":350,"gravity":0,"air_drag":0}
        scene=self.authored(settings,self.crossing)
        report=run_advanced_session("physics",
            {"collision_geometry":"oriented_box",**settings},
            ("inspect",),scene=scene)
        self.assertTrue(verify_advanced_session(report,
            {"collision_geometry":"oriented_box",**settings}))
        self.assertGreater(report["state"]["rotating_swept_contacts"],0)
        self.assertIn("oriented_rotating_swept_dynamic_manifold_resolved",
                      report["state"]["events"])
        self.assertLess(report["state"]["bodies"][0]["position"][0],
                        report["state"]["bodies"][1]["position"][0])

    def test_switch_off_rotational_sweep_is_observable_policy(self):
        settings={"speed_limit":350,"gravity":0,"air_drag":0,
                  "rotating_sweep_enabled":False}
        scene=self.authored(settings,self.crossing)
        report=run_advanced_session("physics",
            {"collision_geometry":"oriented_box",**settings},
            ("inspect",),scene=scene)
        self.assertEqual(report["state"]["rotating_swept_contacts"],0)
        self.assertEqual(report["state"]["broadphase_pairs"],0)
        self.assertTrue(verify_advanced_session(report,
            {"collision_geometry":"oriented_box",**settings}))

    def test_spatial_hash_prunes_faraway_dynamic_pair_and_fixtures(self):
        cfg=self.cfg(gravity=0)
        state=start(cfg,0)
        previous={b["id"]:b["position"][:] for b in state["bodies"]}
        pairs,fixtures=candidates(state,previous,cfg)
        self.assertEqual(pairs,())
        self.assertEqual(fixtures,())
        report=run_advanced_session("physics",
            {"collision_geometry":"oriented_box","gravity":0},("inspect",))
        self.assertGreater(report["state"]["broadphase_pruned"],0)
        self.assertEqual(report["state"]["rotating_swept_contacts"],0)

    def test_spatial_hash_is_deterministic_for_repeated_and_reordered_cells(self):
        cfg=self.cfg(gravity=0)
        state=start(cfg,0)
        state["bodies"][0]["position"]=[300,900,0]
        state["bodies"][1]["position"]=[350,900,0]
        old={"payload":[250,900,0],"counterweight":[400,900,0]}
        a=candidates(state,old,cfg)
        b=candidates(state,old,cfg)
        self.assertEqual(a,b)
        self.assertEqual(a[0],((0,1),))
        self.assertEqual(len(a[0]),len(set(a[0])))

    def test_real_z_separation_prevents_invalid_3d_swept_contact(self):
        settings={"dimension":"3d","speed_limit":350,
                  "gravity":0,"air_drag":0}
        def distant(layout):
            self.crossing(layout)
            layout["bodies"][0]["position"][2]=45
            layout["bodies"][1]["position"][2]=155
        scene=self.authored(settings,distant)
        report=run_advanced_session("physics",
              {"collision_geometry":"oriented_box",**settings},
              ("inspect",),scene=scene)
        self.assertEqual(report["state"]["rotating_swept_contacts"],0)
        self.assertTrue(verify_advanced_session(report,
              {"collision_geometry":"oriented_box",**settings}))

    def test_rotation_only_sweep_catches_contact_without_translation(self):
        cfg=self.cfg(gravity=0,air_drag=0)
        state=start(cfg,0)
        body=state["bodies"][0]
        body["position"]=[300,600,0]
        body["shape_half"]=[40,10]  # Genuine thin rectangle: starts clear, rotates into contact.
        body["orientation"]=90000
        body["angular_velocity"]=12000
        state["fixtures"]=[
            {"position":[300,640,0],
             "half_size":[25,10,40],"orientation":0,"layer":3}
        ]
        events=[]
        self.assertTrue(swept_fixtures(
            body,state,cfg,[300,600,0],0,[0],events))
        self.assertGreater(state["rotating_swept_contacts"],0)
        self.assertEqual(body["position"],[300,600,0])
        self.assertLess(body["orientation"],90000)
        self.assertIn("oriented_rotating_swept_fixture_manifold_resolved",events)

    def test_signed_scene_high_speed_thin_fixture_is_not_ghosted(self):
        settings={"gravity":0,"air_drag":0,"speed_limit":400,
                  "impulse_strength":500}
        def thin(layout):
            layout["fixtures"]=[
                {"position":[430,900,0],
                 "half_size":[10,100,40],"layer":3,"orientation":0}
            ]
        scene=self.authored(settings,thin)
        original={"collision_geometry":"oriented_box",**settings}
        report=run_advanced_session("physics",original,
                 ("push:east","push:east"),scene=scene)
        self.assertTrue(verify_advanced_session(report,original))
        self.assertLess(report["state"]["bodies"][0]["position"][0],430)
        self.assertTrue(any(
            "oriented_rotating_swept_fixture_manifold_resolved" in frame["events"]
            or "oriented_fixture_manifold_resolved" in frame["events"]
            for frame in report["trace"]))

    def test_sample_budget_never_exceeds_explicit_editor_ceiling(self):
        cfg=self.cfg(oriented_sweep_budget=8,speed_limit=400)
        body=start(cfg,0)["bodies"][0]
        original=body["position"][:]
        body["position"][0]+=400
        body["orientation"]=120000
        self.assertEqual(_samples(cfg,body,original,0),8)

    def test_resting_on_ground_requires_real_supported_hull(self):
        settings={"gravity":0,"rest_speed":0,"sleep_frames":2}
        config={"collision_geometry":"oriented_box",**settings}
        report=run_advanced_session("physics",config,
               ("inspect","inspect","inspect"))
        self.assertTrue(verify_advanced_session(report,config))
        self.assertEqual(report["state"]["bodies"][0]["sleep"],2)
        self.assertEqual(report["state"]["sleeping_bodies"],1)
        self.assertEqual(report["state"]["rest_stabilizations"],1)
        self.assertEqual(report["state"]["bodies"][0]["velocity"],[0,0,0])

    def test_unfounded_midair_body_cannot_sleep_for_free(self):
        cfg=self.cfg(gravity=0,rest_speed=0,sleep_frames=1)
        state=start(cfg,0)
        state["bodies"][0]["position"]=[250,600,0]
        self.assertFalse(has_support(state["bodies"][0],state))
        self.assertFalse(is_sleeping(state["bodies"][0],state,cfg))

    def test_paid_impulse_wakes_body_and_movement_still_costs_stock(self):
        options={"collision_geometry":"oriented_box","gravity":0,
                 "rest_speed":0,"sleep_frames":2}
        report=run_advanced_session("physics",options,
               ("inspect","inspect","push:east"))
        self.assertLess(report["state"]["bodies"][0]["sleep"],2)
        self.assertLess(report["state"]["impulses_left"],30)
        self.assertGreater(report["state"]["bodies"][0]["position"][0],200)
        self.assertTrue(verify_advanced_session(report,options))

    def test_motor_power_prevents_false_sleep(self):
        settings={"collision_geometry":"oriented_box","gravity":0,
                  "rest_speed":40,"sleep_frames":1}
        report=run_advanced_session("physics",settings,
               ("fan:on","inspect"))
        self.assertEqual(report["state"]["sleeping_bodies"],0)
        self.assertGreater(report["state"]["motors_used"],0)

    def test_exhausted_motor_allows_real_supported_sleep_without_free_energy(self):
        cfg={"collision_geometry":"oriented_box","gravity":0,
             "initial_battery":1,"fan_force":0,
             "rest_speed":20,"sleep_frames":2}
        result=run_advanced_session("physics",cfg,
                      ("fan:on","inspect","inspect"))
        self.assertEqual(result["state"]["battery"],0)
        self.assertEqual(result["state"]["bodies"][0]["sleep"],2)
        self.assertEqual(result["state"]["sleeping_bodies"],1)
        self.assertTrue(verify_advanced_session(result,cfg))

    def test_collision_metrics_are_reconstructed_not_client_owned(self):
        options={"collision_geometry":"oriented_box",
                 "speed_limit":350,"gravity":0,"air_drag":0}
        scene=self.authored({k:v for k,v in options.items()
                             if k!="collision_geometry"},self.crossing)
        session=run_advanced_session("physics",options,("inspect",),scene=scene)
        save=export_advanced_savegame(session,options)
        self.assertEqual(import_advanced_savegame(save)["session"],session)
        for key in ("broadphase_pairs","rotating_swept_contacts",
                    "oriented_sat_evaluations","rest_stabilizations"):
            altered=deepcopy(session)
            altered["state"][key]=999999
            with self.assertRaises(AdvancedRuntimeError):
                verify_advanced_session(altered,options)

    def test_aabb_reference_remains_unaffected_by_rotating_pipeline(self):
        report=run_advanced_session("physics",actions=("inspect",))
        self.assertTrue(verify_advanced_session(report))
        self.assertEqual(report["state"]["broadphase_pairs"],0)
        self.assertEqual(report["state"]["rotating_swept_contacts"],0)
        self.assertEqual(report["state"]["sleeping_bodies"],0)

    def test_signed_original_layout_with_new_fields_roundtrips(self):
        original={"collision_geometry":"oriented_box",
                  "broadphase_cell_size":160,
                  "oriented_sweep_budget":12}
        scene=self.authored({k:v for k,v in original.items()
                             if k!="collision_geometry"})
        self.assertEqual(validate_advanced_scene(scene,original),scene)
        session=run_advanced_session("physics",original,
               ("inspect","torque:cw"),scene=scene)
        self.assertTrue(verify_advanced_session(session,original))


if __name__=="__main__":
    unittest.main()
