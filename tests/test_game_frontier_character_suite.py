"""ElasticBodySkin3D, load distribution, simulated navigation and RPG trigger tests."""
import math
import unittest
from dataclasses import replace

from skeleton.jeeves.game_frontier_production import (
    Vec3, Bone, CharacterSkeleton, AnimationClip, AnimationKeyframe,
    BonePose, skeleton_to_polygon,
)
from skeleton.jeeves.game_frontier_motion import Weather
from skeleton.jeeves.game_frontier_body_balance import (
    BodyMass, SupportFoot, distribute_character_weight, BodyBalanceError,
)
from skeleton.jeeves.game_frontier_elastic_skin3d import (
    ElasticBodySkin3D, ElasticSkinState, initial_skin_state,
    simulate_elastic_skin, ElasticSkinError,
)
from skeleton.jeeves.game_frontier_instruments import (
    NavigationEnvironment, Gyroscope, advance_gyroscope, sample_compass,
    sight_sextant, sight_bubble_sextant, barometric_altimeter,
    trigonometric_altimeter, instrument_manifest, InstrumentError,
)
from skeleton.forge.game_frontier_studio import (
    StudioProject, MapLayer, StudioEvent, compile_studio_project, StudioError,
)
from skeleton.jeeves.game_frontier_worlds import ProjectionMode, WorldFamily
from skeleton.forge.game_frontier_rpg_events import (
    EnvironmentalTrigger, RPGEventPage, RPGEventAction,
    evaluate_environment_events, event_authoring_catalog, RPGEventError,
)
from skeleton.jeeves.game_frontier_character_suite import (
    CharacterSuiteConfig, compile_character_suite, CharacterSuiteError,
)
from tests.test_game_frontier_advanced_scene import scene_params
from skeleton.jeeves.game_frontier import compile_frontier_scene
from skeleton.jeeves.game_frontier_realism import audit_scene_realism
from skeleton.forge.game_frontier_godot import emit_frontier_godot_overlay


def body():
    segments = (
        BodyMass("torso",50,Vec3(0,0,1)),
        BodyMass("head",10,Vec3(0,0,1.8)),
        BodyMass("backpack",20,Vec3(.2,.4,1.1),carried=True),
    )
    feet = tuple(SupportFoot(name,Vec3(x,y,0),500,.9)
                 for name,x,y in (("front-left",-.4,-.4),
                                  ("front-right",.4,-.4),
                                  ("back-left",-.4,.4),
                                  ("back-right",.4,.4)))
    return segments,feet


def animation():
    rig=CharacterSkeleton((Bone("torso",-1,Vec3(0,0,0),Vec3(0,0,1.4),.2),))
    mesh=skeleton_to_polygon(rig,"early_3d")
    zero=BonePose(Vec3(0,0,0))
    return rig,mesh,AnimationClip("idle",(
        AnimationKeyframe(0,(zero,)),
        AnimationKeyframe(1000,(zero,)),
    ))


class BodyWeightTests(unittest.TestCase):
    def test_weight_com_inertia_and_foot_forces(self):
        segments,feet=body()
        result=distribute_character_weight(segments,feet)
        self.assertEqual(result.total_mass_kg,80)
        self.assertEqual(result.carried_mass_kg,20)
        self.assertGreater(result.center_of_mass.y,0)
        self.assertTrue(result.stable)
        self.assertGreater(result.support_margin_m,0)
        self.assertAlmostEqual(sum(force for _,force in result.load_per_foot_n),
                               80*9.80665,places=7)
        self.assertGreater(result.inertia_tensor_kg_m2[0][0],0)
        self.assertEqual(result.inertia_tensor_kg_m2[0][1],
                         result.inertia_tensor_kg_m2[1][0])
        self.assertEqual(len(result.evidence_digest),64)

    def test_cargo_and_acceleration_shift_balance(self):
        segments,feet=body()
        stationary=distribute_character_weight(segments,feet)
        dynamic=distribute_character_weight(
            segments,feet,acceleration_mps2=Vec3(4,0,0))
        self.assertLess(dynamic.support_margin_m,stationary.support_margin_m)
        self.assertFalse(dynamic.stable)
        self.assertGreater(dynamic.required_tangential_force_n,0)

    def test_bad_polygon_and_duplicate_id_refused(self):
        segments,feet=body()
        with self.assertRaises(BodyBalanceError):
            distribute_character_weight(segments,feet[:2])
        with self.assertRaises(BodyBalanceError):
            distribute_character_weight(segments,
                tuple(SupportFoot(str(i),Vec3(i,0,0),500,.9) for i in range(3)))
        with self.assertRaises(BodyBalanceError):
            distribute_character_weight((segments[0],segments[0]),feet)


