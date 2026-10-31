"""Godot reference input receipt bounds, provenance and sequence regression."""
from __future__ import annotations
import copy
import unittest

from skeleton.jeeves.game_frontier_native_control import (
    verify_native_reference_input,NativeControlError,
)


def controls():
    return {"enabled":True,"move_force_n":240.,"max_speed_mps":8.,
            "jump_impulse_ns":120.,"headless_fixture_ticks":2}


def record(tick):
    row={"native_tick":tick}
    if tick==0:
        row["previous_step_control"]={}
    else:
        row["previous_step_control"]={
            "schema":"skeleton.game.native_reference_input.v1",
            "actor_id":"hero","command_tick":tick-1,
            "input_kind":"headless_fixture" if tick<3 else "none",
            "input_axis_xy":[1.,0.] if tick<3 else [0.,0.],
            "force_world_xyz_n":[240.,0.,0.] if tick<3 else [0.,0.,0.],
            "jump_impulse_ns":0.,
            "bounded_reference_controller_not_NPC_AI":True,
        }
    return row


class NativeReferenceInputTests(unittest.TestCase):
    def test_fixture_headless_control_and_no_input(self):
        self.assertEqual(verify_native_reference_input(
            record(0),controls(),actor_id="hero")["source"],"initial_no_input")
        for tick in (1,2,3,4):
            accepted=verify_native_reference_input(
                record(tick),controls(),actor_id="hero")
            self.assertEqual(accepted["frame"],tick)
        self.assertEqual(verify_native_reference_input(
            record(3),controls(),actor_id="hero")["applied_force_n"],0.)

    def test_rejects_tampered_force_provenance_identity_and_input(self):
        mutations=[
            lambda c: c.update(command_tick=20),
            lambda c: c.update(actor_id="villain"),
            lambda c: c.update(force_world_xyz_n=[241.,0.,0.]),
            lambda c: c.update(input_axis_xy=[.5,0.]),
            lambda c: c.update(input_kind="human_input"),
            lambda c: c.update(jump_impulse_ns=121.),
            lambda c: c.update(input_axis_xy=[1.,1.]),
            lambda c: c.update(bounded_reference_controller_not_NPC_AI=False),
        ]
        for change in mutations:
            record1=record(1)
            change(record1["previous_step_control"])
            with self.subTest(change=str(change)),self.assertRaises(NativeControlError):
                verify_native_reference_input(record1,controls(),actor_id="hero")

    def test_missing_unconfigured_and_ended_fixture_source(self):
        with self.assertRaises(NativeControlError):
            verify_native_reference_input(record(1),None,actor_id="hero")
        disabled=controls()
        disabled["enabled"]=False
        with self.assertRaises(NativeControlError):
            verify_native_reference_input(record(1),disabled,actor_id="hero")
        forged=record(3)
        forged["previous_step_control"]["input_kind"]="headless_fixture"
        with self.assertRaises(NativeControlError):
            verify_native_reference_input(forged,controls(),actor_id="hero")
        with self.assertRaises(NativeControlError):
            verify_native_reference_input({"native_tick":0},controls(),actor_id="hero")

    def test_human_analog_and_grounded_jump_receipts(self):
        row=record(5)
        row["previous_step_control"].update(
            input_kind="human_input",input_axis_xy=[0.,-1.],
            force_world_xyz_n=[0.,240.,0.],jump_impulse_ns=120.)
        accepted=verify_native_reference_input(row,controls(),actor_id="hero")
        self.assertEqual(accepted["jump_impulse_ns"],120.)
        self.assertEqual(accepted["source"],"human_input")
