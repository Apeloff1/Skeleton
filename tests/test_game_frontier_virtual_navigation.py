"""Fully virtual game GPS, landmark surveying, routes and per-frame GDD QA."""
from __future__ import annotations

from dataclasses import replace
import math
import unittest

from skeleton.jeeves.game_frontier_production import Vec3
from skeleton.jeeves.game_frontier_virtual_navigation import (
    GameMap, VirtualBeacon, VirtualRange, VirtualSurveyControl,
    VirtualSurveySighting, VirtualNavigationRequest, VirtualPositionError,
    simulated_ranges, solve_virtual_gps, solve_virtual_survey, map_route,
    compose_virtual_navigation,
)
from skeleton.jeeves.game_frontier_frame_coherence import (
    FrameObject, GDDFrameNote, advance_frame, bind_signed_gdd,
)
from skeleton.forge.game_frontier_studio import (
    StudioProject, StudioPrefab, StudioPlacement, MapLayer,
    compile_studio_frame, StudioError,
)
from skeleton.jeeves.game_frontier_worlds import ProjectionMode, WorldFamily
from skeleton.jeeves.game_frontier_realism import audit_scene_realism
from tests.test_game_frontier_position_frames import gdd
from tests.test_game_frontier_advanced_scene import scene_params
from skeleton.jeeves.game_frontier import compile_frontier_scene
from skeleton.forge.game_frontier_godot import emit_frontier_godot_overlay


PLAYER=Vec3(25,25,5)


def world():
    return GameMap("frontier","original",16,16,10,blocked_tiles=((3,2),(3,3)))


def network():
    return (
        VirtualBeacon("northwest",Vec3(-200,-200,100),.001),
        VirtualBeacon("northeast",Vec3(200,-200,200),.001),
        VirtualBeacon("southwest",Vec3(-200,200,200),.001),
        VirtualBeacon("underground",Vec3(200,200,-100),.001),
        VirtualBeacon("zenith",Vec3(0,0,400),.001),
    )


def stations(player=PLAYER):
    positions = (
        ("tower",Vec3(20,0,0)),
        ("gate",Vec3(60,35,0)),
        ("shrine",Vec3(0,40,0)),
    )
    return (
        tuple(VirtualSurveyControl(name,pos) for name,pos in positions),
        tuple(VirtualSurveySighting(
            name,math.degrees(math.atan2(
                player.x-pos.x,player.y-pos.y)) % 360,
            angular_error_deg=.01,
            elevation_deg=math.degrees(math.atan2(
                player.z-pos.z,
                math.hypot(player.x-pos.x,player.y-pos.y))))
            for name,pos in positions),
    )


def request(player=PLAYER, *, with_survey=True):
    controls,sightings=stations(player) if with_survey else ((),())
    return VirtualNavigationRequest(
        world(),"hero",player,network(),noise_seed=2,
        controls=controls,sightings=sightings,destination_tile=(5,2))


class MapCoordinateTests(unittest.TestCase):
    def test_rotated_and_unrotated_map_roundtrip(self):
        for degrees in (0,30,90,-45):
            m=GameMap("other","celestial",10,10,5,
                      origin=Vec3(100,200,900),
                      north_rotation_deg=degrees)
            p=m.tile_world(4,6)
            self.assertEqual(m.grid(p),(4,6))
            fictional=m.fictional_coordinates(p)
            self.assertEqual(len(fictional),2)
            self.assertLess(abs(fictional[0]),1)
            self.assertLess(abs(fictional[1]),1)
            self.assertEqual(m.identity(),m.identity())

    def test_blocked_tile_route_and_inaccessible_destinations(self):
        m=world()
        route=map_route(m,(2,2),(5,2))
        self.assertEqual(route.tiles[0],(2,2))
        self.assertEqual(route.tiles[-1],(5,2))
        self.assertNotIn((3,2),route.tiles)
        self.assertGreater(route.length_m,30)
        with self.assertRaises(VirtualPositionError):
            map_route(m,(2,2),(3,2))
        with self.assertRaises(VirtualPositionError):
            m.grid(Vec3(-1,0,0))


