"""Regression coverage for the world-family/projection/weather/rigid-soft/lighting expansion."""
from __future__ import annotations

import math
import unittest

from skeleton.jeeves.game_frontier_dynamics import (
    Cloud, WindField, WindLayer, WindVector, WorldAxis,
    PresentationClock, FrontierDynamicsError,
)
from skeleton.jeeves.game_frontier_worlds import (
    CameraSpec, ProjectionMode, WorldFamily, WorldVariant,
    WorldGeometryError, project_point, project_scene, variant_world_cell,
)
from skeleton.jeeves.game_frontier_production import (
    AnimationClip, AnimationKeyframe, Bone, BonePose, CharacterSkeleton,
    Percept, Vec3,
)
from skeleton.jeeves.game_frontier_motion import (
    Weather, SoftNode, MATERIALS, CollisionPlane, CharacterState,
    EnvironmentalState, StructureState, MotionPhysicsError,
    simulate_soft_nodes, simulate_character, advance_environment, age_structure,
)
from skeleton.jeeves.game_frontier_lighting import (
    Ray, RayOccluder, LightSource, SurfaceSample, LightingError,
    trace_ray, illuminate_surface,
)
from skeleton.jeeves.game_frontier import compile_frontier_scene

HASH = "a" * 64
AXIS = WorldAxis(7, .4, .6, .7, .8, .95, .2)


class WorldVariantTests(unittest.TestCase):
    def test_all_eight_requested_families(self):
        cases = (
            WorldFamily.INVERSE, WorldFamily.MIRROR, WorldFamily.ELEMENTAL,
            WorldFamily.ETHEREAL, WorldFamily.MYTHIC, WorldFamily.LENSED,
            WorldFamily.SHADOW, WorldFamily.CELESTIAL,
        )
        result = {family: variant_world_cell(
            AXIS, WorldVariant(family, intensity=.9), 10, -4) for family in cases}
        self.assertEqual(len(result), 8)
        self.assertEqual(result[WorldFamily.INVERSE].gravity_sign, -1)
        self.assertEqual(result[WorldFamily.MIRROR].source_x, -10)
        self.assertGreater(result[WorldFamily.ETHEREAL].permeability, .5)
        self.assertLess(result[WorldFamily.SHADOW].luminance, .2)
        self.assertGreater(result[WorldFamily.CELESTIAL].celestial_altitude, 1000)
        self.assertTrue(result[WorldFamily.CELESTIAL].sky_island)
        self.assertEqual(result, {
            family: variant_world_cell(AXIS, WorldVariant(family, intensity=.9), 10, -4)
            for family in cases
        })

    def test_elemental_variants_change_environment(self):
        water = variant_world_cell(AXIS, WorldVariant(
            WorldFamily.ELEMENTAL, element="water", intensity=1), 10, 12)
        fire = variant_world_cell(AXIS, WorldVariant(
            WorldFamily.ELEMENTAL, element="fire", intensity=1), 10, 12)
        ice = variant_world_cell(AXIS, WorldVariant(
            WorldFamily.ELEMENTAL, element="ice", intensity=1), 10, 12)
        self.assertGreater(water.humidity, fire.humidity)
        self.assertGreater(fire.temperature, ice.temperature)
        self.assertEqual(water.dominant_element, "water")

    def test_mirror_is_involution(self):
        x, y = 17, 34
        v = WorldVariant(WorldFamily.MIRROR, mirror_axis_x=5)
        a = variant_world_cell(AXIS, v, x, y)
        b = variant_world_cell(AXIS, v, a.source_x, a.source_y)
        self.assertEqual((b.source_x, b.source_y), (x, y))

    def test_variant_rejects_bad_metadata(self):
        with self.assertRaises(WorldGeometryError):
            WorldVariant(WorldFamily.ELEMENTAL, element="metal")
        with self.assertRaises(WorldGeometryError):
            WorldVariant(WorldFamily.CELESTIAL, intensity=math.nan)

    def test_full_projection_catalog_has_distinct_depth(self):
        source = Vec3(2, 9, 1)
        modes = (ProjectionMode.TOP_DOWN, ProjectionMode.PLATFORMER,
                 ProjectionMode.DEPTH_25, ProjectionMode.DEPTH_26,
                 ProjectionMode.DEPTH_27, ProjectionMode.DEPTH_28,
                 ProjectionMode.DEPTH_29, ProjectionMode.FULL_3D)
        points = {
            m: project_point(source, CameraSpec(
                m, position=Vec3(0, -3, 1), pitch_rad=.1))
            for m in modes
        }
        self.assertEqual(len(points), 8)
        self.assertNotEqual(points[ProjectionMode.TOP_DOWN].screen_y,
                            points[ProjectionMode.PLATFORMER].screen_y)
        self.assertNotEqual(points[ProjectionMode.DEPTH_25].perspective_scale,
                            points[ProjectionMode.DEPTH_29].perspective_scale)
        self.assertTrue(points[ProjectionMode.FULL_3D].visible)

    def test_lensed_projection_changes_screen_not_world(self):
        cam = CameraSpec(ProjectionMode.DEPTH_28)
        p = Vec3(10, 10, 4)
        original = project_point(p, cam)
        lensed = project_point(p, cam, variant=WorldVariant(
            WorldFamily.LENSED, intensity=1, lens_scale=.75))
        self.assertNotEqual(original.screen_x, lensed.screen_x)
        self.assertEqual(p, Vec3(10, 10, 4))

    def test_hiding_behind_camera(self):
        cam = CameraSpec(ProjectionMode.FULL_3D, position=Vec3(0, 0, 0))
        self.assertFalse(project_point(Vec3(0, -10, 0), cam).visible)


