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
            lambda x:x["actors"][0].update(world_xyz_m=[0.,0.,100.]),
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