class ElasticBodySkinTests(unittest.TestCase):
    def test_rig_anchors_wind_wet_and_evidence(self):
        rig,mesh,clip=animation()
        config=ElasticBodySkin3D(collision_ground_z_m=-2)
        state=initial_skin_state(rig,mesh,clip,time_ms=100)
        result=simulate_elastic_skin(
            rig,mesh,clip,config,
            time_ms=100,delta_s=.1,wind_mps=Vec3(20,0,0),
            rainfall_mm_h=200,air_temperature_c=40,
            state=state,pinned_vertices=(0,),
        )
        self.assertEqual(result.positions[0],state.positions[0])
        self.assertGreater(result.wetness,0)
        self.assertGreater(result.temperature_c,20)
        self.assertGreater(result.mean_anchor_displacement_m,0)
        self.assertEqual(result.mesh_digest,mesh.digest)
        self.assertEqual(len(result.evidence_digest),64)
        again=simulate_elastic_skin(rig,mesh,clip,config,
            time_ms=100,delta_s=.1,wind_mps=Vec3(20,0,0),
            rainfall_mm_h=200,air_temperature_c=40,state=state)
        self.assertEqual(result,again)

    def test_impact_moves_unpinned_vertices(self):
        rig,mesh,clip=animation()
        config=ElasticBodySkin3D(collision_ground_z_m=-2)
        still=simulate_elastic_skin(rig,mesh,clip,config,time_ms=100,delta_s=.05)
        struck=simulate_elastic_skin(rig,mesh,clip,config,time_ms=100,delta_s=.05,
                                    impact_force_n=Vec3(20,0,0))
        self.assertGreater(struck.mean_anchor_displacement_m,
                           still.mean_anchor_displacement_m)

    def test_fail_closed_vertex_budget_and_pins(self):
        rig,mesh,clip=animation()
        with self.assertRaises(ElasticSkinError):
            simulate_elastic_skin(
                rig,mesh,clip,ElasticBodySkin3D(maximum_vertices=2),
                time_ms=1,delta_s=.01)
        with self.assertRaises(ElasticSkinError):
            simulate_elastic_skin(
                rig,mesh,clip,ElasticBodySkin3D(),
                time_ms=1,delta_s=.01,pinned_vertices=(100000,))