class MotionTests(unittest.TestCase):
    def test_skin_and_cloth_wind_elasticity(self):
        weather = Weather(Vec3(14, 0, 0), 10, precipitation_mm_h=60)
        nodes = (
            SoftNode("hair", "hair", Vec3(0, 0, 2), Vec3(0, 0, 2),
                     Vec3(0, 0, 0), .03),
            SoftNode("cloth", "cloth", Vec3(0, 0, 2), Vec3(0, 0, 2),
                     Vec3(0, 0, 0), .4),
            SoftNode("skin", "skin", Vec3(0, 0, 2), Vec3(0, 0, 2),
                     Vec3(0, 0, 0), .5),
        )
        result = simulate_soft_nodes(nodes, weather,
                                     anchors=tuple(n.rest_position for n in nodes),
                                     delta_s=.08)
        self.assertGreater(result[0].position.x, 0)
        self.assertGreater(result[0].wetness, 0)
        self.assertGreater(result[1].wetness, result[2].wetness)

    def test_wet_hair_boots_and_temperature_awareness(self):
        state = CharacterState(Vec3(0, 0, .4), Vec3(0, 0, 0), .4, 70)
        weather = Weather(Vec3(4, 0, 0), -25, precipitation_mm_h=120,
                          water_depth_m=1.0, snow_depth_m=.2)
        ground = CollisionPlane("ground", Vec3(0, 0, 0), Vec3(0, 0, 1))
        result = simulate_character(state, weather, (ground,),
                                    desired_velocity=Vec3(2, 0, 0), delta_s=.05)
        self.assertGreater(result.state.clothing_wetness, 0)
        self.assertGreater(result.state.hair_wetness, 0)
        self.assertGreater(result.state.boot_wetness, 0)
        self.assertGreater(result.awareness.cold_stress, .5)
        self.assertLess(result.friction_coefficient, 1)

    def test_contacts_prevent_character_penetration(self):
        state = CharacterState(Vec3(0, 0, .1), Vec3(0, 0, -5), .4, 80)
        wall = CollisionPlane("ground", Vec3(0, 0, 0), Vec3(0, 0, 1))
        result = simulate_character(
            state, Weather(Vec3(0, 0, 0), 20), (wall,),
            desired_velocity=Vec3(0, 0, -5), delta_s=.05)
        self.assertGreaterEqual(result.state.position.z, .4)
        self.assertTrue(result.impacts)
        self.assertGreater(result.impacts[0].impulse_ns, 0)

    def test_environment_impact_weather_and_foliage(self):
        wet = Weather(Vec3(50, 0, 0), 5, precipitation_mm_h=100, snow_depth_m=.1)
        initial = EnvironmentalState()
        aged = advance_environment(initial, wet, delta_days=10)
        self.assertGreater(aged.erosion, initial.erosion)
        self.assertGreater(aged.foliage_bend, initial.foliage_bend)
        self.assertGreater(aged.puddle_depth_m, initial.puddle_depth_m)

    def test_unfinished_construction_then_weathering_and_repairs(self):
        structure = StructureState("house", "wood", 100)
        clear = Weather(Vec3(0, 0, 0), 20)
        build = age_structure(structure, clear, elapsed_days=20, work_days=40)
        self.assertFalse(build.complete)
        complete = age_structure(build, clear, elapsed_days=60, work_days=60)
        self.assertTrue(complete.complete)
        self.assertEqual(complete.construction_progress_days, 100)
        storm = Weather(Vec3(80, 0, 0), -12, precipitation_mm_h=130)
        old = age_structure(complete, storm, elapsed_days=365)
        self.assertLess(old.integrity, complete.integrity)
        self.assertGreater(old.surface_weathering, complete.surface_weathering)
        repaired = age_structure(old, clear, elapsed_days=30,
                                maintenance_days=25)
        self.assertGreater(repaired.integrity, old.integrity)

    def test_invalid_soft_anchor_count_rejected(self):
        node = SoftNode("cloth", "cloth", Vec3(0, 0, 1), Vec3(0, 0, 1),
                        Vec3(0, 0, 0), .1)
        with self.assertRaises(MotionPhysicsError):
            simulate_soft_nodes((node,), Weather(Vec3(0, 0, 0), 20),
                                anchors=(), delta_s=.01)


