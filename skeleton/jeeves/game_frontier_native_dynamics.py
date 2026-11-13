"""Independent internal-consistency proof for reported Godot body/contact telemetry.

Godot's locally captured JSONL is untrusted. This verifier never infers actual
impulses, collision-force magnitudes, device attestation or GPU render success.
It checks source actors, body material, mass and kinetic-energy arithmetic,
contact counts and resolved game-actor peer identities; changes are linked to
the canonical frame/chunk evidence rather than promoted to GDD authority.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from typing import Mapping


SCHEMA = "skeleton.game.native_actor_dynamics.v1"


class NativeDynamicsError(ValueError):
    """Invalid reported native physics telemetry."""


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")).hexdigest()


def _number(value: object, name: str, *, low: float, high: float) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise NativeDynamicsError(f"{name}: bounded finite physics quantity required")
    return float(value)


def _velocity(actor: Mapping) -> tuple[float, float, float]:
    coordinates = actor.get("velocity_xyz_mps")
    if not isinstance(coordinates, list) or len(coordinates) != 3:
        raise NativeDynamicsError("native actor velocity XYZ required")
    return tuple(_number(value, "native velocity", low=-1e5, high=1e5)
                 for value in coordinates)


def inspect_native_dynamics(sample: Mapping, *, require_telemetry: bool = False) -> dict | None:
    """Independently check the *reported* body and collision ledger.

    Legacy native v1 JSONL remains accepted with a None result unless telemetry
    is required; an incomplete or partially upgraded trace is never accepted.
    """
    if not isinstance(sample, Mapping) or type(require_telemetry) is not bool:
        raise NativeDynamicsError("typed native capture and explicit policy required")
    actors = sample.get("actors")
    if not isinstance(actors, list) or not 1 <= len(actors) <= 256:
        raise NativeDynamicsError("bounded native actors required")
    has_schema = "native_dynamics_schema" in sample
    has_rows = any(isinstance(row, Mapping) and "physics_body" in row
                   for row in actors)
    if not has_schema and not has_rows and not require_telemetry:
        return None
    if sample.get("native_dynamics_schema") != SCHEMA:
        raise NativeDynamicsError("missing or unsupported native dynamics schema")
    names = [row.get("id") if isinstance(row, Mapping) else None for row in actors]
    if (any(type(name) is not str or not name or len(name) > 128 for name in names)
            or len(set(names)) != len(names)):
        raise NativeDynamicsError("native dynamics actor IDs must be unique")
    catalog = set(names)
    checked = []
    for actor in actors:
        name = actor["id"]
        physics = actor.get("physics_body")
        required = {"mode", "mass_kg", "friction", "restitution",
                    "kinetic_energy_j", "contact_actor_ids", "external_contact_count"}
        if not isinstance(physics, dict) or set(physics) != required:
            raise NativeDynamicsError("complete, exact native body telemetry required")
        mode = physics["mode"]
        if mode not in ("rigid", "static"):
            raise NativeDynamicsError("unrecognized native body mode")
        if actor.get("source_kind") == "native_rigid_reference" and mode != "rigid":
            raise NativeDynamicsError("authoritative reference must remain a rigid body")
        mass = _number(physics["mass_kg"], "mass", low=0., high=1e6)
        if (mode == "rigid" and mass <= 0.) or (mode == "static" and mass != 0.):
            raise NativeDynamicsError("invalid rigid/static mass")
        friction = _number(physics["friction"], "friction", low=0., high=1.)
        restitution = _number(physics["restitution"], "restitution", low=0., high=1.)
        velocity = _velocity(actor)
        if mode == "static" and any(abs(v) > 1e-8 for v in velocity):
            raise NativeDynamicsError("static actor cannot report dynamic velocity")
        calculated = 0.5 * mass * sum(v * v for v in velocity)
        reported = _number(physics["kinetic_energy_j"], "kinetic energy",
                           low=0., high=1e17)
        if not math.isclose(reported, calculated, rel_tol=1e-5, abs_tol=1e-5):
            raise NativeDynamicsError("reported kinetic energy disagrees with mass/velocity")
        contacts = actor.get("contact_count")
        if type(contacts) is not int or not 0 <= contacts <= 64:
            raise NativeDynamicsError("bounded native contact count required")
        peers = physics["contact_actor_ids"]
        if (not isinstance(peers, list)
                or any(type(peer) is not str for peer in peers)
                or peers != sorted(set(peers))
                or any(peer not in catalog or peer == name for peer in peers)):
            raise NativeDynamicsError("unknown, duplicate, self or unsorted contact peer")
        external = physics["external_contact_count"]
        if (type(external) is not int or external < 0
                or len(peers) + external != contacts):
            raise NativeDynamicsError("observed contact peer counts not conserved")
        if mode == "static" and contacts != 0:
            raise NativeDynamicsError("static proxy cannot report rigid collision polling")
        checked.append({
            "id": name, "source_digest": actor.get("source_digest"),
            "source_kind": actor.get("source_kind"),
            "mode": mode, "mass_kg": mass, "friction": friction,
            "restitution": restitution, "kinetic_energy_j": calculated,
            "contact_count": contacts, "contact_actor_ids": peers,
            "external_contact_count": external,
        })
    checked.sort(key=lambda item: item["id"])
    proof = {
        "schema": "skeleton.game.native_dynamics_inspection.v1",
        "native_tick": sample.get("native_tick"), "fps": sample.get("fps"),
        "scene_candidate_digest": sample.get("scene_candidate_digest"),
        "signed_gdd_digest": sample.get("signed_gdd_digest"),
        "actor_count": len(checked),
        "actors": checked,
        "total_kinetic_energy_j": sum(row["kinetic_energy_j"] for row in checked),
        "resolved_game_actor_contact_count": sum(len(row["contact_actor_ids"])
                                                 for row in checked),
        "external_contact_count": sum(row["external_contact_count"] for row in checked),
        "raw_actor_source_digest": _digest(actors),
        "verification": "self_consistent_reported_Godot_telemetry_not_impulse_attestation",
    }
    proof["receipt_digest"] = _digest(proof)
    return proof


def compare_native_dynamics(current: Mapping, *,
                            previous: Mapping | None = None) -> dict | None:
    """Bind mass/material/contact changes to successive reported engine ticks."""
    now = inspect_native_dynamics(current)
    before = inspect_native_dynamics(previous) if previous is not None else None
    if now is None and (previous is None or before is None):
        return None
    if now is None or (previous is not None and before is None):
        raise NativeDynamicsError("native body telemetry cannot appear or disappear mid-session")
    prior = {row["id"]: row for row in before["actors"]} if before else {}
    current_actors = {row["id"]: row for row in now["actors"]}
    if prior and set(prior) != set(current_actors):
        raise NativeDynamicsError("body actor roster changed without signed authority")
    changes = []
    for name, row in sorted(current_actors.items()):
        old = prior.get(name)
        if old is not None and any(
            row[key] != old[key]
            for key in ("source_digest", "source_kind", "mode", "mass_kg",
                        "friction", "restitution")
        ):
            raise NativeDynamicsError("native body identity/mass/material drift")
        changes.append({
            "id": name, "kinetic_energy_delta_j": (
                row["kinetic_energy_j"] - old["kinetic_energy_j"] if old else None
            ),
            "reported_contact_count": row["contact_count"],
            "reported_peer_ids": row["contact_actor_ids"],
            "external_contact_count": row["external_contact_count"],
        })
    proof = {
        "schema": "skeleton.game.native_dynamics_transition.v1",
        "native_tick": current.get("native_tick"),
        "source_dynamics_digest": now["receipt_digest"],
        "previous_dynamics_digest": before["receipt_digest"] if before else None,
        "actors": changes,
        "total_kinetic_energy_delta_j": (
            now["total_kinetic_energy_j"] - before["total_kinetic_energy_j"]
            if before else None
        ),
        "verification": "reported_energy_delta_not_collision_impulse_measurement",
    }
    proof["receipt_digest"] = _digest(proof)
    return proof