class InstrumentsTests(unittest.TestCase):
    def test_gyro_integrates_rate_and_bias(self):
        gyro=Gyroscope(0,0,0,bias_dps=Vec3(0,0,.1))
        observed=advance_gyroscope(gyro,Vec3(1,0,10),delta_s=5)
        self.assertAlmostEqual(observed.yaw_deg,50.5,places=6)
        self.assertAlmostEqual(observed.pitch_deg,5,places=6)
        self.assertGreater(observed.horizon_tilt_deg,0)

    def test_compass_declination_and_anomaly(self):
        env=NavigationEnvironment(60,10,830,geomagnetic_declination_deg=12)
        reading=sample_compass(100,env)
        self.assertAlmostEqual(reading.magnetic_heading_deg,88)
        disturbed=sample_compass(100,env,interference_deg=15)
        self.assertTrue(disturbed.disturbed)
        self.assertLess(disturbed.confidence,reading.confidence)

    def test_natural_and_bubble_sextant(self):
        env=NavigationEnvironment(60,10,830)
        sight=Vec3(0,math.cos(math.radians(30)),
                     math.sin(math.radians(30)))
        natural=sight_sextant(sight,env,eye_height_m=2)
        bubble=sight_bubble_sextant(sight,env)
        self.assertAlmostEqual(natural.corrected_altitude_deg,30,places=5)
        self.assertAlmostEqual(bubble.corrected_altitude_deg,30,places=5)
        self.assertFalse(natural.synthetic_horizon)
        self.assertTrue(bubble.synthetic_horizon)
        obscured=replace(env,horizon_obscured=True)
        with self.assertRaises(InstrumentError):
            sight_sextant(sight,obscured)
        self.assertAlmostEqual(sight_bubble_sextant(
            sight,obscured).corrected_altitude_deg,30,places=5)

    def test_barometric_and_trigonometric_altimeters(self):
        from skeleton.jeeves.game_frontier_ecosystem import (
            AirConditions,sample_atmosphere,
        )
        atm=sample_atmosphere(AirConditions(altitude_m=830,temperature_c=15))
        baro=barometric_altimeter(atm.pressure_pa,temperature_c=15)
        self.assertAlmostEqual(baro.altitude_m,830,delta=15)
        trig=trigonometric_altimeter(1000,45,observer_altitude_m=830,
                                    instrument_height_m=2)
        self.assertAlmostEqual(trig.altitude_m,1832,places=6)
        self.assertAlmostEqual(trig.altitude_ft,1832*3.280839895,places=5)
        with self.assertRaises(InstrumentError):
            trigonometric_altimeter(1000,90)

    def test_navigation_receipt_is_deterministic(self):
        env=NavigationEnvironment(60,10,830)
        a=instrument_manifest((sample_compass(50,env),
                              trigonometric_altimeter(20,20)))
        self.assertEqual(a,instrument_manifest((sample_compass(50,env),
                              trigonometric_altimeter(20,20))))
        self.assertEqual(a["authority"],"simulation_only_no_location_fix")


class RPGEnvironmentTests(unittest.TestCase):
    def test_crossing_hysteresis_prior_and_cooldown(self):
        rule=EnvironmentalTrigger("rain_mm_h","cross_up",20,hysteresis=2)
        action=RPGEventAction("play_music","audio","rain_stage","storm_theme")
        page=RPGEventPage("storm_theme",10,(rule,),(action,),cooldown_ms=3000)
        yes=evaluate_environment_events(
            (page,),current={"rain_mm_h":30},previous={"rain_mm_h":10},
            now_ms=5000)
        self.assertEqual(len(yes.accepted),1)
        self.assertEqual(yes.accepted[0].actions[0].kind,"play_music")
        self.assertEqual(yes.accepted[0].authority,"proposal_only_no_world_mutation")
        blocked=evaluate_environment_events(
            (page,),current={"rain_mm_h":30},previous={"rain_mm_h":10},
            now_ms=5000,last_fired_ms={"storm_theme":3000})
        self.assertFalse(blocked.accepted)
        self.assertEqual(blocked.suppressed,("storm_theme",))
        cold=evaluate_environment_events((page,),current={"rain_mm_h":30},
                                         now_ms=5000)
        self.assertFalse(cold.accepted)

    def test_priority_and_channel_target_conflicts(self):
        condition=EnvironmentalTrigger("ground_ice_fraction","above",.5)
        high=RPGEventPage("highest",9,(condition,),(
            RPGEventAction("play_cutscene","cinematic","hero","slip"),))
        low=RPGEventPage("lower",1,(condition,),(
            RPGEventAction("show_dialogue","cinematic","hero","caution"),))
        result=evaluate_environment_events((low,high),
            current={"ground_ice_fraction":.8},now_ms=500)
        self.assertEqual(tuple(x.page_id for x in result.accepted),("highest",))
        self.assertEqual(result.suppressed,("lower",))

    def test_environment_catalog_and_unsafe_actions_rejected(self):
        cat=event_authoring_catalog()
        self.assertIn("skin_strain",cat["available_signals"])
        self.assertIn("bubble_sextant_altitude_deg",cat["available_signals"])
        self.assertGreaterEqual(len(cat["available_signals"]),30)
        with self.assertRaises(RPGEventError):
            EnvironmentalTrigger("not_real_signal","above",3)
        with self.assertRaises(RPGEventError):
            RPGEventAction("run_remote_code","world","scene","payload")


