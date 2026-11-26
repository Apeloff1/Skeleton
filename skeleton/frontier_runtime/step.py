"""Authoritative fixed step for soft-body, weather, lifecycle and character collision.

Sub-steps run in that order on a scratch copy. Any failure leaves the committed
snapshot untouched. Scene-candidate output is copied in only after the signed
receipt matches the candidate digest. Actor controllers then consume continuous
collision and sequential impulses; they never write the unconstrained end pose.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Mapping

from skeleton.jeeves.game_frontier_advanced_physics import ZERO, RigidBody, Vec3
from skeleton.jeeves.game_frontier_motion import (
    Impact,
    MotionPhysicsError,
    age_structure,
    advance_environment,
    simulate_character,
    simulate_soft_nodes,
)
from skeleton.jeeves.game_frontier_weather_physics import WeatherCouplingError, evolve_microclimate

from skeleton.frontier_runtime.chunks import partition_actors, verify_dual_chunks
from skeleton.frontier_runtime.contacts import ThinWall, discrete_sphere_tunnels, solve_actor_contacts
from skeleton.frontier_runtime.eras import EraSolver, era_solver, quantize_vec
from skeleton.frontier_runtime.godot_delta import GODOT_SCENE, GODOT_SCRIPT, emit_godot_scene_delta
from skeleton.frontier_runtime.scene_gate import admit_scene_candidate, apply_scene_candidate
from skeleton.frontier_runtime.state import (
    ActorState,
    CharacterBody,
    EnvironmentBody,
    ImpactBody,
    MicroclimateState,
    SoftBodyState,
    StepRejected,
    StructureBody,
    TractionBody,
    WeatherState,
    WorldState,
    canonical_json,
    digest_bytes,
    reject_nonfinite,
)

_SOLVER_ERRORS = (MotionPhysicsError, WeatherCouplingError, ValueError, ZeroDivisionError, OverflowError)

CHANNEL_ORDER = ("soft_body", "weather", "lifecycle", "character_collision")


@dataclass(frozen=True)
class StepReceipt:
    world: WorldState
    canonical_bytes: bytes
    godot_files: Mapping[str, str]
    frame: Mapping[str, object]
    contacts: tuple[dict, ...]

    @property
    def digest(self) -> str:
        return str(self.frame["digest"])


def _vec(value: tuple[float, float, float]) -> Vec3:
    return Vec3(value[0], value[1], value[2])


def _impact_from(body: ImpactBody) -> Impact:
    return Impact(
        body.surface_id, body.relative_speed_mps, body.impulse_ns, body.damage,
        _vec(body.normal), body.material,
    )


def _walls(world: WorldState) -> tuple[ThinWall, ...]:
    return tuple(
        ThinWall(wall.wall_id, _vec(wall.point), _vec(wall.normal),
                 wall.half_thickness_m, wall.friction, wall.restitution)
        for wall in world.walls
    )


def _rigid(actor: ActorState) -> RigidBody:
    return RigidBody(
        actor.actor_id, _vec(actor.position), _vec(actor.velocity),
        actor.mass_kg, actor.radius_m, actor.restitution, actor.friction,
        _vec(actor.angular_velocity),
    )


def _quantize_actor(actor: ActorState, mode: str, impulse: float) -> ActorState:
    return replace(
        actor,
        position=quantize_vec(actor.position, mode),
        velocity=quantize_vec(actor.velocity, mode),
        angular_velocity=quantize_vec(actor.angular_velocity, mode),
        last_contact_impulse_ns=impulse,
    )


def _step_soft(world: WorldState, weather: WeatherState, dt: float, mode: str) -> tuple[SoftBodyState, ...]:
    if not world.soft_nodes:
        return ()
    solved = simulate_soft_nodes(
        tuple(node.as_node() for node in world.soft_nodes),
        weather.as_weather(),
        anchors=tuple(_vec(anchor) for anchor in world.soft_anchors),
        delta_s=dt,
    )
    updated = []
    for original, node in zip(world.soft_nodes, solved):
        updated.append(replace(
            original,
            position=quantize_vec((node.position.x, node.position.y, node.position.z), mode),
            velocity=quantize_vec((node.velocity.x, node.velocity.y, node.velocity.z), mode),
            wetness=node.wetness,
            temperature_c=node.temperature_c,
        ))
    return tuple(updated)


def _step_weather(world: WorldState, dt: float, mode: str) -> tuple[WeatherState, MicroclimateState, TractionBody, dict]:
    evolved = evolve_microclimate(
        world.microclimate.as_microclimate(),
        world.weather.as_weather(),
        world.air.as_air(),
        world.traction.as_traction(),
        delta_s=dt,
        location=_vec(world.character.position) if world.character is not None else ZERO,
    )
    wind = _vec(world.weather.wind) + evolved.pressure_wind_delta
    speed = math.sqrt(wind.dot(wind))
    if speed > 249.0:
        wind = wind.scaled(249.0 / speed)
    weather = replace(
        world.weather,
        wind=quantize_vec((wind.x, wind.y, wind.z), mode),
    )
    climate = evolved.state
    micro = replace(
        world.microclimate,
        terrain_temperature_c=climate.terrain_temperature_c,
        soil_water_fraction=climate.soil_water_fraction,
        ground_ice_fraction=climate.ground_ice_fraction,
        loose_sediment_fraction=climate.loose_sediment_fraction,
    )
    surface = evolved.traction_surface
    traction = replace(
        world.traction,
        wetness=surface.wetness,
        ice_fraction=surface.ice_fraction,
        loose_gravel=surface.loose_gravel,
    )
    report = {
        **weather.public(),
        "terrain_temperature_c": micro.terrain_temperature_c,
        "soil_water_fraction": micro.soil_water_fraction,
        "ground_ice_fraction": micro.ground_ice_fraction,
        "wind_xyz": list(weather.wind),
        "pressure_wind_delta": [
            evolved.pressure_wind_delta.x, evolved.pressure_wind_delta.y, evolved.pressure_wind_delta.z,
        ],
        "rain_absorption_m": evolved.rain_absorption_m,
        "evaporation_m": evolved.evaporation_m,
        "solver": "evolve_microclimate",
    }
    return weather, micro, traction, report


def _step_lifecycle(
    world: WorldState, weather: WeatherState, dt: float,
) -> tuple[EnvironmentBody, tuple[StructureBody, ...], dict]:
    reference = weather.as_weather()
    impact = _impact_from(world.prior_impact) if world.prior_impact is not None else None
    days = dt / 86400.0
    aged_env = advance_environment(world.environment.as_environment(), reference, delta_days=days, impact=impact)
    environment = EnvironmentBody(
        aged_env.soil_saturation, aged_env.erosion, aged_env.foliage_bend,
        aged_env.vegetation_health, aged_env.puddle_depth_m, aged_env.snow_load,
        aged_env.debris_fraction,
    )
    structures = []
    for item in world.structures:
        aged = age_structure(
            item.as_structure(), reference, elapsed_days=days,
            work_days=world.construction_work_days, maintenance_days=world.maintenance_days,
            impact=impact,
        )
        structures.append(replace(
            item,
            construction_progress_days=aged.construction_progress_days,
            age_days=aged.age_days,
            integrity=aged.integrity,
            surface_weathering=aged.surface_weathering,
            biological_growth=aged.biological_growth,
            water_infiltration=aged.water_infiltration,
            maintenance_debt=aged.maintenance_debt,
        ))
    report = {
        "structures": [item.public() for item in structures],
        **environment.public(),
        "solver": "age_structure+advance_environment",
    }
    return environment, tuple(structures), report


def _step_character(
    world: WorldState, weather: WeatherState, dt: float, solver: EraSolver, walls: tuple[ThinWall, ...],
) -> tuple[CharacterBody | None, ImpactBody | None, dict, int]:
    if world.character is None:
        return None, world.prior_impact, {"present": False, "solver": "simulate_character"}, 0
    simulated = simulate_character(
        world.character.as_character(), weather.as_weather(),
        tuple(plane.as_plane() for plane in world.character_surfaces),
        desired_velocity=_vec(world.desired_character_velocity),
        delta_s=dt,
    )
    end = simulated.state.position
    segment = (
        (end.x - world.character.position[0]) / dt,
        (end.y - world.character.position[1]) / dt,
        (end.z - world.character.position[2]) / dt,
    )
    tunnels = [
        wall for wall in walls
        if discrete_sphere_tunnels(
            world.character.position, segment, world.character.radius_m, dt,
            (wall.point.x, wall.point.y, wall.point.z),
            (wall.normal.x, wall.normal.y, wall.normal.z), wall.half_thickness_m,
        )
    ]
    used = 0
    impacts = simulated.impacts
    position = (end.x, end.y, end.z)
    velocity = (simulated.state.velocity.x, simulated.state.velocity.y, simulated.state.velocity.z)
    if tunnels:
        body = RigidBody(
            world.character.character_id, _vec(world.character.position), Vec3(*segment),
            world.character.mass_kg, world.character.radius_m, 0.2,
            max(0.05, simulated.friction_coefficient), ZERO,
        )
        solved, receipts, used = solve_actor_contacts(
            (body,), walls, dt=dt, iteration_cap=solver.iteration_cap,
            integrator=solver.integrator, desired={}, steer=False,
        )
        landed = solved[0]
        position = (landed.position.x, landed.position.y, landed.position.z)
        velocity = (landed.velocity.x, landed.velocity.y, landed.velocity.z)
        impacts = tuple(
            Impact(
                str(receipt["wall_id"] or "contact"),
                math.sqrt(sum(component * component for component in segment)),
                max(0.0, float(receipt["normal_impulse_ns"])),
                max(0.0, float(receipt["damage_a"])),
                Vec3(*receipt["normal"]),
                "stone",
            )
            for receipt in receipts
            if receipt["wall_id"]
        ) or impacts
    mode = solver.numeric_mode
    character = replace(
        world.character,
        position=quantize_vec(position, mode),
        velocity=quantize_vec(velocity, mode),
        core_temperature_c=simulated.state.core_temperature_c,
        clothing_wetness=simulated.state.clothing_wetness,
        hair_wetness=simulated.state.hair_wetness,
        boot_wetness=simulated.state.boot_wetness,
        warmth=simulated.state.warmth,
        stamina=simulated.state.stamina,
        health=simulated.state.health,
        gait=simulated.state.gait,
    )
    carried = None
    impact_rows = []
    for impact in impacts:
        row = ImpactBody(
            impact.surface_id, impact.relative_speed_mps, impact.impulse_ns, impact.damage,
            (impact.normal.x, impact.normal.y, impact.normal.z), impact.material,
        )
        impact_rows.append(row.public())
        carried = row
    report = {
        "present": True,
        "solver": "simulate_character+sweep" if tunnels else "simulate_character",
        **character.public(),
        "traction": simulated.friction_coefficient,
        "impacts": impact_rows,
        "tunneled_wall_corrected": bool(tunnels),
    }
    return character, carried, report, used


def _step_actors(
    world: WorldState, dt: float, solver: EraSolver, walls: tuple[ThinWall, ...],
) -> tuple[tuple[ActorState, ...], tuple[dict, ...], int]:
    if not world.actors:
        return (), (), 0
    bodies = tuple(_rigid(actor) for actor in world.actors)
    desired = {actor.actor_id: actor.desired_velocity for actor in world.actors}
    solved, receipts, used = solve_actor_contacts(
        bodies, walls, dt=dt, iteration_cap=solver.iteration_cap,
        integrator=solver.integrator, desired=desired, steer=True,
    )
    impulses = {actor.actor_id: 0.0 for actor in world.actors}
    for receipt in receipts:
        for key in ("body_a", "body_b"):
            actor_id = receipt[key]
            if actor_id in impulses:
                impulses[actor_id] += max(0.0, float(receipt["normal_impulse_ns"]))
    mode = solver.numeric_mode
    actors = tuple(
        _quantize_actor(
            replace(
                original,
                position=(body.position.x, body.position.y, body.position.z),
                velocity=(body.velocity.x, body.velocity.y, body.velocity.z),
                angular_velocity=(
                    body.angular_velocity.x, body.angular_velocity.y, body.angular_velocity.z,
                ),
            ),
            mode,
            impulses[original.actor_id],
        )
        for original, body in zip(world.actors, solved)
    )
    return actors, receipts, used


def _chunks(world: WorldState) -> dict[str, object]:
    placed: list[tuple[str, tuple[float, float, float]]] = []
    if world.character is not None:
        placed.append((world.character.character_id, world.character.position))
    placed.extend((actor.actor_id, actor.position) for actor in world.actors)
    partition = partition_actors(tuple(placed), chunk_size_m=world.chunk_size_m)
    verify_dual_chunks(partition)
    return partition.as_dict()


class AuthoritativeRuntime:
    """Holds one committed world. ``step`` replaces it only after every sub-step."""

    def __init__(self, world: WorldState) -> None:
        if not isinstance(world, WorldState):
            raise StepRejected("world state required")
        reject_nonfinite(world.public())
        self._committed = world

    @property
    def world(self) -> WorldState:
        return self._committed

    def step(
        self,
        dt: float,
        *,
        candidate: object | None = None,
        authorisation: object | None = None,
        key: bytes | None = None,
        now_ms: int | None = None,
    ) -> StepReceipt:
        prior = self._committed
        try:
            receipt = self._compute(
                prior, dt, candidate=candidate, authorisation=authorisation, key=key, now_ms=now_ms,
            )
        except StepRejected:
            self._committed = prior
            raise
        except _SOLVER_ERRORS as exc:
            self._committed = prior
            raise StepRejected(str(exc)) from exc
        self._committed = receipt.world
        return receipt

    def _compute(
        self,
        prior: WorldState,
        dt: float,
        *,
        candidate: object | None,
        authorisation: object | None,
        key: bytes | None,
        now_ms: int | None,
    ) -> StepReceipt:
        if isinstance(dt, float) and math.isnan(dt):
            raise StepRejected("NaN")
        reject_nonfinite(prior.public())
        for actor in prior.actors:
            if actor.mass_kg < 0:
                raise StepRejected("negative mass")
        if prior.character is not None and prior.character.mass_kg < 0:
            raise StepRejected("negative mass")
        solver = era_solver(prior.engine_era)
        if not solver.accepts_dt(dt):
            raise StepRejected("dt outside the era allow-list")
        paired = (candidate is None) == (authorisation is None)
        if not paired:
            raise StepRejected("scene candidate and signed receipt must be paired")
        working = prior
        candidate_digest = prior.admitted_candidate_digest
        if candidate is not None:
            if not isinstance(key, bytes) or type(now_ms) is not int or authorisation is None:
                raise StepRejected("candidate admission requires key and now_ms")
            manifest = admit_scene_candidate(candidate, authorisation, key=key, now_ms=now_ms)
            working = apply_scene_candidate(working, manifest, authorisation.era)  # type: ignore[attr-defined]
            candidate_digest = working.admitted_candidate_digest
        # Scratch outputs. Nothing here is assigned back to the runtime.
        soft = _step_soft(working, working.weather, dt, solver.numeric_mode)
        weather, micro, traction, weather_report = _step_weather(working, dt, solver.numeric_mode)
        environment, structures, lifecycle_report = _step_lifecycle(working, weather, dt)
        walls = _walls(working)
        character, carried, character_report, character_iters = _step_character(
            working, weather, dt, solver, walls,
        )
        actors, contacts, actor_iters = _step_actors(working, dt, solver, walls)
        iterations_used = max(character_iters, actor_iters)
        if iterations_used > solver.iteration_cap:
            raise StepRejected("iteration cap exceeded")
        proposed = replace(
            working,
            weather=weather,
            soft_nodes=soft,
            environment=environment,
            structures=structures,
            microclimate=micro,
            traction=traction,
            character=character,
            actors=actors,
            prior_impact=carried,
            step_index=prior.step_index + 1,
            parent_digest=prior.digest(),
            admitted_candidate_digest=candidate_digest,
        )
        chunks = _chunks(proposed)
        channels = {
            "soft_body": [node.public() for node in soft],
            "weather": weather_report,
            "lifecycle": lifecycle_report,
            "character_collision": character_report,
        }
        frame: dict[str, object] = {
            "schema": "skeleton.frontier_runtime.fixed_step.v1",
            "engine_era": solver.era_id,
            "step_index": proposed.step_index,
            "parent_digest": proposed.parent_digest,
            "fixed_dt_s": solver.fixed_dt_s,
            "integrator": solver.integrator,
            "iteration_cap": solver.iteration_cap,
            "iterations_used": iterations_used,
            "numeric_mode": solver.numeric_mode,
            "channel_order": list(CHANNEL_ORDER),
            "channels": channels,
            "actor_contacts": [dict(contact) for contact in contacts],
            "actors": [actor.public() for actor in actors],
            "chunks": chunks,
            "candidate_digest": candidate_digest,
            "state": proposed.public(),
        }
        frame["state_digest"] = digest_bytes(frame["state"])
        godot = emit_godot_scene_delta(frame)
        frame["godot_scene"] = godot[GODOT_SCENE]
        frame["godot_script"] = godot[GODOT_SCRIPT]
        frame["ui_status"] = {
            "step_index": proposed.step_index,
            "engine_era": solver.era_id,
            "channels_committed": list(CHANNEL_ORDER),
            "contact_count": len(contacts),
            "candidate_admitted": candidate_digest is not None,
            "candidate_digest": candidate_digest,
            "godot_delta": GODOT_SCENE,
            "integrator": solver.integrator,
            "fixed_dt_s": solver.fixed_dt_s,
        }
        reject_nonfinite(frame["state"])
        sealed = dict(frame)
        sealed["digest"] = digest_bytes(frame)
        line = (canonical_json(sealed) + "\n").encode()
        return StepReceipt(proposed, line, godot, sealed, contacts)


def replay_stream(
    world: WorldState,
    steps: int,
    *,
    candidate: object | None = None,
    authorisation: object | None = None,
    key: bytes | None = None,
    now_ms: int | None = None,
) -> bytes:
    """Re-run ``steps`` fixed ticks from ``world``. A candidate is loaded on tick 0."""
    if type(steps) is not int or steps < 1:
        raise StepRejected("stream length must be positive")
    runtime = AuthoritativeRuntime(world)
    solver = era_solver(world.engine_era)
    chunks = []
    for index in range(steps):
        receipt = runtime.step(
            solver.fixed_dt_s,
            candidate=candidate if index == 0 else None,
            authorisation=authorisation if index == 0 else None,
            key=key if index == 0 else None,
            now_ms=now_ms if index == 0 else None,
        )
        verify_dual_chunks(receipt.frame["chunks"])  # type: ignore[arg-type]
        chunks.append(receipt.canonical_bytes)
    return b"".join(chunks)


def verify_stream(
    world: WorldState,
    blob: bytes,
    *,
    candidate: object | None = None,
    authorisation: object | None = None,
    key: bytes | None = None,
    now_ms: int | None = None,
) -> None:
    """Replay the source world and require the stored stream byte for byte."""
    lines = blob.splitlines()
    if not lines:
        raise StepRejected("empty stream")
    again = replay_stream(
        world, len(lines), candidate=candidate, authorisation=authorisation, key=key, now_ms=now_ms,
    )
    if again != blob:
        raise StepRejected("replay diverged from source stream")
    parent = world.digest()
    for raw in lines:
        frame = json_loads(raw)
        body = dict(frame)
        claimed = body.pop("digest")
        if digest_bytes(body) != claimed:
            raise StepRejected("frame digest mismatch")
        if frame.get("parent_digest") != parent:
            raise StepRejected("broken step chain")
        if frame.get("state_digest") != digest_bytes(frame["state"]):
            raise StepRejected("state digest mismatch")
        verify_dual_chunks(frame["chunks"])
        parent = str(frame["state_digest"])


def json_loads(raw: bytes) -> dict:
    import json
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise StepRejected("frame must be an object")
    return value
