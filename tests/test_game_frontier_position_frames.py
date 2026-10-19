"""Permissioned GNSS/survey and double-verified GDD per-frame progress."""
import unittest
from dataclasses import replace
from math import cos, degrees, radians

from skeleton.jeeves.game_frontier_geoposition import (
    PositionError,LocationConsent,DeviceGPSFix,SurveyControl,SurveySighting,
    ingest_host_gps,solve_control_survey,reconcile_live_and_survey,
    EARTH_RADIUS_M,
)
from skeleton.jeeves.game_frontier_frame_coherence import (
    FrameCoherenceError,FrameObject,GDDFrameNote,
    bind_signed_gdd,advance_frame,verify_frame,ai_design_context,
)
from skeleton.ai.game_builder.story_canon_fabric import (
    BIBLE,story_bible_template,sign,
)
from skeleton.jeeves.game_frontier_production import Vec3


def gdd():
    b=story_bible_template("frontier")
    b.update({
        "title":"The Wind Islands",
        "story":{"premise":"A floating world navigated by instruments.",
                 "conflict":"The weather threatens all routes.",
                 "themes":["navigation"],"planned_chapters":100,"planned_acts":1000},
        "world":{"era":"hybrid","geography":"Sky islands and sea trenches.",
                 "laws":["Gravity is downward in normal realms.",
                         "Weather and wind change flight routes.",
                         "Character appearances remain in canon."]},
        "rights_reviewed":True,
    })
    return sign(b,BIBLE)


def grant():
    return LocationConsent("session-alpha","navigation",
                           "foreground_precise_session",1000,100000,True)


def fix(timestamp=5000,seq=1,lat=60.,lon=10.,accuracy=3):
    return DeviceGPSFix(lat,lon,830,accuracy,4,timestamp,seq)


def objects(x=0.):
    return (FrameObject("hero",Vec3(x,0,1),Vec3(6,0,0),"a"*64),
            FrameObject("island",Vec3(65,0,10),Vec3(0,0,0),"b"*64))


class LiveGPSTests(unittest.TestCase):
    def test_explicit_foreground_permission_and_live_receipt(self):
        reading=ingest_host_gps(fix(),grant(),now_ms=5010)
        self.assertEqual(reading.latitude_deg,60)
        public=reading.public_receipt()
        self.assertFalse(public["retains_coordinates"])
        self.assertNotIn("latitude_deg",public)
        self.assertNotIn("longitude_deg",public)
        self.assertEqual(public["accuracy_m"],3)

    def test_missing_consent_fails_closed(self):
        with self.assertRaises(PositionError):
            LocationConsent("session-alpha","navigation",
                            "foreground_precise_session",0,1000,False)
        with self.assertRaises(PositionError):
            ingest_host_gps(fix(),grant(),now_ms=100001)

    def test_stale_future_low_accuracy_and_replay_rejected(self):
        with self.assertRaises(PositionError):
            ingest_host_gps(fix(timestamp=5000),grant(),now_ms=30000)
        with self.assertRaises(PositionError):
            ingest_host_gps(fix(timestamp=11000),grant(),now_ms=10000)
        with self.assertRaises(PositionError):
            ingest_host_gps(fix(accuracy=300),grant(),now_ms=5000)
        with self.assertRaises(PositionError):
            ingest_host_gps(fix(6000,1),grant(),now_ms=6000,prior=fix())

    def test_gps_teleport_rejected_but_motion_allowed(self):
        prior=fix()
        moving=fix(7000,2,60.00001,10.)
        got=ingest_host_gps(moving,grant(),now_ms=7000,prior=prior)
        self.assertEqual(got.sequence,2)
        with self.assertRaises(PositionError):
            ingest_host_gps(fix(7000,2,61,10),grant(),now_ms=7000,prior=prior)