class StudioEnvironmentalEditorTests(unittest.TestCase):
    def test_modern_studio_serializes_environmental_event_graph(self):
        page=RPGEventPage("rain_alarm",5,(
            EnvironmentalTrigger("rain_mm_h","cross_up",25),
        ),(RPGEventAction("play_cutscene","cinematic","hero","flood"),))
        studio=StudioProject("game","modern",ProjectionMode.DEPTH_29,
                             WorldFamily.CELESTIAL,
                             (MapLayer("floor",1,1,("grass",),(0,)),),
                             environmental_pages=(page,))
        result=compile_studio_project(studio)
        self.assertIn("elastic_body_skin3d_editor",result["editors"])
        self.assertIn("instrument_event_graph",result["editors"])
        self.assertIn("center_of_mass_inspector",result["editors"])
        self.assertEqual(result["environmental_pages"][0]["id"],"rain_alarm")
        self.assertEqual(result["environmental_pages"][0]["conditions"][0]["signal"],
                         "rain_mm_h")
        self.assertEqual(result,compile_studio_project(studio))

    def test_cannot_create_colliding_old_new_event_ids(self):
        page=RPGEventPage("same",2,(
            EnvironmentalTrigger("wind_mps","above",20),
        ),(RPGEventAction("change_camera","cinematic","hero","wide"),))
        old=StudioEvent("same","interact","",False,"show_dialogue","hero","hi")
        with self.assertRaises(StudioError):
            StudioProject("game","early_3d",ProjectionMode.TOP_DOWN,
                          WorldFamily.ORIGINAL,
                          (MapLayer("ground",1,1,("floor",),(0,)),),
                          events=(old,),environmental_pages=(page,))


