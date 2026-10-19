"""Studio-native Godot 3D trigger authoring, event integrity and source exports."""
import unittest
from dataclasses import replace

from skeleton.forge.game_frontier_studio import (
    StudioProject,StudioPrefab,StudioEvent,StudioPlacement,StudioTriggerVolume,
    MapLayer,StudioError,compile_studio_gameplay_zones,compile_studio_project,STUDIO_TOOLS,
)
from skeleton.jeeves.game_frontier_worlds import ProjectionMode,WorldFamily
from skeleton.jeeves.game_frontier_native_zones import normalize_gameplay_zones


def authored(action="start_quest",target="hero",condition=""):
    return StudioProject(
        "realm","early_3d",ProjectionMode.DEPTH_27,WorldFamily.MYTHIC,
        (MapLayer("floor",2,2,("grass",),(0,0,0,0)),),
        (StudioPrefab("hero","character","early_3d","a"*64),),
        (StudioPlacement("hero",2.,3.,4.),),
        (StudioEvent("begin","enter",condition,False,action,target,"chapter-1"),),
        native_trigger_volumes=(
            StudioTriggerVolume("quest_volume","hero:0","begin",1.5,(1.,0.,-.5)),
        ),
    )


class StudioZoneAuthoringTests(unittest.TestCase):
    def test_real_editor_placement_event_and_godot_source_compilation(self):
        project=authored()
        report=compile_studio_gameplay_zones(project)
        zone=report["zones"][0]
        self.assertEqual(report["zone_count"],1)
        self.assertEqual(zone["center_xyz_m"],[3.,3.,3.5])
        self.assertEqual(zone["actor_id"],"hero:0")
        self.assertEqual(zone["action_kind"],"start_quest")
        self.assertEqual(zone["event_page_id"],"begin")
        self.assertEqual(report,compile_studio_gameplay_zones(project))
        self.assertEqual(normalize_gameplay_zones(report["zones"]),report["zones"])
        self.assertEqual(len(report["receipt_digest"]),64)
        self.assertEqual(len(report["studio_manifest_digest"]),64)
        self.assertEqual(compile_studio_project(project)["native_trigger_volumes"][0][
            "zone_id"],"quest_volume")
        self.assertIn("native_3d_trigger_volume_editor",STUDIO_TOOLS)

    def test_audio_and_dialogue_use_registered_engine_candidate_actions(self):
        for editor_action,engine_action in (
            ("show_dialogue","show_dialogue"),("play_audio","spatial_audio"),
            ("start_quest","start_quest")):
            with self.subTest(action=editor_action):
                project=authored(action=editor_action)
                self.assertEqual(compile_studio_gameplay_zones(project)[
                    "zones"][0]["action_kind"],engine_action)

    def test_invalid_actor_pages_conditions_and_unsafe_actions_fail_closed(self):
        valid=authored()
        for bad_event in (
            StudioEvent("begin","exit","",False,"start_quest","hero","q"),
            StudioEvent("begin","enter","quest_flag",True,"start_quest","hero","q"),
            StudioEvent("begin","enter","",False,"open_portal","hero","q"),
            StudioEvent("begin","enter","",False,"start_quest","villain","q"),
        ):
            with self.subTest(event=bad_event),self.assertRaises(StudioError):
                replace(valid,events=(bad_event,))
        for zone in (
            StudioTriggerVolume("zone2","npc:8","begin",1.),
            StudioTriggerVolume("zone3","hero:0","unknown",1.),
        ):
            with self.assertRaises(StudioError):
                replace(valid,native_trigger_volumes=(zone,))
        with self.assertRaises(StudioError):
            replace(valid,native_trigger_volumes=valid.native_trigger_volumes*2)

    def test_volume_validation_bounds_and_bad_coordinates(self):
        for kwargs in (
            {"radius_m":0.},
            {"radius_m":float("nan")},
            {"actor_entity_id":"../../etc"},
            {"offset_xyz_m":(0.,float("inf"),0.)},
            {"offset_xyz_m":(0.,0.)},
        ):
            source=dict(zone_id="valid",actor_entity_id="hero:0",
                        event_page_id="begin",radius_m=1.)
            source.update(kwargs)
            with self.assertRaises(StudioError):
                StudioTriggerVolume(**source)

    def test_legacy_studio_without_native_zones_keeps_existing_workflow(self):
        p=authored()
        legacy=replace(p,native_trigger_volumes=(),events=())
        a=compile_studio_gameplay_zones(legacy)
        self.assertEqual(a["zones"],[])
        self.assertEqual(a["zone_count"],0)
        self.assertEqual(a,compile_studio_gameplay_zones(legacy))
