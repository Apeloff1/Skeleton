"""Focused tests for 830m air, actual ray-light dampening, tidal water,
old/new mesh authoring, all-era double-verified chunks and RPG tools.
"""
import math
import unittest
from dataclasses import replace

from skeleton.jeeves.game_frontier_production import Vec3
from skeleton.jeeves.game_frontier_ecosystem import (
    AirConditions, CelestialCycle, LiquidGrid, AudioEnvironment,
    sample_atmosphere, sample_tides, advance_liquid, interact_with_water,
    mix_environment_audio,
)
from skeleton.jeeves.game_frontier_photometry import (
    LeafPose, LightClimate, move_leaf, verify_leaf_shadow,
    illuminate_atmosphere_3d, ray_intersects_leaf,
)
from skeleton.jeeves.game_frontier_lighting import (
    SurfaceSample, LightSource, Ray, RayOccluder,
)
from skeleton.jeeves.game_frontier_mesh_evolution import (
    PixelAsset, sprite_to_3d, create_old_new_asset_pair, MeshEvolutionError,
)
from skeleton.jeeves.game_frontier_chunks import (
    chunk_mesh, verify_chunks, verify_registered_era_chunks,
)
from skeleton.jeeves.game_engine_lab import EngineEra
from skeleton.forge.game_frontier_studio import (
    STUDIO_TOOLS, StudioProject, StudioEvent, StudioPrefab, StudioPlacement,
    MapLayer, paint_tile, compile_studio_project, propose_event_actions,
    StudioError,
)

class AtmosphereTests(unittest.TestCase):
    def test_830m_and_feet(self):
        air = sample_atmosphere(AirConditions(altitude_m=830,temperature_c=15))
        sea = sample_atmosphere(AirConditions(altitude_m=0,temperature_c=15))
        self.assertAlmostEqual(air.altitude_ft, 2723.097, delta=.05)
        self.assertLess(air.density_kg_m3,sea.density_kg_m3)
        self.assertLess(air.pressure_pa,sea.pressure_pa)

    def test_hot_air_thins_and_fog_dampens_visibility(self):
        hot=sample_atmosphere(AirConditions(altitude_m=830,temperature_c=37))
        cold=sample_atmosphere(AirConditions(altitude_m=830,temperature_c=-5))
        self.assertLess(hot.density_kg_m3,cold.density_kg_m3)
        fog=sample_atmosphere(AirConditions(fog_liquid_g_m3=.2))
        clear=sample_atmosphere(AirConditions())
        self.assertLess(fog.meteorological_visibility_m,clear.meteorological_visibility_m)

    def test_rain_cleaning_and_cold_wind_damping_are_explicit(self):
        baseline=sample_atmosphere(AirConditions(temperature_c=-10,
                                                particulate_index=.9,cold_wind_damping=1))
        rain=sample_atmosphere(AirConditions(temperature_c=-10,
                                           rain_mm_h=120,particulate_index=.9,
                                           cold_wind_damping=1))
        natural=sample_atmosphere(AirConditions(temperature_c=-10,
                                              cold_wind_damping=0))
        self.assertGreater(rain.rain_washed_freshness,baseline.rain_washed_freshness)
        self.assertLess(rain.effective_wind_factor,natural.effective_wind_factor)

    def test_lunar_and_solar_tide_interference(self):
        spring=sample_tides(CelestialCycle(time_hours=0,moon_phase_cycles=0))
        neap=sample_tides(CelestialCycle(time_hours=0,moon_phase_cycles=.25))
        self.assertGreater(spring.water_height_m,neap.water_height_m)
        self.assertEqual(spring.tidal_alignment,1)
        self.assertAlmostEqual(neap.tidal_alignment,-1,places=7)

    def test_water_conservation_and_characters(self):
        source=LiquidGrid(3,1,1,(0,0,0),(1.,0.,0.))
        a=advance_liquid(source,delta_s=.2)
        self.assertAlmostEqual(a.final_volume_m3,source.volume_m3,delta=1e-10)
        self.assertAlmostEqual(a.mass_residual_m3,0,delta=1e-10)
        self.assertGreater(a.grid.water_depth_m[1],0)
        b=advance_liquid(a.grid,delta_s=1,rain_mm_h=100)
        self.assertAlmostEqual(b.final_volume_m3,b.initial_volume_m3+
                              b.rain_added_m3-b.evaporation_removed_m3,delta=1e-10)
        wet=interact_with_water(water_surface_z_m=1.8,character_foot_z_m=0,
                                character_height_m=1.7,character_volume_m3=.07,
                                velocity=Vec3(1,0,0))
        self.assertEqual(wet.suggested_gait,"swim")
        self.assertGreater(wet.buoyant_force_n,0)
        self.assertLess(wet.drag_force.x,0)

    def test_audio_weather_tide_synergy(self):
        air=sample_atmosphere(AirConditions(altitude_m=830,fog_liquid_g_m3=.2))
        tide=sample_tides(CelestialCycle(time_hours=3))
        audio=mix_environment_audio(AudioEnvironment(10,2,air,100,True,tide))
        self.assertGreater(audio.delay_s,0)
        self.assertIn("rain_on_roof",audio.cues)
        self.assertIn("fog_muffled",audio.cues)
        self.assertIn("occluded_sound",audio.cues)


