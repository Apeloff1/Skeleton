"""Authoritative fixed-step runtime: soft-body, weather, lifecycle, contacts, eras."""
from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.frontier_runtime import (
    GODOT_SCENE,
    ActorState,
    AirBody,
    AuthoritativeRuntime,
    CharacterBody,
    EnvironmentBody,
    MicroclimateState,
    SoftBodyState,
    StepRejected,
    StructureBody,
    TractionBody,
    WallState,
    WeatherState,
    WorldState,
    discover_era_solvers,
    discrete_sphere_tunnels,
    era_solver,
    replay_stream,
    verify_dual_chunks,
    verify_stream,
)
from skeleton.jeeves.game_engine_lab import list_engine_eras
from skeleton.jeeves.game_frontier_runtime_binding import (
    CANDIDATE_SCHEMA,
    authorise_candidate,
    digest_of,
)
from skeleton.jeeves.game_frontier import FrontierSceneCandidate


KEY = b"operator-key-0123456789"
ERA = "shader_console_2001"


def _weather(**kwargs) -> WeatherState:
    values = dict(
        wind=(3.0, 0.5, 0.0), temperature_c=18.0, precipitation_mm_h=60.0,
        humidity=0.4, water_depth_m=0.0, sunlight=0.7, snow_depth_m=0.0,
        airborne_dust=0.0,
    )
    values.update(kwargs)
    return WeatherState(**values)


def _world(era: str = ERA, **kwargs) -> WorldState:
    actors = kwargs.pop("actors", (
        ActorState("walker", (0.0, 0.0, 1.0), (0.0, 0.0, 0.0), 70.0, 0.4, (1.0, 0.0, 0.0)),
    ))
    walls = kwargs.pop("walls", ())
    character = kwargs.pop("character", CharacterBody("player", (0.0, 4.0, 1.0), (0.0, 0.0, 0.0), 0.4, 70.0))
    values = dict(
        engine_era=era,
        weather=_weather(),
        soft_nodes=(
            SoftBodyState("cape", "cloth", (0.0, 0.0, 1.2), (0.0, 0.0, 1.2), (0.0, 0.0, 0.0), 0.2),
        ),
        soft_anchors=((0.0, 0.0, 1.2),),
        environment=EnvironmentBody(),
        structures=(
            StructureBody("hut", "wood", 10.0, 10.0, 3.0, 0.9, 0.05, 0.0, 0.0, 0.0, (2.0, 0.0, 0.0)),
        ),
        actors=actors,
        walls=walls,
        microclimate=MicroclimateState(10.0, 0.3, 0.0, 0.1, 0.4, 0.5, (0.2, 0.0, 0.0)),
        traction=TractionBody((0.0, 0.0, 1.0), 0.8, 0.6),
        air=AirBody(temperature_c=18.0, relative_humidity=0.4, rain_mm_h=60.0),
        character=character,
        character_surfaces=(
            # PlaneBody is constructed inside the world via the public type re-export path.
        ),
        desired_character_velocity=(0.4, 0.0, 0.0),
    )
    # character_surfaces default empty; supply a ground plane through the state type.
    from skeleton.frontier_runtime.state import PlaneBody
    values["character_surfaces"] = kwargs.pop(
        "character_surfaces",
        (PlaneBody("ground", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), "stone"),),
    )
    values.update(kwargs)
    return WorldState(**values)


def _candidate(temperature: float = 30.0):
    manifest = {
        "schema": CANDIDATE_SCHEMA,
        "render": {"era": "early_3d", "fps": 60},
        "weather_physics": {
            "temperature_c": temperature,
            "wind_xyz": [3.0, 0.5, 0.0],
            "rain_mm_h": 60.0,
            "water_depth_m": 0.0,
            "snow_depth_m": 0.0,
        },
        "soft_material_motion": [{
            "id": "cape", "material": "cloth", "xyz": [0.0, 0.0, 1.2],
            "wetness": 0.0, "temperature_c": 18.0,
        }],
        "structures": [{
            "id": "hut", "material": "wood", "built": True, "age_days": 3.0,
            "integrity": 0.9, "weathering": 0.05, "maintenance_debt": 0.0,
        }],
        "character_physics": {
            "position": [5.0, 4.0, 1.0],
            "velocity": [0.0, 0.0, 0.0],
            "traction": 0.8,
            "impacts": [],
        },
    }
    digest = digest_of(manifest)
    candidate = FrontierSceneCandidate(
        manifest=manifest, manifest_digest=digest, geometry_vertices=(), moved_clouds=(),
    )
    auth = authorise_candidate(
        digest, operator_id="ops", era="early_3d", issued_ms=1000, ttl_ms=60_000, key=KEY,
    )
    return candidate, auth


