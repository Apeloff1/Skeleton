"""Godot native physics -> existing RPG event-page and GDD replay integration."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.forge.game_frontier_rpg_events import (
    RPGEventPage,RPGEventAction,EnvironmentalTrigger,
)
from skeleton.jeeves.game_frontier_native_rpg_bridge import (
    NativeRPGBridgeError,parse_native_rpg_pages,native_rpg_observations,
    evaluate_native_rpg_timeline,
)
from skeleton.jeeves.game_frontier_native_capture import GodotPhysicsCaptureIngestor
from skeleton.jeeves.game_frontier_receipt_journal import FrameReceiptJournal
from skeleton.jeeves.game_frontier_frame_coherence import bind_signed_gdd
from tests.test_game_frontier_native_chunks import sample
from tests.test_game_frontier_position_frames import gdd


def pages():
    return (
        RPGEventPage("falling",80,(
            EnvironmentalTrigger("fall_speed_mps","at_least",10.),),
            (RPGEventAction("show_dialogue","ui","hero","fall warning"),),
            repeat=False),
        RPGEventPage("contact",25,(
            EnvironmentalTrigger("native_contact_count","at_least",1.),),
            (RPGEventAction("trigger_impact_fx","world","hero","dust"),),
            cooldown_ms=100),
        RPGEventPage("missing_signal",-5,(
            EnvironmentalTrigger("rain_mm_h","above",1.),),
            (RPGEventAction("show_dialogue","ui","weather","raining"),)),
    )


class NativeRPGRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"native_event.sqlite"
        self.gdd=bind_signed_gdd(gdd())

    def journal(self,frames=8):
        j=FrameReceiptJournal(self.db,self.gdd)
        ingest=GodotPhysicsCaptureIngestor(
            j,candidate_digest="d"*64,
            allowed_assets={"hero":"a"*64,"npc":"b"*64,"island":"c"*64})
        for i in range(frames):
            ingest.ingest(sample(i,self.gdd.source_digest))
        return j

    def test_native_sensor_inventory_does_not_invent_weather_or_collision_impulse(self):
        record=sample(0,self.gdd.source_digest)
        observations=native_rpg_observations(record,actor_id="hero")
        self.assertEqual(observations["fall_speed_mps"],20.)
        self.assertEqual(observations["native_contact_count"],1.)
        self.assertEqual(observations["altitude_m"],30.)
        self.assertNotIn("rain_mm_h",observations)
        self.assertNotIn("impact_impulse_ns",observations)
        self.assertNotIn("native_kinetic_energy_j",observations)

    def test_priority_one_shot_cooldown_and_paged_source_replay(self):
        with self.journal() as journal:
            report=evaluate_native_rpg_timeline(
                journal,pages(),actor_id="hero",start_frame=3,limit=3)
            self.assertEqual(report["source_prefix_verified_frames"],6)
            self.assertEqual(len(report["entries"]),3)
            self.assertTrue(report["entries"][0]["missing_signals"])
            self.assertNotIn("falling",[x["page_id"] for x in report[
                "entries"][0]["accepted_proposals"]])
            self.assertEqual(report["last_fired_clocks_ms"]["falling"],0)
            self.assertEqual(report, evaluate_native_rpg_timeline(
                journal,pages(),actor_id="hero",start_frame=3,limit=3))
            whole=evaluate_native_rpg_timeline(journal,pages(),actor_id="hero")
            self.assertEqual(sum(1 for e in whole["entries"] for p in e[
                "accepted_proposals"] if p["page_id"]=="falling"),1)
            self.assertGreaterEqual(whole["candidate_fire_count"],2)
            self.assertTrue(all(e["requires_runtime_approval"] for e in whole["entries"]))
            self.assertEqual(len(whole["receipt_digest"]),64)

    def test_authoring_schema_and_conflict_priority_resolve(self):
        source={"schema":"skeleton.game.native_rpg_pages.v1","pages":[{
            "id":"falling","priority":50,
            "conditions":[{"signal":"fall_speed_mps","comparison":"above",
                           "threshold":10.}],
            "actions":[{"kind":"show_dialogue","channel":"ui",
                        "target":"hero","value":"danger"}],
            "required_flags":[],"cooldown_ms":0,"repeat":False,"enabled":True,
        }]}
        parsed=parse_native_rpg_pages(source)
        self.assertEqual(parsed[0].page_id,"falling")
        with self.journal(frames=2) as journal:
            result=evaluate_native_rpg_timeline(journal,parsed,actor_id="hero")
            self.assertEqual(result["candidate_fire_count"],1)
        for corrupt in (
            {**source,"schema":"unknown"},
            {**source,"pages":[{**source["pages"][0],"conditions":[
                {"signal":"native_false_signal","comparison":"above","threshold":1.}]}]},
            {**source,"pages":source["pages"]*2},
        ):
            with self.assertRaises(NativeRPGBridgeError):
                parse_native_rpg_pages(corrupt)

    def test_source_tamper_aborts_before_event_proposals(self):
        with self.journal() as journal:
            self.assertEqual(evaluate_native_rpg_timeline(
                journal,pages(),actor_id="hero")["source_prefix_verified_frames"],8)
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE frontier_blobs SET content='{}' WHERE digest IN "
                       "(SELECT evidence_digest FROM frontier_commits WHERE frame=1)")
        with FrameReceiptJournal(self.db,self.gdd) as journal:
            with self.assertRaises(ValueError):
                evaluate_native_rpg_timeline(journal,pages(),actor_id="hero")

    def test_invalid_page_filter_and_missing_native_capture(self):
        with self.journal(frames=2) as journal:
            for opts in (
                {"actor_id":"unknown"},{"start_frame":7},
                {"limit":0},{"flags":{"x":42}},
            ):
                with self.assertRaises((NativeRPGBridgeError,ValueError)):
                    evaluate_native_rpg_timeline(journal,pages(),**{
                        "actor_id":"hero",**opts})

    def test_physics_driven_updraft_force_sensor_never_guesses_the_aerodynamics(self):
        from skeleton.jeeves.game_frontier_native_fields import (
            normalize_native_force_fields,calculated_native_field_force,
        )
        old=sample(0,self.gdd.source_digest)
        new=sample(1,self.gdd.source_digest)
        src=normalize_native_force_fields(({
            "id":"thermal","actor_id":"hero","kind":"updraft",
            "center_xyz_m":[31.99,-1.,30.],"radius_m":5.,
            "acceleration_mps2":8.,
        },))
        for frame in (old,new):
            frame["native_force_field_schema"]="skeleton.game.native_force_fields.v1"
            frame["native_force_fields"]=src
            frame["previous_step_field_forces"]=[]
        applied=calculated_native_field_force(
            src[0],old["actors"][0]["world_xyz_m"],80.)
        new["previous_step_field_forces"]=[{
            "field_id":"thermal","actor_id":"hero","command_tick":0,
            "source_position_xyz_m":old["actors"][0]["world_xyz_m"],
            "force_world_xyz_n":list(applied),
        }]
        records=native_rpg_observations(new,actor_id="hero")
        self.assertAlmostEqual(records["native_gameplay_updraft_force_n"],640.)
        self.assertAlmostEqual(records["native_gameplay_field_force_n"],640.)
        self.assertNotIn("weather_turbulence_mps2",records)