class LeafAndLightTests(unittest.TestCase):
    def leaf(self):
        return LeafPose("oak-1",Vec3(0,0,2),Vec3(0,0,2),
                        Vec3(0,0,0),Vec3(0,0,1),.4,.6)

    def test_leaf_shadow_tracks_physical_leaf_area(self):
        first=self.leaf()
        audited=verify_leaf_shadow(first,sun_toward=Vec3(0,0,1))
        self.assertTrue(audited.verified)
        self.assertAlmostEqual(audited.geometric_area_m2,.24,places=6)
        self.assertEqual(audited.ray_shadow_coverage,1.)
        self.assertAlmostEqual(audited.area_error_m2,0,places=6)

    def test_wind_moves_leaf_and_shadow(self):
        leaf=self.leaf()
        moved=move_leaf(leaf,wind_mps=Vec3(20,0,0),dt_s=.05)
        self.assertNotEqual(moved.center,leaf.center)
        a=verify_leaf_shadow(leaf,sun_toward=Vec3(.3,0,1))
        b=verify_leaf_shadow(moved,sun_toward=Vec3(.3,0,1))
        self.assertNotEqual(a.polygon,b.polygon)
        self.assertTrue(a.verified)
        self.assertTrue(b.verified)

    def test_light_distance_fog_cloud_and_leaves_dampen_radiance(self):
        ground=SurfaceSample("ground",Vec3(0,0,0),Vec3(0,0,1))
        near=LightSource("lamp",Vec3(0,0,4),1000)
        far=LightSource("lamp",Vec3(0,0,10),1000)
        dry=LightClimate(sample_atmosphere(AirConditions()))
        fog=LightClimate(sample_atmosphere(AirConditions(fog_liquid_g_m3=.3)),
                         rain_mm_h=100,cloud_opacity=.8)
        clear=illuminate_atmosphere_3d(ground,(near,),(),(),dry)
        distant=illuminate_atmosphere_3d(ground,(far,),(),(),dry)
        obscured=illuminate_atmosphere_3d(ground,(near,),(),(),fog)
        self.assertGreater(clear.delivered_direct,distant.delivered_direct)
        self.assertLess(obscured.delivered_direct,clear.delivered_direct)
        leaf=illuminate_atmosphere_3d(ground,(near,),(),(self.leaf(),),dry)
        self.assertGreater(leaf.leaf_shadow_fraction,0)
        self.assertLess(leaf.delivered_direct,clear.delivered_direct)

    def test_3d_character_blocker_reduces_shadowed_light(self):
        surface=SurfaceSample("ground",Vec3(0,0,0),Vec3(0,0,1))
        lamp=LightSource("sun",Vec3(0,0,10),500)
        actor=RayOccluder("actor","character",Vec3(0,0,5),"sphere",1)
        climate=LightClimate(sample_atmosphere(AirConditions()))
        bright=illuminate_atmosphere_3d(surface,(lamp,),(),(),climate)
        blocked=illuminate_atmosphere_3d(surface,(lamp,),(actor,),(),climate)
        self.assertEqual(blocked.geometric_shadow_fraction,1)
        self.assertLess(blocked.delivered_direct,bright.delivered_direct)