def test_registered_eras_match_the_engine_catalogue():
    solvers = discover_era_solvers()
    profiles = list_engine_eras()
    assert [solver.era_id for solver in solvers] == [profile.era.value for profile in profiles]
    assert len(solvers) >= 1
    for solver, profile in zip(solvers, profiles):
        assert solver.fixed_dt_s == 1.0 / profile.tick_hz
        assert solver.allowed_dt_s == (solver.fixed_dt_s,)
        assert solver.integrator == profile.physics_model
        assert solver.iteration_cap == profile.entity_budget.bit_length()
        assert solver.numeric_mode == profile.numeric_mode.value
        assert era_solver(solver.era_id) == solver
    with pytest.raises(StepRejected, match="no registered engine era"):
        _world(era="not_an_era")


def test_ordered_channels_commit_together_and_replay():
    world = _world()
    runtime = AuthoritativeRuntime(world)
    solver = era_solver(ERA)
    receipt = runtime.step(solver.fixed_dt_s)
    assert runtime.world is receipt.world
    assert runtime.world is not world
    assert receipt.frame["channel_order"] == [
        "soft_body", "weather", "lifecycle", "character_collision",
    ]
    soft = receipt.frame["channels"]["soft_body"]
    assert soft[0]["wetness"] > world.soft_nodes[0].wetness
    assert receipt.frame["channels"]["weather"]["terrain_temperature_c"] != (
        world.microclimate.terrain_temperature_c
    )
    assert receipt.world.structures[0].age_days > world.structures[0].age_days
    assert receipt.frame["channels"]["character_collision"]["present"] is True
    assert receipt.world.character.clothing_wetness > 0
    assert receipt.godot_files[GODOT_SCENE] == receipt.frame["godot_scene"]
    again = AuthoritativeRuntime(world).step(solver.fixed_dt_s)
    assert receipt.canonical_bytes == again.canonical_bytes
    assert receipt.godot_files == again.godot_files
    blob = replay_stream(world, 3)
    assert replay_stream(world, 3) == blob
    verify_stream(world, blob)
    verify_dual_chunks(receipt.frame["chunks"])


def test_preflight_rejects_nan_mass_duplicates_and_foreign_dt_without_commit():
    world = _world()
    runtime = AuthoritativeRuntime(world)
    with pytest.raises(StepRejected, match="NaN"):
        runtime.step(float("nan"))
    assert runtime.world is world
    with pytest.raises(StepRejected, match="dt outside"):
        runtime.step(1.0 / 50.0)
    assert runtime.world is world
    with pytest.raises(StepRejected, match="negative mass"):
        _world(actors=(ActorState("runner", (0.0, 0.0, 1.0), (0.0, 0.0, 0.0), -2.0, 0.3, (0.0, 0.0, 0.0)),))
    with pytest.raises(StepRejected, match="duplicate actor id"):
        _world(actors=(
            ActorState("runner", (0.0, 0.0, 1.0), (0.0, 0.0, 0.0), 2.0, 0.3, (0.0, 0.0, 0.0)),
            ActorState("runner", (1.0, 0.0, 1.0), (0.0, 0.0, 0.0), 2.0, 0.3, (0.0, 0.0, 0.0)),
        ))
    with pytest.raises(StepRejected, match="NaN"):
        _world(actors=(ActorState("runner", (float("nan"), 0.0, 1.0), (0.0, 0.0, 0.0), 2.0, 0.3, (0.0, 0.0, 0.0)),))


def test_failed_lifecycle_substep_rolls_the_whole_step_back():
    world = _world(construction_work_days=1.0)
    runtime = AuthoritativeRuntime(world)
    with pytest.raises(StepRejected):
        runtime.step(era_solver(ERA).fixed_dt_s)
    assert runtime.world is world
    assert runtime.world.structures[0].age_days == world.structures[0].age_days
    assert runtime.world.soft_nodes[0].wetness == world.soft_nodes[0].wetness


