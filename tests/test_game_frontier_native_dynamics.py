"""Adversarial Godot native contact/material/energy receipt verification."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.jeeves.game_frontier_native_dynamics import (
    inspect_native_dynamics, compare_native_dynamics, NativeDynamicsError,
)
from skeleton.jeeves.game_frontier_native_chunks import (
    inspect_native_chunks, compare_native_chunk_transitions, NativeChunkError,
)


def observation(tick: int = 0, *, fps: int = 60) -> dict:
    hero = {
        "id": "hero", "source_digest": "a"*64,
        "source_kind": "native_rigid_reference",
        "world_xyz_m": [0. + tick * .02, 0., 2.],
        "velocity_xyz_mps": [1.2, 0., -0.5], "contact_count": 2,
        "physics_body": {
            "mode": "rigid", "mass_kg": 80., "friction": .3,
            "restitution": .2, "kinetic_energy_j": 67.6,
            "contact_actor_ids": ["npc"], "external_contact_count": 1,
        },
    }
    npc = {
        "id": "npc", "source_digest": "b"*64,
        "source_kind": "generated_source_proxy",
        "world_xyz_m": [1., 0., 2.],
        "velocity_xyz_mps": [0., 0., 0.], "contact_count": 0,
        "physics_body": {
            "mode": "static", "mass_kg": 0., "friction": 1.,
            "restitution": 0., "kinetic_energy_j": 0.,
            "contact_actor_ids": [], "external_contact_count": 0,
        },
    }
    return {
        "native_tick": tick, "fps": fps, "actors": [hero, npc],
        "native_dynamics_schema": "skeleton.game.native_actor_dynamics.v1",
        "native_chunk_size_m": 32.,
        "native_chunks": [{"chunk_xy": [0, 0], "actor_ids": ["hero", "npc"]}],
        "scene_candidate_digest": "c"*64,
        "signed_gdd_digest": "d"*64,
    }


class DynamicsValidationTests(unittest.TestCase):
    def test_energy_mass_friction_and_contact_conservation(self):
        doc = observation()
        proof = inspect_native_dynamics(doc, require_telemetry=True)
        self.assertEqual(proof["actor_count"], 2)
        self.assertAlmostEqual(proof["total_kinetic_energy_j"], 67.6)
        self.assertEqual(proof["resolved_game_actor_contact_count"], 1)
        self.assertEqual(proof["external_contact_count"], 1)
        self.assertEqual(proof, inspect_native_dynamics(doc))
        self.assertEqual(len(proof["receipt_digest"]), 64)

    def test_chunk_verifier_binds_telemetry_digest(self):
        sample = observation()
        verified = inspect_native_chunks(sample, require_native_partition=True)
        self.assertEqual(verified["native_dynamics_digest"],
                         inspect_native_dynamics(sample)["receipt_digest"])
        future = observation(1)
        transition = compare_native_chunk_transitions(future, previous=sample)
        self.assertEqual(len(transition["native_dynamics_transition_digest"]), 64)

    def test_legacy_samples_do_not_claim_dynamics(self):
        sample = observation()
        sample.pop("native_dynamics_schema")
        for actor in sample["actors"]:
            actor.pop("physics_body")
        self.assertIsNone(inspect_native_dynamics(sample))
        self.assertNotIn("native_dynamics_digest", inspect_native_chunks(sample))
        with self.assertRaises(NativeDynamicsError):
            inspect_native_dynamics(sample, require_telemetry=True)

    def test_rejects_tamper_and_partial_upgrades(self):
        for mutate in (
            lambda s: s["actors"][0]["physics_body"].update(mass_kg=-1),
            lambda s: s["actors"][0]["physics_body"].update(mass_kg=81),
            lambda s: s["actors"][0]["physics_body"].update(kinetic_energy_j=100),
            lambda s: s["actors"][0]["physics_body"].update(restitution=2),
            lambda s: s["actors"][0]["physics_body"].update(friction=float("nan")),
            lambda s: s["actors"][0]["physics_body"].update(contact_actor_ids=["ghost"]),
            lambda s: s["actors"][0]["physics_body"].update(contact_actor_ids=["hero"]),
            lambda s: s["actors"][0]["physics_body"].update(contact_actor_ids=["npc","npc"]),
            lambda s: s["actors"][0]["physics_body"].update(external_contact_count=0),
            lambda s: s["actors"][0]["physics_body"].update(mode="static"),
            lambda s: s["actors"][1]["physics_body"].update(mass_kg=5),
            lambda s: s["actors"][1]["velocity_xyz_mps"].__setitem__(0, .01),
            lambda s: s["actors"][1].pop("physics_body"),
            lambda s: s.pop("native_dynamics_schema"),
            lambda s: s.update(native_dynamics_schema="unknown.version"),
        ):
            sample = observation()
            mutate(sample)
            with self.subTest(sample=repr(sample)[:250]):
                with self.assertRaises(NativeDynamicsError):
                    inspect_native_dynamics(sample)
                with self.assertRaises(NativeChunkError):
                    inspect_native_chunks(sample)

    def test_transition_refuses_mass_material_identity_mutations(self):
        first = observation()
        for key, value in (("mass_kg", 85.), ("friction", .1),
                           ("restitution", .9), ("mode", "static")):
            second = observation(1)
            second["actors"][0]["physics_body"][key] = value
            if key == "mass_kg":
                second["actors"][0]["physics_body"]["kinetic_energy_j"] = 71.825
            with self.subTest(key=key):
                with self.assertRaises((NativeDynamicsError, NativeChunkError)):
                    compare_native_chunk_transitions(second, previous=first)

    def test_all_frame_rates_and_source_receipt_chaining(self):
        for fps in (30, 50, 60, 120):
            first, next_frame = observation(fps=fps), observation(1, fps=fps)
            delta = compare_native_dynamics(next_frame, previous=first)
            self.assertEqual(delta["native_tick"], 1)
            self.assertAlmostEqual(delta["total_kinetic_energy_delta_j"], 0)
            self.assertEqual(len(delta["receipt_digest"]), 64)
            self.assertEqual(len(compare_native_chunk_transitions(
                next_frame, previous=first)["receipt_digest"]), 64)

    def test_failed_partial_upgrade_and_future_downgrade(self):
        first = observation()
        older = deepcopy(first)
        older.pop("native_dynamics_schema")
        for actor in older["actors"]:
            actor.pop("physics_body")
        with self.assertRaises(NativeDynamicsError):
            compare_native_dynamics(observation(1), previous=older)
        with self.assertRaises(NativeDynamicsError):
            compare_native_dynamics(older, previous=first)