class VirtualGPSPhysicsTests(unittest.TestCase):
    def test_four_or_five_beacons_resolve_true_3d_position(self):
        stations_list=network()
        for selected in (stations_list[:4],stations_list):
            readings=simulated_ranges(PLAYER,selected,noise_seed=2)
            found=solve_virtual_gps(selected,readings)
            self.assertLess(math.dist(
                (found.position.x,found.position.y,found.position.z),
                (PLAYER.x,PLAYER.y,PLAYER.z)),.2)
            self.assertEqual(found.authority,"virtual_game_only_no_device_location")
            self.assertGreater(found.horizontal_uncertainty_m,0)

    def test_no_real_gps_permission_needed_and_deterministic(self):
        nav=request()
        first=compose_virtual_navigation(nav)
        self.assertEqual(first,compose_virtual_navigation(nav))
        self.assertFalse(first["device_location_used"])
        self.assertEqual(first["source"],"fictional_simulated_beacons_no_device_gps")
        self.assertEqual(first["fictional_datum"],"planet_local_enu_not_earth_wgs84")
        self.assertEqual(first["map_tile_xy"],[2,2])
        self.assertEqual(first["world_id"],"frontier")
        self.assertIsNotNone(first["route"])
        self.assertEqual(first["survey"]["consistent"],True)
        self.assertEqual(len(first["receipt_digest"]),64)

    def test_independent_virtual_landmark_survey_xy_and_z(self):
        controls,obs=stations()
        fix=solve_virtual_survey(controls,obs)
        self.assertTrue(fix.altitude_resolved)
        self.assertAlmostEqual(fix.position.x,PLAYER.x,places=5)
        self.assertAlmostEqual(fix.position.y,PLAYER.y,places=5)
        self.assertAlmostEqual(fix.position.z,PLAYER.z,places=5)

    def test_bad_ranges_parallel_geometry_and_signal_occlusion(self):
        beacons=network()
        ranges=simulated_ranges(PLAYER,beacons)
        with self.assertRaises(VirtualPositionError):
            solve_virtual_gps(beacons,ranges[:3])
        corrupt=replace(ranges[0],measured_range_m=10000)
        with self.assertRaises(VirtualPositionError):
            solve_virtual_gps(beacons,(corrupt,*ranges[1:]))
        planar=tuple(VirtualBeacon(f"s{i}",Vec3(i*10,i*4,0),.1)
                     for i in range(5))
        with self.assertRaises(VirtualPositionError):
            solve_virtual_gps(planar,simulated_ranges(PLAYER,planar))
        with self.assertRaises(VirtualPositionError):
            solve_virtual_gps(beacons,tuple(replace(s,blocked=True)
                              for s in ranges[:2])+ranges[2:4])

    def test_virtual_survey_tamper_and_disagreement_fail_closed(self):
        control,obs=stations()
        altered=replace(obs[1],bearing_from_station_deg=10)
        with self.assertRaises(VirtualPositionError):
            solve_virtual_survey(control,(obs[0],altered,obs[2]),
                                 maximum_residual_m=.5)
        with self.assertRaises(VirtualPositionError):
            VirtualSurveyControl("fake",Vec3(0,0,0),False)