class RayTraceTests(unittest.TestCase):
    def test_ray_hits_sphere_and_box(self):
        sphere = RayOccluder("npc", "character", Vec3(0, 0, 5), "sphere", 1)
        box = RayOccluder("hut", "building", Vec3(0, 0, 9), "box")
        ray = Ray(Vec3(0, 0, 0), Vec3(0, 0, 1))
        closest = trace_ray(ray, (box, sphere), max_distance=20)
        self.assertEqual(closest.object_id, "npc")
        self.assertAlmostEqual(closest.distance_m, 4)
        self.assertEqual(trace_ray(ray, (box,), max_distance=20).object_id, "hut")

    def test_character_casts_shadows(self):
        actor = RayOccluder("actor", "character", Vec3(0, 0, 5), "sphere", 1)
        lamp = LightSource("sun", Vec3(0, 0, 10), 10)
        surface = SurfaceSample("ground", Vec3(0, 0, 0), Vec3(0, 0, 1))
        shadow = illuminate_surface(surface, (lamp,), (actor,))
        lit = illuminate_surface(surface, (lamp,), ())
        self.assertGreater(shadow.shadow_occlusion, .9)
        self.assertIn("actor", shadow.character_occluders)
        self.assertGreater(lit.direct_light, shadow.direct_light)

    def test_wet_material_reflectance(self):
        lamp = LightSource("lamp", Vec3(0, 0, 4), 50)
        wet = SurfaceSample("wet", Vec3(0, 0, 0), Vec3(0, 0, 1),
                            roughness=.1, wetness=1)
        dry = SurfaceSample("dry", Vec3(0, 0, 0), Vec3(0, 0, 1),
                            roughness=.1, wetness=0)
        self.assertGreater(illuminate_surface(wet, (lamp,), ()).wet_specular,
                           illuminate_surface(dry, (lamp,), ()).wet_specular)

    def test_light_bad_geometry_rejected(self):
        with self.assertRaises(LightingError):
            Ray(Vec3(0, 0, 0), Vec3(0, 0, 2))


