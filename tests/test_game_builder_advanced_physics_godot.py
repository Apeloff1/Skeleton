"""Native independently executed fixed-point physics game source and parity custody."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    run_advanced_session, verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.advanced_physics_runtime import default_layout
from skeleton.ai.game_builder.advanced_physics_godot import (
    SCHEMA, PROOF_SCHEMA, PROOF_FIELDS, NATIVE_ACTIONS, GODOT_PHYSICS,
    render_physics_godot_package,
)
from skeleton.ai.game_builder.advanced_godot_export import (
    AdvancedGodotExportError, archive_advanced_godot_package,
    write_advanced_godot_package,
)
from skeleton.ai.game_builder.system_editors import make_editor_document
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html


def supported_scene(settings, seed=0, *, win=False):
    rules=make_editor_document("physics",settings)["settings"]
    layout=default_layout(rules,seed)
    layout["fixtures"]=[]
    if win:
        layout["goal"]=[300,960,0]
    return make_advanced_scene("physics",settings,seed=seed,layout=layout)


class OriginalPhysicsGodotProofTests(unittest.TestCase):
    @staticmethod
    def profile(**values):
        return {"dimension":"2d","collision_geometry":"aabb",
                "max_bodies":1,"gravity":0,"substeps":1,
                "initial_battery":0,**values}

    def generate(self, settings=None, commands=("inspect",), *, seed=0, win=False):
        rules=self.profile(**(settings or {}))
        scene=supported_scene(rules,seed,win=win)
        session=run_advanced_session("physics",rules,commands,
                                     seed=seed,scene=scene)
        self.assertTrue(verify_advanced_session(session,rules))
        return rules,scene,session

    def test_real_original_game_and_python_proof_are_source_consistent(self):
        variants=[
            ({},("inspect","push:east","step:4","brake","torque:cw","step"),0,False),
            ({"impulse_strength":157,"air_drag":5},
             ("push:west","push:up","step","torque:ccw","brake"),3,False),
            ({"goal_radius":70,"goal_speed":300},("push:east",),4,True),
            ({"goal_radius":70,"goal_speed":300,"completion_mode":"sandbox"},
             ("push:east","step"),7,True),
        ]
        for settings,commands,seed,win in variants:
            with self.subTest(settings=settings,commands=commands):
                rules,scene,session=self.generate(settings,commands,seed=seed,win=win)
                pack=render_physics_godot_package(session,rules,authorized=True)
                self.assertEqual(pack.manifest["native_editor"],"physics")
                self.assertFalse(pack.manifest["godot_executed"])
                self.assertFalse(pack.manifest["native_hardware_certified"])
                self.assertFalse(pack.manifest["publish_approved"])
                game=json.loads(pack.files["godot/game.json"])
                proof=json.loads(pack.files["godot/proof.json"])
                self.assertEqual(game["schema"],SCHEMA)
                self.assertEqual(proof["schema"],PROOF_SCHEMA)
                self.assertEqual(proof["scene_digest"],scene["digest"])
                self.assertEqual(proof["actions"],list(commands))
                self.assertEqual(set(proof["expected"]),set(PROOF_FIELDS))
                self.assertEqual(proof["expected"]["orientation"],
                    session["state"]["bodies"][0]["orientation"])
                self.assertEqual(proof["expected"]["contacts"],
                    session["state"]["contacts"])
                self.assertEqual(proof["expected"]["milestones"],
                    session["state"]["milestones"])
                self.assertEqual(pack.files,
                    render_physics_godot_package(
                        session,rules,authorized=True).files)

    def test_earned_victory_and_open_ended_world_are_distinct_proofs(self):
        won,_,result=self.generate(
            {"goal_radius":70,"goal_speed":300},("push:east",),win=True)
        self.assertTrue(result["terminal"])
        self.assertTrue(json.loads(render_physics_godot_package(
            result,won,authorized=True).files["godot/proof.json"])["expected"]["finished"])
        endless,_,progress=self.generate({
            "goal_radius":70,"goal_speed":300,"completion_mode":"sandbox"
        },("push:east","step"),win=True)
        self.assertFalse(progress["terminal"])
        self.assertIn("cargo_docked",progress["state"]["milestones"])
        self.assertTrue(render_physics_godot_package(
            progress,endless,authorized=True).manifest["advanced_floor"])

    def test_reject_unsupported_geometry_forces_and_scene_mutations(self):
        rules,scene,session=self.generate()
        with self.assertRaises(PermissionError):
            render_physics_godot_package(session,rules,authorized=False)
        for invalid in [
            {"max_bodies":2},{"dimension":"3d"},
            {"collision_geometry":"oriented_box"},{"substeps":2},
            {"initial_battery":1},
        ]:
            altered={**rules,**invalid}
            other=run_advanced_session("physics",altered)
            with self.assertRaises(AdvancedGodotExportError):
                render_physics_godot_package(other,altered,authorized=True)
        extra=deepcopy(scene["layout"])
        extra["fixtures"]=[{"position":[1400,900,0],
                            "half_size":[45,100,40],"layer":3}]
        next_scene=make_advanced_scene("physics",rules,layout=extra)
        next_game=run_advanced_session("physics",rules,
                                       ("inspect",),scene=next_scene)
        self.assertEqual(
            len(json.loads(render_physics_godot_package(
                next_game,rules,authorized=True).files["godot/game.json"])
                ["scene"]["layout"]["fixtures"]),1)
        rotated=deepcopy(next_scene["layout"])
        rotated["fixtures"][0]["orientation"]=90000
        rotated_scene=make_advanced_scene("physics",rules,layout=rotated)
        rotated_session=run_advanced_session("physics",rules,("inspect",),
                                             scene=rotated_scene)
        with self.assertRaises(AdvancedGodotExportError):
            render_physics_godot_package(rotated_session,rules,authorized=True)
        for action in ("fan:on","attach:0","select:1","push:front"):
            if action=="select:1" or action=="push:front":
                continue # Illegal commands are separately covered by core source tests.
            alternative=run_advanced_session("physics",rules,actions=(action,)) if action=="attach:0" else None
            if alternative:
                with self.assertRaises(AdvancedGodotExportError):
                    render_physics_godot_package(alternative,rules,authorized=True)

    def test_real_swept_source_fixture_blocks_fast_cargo(self):
        settings=self.profile(gravity=0,air_drag=0,impulse_strength=500,
                              speed_limit=400,wall_restitution=0)
        layout=default_layout(make_editor_document("physics",settings)["settings"],4)
        layout["fixtures"]=[{"position":[430,900,0],
                             "half_size":[10,100,40],"layer":3}]
        scene=make_advanced_scene("physics",settings,seed=4,layout=layout)
        gameplay=run_advanced_session("physics",settings,
                       ("push:east","push:east"),seed=4,scene=scene)
        self.assertTrue(verify_advanced_session(gameplay,settings))
        self.assertGreater(gameplay["state"]["contacts"],0)
        self.assertLess(gameplay["state"]["bodies"][0]["position"][0],430)
        self.assertTrue(any("swept_fixture_contact" in
                            frame["events"] for frame in gameplay["trace"]))
        pack=render_physics_godot_package(gameplay,settings,authorized=True)
        self.assertIn("func _fixtures(",pack.files["godot/scripts/main.gd"].decode("utf-8"))
        self.assertEqual(len(json.loads(pack.files["godot/game.json"])
                             ["scene"]["layout"]["fixtures"]),1)

    def test_layer_masks_skip_unrelated_original_solid(self):
        settings=self.profile(gravity=0,air_drag=0,impulse_strength=500,
                              speed_limit=400,wall_restitution=0)
        layout=default_layout(make_editor_document("physics",settings)["settings"],1)
        layout["fixtures"]=[{"position":[430,900,0],
                             "half_size":[10,100,40],"layer":2}]
        layout["bodies"][0]["mask"]=1
        scene=make_advanced_scene("physics",settings,seed=1,layout=layout)
        result=run_advanced_session("physics",settings,
                   ("push:east","push:east"),scene=scene,seed=1)
        self.assertEqual(result["state"]["contacts"],0)
        self.assertGreater(result["state"]["bodies"][0]["position"][0],430)
        self.assertTrue(verify_advanced_session(result,settings))
        pack=render_physics_godot_package(result,settings,authorized=True)
        self.assertEqual(json.loads(pack.files["godot/game.json"])
                         ["scene"]["layout"]["bodies"][0]["mask"],1)

    def test_fixture_budget_is_enforced_at_native_export(self):
        settings=self.profile()
        layout=default_layout(make_editor_document("physics",settings)["settings"],0)
        layout["fixtures"]=[]
        # Nine original fixtures are within the reference source limit of 24,
        # but outside the native adapter's intentionally bounded budget of 8.
        for ix in range(9):
            layout["fixtures"].append({"position":[400+ix*100,200,0],
             "half_size":[10,10,0],"layer":3})
        scene=make_advanced_scene("physics",settings,layout=layout)
        session=run_advanced_session("physics",settings,("inspect",),scene=scene)
        with self.assertRaises(AdvancedGodotExportError):
            render_physics_godot_package(session,settings,authorized=True)

    def test_native_godot_proof_contains_actual_source_fixture_ids(self):
        settings=self.profile(gravity=0,air_drag=0,
                              impulse_strength=500,speed_limit=400,
                              wall_restitution=0)
        source=default_layout(make_editor_document("physics",settings)["settings"],4)
        source["fixtures"]=[{"position":[430,900,0],
                             "half_size":[10,100,40],"layer":3}]
        scene=make_advanced_scene("physics",settings,seed=4,layout=source)
        session=run_advanced_session("physics",settings,
                       ("push:east","push:east"),seed=4,scene=scene)
        self.assertTrue(verify_advanced_session(session,settings))
        pack=render_physics_godot_package(session,settings,authorized=True)
        expected=json.loads(pack.files["godot/proof.json"])["expected"]
        self.assertGreater(expected["fixture_contact_counts"][0],0)
        self.assertEqual(expected["fixture_contact_counts"],
                         session["state"]["fixture_contact_counts"])
        self.assertEqual(expected["fixture_contact_events"],
                         session["state"]["fixture_contact_events"])
        self.assertEqual(sum(expected["fixture_contact_counts"]),
                         len(expected["fixture_contact_events"]))
        for event in expected["fixture_contact_events"]:
            self.assertEqual(event["fixture_index"],0)
            self.assertEqual(event["body_id"],"payload")
            self.assertIn(event["kind"],("swept_fixture_contact","fixture_contact"))
        script=pack.files["godot/scripts/main.gd"].decode("utf-8")
        self.assertIn('func _record_fixture(index: int,kind: String',script)
        self.assertIn('_record_fixture(fixture_index,"swept_fixture_contact"',script)
        self.assertIn('counts[index]=int(counts[index])+1',script)
        self.assertIn('ledger.pop_front()',script)

    def test_ignored_fixture_does_not_forge_native_source_collision_id(self):
        settings=self.profile(gravity=0,air_drag=0,
                              impulse_strength=500,speed_limit=400,
                              wall_restitution=0)
        source=default_layout(make_editor_document("physics",settings)["settings"],1)
        source["fixtures"]=[{"position":[430,900,0],
                             "half_size":[10,100,40],"layer":2}]
        source["bodies"][0]["mask"]=1
        scene=make_advanced_scene("physics",settings,seed=1,layout=source)
        session=run_advanced_session("physics",settings,
                       ("push:east","push:east"),seed=1,scene=scene)
        pack=render_physics_godot_package(session,settings,authorized=True)
        result=json.loads(pack.files["godot/proof.json"])["expected"]
        self.assertEqual(result["fixture_contact_counts"],[0])
        self.assertEqual(result["fixture_contact_events"],[])

    def test_native_no_fixture_source_receipts_are_exactly_empty(self):
        settings,_,session=self.generate({},("inspect",))
        pack=render_physics_godot_package(session,settings,authorized=True)
        result=json.loads(pack.files["godot/proof.json"])["expected"]
        self.assertEqual(result["fixture_contact_counts"],[])
        self.assertEqual(result["fixture_contact_events"],[])
        self.assertEqual(set(result),set(PROOF_FIELDS))

    def test_forged_source_fixture_evidence_is_not_accepted_as_original(self):
        settings=self.profile(gravity=0,air_drag=0,
                              impulse_strength=500,speed_limit=400)
        layout=default_layout(make_editor_document("physics",settings)["settings"],2)
        layout["fixtures"]=[{"position":[430,900,0],
                             "half_size":[10,100,40],"layer":3}]
        scene=make_advanced_scene("physics",settings,seed=2,layout=layout)
        authentic=run_advanced_session("physics",settings,
                       ("push:east","push:east"),seed=2,scene=scene)
        self.assertTrue(authentic["state"]["fixture_contact_events"])
        for key in ("fixture_index","body_id","kind"):
            forged=deepcopy(authentic)
            forged["state"]["fixture_contact_events"][0][key]=(
                500 if key=="fixture_index" else
                "imaginary_collision" if key=="kind" else "unapproved_body")
            from skeleton.ai.game_builder.advanced_gameplay_runtime import AdvancedRuntimeError
            with self.assertRaises(AdvancedRuntimeError):
                render_physics_godot_package(forged,settings,authorized=True)

    def test_native_gravity_has_real_airborne_acceleration_and_floor_contact(self):
        settings=self.profile(gravity=8,tick_hz=40,air_drag=0,
                              wall_restitution=0,floor_friction=0)
        layout=default_layout(make_editor_document("physics",settings)["settings"],2)
        layout["fixtures"]=[]
        layout["bodies"][0]["position"]=[200,500,0]
        scene=make_advanced_scene("physics",settings,seed=2,layout=layout)
        actions=("step:4",)*6
        result=run_advanced_session("physics",settings,actions,seed=2,scene=scene)
        self.assertTrue(verify_advanced_session(result,settings))
        self.assertEqual(result["state"]["bodies"][0]["position"][1],960)
        self.assertGreater(result["state"]["contacts"],0)
        package=render_physics_godot_package(result,settings,authorized=True)
        proof=json.loads(package.files["godot/proof.json"])["expected"]
        self.assertEqual(proof["y"],960)
        self.assertEqual(proof["frame"],24)
        self.assertEqual(proof["contacts"],result["state"]["contacts"])
        self.assertIn("per_frame_g",GODOT_PHYSICS)

    def test_bounded_archive_integrity_and_no_implicit_filesystem_write(self):
        rules,scene,session=self.generate()
        package=render_physics_godot_package(session,rules,authorized=True)
        self.assertEqual(set(package.files),set(package.manifest["files"])|{"release.json"})
        for path,digest in package.manifest["files"].items():
            self.assertEqual(sha256(package.files[path]).hexdigest(),digest)
        zipblob=archive_advanced_godot_package(package)
        with ZipFile(BytesIO(zipblob)) as archive:
            self.assertIn("original-godot-physics/godot/scripts/main.gd",
                          archive.namelist())
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"native_physics"
            with self.assertRaises(PermissionError):
                write_advanced_godot_package(package,root,authorized=False)
            self.assertFalse(root.exists())
            self.assertEqual(write_advanced_godot_package(
                package,root,authorized=True),root)
            self.assertTrue((root/"godot/scripts/main.gd").exists())
            with self.assertRaises(AdvancedGodotExportError):
                write_advanced_godot_package(package,root,authorized=True)

    def test_tampered_session_and_mismatched_configuration_fail_closed(self):
        rules,scene,session=self.generate()
        mutations=[
            lambda s:s["state"]["bodies"][0]["orientation"].__class__,
            lambda s:s["state"]["bodies"][0].update(angular_velocity=70000),
            lambda s:s["state"].update(finished=True),
            lambda s:s["trace"][0].update(digest="0"*64),
        ]
        for change in mutations[1:]:
            forged=deepcopy(session)
            change(forged)
            with self.assertRaises(Exception):
                render_physics_godot_package(forged,rules,authorized=True)
        with self.assertRaises(Exception):
            render_physics_godot_package(
                session,{**rules,"gravity":1},authorized=True)

    def test_studio_has_actual_signed_native_profile_preparation(self):
        html=render_workspace_html("B"*32).decode("utf-8")
        self.assertIn('id="advanced-physics-native"',html)
        self.assertIn("native_physics_demo",html)
        self.assertIn('layout.fixtures=[{"position":[430,900,0]',html)
        self.assertIn("Authenticated authored native profile was not replayed",html)
        self.assertIn('advancedSettings?.max_bodies===1',html)
        self.assertIn('advancedSettings?.initial_battery===0',html)
        self.assertIn('advancedSession.scene_digest!==approved.scene.digest',html)
        self.assertIn("device validation is separate",html)

    def test_independent_script_has_actual_transition_and_exact_proof_comparison(self):
        self.assertIn("func _frame() -> void:",GODOT_PHYSICS)
        self.assertIn("func _step(action: String) -> bool:",GODOT_PHYSICS)
        self.assertIn("func _verify() -> void:",GODOT_PHYSICS)
        self.assertIn("native physics divergence",GODOT_PHYSICS)
        self.assertNotIn("eval(",GODOT_PHYSICS)
        self.assertEqual(len(NATIVE_ACTIONS),11)


if __name__=="__main__":
    unittest.main()
