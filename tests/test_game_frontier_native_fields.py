"""Adversarial 3D native authored physics force-fields and replay verification."""
from __future__ import annotations
from copy import deepcopy
import unittest

from skeleton.jeeves.game_frontier_native_fields import (
    SCHEMA,NativeForceFieldError,normalize_native_force_fields,
    calculated_native_field_force,inspect_native_force_fields,
)


FIELDS=(
    {"id":"lift","actor_id":"hero","kind":"updraft",
     "center_xyz_m":[0.,0.,30.],"radius_m":5.,
     "acceleration_mps2":9.8},
    {"id":"spin","actor_id":"hero","kind":"vortex",
     "center_xyz_m":[0.,0.,30.],"radius_m":8.,
     "acceleration_mps2":4.},
)


def make(tick:int,prior:dict|None=None,*,x:float=1.) -> dict:
    catalog=normalize_native_force_fields(FIELDS,allowed_actors={"hero"})
    actor={"id":"hero","world_xyz_m":[x,0.,30.],
           "physics_body":{"mode":"rigid","mass_kg":80.}}
    result={
        "native_tick":tick,"native_force_field_schema":SCHEMA,
        "native_force_fields":catalog,"actors":[actor],
        "signed_gdd_digest":"a"*64,"scene_candidate_digest":"b"*64,
        "previous_step_field_forces":[],
    }
    if tick>0 and prior is not None:
        for field in catalog:
            prev=prior["actors"][0]
            force=calculated_native_field_force(
                field,prev["world_xyz_m"],prev["physics_body"]["mass_kg"])
            result["previous_step_field_forces"].append({
                "field_id":field["id"],"actor_id":"hero","command_tick":tick-1,
                "source_position_xyz_m":prev["world_xyz_m"],
                "force_world_xyz_n":list(force),
            })
    return result


class AuthoredNativeForceTests(unittest.TestCase):
    def test_actual_updraft_current_and_vortex_have_source_bounded_acceleration(self):
        catalog=normalize_native_force_fields(FIELDS)
        lift=catalog[0]
        self.assertEqual(lift["id"],"lift")
        self.assertAlmostEqual(calculated_native_field_force(
            lift,[0.,0.,30.],80.)[2],784.)
        self.assertEqual(calculated_native_field_force(
            lift,[10.,0.,30.],80.),(0.,0.,0.))
        vortex=catalog[1]
        tangential=calculated_native_field_force(vortex,[1.,0.,30.],80.)
        self.assertAlmostEqual(tangential[0],0.)
        self.assertGreater(tangential[1],0.)

    def test_strict_source_tick_telemetry_and_digests(self):
        a=make(0)
        b=make(1,a,x=1.5)
        self.assertEqual(inspect_native_force_fields(a,expected_catalog=FIELDS)[
            "step_force_count"],0)
        report=inspect_native_force_fields(b,previous=a,expected_catalog=FIELDS)
        self.assertEqual(report["step_force_count"],2)
        self.assertTrue(report["previous_source_verified"])
        self.assertEqual(report,inspect_native_force_fields(
            b,previous=a,expected_catalog=FIELDS))
        self.assertEqual(len(report["receipt_digest"]),64)

    def test_rejects_force_and_authored_source_tamper(self):
        a=make(0)
        edits=[
            lambda s:s["previous_step_field_forces"][0][
                "force_world_xyz_n"].__setitem__(2,100.),
            lambda s:s["previous_step_field_forces"][1].update(command_tick=8),
            lambda s:s["previous_step_field_forces"][0].update(actor_id="villain"),
            lambda s:s["previous_step_field_forces"][0].update(
                source_position_xyz_m=[20.,0.,30.]),
            lambda s:s["native_force_fields"][0].update(acceleration_mps2=20.),
            lambda s:s["previous_step_field_forces"].pop(),
            lambda s:s["native_force_field_schema"].__class__,
        ]
        for modify in edits[:-1]:
            sample=make(1,a)
            modify(sample)
            with self.subTest(state=repr(sample)[:120]),self.assertRaises(NativeForceFieldError):
                inspect_native_force_fields(sample,previous=a,expected_catalog=FIELDS)
        sample=make(1,a)
        sample["native_force_field_schema"]="unknown"
        with self.assertRaises(NativeForceFieldError):
            inspect_native_force_fields(sample,previous=a)

    def test_field_source_enforces_bounds_and_actor_authority(self):
        for bad in (
            {**FIELDS[0],"radius_m":0.},
            {**FIELDS[0],"acceleration_mps2":30.},
            {**FIELDS[0],"actor_id":"other"},
            {**FIELDS[0],"kind":"script"},
            {**FIELDS[0],"center_xyz_m":[float("inf"),0.,0.]},
        ):
            with self.assertRaises(NativeForceFieldError):
                normalize_native_force_fields((bad,),allowed_actors={"hero"})
        with self.assertRaises(NativeForceFieldError):
            normalize_native_force_fields((FIELDS[0],FIELDS[0]))
        with self.assertRaises(NativeForceFieldError):
            normalize_native_force_fields(FIELDS*33)