def test_scene_candidate_enters_only_with_matching_receipt():
    world = _world()
    candidate, auth = _candidate(30.0)
    runtime = AuthoritativeRuntime(world)
    receipt = runtime.step(
        era_solver(ERA).fixed_dt_s, candidate=candidate, authorisation=auth, key=KEY, now_ms=2000,
    )
    assert receipt.world.weather.temperature_c == 30.0
    assert receipt.world.character.position[0] != world.character.position[0]
    assert receipt.frame["candidate_digest"] == candidate.manifest_digest
    assert "Character" in receipt.godot_files[GODOT_SCENE]
    blob = replay_stream(
        world, 2, candidate=candidate, authorisation=auth, key=KEY, now_ms=2000,
    )
    assert replay_stream(
        world, 2, candidate=candidate, authorisation=auth, key=KEY, now_ms=2000,
    ) == blob
    verify_stream(world, blob, candidate=candidate, authorisation=auth, key=KEY, now_ms=2000)

    mismatched = AuthoritativeRuntime(world)
    forged = replace(candidate, manifest_digest="a" * 64)
    with pytest.raises(StepRejected, match="digest"):
        mismatched.step(
            era_solver(ERA).fixed_dt_s, candidate=forged, authorisation=auth, key=KEY, now_ms=2000,
        )
    assert mismatched.world is world
    assert mismatched.world.weather.temperature_c == world.weather.temperature_c

    bad_key = AuthoritativeRuntime(world)
    with pytest.raises(StepRejected, match="signature"):
        bad_key.step(
            era_solver(ERA).fixed_dt_s, candidate=candidate, authorisation=auth,
            key=b"z" * 16, now_ms=2000,
        )
    assert bad_key.world is world


def test_fast_sphere_is_caught_by_sweep_and_controller_does_not_cross():
    solver = era_solver(ERA)
    dt = solver.fixed_dt_s
    start = (0.0, 0.0, 1.0)
    velocity = (80.0, 0.0, 0.0)
    radius = 0.2
    wall = WallState("pane", (1.0, 0.0, 1.0), (1.0, 0.0, 0.0), 0.01, friction=0.8, restitution=0.3)
    assert discrete_sphere_tunnels(start, velocity, radius, dt, wall.point, wall.normal, wall.half_thickness_m)
    unconstrained = start[0] + velocity[0] * dt
    assert unconstrained > wall.point[0] + wall.half_thickness_m
    actor = ActorState("runner", start, velocity, 2.0, radius, velocity, restitution=0.3, friction=0.8)
    world = _world(actors=(actor,), walls=(wall,))
    receipt = AuthoritativeRuntime(world).step(dt)
    landed = receipt.world.actors[0]
    near_face = wall.point[0] - wall.half_thickness_m
    assert landed.position[0] + landed.radius_m <= near_face + 1e-3
    assert landed.desired_velocity == velocity
    assert landed.last_contact_impulse_ns > 0
    assert landed.velocity[0] < velocity[0]
    contact = receipt.contacts[0]
    assert contact["source"]
    assert contact["normal_impulse_ns"] > 0
    assert contact["energy_after_j"] <= contact["energy_before_j"] + 1e-4
    assert contact["friction_impulse_ns"] <= contact["friction_coefficient"] * contact["normal_impulse_ns"] + 1e-4
    assert "runner" in receipt.godot_files[GODOT_SCENE]
    verify_dual_chunks(receipt.frame["chunks"])


def test_character_reference_motion_cannot_tunnel_a_thin_wall():
    solver = era_solver(ERA)
    dt = solver.fixed_dt_s
    wall = WallState("glass", (0.8, 4.0, 1.0), (1.0, 0.0, 0.0), 0.01)
    character = CharacterBody("player", (0.0, 4.0, 1.0), (0.0, 0.0, 0.0), 0.4, 70.0)
    world = _world(
        character=character,
        walls=(wall,),
        desired_character_velocity=(1000.0, 0.0, 0.0),
        actors=(ActorState("bystander", (8.0, 8.0, 1.0), (0.0, 0.0, 0.0), 4.0, 0.3, (0.0, 0.0, 0.0)),),
    )
    receipt = AuthoritativeRuntime(world).step(dt)
    landed = receipt.world.character
    assert landed is not None
    near_face = wall.point[0] - wall.half_thickness_m
    assert landed.position[0] + landed.radius_m <= near_face + 1e-2
    assert receipt.frame["channels"]["character_collision"]["tunneled_wall_corrected"] is True
    verify_dual_chunks(receipt.frame["chunks"])