class GDDNavigationFrameTests(unittest.TestCase):
    def test_two_verifier_frame_position_and_between_frame_ai_notes(self):
        source=bind_signed_gdd(gdd())
        for fps in (30,50,60,120):
            first=advance_frame(frame_index=0,fps=fps,gdd=source,
                objects=(FrameObject("hero",PLAYER,Vec3(6,0,0),"a"*64),))
            first_nav=compose_virtual_navigation(request(),frame=first,gdd=source)
            self.assertEqual(first_nav["frame_receipt_digest"],first.receipt_digest)
            shifted=PLAYER+Vec3(6/fps,0,0)
            second=advance_frame(frame_index=1,fps=fps,gdd=source,
                objects=(FrameObject("hero",shifted,Vec3(6,0,0),"a"*64),),
                previous=first,
                notes=(GDDFrameNote(1,"design_context",
                    "Virtual navigation tracks a weather-exposed sky island."),))
            second_nav=compose_virtual_navigation(
                request(shifted),frame=second,gdd=source,previous_frame=first)
            self.assertEqual(second_nav["gdd_digest"],source.source_digest)
            self.assertEqual(second_nav["frame_receipt_digest"],second.receipt_digest)
            with self.assertRaises(VirtualPositionError):
                compose_virtual_navigation(
                    request(),frame=second,gdd=source,previous_frame=first)

    def test_navigation_receipt_chain_rejects_map_swaps_and_tampering(self):
        signed=bind_signed_gdd(gdd())
        first=advance_frame(frame_index=0,fps=60,gdd=signed,
            objects=(FrameObject("hero",PLAYER,Vec3(6,0,0),"a"*64),))
        initial=compose_virtual_navigation(request(),frame=first,gdd=signed)
        actor=PLAYER+Vec3(.1,0,0)
        second=advance_frame(frame_index=1,fps=60,gdd=signed,
            objects=(FrameObject("hero",actor,Vec3(6,0,0),"a"*64),),
            previous=first,
            notes=(GDDFrameNote(1,"design_context",
                "Navigation fix and movement remain bound to the GDD."),))
        latest=compose_virtual_navigation(
            request(actor),frame=second,gdd=signed,previous_frame=first,
            previous_navigation=initial)
        self.assertEqual(latest["previous_navigation_receipt_digest"],
                         initial["receipt_digest"])
        self.assertEqual(latest["frame_index"],1)
        corrupt=dict(initial)
        corrupt["world_xyz_m"]=[1000,1000,1000]
        with self.assertRaises(VirtualPositionError):
            compose_virtual_navigation(
                request(actor),frame=second,gdd=signed,
                previous_frame=first,previous_navigation=corrupt)
        alternate=replace(request(actor),world=GameMap(
            "frontier","original",16,16,10,north_rotation_deg=30))
        with self.assertRaises(VirtualPositionError):
            compose_virtual_navigation(
                alternate,frame=second,gdd=signed,
                previous_frame=first,previous_navigation=initial)
        with self.assertRaises(VirtualPositionError):
            compose_virtual_navigation(request(actor),
                previous_navigation=initial)

    def test_scene_and_real_gps_sources_are_separate(self):
        anchor=bind_signed_gdd(gdd())
        frame_entities=(FrameObject("hero",PLAYER,Vec3(0,0,0),"a"*64),)
        scene=compile_frontier_scene(**scene_params(),frame_gdd=anchor,
            frame_index=0,frame_objects=frame_entities,
            virtual_navigation=request())
        values=scene.manifest
        self.assertIsNone(values["position_fix"])
        self.assertFalse(values["virtual_game_gps"]["device_location_used"])
        self.assertTrue(values["frame_progress"]["double_verified"])
        self.assertTrue(values["realism_audit"]["reference_checks_passed"])
        self.assertIn("virtual_game_gps",
                      values["realism_audit"]["participating_domains"])
        overlay=emit_frontier_godot_overlay(scene,cloud_path_duration_s=2)
        self.assertIn("VIRTUAL GAME GPS",overlay["frontier/frontier_scene.gd"])
        self.assertIn("VirtualMinimapPath",overlay["frontier/frontier_scene.gd"])
        import json
        self.assertEqual(json.loads(overlay["frontier/data/scene.json"])
                         ["virtual_game_gps"]["actor_id"],"hero")

    def test_auditor_rejects_navigation_privacy_or_frame_forgery(self):
        anchor=bind_signed_gdd(gdd())
        scene=compile_frontier_scene(**scene_params(),frame_gdd=anchor,
            frame_index=0,frame_objects=(
                FrameObject("hero",PLAYER,Vec3(0,0,0),"a"*64),),
            virtual_navigation=request())
        initial=scene.manifest
        for updates in (
            {"device_location_used":True},
            {"frame_receipt_digest":"0"*64},
            {"world_xyz_m":[9999,0,0]},
        ):
            forged=dict(initial)
            gps=dict(forged["virtual_game_gps"])
            gps.update(updates)
            forged["virtual_game_gps"]=gps
            result=audit_scene_realism(forged)
            self.assertFalse(result.reference_checks_passed)

    def test_studio_project_map_and_frame_binding(self):
        m=world()
        art=StudioPrefab("hero","character","modern","a"*64)
        studio=StudioProject("frontier","modern",ProjectionMode.DEPTH_29,
            WorldFamily.ORIGINAL,(MapLayer("terrain",1,1,("grass",),(0,)),),
            prefabs=(art,),placements=(StudioPlacement("hero",*(
                PLAYER.x,PLAYER.y,PLAYER.z)),),virtual_game_map=m)
        source=gdd()
        initial=compile_studio_frame(
            studio,source,frame_index=0,fps=60,
            virtual_navigation=replace(request(),actor_id="hero:0"),
            entity_velocities={"hero:0":(6.,0.,0.)})
        self.assertTrue(initial["verified_a"] and initial["verified_b"])
        self.assertEqual(initial["virtual_game_gps"]["map_tile_xy"],[2,2])
        self.assertEqual(initial["virtual_game_gps"]["frame_receipt_digest"],
                         initial["frame_receipt_digest"])
        moved=PLAYER+Vec3(.1,0,0)
        next_studio=replace(studio,placements=(
            StudioPlacement("hero",moved.x,moved.y,moved.z),))
        later=compile_studio_frame(next_studio,source,frame_index=1,fps=60,
            preceding_frames=(initial["record"],),
            virtual_navigation=replace(request(moved),actor_id="hero:0"),
            previous_virtual_navigation=initial["virtual_game_gps"],
            entity_velocities={"hero:0":(6.,0.,0.)},
            notes=(GDDFrameNote(1,"design_context",
                               "Navigation through gusty air continues."),))
        self.assertEqual(later["gdd_ai_context"]["final_verified_frame"],1)
        self.assertEqual(later["note_count"],1)
        self.assertEqual(later["virtual_game_gps"]["previous_navigation_receipt_digest"],
                         initial["virtual_game_gps"]["receipt_digest"])
        self.assertEqual(
            later["gdd_ai_context"]["verified_virtual_navigation"]["frame_receipt_digest"],
            later["frame_receipt_digest"])
        self.assertTrue(
            later["gdd_ai_context"]["verified_virtual_navigation"]["requires_human_canon_approval"])
        with self.assertRaises(StudioError):
            replace(studio,virtual_game_map=GameMap(
                "otherworld","original",10,10,1))


if __name__=="__main__":
    unittest.main()