class WholeSceneTests(unittest.TestCase):
    def test_inverse_gravity_and_ethereal_contact_affect_character_dynamics(self):
        skeleton = CharacterSkeleton((
            Bone("root", -1, Vec3(0, 0, 0), Vec3(0, 0, 1), .2),
        ))
        zero = BonePose(Vec3(0, 0, 0))
        clip = AnimationClip("idle", (
            AnimationKeyframe(0, (zero,)),
            AnimationKeyframe(1000, (zero,)),
        ))
        params = dict(
            world_axes=AXIS, cell_x=0, cell_y=1,
            wind_field=WindField((WindLayer(0, WindVector(0, 0)),)),
            clouds=(), time_s=0, delta_s=.05,
            skeleton=skeleton, animation=clip, animation_time_ms=200,
            era="early_3d", fps=60,
            evidence=(Percept("npc", "character", True, 1, .9, HASH),),
            world_goal_kind="character", available_actions=("inspect", "interact"),
            weather=Weather(Vec3(0, 0, 0), 20),
            character_state=CharacterState(Vec3(0, 0, .5),
                                           Vec3(0, 0, 0), .5, 70),
            collision_surfaces=(CollisionPlane(
                "ceiling", Vec3(0, 0, .75), Vec3(0, 0, -1)),),
            desired_character_velocity=Vec3(0, 0, 0),
        )
        original = compile_frontier_scene(**params)
        inverted = compile_frontier_scene(
            **params, world_variant=WorldVariant(WorldFamily.INVERSE, intensity=1))
        self.assertGreater(inverted.manifest["character_physics"]["velocity"][2],
                           original.manifest["character_physics"]["velocity"][2])
        ethereal = compile_frontier_scene(
            **params, world_variant=WorldVariant(WorldFamily.ETHEREAL, intensity=1))
        self.assertTrue(ethereal.manifest["world_variant"]["character_collision_ethereal_pass_through"])
        self.assertFalse(ethereal.manifest["character_physics"]["impacts"])

    def test_60fps_world_motion_lighting_candidate(self):
        skeleton = CharacterSkeleton((
            Bone("root", -1, Vec3(0, 0, 0), Vec3(0, 0, 1.2), .25),
        ))
        zero = BonePose(Vec3(0, 0, 0))
        walk = BonePose(Vec3(.1, 0, 0))
        animation = AnimationClip("walk", (
            AnimationKeyframe(0, (zero,)), AnimationKeyframe(1000, (walk,)),
        ))
        config = dict(
            world_axes=AXIS, cell_x=0, cell_y=1,
            wind_field=WindField((WindLayer(0, WindVector(5, 0)),)),
            clouds=(Cloud("storm", 5, 3, 100, .7),),
            time_s=0, delta_s=.05, skeleton=skeleton, animation=animation,
            animation_time_ms=500, era="fixed_3d", fps=60,
            evidence=(Percept("npc", "character", True, 1, .9, HASH),),
            world_goal_kind="character", available_actions=("inspect", "interact"),
            world_variant=WorldVariant(WorldFamily.CELESTIAL),
            camera=CameraSpec(ProjectionMode.DEPTH_29),
            weather=Weather(Vec3(5, 0, 0), -5, precipitation_mm_h=100),
            character_state=CharacterState(Vec3(0, 0, .5),
                                           Vec3(0, 0, -2), .5, 70),
            collision_surfaces=(CollisionPlane(
                "floor", Vec3(0, 0, 0), Vec3(0, 0, 1)),),
            desired_character_velocity=Vec3(2, 0, 0),
            environment_state=EnvironmentalState(),
            structures=(StructureState("home", "wood", 14),),
            lighting_surfaces=(SurfaceSample("ground", Vec3(0, 0, 0),
                                             Vec3(0, 0, 1)),),
            light_sources=(LightSource("sun", Vec3(0, 0, 10), 20),),
            light_occluders=(RayOccluder("npc", "character",
                                         Vec3(0, 0, 5), "sphere"),),
        )
        a = compile_frontier_scene(**config)
        b = compile_frontier_scene(**config)
        self.assertEqual(a.manifest_digest, b.manifest_digest)
        self.assertFalse(a.approved_for_runtime)
        self.assertEqual(a.manifest["render"]["fps"], 60)
        self.assertEqual(a.manifest["projection"]["mode"], "2.9d")
        self.assertEqual(a.manifest["world_variant"]["family"], "celestial")
        self.assertTrue(a.manifest["character_physics"]["impacts"])
        self.assertTrue(a.manifest["ray_lighting"][0]["character_occluders"])
        self.assertEqual(a.manifest["structures"][0]["id"], "home")


if __name__ == "__main__":
    unittest.main()
