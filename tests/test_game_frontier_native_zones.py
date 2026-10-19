"""Adversarial native RPG zone geometry, source and transition receipts."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.jeeves.game_frontier_native_zones import (
    ZONE_SCHEMA,EVENT_AUTHORITY,NativeZoneError,
    normalize_gameplay_zones,inspect_native_gameplay_zones,
)

ZONES=({"id":"spawn","actor_id":"hero",
        "center_xyz_m":[0.,0.,30.],"radius_m":1.,
        "event_page_id":"on_spawn","action_kind":"show_dialogue"},
       {"id":"river","actor_id":"hero",
        "center_xyz_m":[3.,0.,30.],"radius_m":.7,
        "event_page_id":"river_quest","action_kind":"start_quest"})

def frame(tick:int,x:float,previous_x:float|None=None)->dict:
    zones=normalize_gameplay_zones(ZONES,allowed_actors={"hero"})
    occ=[{"zone_id":z["id"],"actor_id":"hero"} for z in zones
         if (x-z["center_xyz_m"][0])**2<=z["radius_m"]**2]
    prev=[{"zone_id":z["id"],"actor_id":"hero"} for z in zones
          if previous_x is not None and
          (previous_x-z["center_xyz_m"][0])**2<=z["radius_m"]**2]
    actions=[]
    for name in occ:
        if name not in prev:
            z=next(z for z in zones if z["id"]==name["zone_id"])
            actions.append({**name,"transition":"enter","event_page_id":z["event_page_id"],
                            "action_kind":z["action_kind"],"authority":EVENT_AUTHORITY})
    for name in prev:
        if name not in occ:
            z=next(z for z in zones if z["id"]==name["zone_id"])
            actions.append({**name,"transition":"exit","event_page_id":z["event_page_id"],
                            "action_kind":z["action_kind"],"authority":EVENT_AUTHORITY})
    actions.sort(key=lambda x:(x["zone_id"],x["actor_id"],x["transition"]))
    return {
        "native_tick":tick,"native_zone_schema":ZONE_SCHEMA,
        "gameplay_zones":zones,
        "actors":[{"id":"hero","world_xyz_m":[x,0.,30.]}],
        "native_zone_occupancy":occ,
        "native_zone_events":actions,
        "scene_candidate_digest":"a"*64,"signed_gdd_digest":"b"*64,
    }


class ZoneRuntimeTests(unittest.TestCase):
    def test_enter_exit_checkpoint_and_quest_candidates(self):
        frames=[frame(0,0.),frame(1,2.,0.),frame(2,3.,2.)]
        proof0=inspect_native_gameplay_zones(frames[0],expected_catalog=ZONES)
        proof1=inspect_native_gameplay_zones(frames[1],previous=frames[0],
                                               expected_catalog=ZONES)
        proof2=inspect_native_gameplay_zones(frames[2],previous=frames[1])
        self.assertEqual(proof0["event_count"],1)
        self.assertEqual(proof1["event_count"],1)
        self.assertEqual(proof2["event_count"],1)
        self.assertEqual(frames[2]["native_zone_events"][0]["action_kind"],"start_quest")
        self.assertEqual(len(proof2["receipt_digest"]),64)
        self.assertTrue(proof2["transition_verified"])
        self.assertEqual(proof2,inspect_native_gameplay_zones(frames[2],previous=frames[1]))

    def test_legacy_requires_no_false_zone_proof(self):
        legacy={"native_tick":0,"actors":[{"id":"hero","world_xyz_m":[0,0,30]}]}
        self.assertIsNone(inspect_native_gameplay_zones(legacy))
        with self.assertRaises(NativeZoneError):
            inspect_native_gameplay_zones(legacy,expected_catalog=ZONES)

    def test_tampered_position_catalog_event_or_membership_rejected(self):
        prior=frame(0,0.)
        for bad in (
            lambda x:x["actors"][0].update(world_xyz_m=[0.,0.,30.]),
            lambda x:x["native_zone_occupancy"].append({"zone_id":"forged","actor_id":"hero"}),
            lambda x:x["native_zone_events"].clear(),
            lambda x:x["native_zone_events"][0].update(action_kind="world_portal"),
            lambda x:x["gameplay_zones"][0].update(radius_m=99.),
            lambda x:x["gameplay_zones"][0].update(actor_id="villain"),
            lambda x:x.update(native_zone_schema="unknown"),
        ):
            sample=frame(1,2.,0.)
            bad(sample)
            with self.subTest(sample=repr(sample)[:120]),self.assertRaises(NativeZoneError):
                inspect_native_gameplay_zones(
                    sample,previous=prior,expected_catalog=ZONES)

    def test_catalog_guards_and_no_mutation_actions(self):
        for zone in (
            {**ZONES[0],"action_kind":"spawn_prefab"},
            {**ZONES[0],"center_xyz_m":[float("nan"),0,0]},
            {**ZONES[0],"radius_m":-1},
            {**ZONES[0],"id":"../../etc"},
            {**ZONES[0],"actor_id":"unverified"},
        ):
            with self.assertRaises(NativeZoneError):
                normalize_gameplay_zones([zone],allowed_actors={"hero"})
        with self.assertRaises(NativeZoneError):
            normalize_gameplay_zones([ZONES[0],ZONES[0]])
        with self.assertRaises(NativeZoneError):
            normalize_gameplay_zones([ZONES[0]]*65)

    def test_out_of_order_frames_and_source_zone_switch_rejected(self):
        old=frame(0,0.)
        future=frame(2,3.,0.)
        with self.assertRaises(NativeZoneError):
            inspect_native_gameplay_zones(future,previous=old)
        changed=frame(1,2.,0.)
        changed["gameplay_zones"][0]["radius_m"]=2.
        with self.assertRaises(NativeZoneError):
            inspect_native_gameplay_zones(changed,previous=old)

class NativeZoneJournalTests(unittest.TestCase):
    def test_engine_source_ingest_event_replay_timeline_and_fork(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from skeleton.jeeves.game_frontier_frame_coherence import bind_signed_gdd
        from skeleton.jeeves.game_frontier_native_capture import (
            GodotPhysicsCaptureIngestor, NativeObservationError,
        )
        from skeleton.jeeves.game_frontier_receipt_journal import FrameReceiptJournal
        from tests.test_game_frontier_native_chunks import sample
        from tests.test_game_frontier_position_frames import gdd
        anchor=bind_signed_gdd(gdd())
        catalog=({
            "id":"cross32", "actor_id":"hero",
            "center_xyz_m":[31.895,-1.,30.],"radius_m":.1,
            "event_page_id":"cross_border","action_kind":"show_dialogue",
        },)
        zones=normalize_gameplay_zones(catalog,allowed_actors={"hero","npc","island"})
        def native(tick):
            record=sample(tick,anchor.source_digest)
            record["native_zone_schema"]=ZONE_SCHEMA
            record["gameplay_zones"]=zones
            occupied=([{"zone_id":"cross32","actor_id":"hero"}] if tick==0 else [])
            record["native_zone_occupancy"]=occupied
            record["native_zone_events"]=[{
                "zone_id":"cross32","actor_id":"hero",
                "transition":"enter" if tick==0 else "exit",
                "event_page_id":"cross_border","action_kind":"show_dialogue",
                "authority":EVENT_AUTHORITY,
            }]
            return record
        with TemporaryDirectory() as name:
            db=Path(name)/"zones.sqlite"
            with FrameReceiptJournal(db,anchor) as journal:
                ingest=GodotPhysicsCaptureIngestor(
                    journal,candidate_digest="d"*64,
                    allowed_assets={"hero":"a"*64,"npc":"b"*64,"island":"c"*64},
                    expected_gameplay_zones=catalog)
                first=ingest.ingest(native(0))
                second=ingest.ingest(native(1))
                self.assertEqual(second["frame"],1)
                self.assertEqual(journal.replay()["verified_frames"],2)
                self.assertEqual(journal.native_chunk_transitions(1)[
                    "native_zone_event_count"],1)
                page=journal.evidence_page(actor_id="hero",limit=2)
                self.assertEqual([x["native_zone_event_proposals"][0]["transition"]
                                  for x in page["entries"]],["enter","exit"])
                self.assertTrue(all(x["native_zone_evidence_digest"]
                                    for x in page["entries"]))
                journal.fork("rollback_zone",through=0)
                corrupt=native(2)
                corrupt["native_zone_events"]=[]
                with self.assertRaises(NativeObservationError):
                    ingest.ingest(corrupt)
                self.assertEqual(journal.stats()["head"],1)
            with FrameReceiptJournal(db,anchor,track="rollback_zone") as restored:
                self.assertEqual(restored.replay()["verified_frames"],1)
                self.assertEqual(restored.evidence_page()["entries"][0][
                    "native_zone_event_proposals"][0]["transition"],"enter")

    def test_godot_smoke_really_exports_gameplay_zone_sources(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import json
        from scripts.build_game_frontier_smoke import build_smoke_project
        with TemporaryDirectory() as root:
            target=Path(root)
            build_smoke_project(target,frames=20)
            source=json.loads((target/"frontier/data/scene.json").read_text())
            zone=source["native_capture"]["gameplay_zones"][0]
            self.assertEqual(zone["actor_id"],"hero")
            self.assertEqual(zone["action_kind"],"show_dialogue")
            code=(target/"frontier/frontier_scene.gd").read_text()
            for marker in ("Area3D.new()", "_native_zone_event",
                           "native_zone_occupancy", "native_zone_events",
                           "proposal_only_no_world_mutation"):
                self.assertIn(marker,code)

    def test_exporter_rejects_unauthorized_zone_mutations(self):
        from skeleton.jeeves.game_frontier import compile_frontier_scene
        from skeleton.jeeves.game_frontier_frame_coherence import bind_signed_gdd,FrameObject
        from skeleton.jeeves.game_frontier_production import Vec3
        from skeleton.forge.game_frontier_godot import (
            emit_frontier_godot_overlay,FrontierGodotError,
        )
        from tests.test_game_frontier_position_frames import gdd
        from tests.test_game_frontier_advanced_scene import scene_params
        cfg=scene_params()
        cfg.update(frame_gdd=bind_signed_gdd(gdd()),frame_index=0,
            frame_objects=(FrameObject("hero",Vec3(0,0,30),
                                      Vec3(0,0,-20),"a"*64),))
        scene=compile_frontier_scene(**cfg)
        forged={**ZONES[0],"actor_id":"unlisted"}
        with self.assertRaises(FrontierGodotError):
            emit_frontier_godot_overlay(scene,
                enable_native_capture=True,native_gameplay_zones=(forged,))
        with self.assertRaises(FrontierGodotError):
            emit_frontier_godot_overlay(scene,native_gameplay_zones=(ZONES[0],))