class ChunkAndAssetTests(unittest.TestCase):
    def quad(self):
        vertices=(Vec3(-2,0,0),Vec3(-1,0,0),Vec3(-1,1,0),
                  Vec3(-2,1,0),Vec3(1,0,0),Vec3(2,0,0),Vec3(2,1,0))
        triangles=((0,1,2),(0,2,3),(4,5,6))
        return vertices,triangles

    def test_two_independent_chunk_verifiers_for_every_engine_era(self):
        vertices,faces=self.quad()
        all_eras=verify_registered_era_chunks(vertices,faces,size_m=1)
        self.assertEqual(len(all_eras),len(tuple(EngineEra)))
        self.assertTrue(all(report.approved_by_both for report in all_eras))

    def test_corruption_caught_independently(self):
        vertices,faces=self.quad()
        chunks=chunk_mesh(vertices,faces,era=EngineEra.EARLY_3D,chunk_size_m=1)
        valid=verify_chunks(chunks,vertices,faces,era=EngineEra.EARLY_3D)
        self.assertTrue(valid.approved_by_both)
        bad=replace(chunks[0],content_digest="0"*64)
        invalid=verify_chunks((bad,)+chunks[1:],vertices,faces,era=EngineEra.EARLY_3D)
        self.assertFalse(invalid.authenticated)
        self.assertTrue(invalid.topology_reconstructed)

    def test_original_sprite_retained_in_old_and_new_3d(self):
        art=PixelAsset("tree",(".#.","###",".#."))
        old,new=create_old_new_asset_pair(art)
        self.assertEqual(old.source_digest,new.source_digest)
        self.assertTrue(old.source_preserved and new.source_preserved)
        self.assertGreater(new.triangle_count,old.triangle_count)
        self.assertEqual(new.era,"modern")
        self.assertTrue(all(0<=index<len(new.vertices) for f in new.triangles for index in f))
        with self.assertRaises(MeshEvolutionError):
            sprite_to_3d(art,era="no-real-engine")


class StudioTests(unittest.TestCase):
    def project(self):
        layer=MapLayer("terrain",2,2,("grass","stone"),(0,0,0,1))
        prefab=StudioPrefab("hero","character","early_3d","a"*64,"dialogue")
        event=StudioEvent("hello","interact","met_hero",False,
                          "show_dialogue","hero","welcome")
        return StudioProject("realm","early_3d",
                             __import__("skeleton.jeeves.game_frontier_worlds",
                                        fromlist=["ProjectionMode"]).ProjectionMode.DEPTH_27,
                             __import__("skeleton.jeeves.game_frontier_worlds",
                                        fromlist=["WorldFamily"]).WorldFamily.MYTHIC,
                             (layer,),(prefab,),(StudioPlacement("hero",0,0,1),),
                             (event,),("theme",))

    def test_2030s_editor_surface_and_event_graph(self):
        project=self.project()
        self.assertGreaterEqual(len(STUDIO_TOOLS),25)
        a=compile_studio_project(project)
        self.assertEqual(a,compile_studio_project(project))
        self.assertEqual(a["projection"],"2.7d")
        self.assertEqual(len(propose_event_actions(project,trigger="interact",
                      flags={},actor_target="hero")),1)
        self.assertEqual(len(propose_event_actions(project,trigger="interact",
                      flags={"met_hero":True},actor_target="hero")),0)

    def test_layer_paint_is_immutable_and_bounded(self):
        project=self.project()
        original=project.layers[0]
        changed=paint_tile(original,x=0,y=1,tile_index=1)
        self.assertNotEqual(changed,original)
        self.assertEqual(original.data[2],0)
        self.assertEqual(changed.data[2],1)
        with self.assertRaises(StudioError):
            paint_tile(original,x=3,y=0,tile_index=1)