class SurveyTests(unittest.TestCase):
    def stations(self):
        delta=degrees(100/EARTH_RADIUS_M)
        east=degrees(100/(EARTH_RADIUS_M*cos(radians(60))))
        c=(SurveyControl("north",60+delta,10,830,True),
           SurveyControl("east",60,10+east,830,True))
        s=(SurveySighting("north",0,0.1,horizontal_range_m=100),
           SurveySighting("east",90,0.1,horizontal_range_m=100))
        return c,s

    def test_orthogonal_verified_controls_yield_position(self):
        c,s=self.stations()
        result=solve_control_survey(c,s)
        self.assertAlmostEqual(result.latitude_deg,60,places=5)
        self.assertAlmostEqual(result.longitude_deg,10,places=5)
        self.assertIsNone(result.altitude_m)
        self.assertAlmostEqual(result.geometry_angle_deg,90,places=3)
        self.assertLess(result.rms_cross_track_m,1e-6)
        self.assertGreater(result.estimated_horizontal_uncertainty_m,0)
        self.assertFalse(result.public_receipt()["retains_coordinates"])
        matched=reconcile_live_and_survey(
            ingest_host_gps(fix(),grant(),now_ms=5000),result)
        self.assertTrue(matched["consistent"])
        self.assertTrue(matched["coordinates_redacted"])

    def test_parallel_bearings_and_unverified_controls_rejected(self):
        c,s=self.stations()
        with self.assertRaises(PositionError):
            solve_control_survey(c,(
                SurveySighting("north",0,.1),
                SurveySighting("east",0,.1)))
        with self.assertRaises(PositionError):
            SurveyControl("unverified",60,10,0,False)

    def test_conflicting_range_rejected(self):
        c,s=self.stations()
        with self.assertRaises(PositionError):
            solve_control_survey(c,(s[0],replace(s[1],horizontal_range_m=1000)))

    def test_survey_disagreement_is_explicit_not_silently_blended(self):
        c,s=self.stations()
        surveyed=solve_control_survey(c,s)
        live=ingest_host_gps(fix(lat=60.003),grant(),now_ms=5000)
        result=reconcile_live_and_survey(live,surveyed)
        self.assertFalse(result["consistent"])


class FrameVerificationTests(unittest.TestCase):
    def test_signed_story_source_required(self):
        bible=gdd()
        anchor=bind_signed_gdd(bible)
        self.assertEqual(anchor.source_digest,bible["digest"])
        altered=dict(bible)
        altered["title"]="unverified change"
        with self.assertRaises(FrameCoherenceError):
            bind_signed_gdd(altered)

    def test_30_50_60_120_independent_receipts(self):
        anchor=bind_signed_gdd(gdd())
        for fps in (30,50,60,120):
            zero=advance_frame(frame_index=0,fps=fps,gdd=anchor,objects=objects())
            first=advance_frame(
                frame_index=1,fps=fps,gdd=anchor,
                previous=zero,objects=objects(6/fps),
                notes=(GDDFrameNote(1,"weather",
                                    "Wind changes aerial transit paths."),))
            self.assertEqual(verify_frame(first,anchor,previous=zero),(True,True))
            self.assertNotEqual(first.receipt_digest,zero.receipt_digest)
            self.assertEqual(len(first.chunks),2)
            ctx=ai_design_context(anchor,(zero,first))
            self.assertEqual(ctx["notes"][0]["source_world_law_index"],1)
            self.assertTrue(ctx["requires_human_canon_approval"])
            self.assertEqual(ctx["final_verified_frame"],1)
            self.assertEqual(first.note_from_previous[0].author_kind,"ai_proposal")

    def test_chunk_migration_continuity_and_dual_integrity(self):
        anchor=bind_signed_gdd(gdd())
        a=(FrameObject("hero",Vec3(31.95,0,1),Vec3(6,0,0),"a"*64),)
        b=(FrameObject("hero",Vec3(32.05,0,1),Vec3(6,0,0),"a"*64),)
        first=advance_frame(frame_index=0,fps=60,gdd=anchor,objects=a)
        next=advance_frame(frame_index=1,fps=60,gdd=anchor,objects=b,
                           previous=first)
        self.assertNotEqual(first.chunks[0].chunk_key,next.chunks[0].chunk_key)
        self.assertEqual(verify_frame(next,anchor,previous=first),(True,True))

    def test_corrupt_geometry_or_prior_digest_refused(self):
        anchor=bind_signed_gdd(gdd())
        zero=advance_frame(frame_index=0,fps=60,gdd=anchor,objects=objects())
        modified=replace(zero,receipt_digest="0"*64)
        self.assertEqual(verify_frame(modified,anchor)[0],False)
        with self.assertRaises(FrameCoherenceError):
            advance_frame(frame_index=2,fps=60,gdd=anchor,
                          objects=objects(.2),previous=zero)
        with self.assertRaises(FrameCoherenceError):
            advance_frame(frame_index=1,fps=60,gdd=anchor,
                          objects=objects(99),previous=zero)

    def test_gdd_note_cannot_invent_law(self):
        anchor=bind_signed_gdd(gdd())
        zero=advance_frame(frame_index=0,fps=60,gdd=anchor,objects=objects())
        with self.assertRaises(FrameCoherenceError):
            advance_frame(frame_index=1,fps=60,gdd=anchor,
                          objects=objects(.1),previous=zero,
                          notes=(GDDFrameNote(999,"narrative","new canon"),))

    def test_ai_context_rejects_mismatched_frame_chain(self):
        anchor=bind_signed_gdd(gdd())
        zero=advance_frame(frame_index=0,fps=60,gdd=anchor,objects=objects())
        one=advance_frame(frame_index=1,fps=60,gdd=anchor,
                          objects=objects(.1),previous=zero)
        with self.assertRaises(FrameCoherenceError):
            ai_design_context(anchor,(one,))
        with self.assertRaises(FrameCoherenceError):
            ai_design_context(anchor,(zero,replace(one,previous_digest="0"*64)))