def test_multi_body_contact_resolves_friction_restitution_and_momentum():
    solver = era_solver(ERA)
    left = ActorState(
        "left", (0.0, 0.0, 1.0), (2.0, 0.4, 0.0), 2.0, 0.25, (2.0, 0.4, 0.0),
        restitution=0.5, friction=0.9,
    )
    right = ActorState(
        "right", (0.55, 0.0, 1.0), (-2.0, -0.1, 0.0), 2.0, 0.25, (-2.0, -0.1, 0.0),
        restitution=0.5, friction=0.4,
    )
    world = _world(actors=(left, right), walls=())
    receipt = AuthoritativeRuntime(world).step(solver.fixed_dt_s)
    assert receipt.contacts
    contact = receipt.contacts[0]
    assert contact["body_b"] == "right"
    assert contact["normal_impulse_ns"] > 0
    assert contact["friction_impulse_ns"] > 0
    assert contact["restitution"] == pytest.approx(0.5)
    assert contact["friction_impulse_ns"] <= contact["friction_coefficient"] * contact["normal_impulse_ns"] + 1e-4
    assert contact["energy_after_j"] <= contact["energy_before_j"] + 1e-4
    assert contact["energy_dissipated_j"] >= 0
    assert abs(contact["momentum_residual_ns"]) < 1e-3
    assert receipt.frame["iterations_used"] >= 1
    assert receipt.frame["iterations_used"] <= receipt.frame["iteration_cap"]
    # Controllers keep their intent and take the post-contact velocity.
    landed = {actor.actor_id: actor for actor in receipt.world.actors}
    assert landed["left"].desired_velocity == left.desired_velocity
    assert landed["left"].velocity != left.velocity
    assert landed["right"].velocity != right.velocity
    verify_dual_chunks(receipt.frame["chunks"])


def test_each_registered_era_replays_and_keeps_one_chunk_per_actor():
    for solver in discover_era_solvers():
        world = _world(
            solver.era_id,
            actors=(
                ActorState("near", (1.0, 0.0, 1.0), (0.0, 0.0, 0.0), 4.0, 0.3, (0.2, 0.0, 0.0)),
                ActorState("far", (40.0, -8.0, 1.0), (0.0, 0.0, 0.0), 4.0, 0.3, (0.0, 0.0, 0.0)),
            ),
        )
        blob = replay_stream(world, 2)
        assert replay_stream(world, 2) == blob
        verify_stream(world, blob)
        runtime = AuthoritativeRuntime(world)
        receipt = runtime.step(solver.fixed_dt_s)
        verify_dual_chunks(receipt.frame["chunks"])
        inverse = dict(receipt.frame["chunks"]["inverse"])
        members = {
            actor_id
            for _chunk, actor_ids in receipt.frame["chunks"]["membership"]
            for actor_id in actor_ids
        }
        assert set(inverse) == members
        assert len(inverse) == len(members) == 3  # player + two actors
        assert inverse["near"] != inverse["far"]
        assert receipt.frame["integrator"] == solver.integrator
        assert receipt.frame["fixed_dt_s"] == solver.fixed_dt_s
        assert receipt.frame["iteration_cap"] == solver.iteration_cap


def test_integrator_changes_the_committed_pose_at_the_same_tick_rate():
    kinematic = era_solver("vector_sprite_1977")
    rigid = era_solver("shader_console_2001")
    assert kinematic.fixed_dt_s == rigid.fixed_dt_s
    assert kinematic.integrator != rigid.integrator

    def pose(solver):
        actor = ActorState("mover", (0.0, 0.0, 1.0), (0.0, 0.0, 0.0), 8.0, 0.3, (10.0, 0.0, 0.0))
        world = _world(solver.era_id, actors=(actor,))
        return AuthoritativeRuntime(world).step(solver.fixed_dt_s).world.actors[0].position[0]

    assert pose(kinematic) > pose(rigid)


def test_actor_crossing_a_chunk_boundary_stays_in_exactly_one_chunk():
    solver = era_solver(ERA)
    actor = ActorState("hopper", (15.9, 0.0, 1.0), (30.0, 0.0, 0.0), 5.0, 0.3, (30.0, 0.0, 0.0))
    world = _world(actors=(actor,), character=CharacterBody("player", (0.0, 0.0, 1.0), (0.0, 0.0, 0.0), 0.4, 70.0))
    receipt = AuthoritativeRuntime(world).step(solver.fixed_dt_s)
    inverse = dict(receipt.frame["chunks"]["inverse"])
    assert inverse["hopper"] != "0:0:0"
    verify_dual_chunks(receipt.frame["chunks"])