class FullFrontierCandidateTests(unittest.TestCase):
    def test_combined_sun_tide_liquid_fog_leaf_chunk_and_mesh_export(self):
        from skeleton.jeeves.game_frontier import compile_frontier_scene
        from skeleton.jeeves.game_frontier_dynamics import (
            WorldAxis, WindField, WindLayer, WindVector, Cloud,
        )
        from skeleton.jeeves.game_frontier_production import (
            Bone, BonePose, CharacterSkeleton, AnimationClip, AnimationKeyframe, Percept,
        )
        from skeleton.jeeves.game_frontier_motion import CharacterState, Weather
        from skeleton.forge.game_frontier_godot import emit_frontier_godot_overlay
        from skeleton.jeeves.game_frontier_worlds import (
            WorldVariant, WorldFamily, CameraSpec, ProjectionMode,
        )
        zero=BonePose(Vec3(0,0,0))
        scene=compile_frontier_scene(
            world_axes=WorldAxis(11,.4,.6,.7,.8,.9,.2),cell_x=0,cell_y=0,
            wind_field=WindField((WindLayer(0,WindVector(0,0)),)),
            clouds=(Cloud("stratus",3,4,100,.5),),time_s=10,delta_s=.05,
            skeleton=CharacterSkeleton((Bone("root",-1,Vec3(0,0,0),Vec3(0,0,1),.2),)),
            animation=AnimationClip("idle",(AnimationKeyframe(0,(zero,)),
                                           AnimationKeyframe(1000,(zero,)))),
            animation_time_ms=200,era="fixed_3d",fps=60,
            evidence=(Percept("hero","character",True,1,.9,"f"*64),),
            world_goal_kind="character",available_actions=("inspect","interact"),
            world_variant=WorldVariant(WorldFamily.MYTHIC),
            camera=CameraSpec(ProjectionMode.DEPTH_27),
            weather=Weather(Vec3(0,0,0),13,precipitation_mm_h=60),
            character_state=CharacterState(Vec3(0,0,.5),Vec3(0,0,0),.5,80),
            desired_character_velocity=Vec3(0,0,0),
            air_conditions=AirConditions(altitude_m=830,temperature_c=13,
                                         fog_liquid_g_m3=.01,rain_mm_h=60),
            celestial_cycle=CelestialCycle(time_hours=3,moon_phase_cycles=.25),
            liquid_grid=LiquidGrid(2,1,1,(0.,0.),(2.,0.)),
            leaf_poses=(LeafPose("leaf",Vec3(0,0,2),Vec3(0,0,2),
                                 Vec3(0,0,0),Vec3(0,0,1),.4,.6),),
            trace_3d_lighting=True,
            lighting_surfaces=(SurfaceSample("ground",Vec3(0,0,0),Vec3(0,0,1)),),
            light_sources=(LightSource("sun",Vec3(0,0,10),800),),
            audio_source_distance_m=10,verify_all_era_chunks=True,
            original_pixel_asset=PixelAsset("grass",(".#","##")),
        )
        m=scene.manifest
        self.assertEqual(m["atmosphere"]["altitude_m"],830)
        self.assertIsNotNone(m["tides"])
        self.assertIsNotNone(m["character_water"])
        self.assertTrue(m["leaf_shadows"][0]["double_verified"])
        self.assertLess(m["photometric_3d"][0]["source_delivered"],
                        m["photometric_3d"][0]["source_unblocked"])
        self.assertEqual(len(m["chunk_verification"]),len(tuple(EngineEra)))
        self.assertTrue(all(x["passed_both"] for x in m["chunk_verification"]))
        self.assertEqual(len(m["old_new_assets"]),2)
        self.assertFalse(scene.approved_for_runtime)
        from json import loads
        files=emit_frontier_godot_overlay(scene,cloud_path_duration_s=2)
        data=loads(files["frontier/data/scene.json"])
        self.assertEqual(data["atmosphere"]["altitude_m"],830)
        self.assertEqual(len(data["leaf_shadows"]),1)
        gd=files["frontier/frontier_scene.gd"]
        self.assertIn("FrontierLiquidSurface",gd)
        self.assertIn("VerifiedLeafShadow",gd)
        self.assertIn("volumetric_transmission",gd)


if __name__=="__main__":
    unittest.main()