class SceneAndStudioIntegrationTests(unittest.TestCase):
    def test_permissioned_live_survey_and_gdd_frames_enter_scene_redacted(self):
        from tests.test_game_frontier_advanced_scene import scene_params
        from skeleton.jeeves.game_frontier import compile_frontier_scene
        import json
        source=bind_signed_gdd(gdd())
        result=compile_frontier_scene(**scene_params(),
            gps_fix=fix(),gps_consent=grant(),gps_now_ms=5000,
            survey_controls=SurveyTests().stations()[0],
            survey_sightings=SurveyTests().stations()[1],
            frame_gdd=source,frame_index=0,frame_objects=objects(),
        )
        scene=result.manifest
        self.assertTrue(scene["position_fix"]["coordinates_redacted"])
        self.assertTrue(scene["position_fix"]["coherence"]["consistent"])
        self.assertTrue(scene["frame_progress"]["double_verified"])
        self.assertEqual(scene["frame_progress"]["chunk_count"],2)
        self.assertFalse(result.approved_for_runtime)
        json_location=json.dumps(scene["position_fix"])
        self.assertNotIn("latitude_deg",json_location)
        self.assertNotIn("longitude_deg",json_location)
        self.assertNotIn('"altitude_m"',json_location)

    def test_scene_rejects_unsigned_gdd_and_missing_location_permission(self):
        from tests.test_game_frontier_advanced_scene import scene_params
        from skeleton.jeeves.game_frontier import compile_frontier_scene
        with self.assertRaises(ValueError):
            compile_frontier_scene(**scene_params(),gps_fix=fix())
        with self.assertRaises(ValueError):
            compile_frontier_scene(**scene_params(),frame_index=0,
                                   frame_objects=objects())

    def test_studio_progress_uses_actual_prefabs_and_signed_gdd_ai_notes(self):
        from skeleton.forge.game_frontier_studio import (
            StudioProject,StudioPrefab,StudioPlacement,MapLayer,
            compile_studio_frame,
        )
        from skeleton.jeeves.game_frontier_worlds import ProjectionMode,WorldFamily
        project=StudioProject("frontier","modern",
            ProjectionMode.DEPTH_29,WorldFamily.CELESTIAL,
            (MapLayer("floor",1,1,("grass",),(0,)),),
            prefabs=(StudioPrefab("hero","character","modern","a"*64),),
            placements=(StudioPlacement("hero",0,0,1),))
        zero=compile_studio_frame(project,gdd(),frame_index=0,fps=60,
            entity_velocities={"hero:0":(6.,0.,0.)})
        next_project=replace(project,placements=(StudioPlacement("hero",.1,0,1),))
        one=compile_studio_frame(
            next_project,gdd(),frame_index=1,fps=60,
            preceding_frames=(zero["record"],),
            entity_velocities={"hero:0":(6.,0.,0.)},
            notes=(GDDFrameNote(1,"design_context",
               "Climbing through the gust requires slower motion."),))
        self.assertTrue(one["verified_a"] and one["verified_b"])
        self.assertEqual(one["note_count"],1)
        self.assertEqual(one["gdd_ai_context"]["notes"][0]["source_world_law_index"],1)
        self.assertEqual(one["gdd_ai_context"]["authority"],
                         "proposed_ai_context_not_signed_gdd")
        self.assertEqual(one["authority"],"studio_preview_proposed_not_engine_mutated")

    def test_studio_refuses_cross_project_gdd(self):
        from skeleton.forge.game_frontier_studio import (
            StudioProject,StudioPrefab,StudioPlacement,MapLayer,
            compile_studio_frame,StudioError,
        )
        from skeleton.jeeves.game_frontier_worlds import ProjectionMode,WorldFamily
        project=StudioProject("other","modern",
            ProjectionMode.DEPTH_29,WorldFamily.CELESTIAL,
            (MapLayer("floor",1,1,("grass",),(0,)),),
            prefabs=(StudioPrefab("hero","character","modern","a"*64),),
            placements=(StudioPlacement("hero",0,0,1),))
        with self.assertRaises(StudioError):
            compile_studio_frame(project,gdd(),frame_index=0,fps=60)



if __name__=="__main__":
    unittest.main()