class SuiteIntegrationTests(unittest.TestCase):
    def suite(self):
        segments,feet=body()
        rule=RPGEventPage(
            "wet_ground",5,(
                EnvironmentalTrigger("rain_mm_h","above",20),
                EnvironmentalTrigger("support_margin_m","below",.5),
            ),(RPGEventAction("show_dialogue","character","hero","Seek shelter"),))
        return CharacterSuiteConfig(
            body_segments=segments,support_feet=feet,
            elastic_skin=ElasticBodySkin3D(collision_ground_z_m=-2),
            navigation=NavigationEnvironment(60,10,830,horizon_obscured=True,
                                             geomagnetic_declination_deg=12),
            gyroscope=Gyroscope(40,0,0),
            celestial_target_enu=Vec3(0,.8660254,.5),
            horizontal_baseline_m=100,
            target_elevation_angle_deg=20,
            rpg_pages=(rule,),clock_ms=1000,
        )

    def test_suite_coordinates_balance_skin_sensors_and_rpg(self):
        rig,mesh,clip=animation()
        result=compile_character_suite(self.suite(),skeleton=rig,mesh=mesh,
             animation=clip,animation_time_ms=100,delta_s=.05,
             weather=Weather(Vec3(10,0,0),15,precipitation_mm_h=50))
        self.assertEqual(result["weight_distribution"]["total_mass_kg"],80)
        self.assertGreater(result["elastic_skin3d"]["vertex_count"],0)
        self.assertEqual(result["elastic_skin3d"]["pinned_vertices"],[0])
        kinds={v["type"] for v in result["instruments"]["readings"]}
        self.assertIn("CompassReading",kinds)
        self.assertIn("GyroReading",kinds)
        self.assertIn("SextantReading",kinds)
        self.assertIn("AltimeterReading",kinds)
        self.assertEqual(len(result["rpg_events"]["accepted"]),1)
        self.assertFalse(result["rpg_events"]["executed"])

    def test_scene_godot_uses_native_soft_body_wrapper(self):
        cfg=scene_params()
        cfg["character_suite"]=self.suite()
        cfg["weather"]=Weather(Vec3(10,0,0),15,precipitation_mm_h=50)
        scene=compile_frontier_scene(**cfg)
        self.assertFalse(scene.approved_for_runtime)
        self.assertEqual(scene.manifest["character_suite"]["weight_distribution"]["total_mass_kg"],80)
        overlay=emit_frontier_godot_overlay(scene,cloud_path_duration_s=2)
        script=overlay["frontier/frontier_scene.gd"]
        self.assertIn("SoftBody3D.new()",script)
        self.assertIn('soft.name = "ElasticBodySkin3D"',script)
        self.assertIn("NavigationInstrumentInspector",script)
        import json
        data=json.loads(overlay["frontier/data/scene.json"])
        self.assertGreater(len(data["character_suite"]["elastic_skin3d"]["positions_xyz"]),0)
        self.assertEqual(data["character_suite"]["rpg_events"]["executed"],False)

    def test_second_realism_auditor_detects_mass_and_event_custody_tampering(self):
        cfg=scene_params()
        cfg["character_suite"]=self.suite()
        cfg["weather"]=Weather(Vec3(10,0,0),15,precipitation_mm_h=50)
        original=compile_frontier_scene(**cfg).manifest
        self.assertTrue(original["realism_audit"]["reference_checks_passed"])
        self.assertIn("balance",original["realism_audit"]["participating_domains"])
        self.assertIn("elastic_skin",original["realism_audit"]["participating_domains"])
        self.assertIn("instruments",original["realism_audit"]["participating_domains"])
        self.assertIn("rpg_events",original["realism_audit"]["participating_domains"])
        modified=dict(original)
        suite=dict(original["character_suite"])
        balance=dict(suite["weight_distribution"])
        loads=[list(item) for item in balance["load_per_foot_n"]]
        loads[0][1]+=100
        balance["load_per_foot_n"]=loads
        suite["weight_distribution"]=balance
        modified["character_suite"]=suite
        audit=audit_scene_realism(modified)
        self.assertFalse(audit.reference_checks_passed)
        self.assertTrue(any(x.domain=="balance" and not x.passed
                            for x in audit.invariants))
        other_suite=dict(original["character_suite"])
        event=dict(other_suite["rpg_events"])
        event["executed"]=True
        other_suite["rpg_events"]=event
        modified["character_suite"]=other_suite
        audit=audit_scene_realism(modified)
        self.assertFalse(audit.reference_checks_passed)
        self.assertTrue(any(x.domain=="rpg_events" and not x.passed
                            for x in audit.invariants))

    def test_empty_suite_does_not_change_legacy_authority(self):
        cfg=scene_params()
        cfg["character_suite"]=CharacterSuiteConfig()
        scene=compile_frontier_scene(**cfg)
        self.assertIsNone(scene.manifest["character_suite"]["elastic_skin3d"])
        self.assertIsNone(scene.manifest["character_suite"]["weight_distribution"])
        self.assertFalse(scene.approved_for_runtime)

    def test_partial_requirements_fail_closed(self):
        rig,mesh,clip=animation()
        with self.assertRaises(CharacterSuiteError):
            compile_character_suite(CharacterSuiteConfig(
                body_segments=body()[0]),skeleton=rig,mesh=mesh,
                animation=clip,animation_time_ms=0,delta_s=.05)
        with self.assertRaises(CharacterSuiteError):
            compile_character_suite(CharacterSuiteConfig(
                gyroscope=Gyroscope(0,0,0)),skeleton=rig,mesh=mesh,
                animation=clip,animation_time_ms=0,delta_s=.05)


if __name__=="__main__":
    unittest.main()
