"""Single candidate-only composition entry point for the frontier game milestones.

This module joins *existing Jeeves-owned* deterministic game components. It
does not open GPU providers, mutate world state, or certify neural-model output.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Iterable

from .game_frontier_dynamics import (
    Cloud, InputObservation, PresentationClock, WindField, WorldAxis,
    advect_clouds, anticipate_user_motion, generate_world_cell,
)
from .game_frontier_production import (
    AnimationClip, CharacterSkeleton, Percept, plan_cinematic,
    pose_skinned_mesh, reason_about_world, skeleton_to_polygon, Vec3,
)
from .game_frontier_worlds import (
    WorldVariant, CameraSpec, variant_world_cell, project_scene,
)
from .game_frontier_motion import (
    Weather, CharacterState, CharacterStep, CollisionPlane,
    SoftNode, EnvironmentalState, StructureState,
    simulate_character, simulate_soft_nodes, advance_environment, age_structure,
)
from .game_frontier_lighting import (
    SurfaceSample, LightSource, RayOccluder, illuminate_scene,
)
from .game_frontier_ecosystem import (
    AirConditions, CelestialCycle, LiquidGrid, AudioEnvironment,
    sample_atmosphere, sample_tides, advance_liquid,
    interact_with_water, mix_environment_audio,
)
from .game_frontier_photometry import (
    LeafPose, LightClimate, move_leaf, verify_leaf_shadow, illuminate_atmosphere_3d,
)
from .game_frontier_chunks import verify_registered_era_chunks
from .game_frontier_chunk_evidence import (
    build_frame_chunk_receipts, build_mesh_chunk_receipts,
)
from .game_frontier_mesh_evolution import PixelAsset, create_old_new_asset_pair
from .game_frontier_biome_motion import (
    ShrubState, SmallRockState, ContactForce, BiomeMotion, advance_biome_objects,
)
from .game_frontier_advanced_physics import (
    RigidBody, AeroProfile, WakeSource, UpdraftColumn, TractionSurface,
    Climber, CollisionContact, airflow_at, integrate_air_motion,
    evaluate_climbing, resolve_contact, aggregate_realism,
)
from .game_frontier_realism import audit_scene_realism
from .game_frontier_weather_physics import Microclimate, evolve_microclimate
from .game_frontier_character_suite import CharacterSuiteConfig, compile_character_suite
from .game_frontier_geoposition import (
    LocationConsent, DeviceGPSFix, SurveyControl, SurveySighting,
    ingest_host_gps, solve_control_survey, reconcile_live_and_survey,
)
from .game_frontier_virtual_navigation import (
    VirtualNavigationRequest, compose_virtual_navigation,
)
from .game_frontier_frame_coherence import (
    GDDSource, FrameObject, FrameReceipt, GDDFrameNote, advance_frame,
)

FRONTIER_SCENE_SCHEMA = "skeleton.game.frontier_scene_candidate.v1"
FRONTIER_MODEL_STATUS = "engine_candidate_only_no_proprietary_weights"


@dataclass(frozen=True)
class FrontierSceneCandidate:
    manifest: dict
    manifest_digest: str
    geometry_vertices: tuple
    moved_clouds: tuple[Cloud, ...]
    approved_for_runtime: bool = False
    geometry_triangles: tuple[tuple[int, int, int], ...] = ()
    geometry_colliders: tuple = ()


def compile_frontier_scene(
    *,
    world_axes: WorldAxis,
    cell_x: int,
    cell_y: int,
    wind_field: WindField,
    clouds: Iterable[Cloud],
    time_s: float,
    delta_s: float,
    skeleton: CharacterSkeleton,
    animation: AnimationClip,
    animation_time_ms: int,
    era: str,
    fps: int,
    evidence: Iterable[Percept],
    world_goal_kind: str,
    available_actions: Iterable[str],
    speculative_input: InputObservation | None = None,
    prediction_horizon_ms: int = 100,
    triangle_budget: int | None = None,
    world_variant: WorldVariant | None = None,
    camera: CameraSpec | None = None,
    weather: Weather | None = None,
    character_state: CharacterState | None = None,
    collision_surfaces: tuple[CollisionPlane, ...] = (),
    desired_character_velocity: Vec3 | None = None,
    soft_nodes: tuple[SoftNode, ...] = (),
    soft_anchors: tuple[Vec3, ...] = (),
    environment_state: EnvironmentalState | None = None,
    structures: tuple[StructureState, ...] = (),
    construction_work_days: float = 0,
    maintenance_work_days: float = 0,
    lighting_surfaces: tuple[SurfaceSample, ...] = (),
    light_sources: tuple[LightSource, ...] = (),
    light_occluders: tuple[RayOccluder, ...] = (),
    air_conditions: AirConditions | None = None,
    celestial_cycle: CelestialCycle | None = None,
    liquid_grid: LiquidGrid | None = None,
    leaf_poses: tuple[LeafPose, ...] = (),
    solar_direction: Vec3 = Vec3(0, 0, 1),
    trace_3d_lighting: bool = False,
    audio_source_distance_m: float | None = None,
    verify_all_era_chunks: bool = False,
    original_pixel_asset: PixelAsset | None = None,
    shrubs: tuple[ShrubState, ...] = (),
    small_rocks: tuple[SmallRockState, ...] = (),
    advanced_body: RigidBody | None = None,
    advanced_aero: AeroProfile | None = None,
    advanced_traction: TractionSurface | None = None,
    advanced_climber: Climber | None = None,
    advanced_wakes: tuple[WakeSource, ...] = (),
    advanced_thermals: tuple[UpdraftColumn, ...] = (),
    advanced_contact: CollisionContact | None = None,
    advanced_other_body: RigidBody | None = None,
    advanced_turbulence_amplitude: float = 0.,
    advanced_microclimate: Microclimate | None = None,
    character_suite: CharacterSuiteConfig | None = None,
    gps_fix: DeviceGPSFix | None = None,
    gps_consent: LocationConsent | None = None,
    gps_now_ms: int | None = None,
    previous_gps_fix: DeviceGPSFix | None = None,
    survey_controls: tuple[SurveyControl, ...] = (),
    survey_sightings: tuple[SurveySighting, ...] = (),
    frame_gdd: GDDSource | None = None,
    frame_index: int | None = None,
    frame_objects: tuple[FrameObject, ...] = (),
    previous_frame_receipt: FrameReceipt | None = None,
    previous_frame_evidence: dict | None = None,
    between_frame_notes: tuple[GDDFrameNote, ...] = (),
    virtual_navigation: VirtualNavigationRequest | None = None,
    previous_virtual_navigation: dict | None = None,
) -> FrontierSceneCandidate:
    """Produce a content-addressed, inspectable, playable-engine-side proposal.

    Authority changes, scene import and model checkpoint inference MUST go
    through the existing engine/forge acceptance and provider-runtime planes.
    A candidate is never marked approved merely because it can be composed.
    """
    cell = generate_world_cell(world_axes, cell_x, cell_y)
    moved = advect_clouds(clouds, wind_field, time_s=time_s, elapsed_s=delta_s)
    clock = PresentationClock(fps)
    mesh = skeleton_to_polygon(skeleton, era, max_triangles=triangle_budget)
    vertices = pose_skinned_mesh(skeleton, mesh, animation, animation_time_ms)
    observations = tuple(evidence)
    cinematic = plan_cinematic(observations)
    next_action = reason_about_world(observations,
                                     goal_kind=world_goal_kind,
                                     available_actions=available_actions)
    variant_cell = (variant_world_cell(world_axes, world_variant, cell_x, cell_y)
                    if world_variant is not None else None)
    points = project_scene(vertices, camera, variant=world_variant) if camera is not None else ()
    physical_weather = weather
    if physical_weather is None and any((character_state is not None, soft_nodes,
                                         environment_state is not None, structures)):
        wind = wind_field.sample(cell_x, cell_y, 0, time_s)
        # World variant affects derived weather and liquid exposure, not just
        # display metadata. An explicit Weather supplied by the host wins.
        local_temp = variant_cell.temperature if variant_cell else cell.temperature
        local_humidity = variant_cell.humidity if variant_cell else cell.humidity
        elemental_water_depth = (max(0, local_humidity - cell.humidity) * 2
                                 if world_variant is not None
                                 and world_variant.family.value == "elemental"
                                 and world_variant.element == "water" else 0)
        physical_weather = Weather(Vec3(wind.east_mps, wind.north_mps, 0),
                                   (local_temp - .5) * 60,
                                   humidity=local_humidity,
                                   water_depth_m=elemental_water_depth)
    # Do not infer authority, run prediction model or mutate host-scene objects.
    if (character_state is not None and desired_character_velocity is None):
        raise ValueError("character simulation requires explicit desired velocity")
    if (soft_nodes or soft_anchors) and physical_weather is None:
        raise ValueError("soft material simulation requires weather")
    ethereal_collision_disabled = bool(variant_cell and variant_cell.permeability >= .8)
    collision_candidates = () if ethereal_collision_disabled else collision_surfaces
    signed_gravity = 9.81 * (variant_cell.gravity_sign if variant_cell else 1)
    character_step = (simulate_character(character_state, physical_weather,
                                         collision_candidates,
                                         desired_velocity=desired_character_velocity,
                                         gravity_mps2=signed_gravity,
                                         delta_s=delta_s)
                      if character_state is not None else None)
    simulated_soft = (simulate_soft_nodes(soft_nodes, physical_weather,
                                           anchors=soft_anchors, delta_s=delta_s)
                      if soft_nodes else ())
    if soft_anchors and not soft_nodes:
        raise ValueError("soft anchors require soft nodes")
    environment_step = (advance_environment(environment_state, physical_weather,
                                            delta_days=delta_s / 86400,
                                            impact=character_step.impacts[0]
                                            if character_step and character_step.impacts else None)
                        if environment_state is not None else None)
    if (construction_work_days or maintenance_work_days) and not structures:
        raise ValueError("construction or maintenance requires structures")
    if len(structures) > 1024:
        raise ValueError("structure batch exceeds limit")
    structure_steps = tuple(
        age_structure(s, physical_weather, elapsed_days=delta_s / 86400,
                      work_days=construction_work_days,
                      maintenance_days=maintenance_work_days,
                      impact=character_step.impacts[0]
                      if character_step and character_step.impacts else None)
        for s in structures
    )
    cloud_coverage = (sum(c.opacity for c in moved) / len(moved)) if moved else 0
    world_luminance = variant_cell.luminance if variant_cell else .7
    ambient = max(.005, .1 * (world_luminance / .7) * (1 - cloud_coverage * .45))
    light_steps = (illuminate_scene(
        lighting_surfaces, light_sources, light_occluders,
        ambient_rgb=(ambient, ambient, ambient),
    ) if lighting_surfaces else ())
    # New environmental measurements remain explicit and reproducible; no
    # invented live meteorological observations or gameplay mutations.
    if air_conditions is None:
        if physical_weather is not None:
            air_conditions = AirConditions(
                altitude_m=830, temperature_c=physical_weather.temperature_c,
                relative_humidity=physical_weather.humidity,
                rain_mm_h=physical_weather.precipitation_mm_h)
        else:
            air_conditions = AirConditions()
    atmosphere = sample_atmosphere(air_conditions)
    tide = sample_tides(celestial_cycle) if celestial_cycle is not None else None
    liquid_step = (advance_liquid(
        liquid_grid, delta_s=delta_s,
        rain_mm_h=air_conditions.rain_mm_h)
                   if liquid_grid is not None else None)
    water_response = None
    if character_step is not None and liquid_step is not None:
        # Reference water interaction uses a nominated cell, not an
        # unsupported claim that this grid is a 3D fluid solver.
        surface_z = (liquid_step.grid.bed_elevation_m[0] +
                     liquid_step.grid.water_depth_m[0] +
                     (tide.water_height_m if tide else 0))
        water_response = interact_with_water(
            water_surface_z_m=surface_z,
            character_foot_z_m=character_step.state.position.z -
                               character_step.state.radius_m,
            character_height_m=character_step.state.radius_m * 3.4,
            character_volume_m3=character_step.state.mass_kg / 985,
            velocity=character_step.state.velocity)
    if len(leaf_poses) > 1024:
        raise ValueError("leaf budget exceeded")
    active_wind = (physical_weather.wind if physical_weather else
                   Vec3(wind_field.sample(cell_x, cell_y, 0, time_s).east_mps,
                        wind_field.sample(cell_x, cell_y, 0, time_s).north_mps, 0))
    moved_leaves = []
    for leaf in leaf_poses:
        contact_force = Vec3(0, 0, 0)
        if character_step and character_step.impacts and (
                (character_step.state.position - leaf.center).dot(
                    character_step.state.position - leaf.center) < 4):
            impact = character_step.impacts[0]
            contact_force = impact.normal.scaled(min(3., impact.impulse_ns / 100))
        moved_leaves.append(move_leaf(leaf, wind_mps=active_wind,
                                     dt_s=delta_s, impact_impulse_ns=contact_force))
    audit_leaves = tuple(verify_leaf_shadow(leaf, sun_toward=solar_direction)
                         for leaf in moved_leaves) if leaf_poses else ()
    object_contacts = tuple(
        ContactForce(character_step.state.position,
                     impact.normal.scaled(impact.impulse_ns),
                     character_step.state.radius_m)
        for impact in (character_step.impacts if character_step else ())
    )
    if shrubs or small_rocks:
        # Integrate in physical substeps; ordinary long-duration scenes
        # without biome objects must remain backwards-compatible.
        import math
        steps = max(1, math.ceil(delta_s / .1))
        if steps > 1024:
            raise ValueError("biome solver requires bounded host time chunks")
        shrub_state, rock_state, contact_count = shrubs, small_rocks, 0
        for step in range(steps):
            updated = advance_biome_objects(
                shrub_state, rock_state, wind=active_wind,
                dt_s=delta_s / steps,
                contacts=object_contacts if step == 0 else ())
            shrub_state, rock_state = updated.shrubs, updated.rocks
            contact_count += updated.impact_count
        biome_motion = BiomeMotion(shrub_state, rock_state, contact_count)
    else:
        biome_motion = BiomeMotion((), (), 0)
    # Current moving geometry participates in *the same frame's* rays.
    extra_occluders = tuple(
        RayOccluder("shrub:"+obj.shrub_id,"foliage",obj.tip,
                    "sphere",obj.radius_m,opacity=.65)
        for obj in biome_motion.shrubs
    ) + tuple(
        RayOccluder("rock:"+obj.rock_id,"object",obj.position,
                    "sphere",obj.radius_m)
        for obj in biome_motion.rocks
    )
    if character_step is not None:
        extra_occluders += (
            RayOccluder("character:current","character",
                        character_step.state.position,"sphere",
                        character_step.state.radius_m),
        )
    climate = LightClimate(
        atmosphere, rain_mm_h=air_conditions.rain_mm_h,
        cloud_opacity=cloud_coverage)
    traced = (tuple(illuminate_atmosphere_3d(
        surface, light_sources, light_occluders + extra_occluders,
        tuple(moved_leaves), climate)
                    for surface in lighting_surfaces)
              if trace_3d_lighting and lighting_surfaces else ())
    audio = (mix_environment_audio(AudioEnvironment(
        audio_source_distance_m, 1., atmosphere,
        air_conditions.rain_mm_h, bool(light_occluders), tide))
             if audio_source_distance_m is not None else None)
    chunk_reports = (verify_registered_era_chunks(
        vertices, mesh.triangles) if verify_all_era_chunks else ())
    # Per-era mesh evidence remains opt-in; it records source and independent
    # topology checks, not actual console/GPU streaming acceptance.
    mesh_evidence = [
        build_mesh_chunk_receipts(vertices,mesh.triangles,era=report.era)
        for report in chunk_reports
    ]
    old_new_meshes = (create_old_new_asset_pair(original_pixel_asset)
                      if original_pixel_asset is not None else ())
    # Advanced physics runs only by explicit actor opt-in. The old
    # CharacterStep stays authoritative to the reference and cannot be
    # silently overwritten by a later/parallel physics candidate.
    advanced_receipt = None
    if advanced_body is None and any((
        advanced_aero is not None, advanced_traction is not None,
        advanced_climber is not None, advanced_wakes, advanced_thermals,
        advanced_contact is not None, advanced_other_body is not None,
        advanced_turbulence_amplitude != 0,
        advanced_microclimate is not None,
    )):
        raise ValueError("advanced physics inputs require advanced_body")
    if advanced_body is not None:
        if (advanced_aero is None or advanced_traction is None
                or advanced_climber is None):
            raise ValueError("advanced physics requires aero, traction, climber")
        if advanced_other_body is not None and advanced_contact is None:
            raise ValueError("second body requires an explicit contact")
        import math
        count = max(1, math.ceil(delta_s / .05))
        if count > 1024:
            raise ValueError("advanced physics requires host-subdivided time")
        candidate_body = advanced_body
        terrain_step = None
        active_traction = advanced_traction
        active_thermals = advanced_thermals
        physical_wind = active_wind
        if advanced_microclimate is not None:
            # Weather and terrain grip evolve from the same source conditions,
            # rather than adjusting character friction through a visual cue.
            climate_weather = physical_weather or Weather(
                active_wind, air_conditions.temperature_c,
                precipitation_mm_h=air_conditions.rain_mm_h,
                humidity=air_conditions.relative_humidity)
            terrain_step = evolve_microclimate(
                advanced_microclimate, climate_weather,
                air_conditions, advanced_traction,
                delta_s=delta_s, location=advanced_body.position)
            active_traction = terrain_step.traction_surface
            active_thermals = (*advanced_thermals, terrain_step.terrain_updraft)
            physical_wind = active_wind + terrain_step.pressure_wind_delta
        flow = None
        aero_step = None
        for tick in range(count):
            flow = airflow_at(
                candidate_body.position, ambient_wind=physical_wind,
                air=air_conditions, wakes=advanced_wakes,
                thermals=active_thermals,
                turbulence_seed=wind_field.seed,
                time_s=time_s + tick * (delta_s / count),
                turbulence_amplitude=advanced_turbulence_amplitude,
            )
            aero_step = integrate_air_motion(
                candidate_body, advanced_aero, flow,
                delta_s=delta_s / count,
                gravity_mps2=abs(signed_gravity),
            )
            candidate_body = aero_step.body
        assert flow is not None and aero_step is not None
        grip = evaluate_climbing(
            active_traction, advanced_climber,
            wind=flow.wind,
            motion_mps=math.hypot(candidate_body.velocity.x,
                                  candidate_body.velocity.y),
            gravity_mps2=abs(signed_gravity),
        )
        collision = (resolve_contact(candidate_body, advanced_other_body,
                                     advanced_contact)
                     if advanced_contact is not None else None)
        final_body = collision.body_a if collision is not None else candidate_body
        metrics = aggregate_realism(aero_step, flow, grip,
                                    active_traction, collision)
        advanced_receipt = {
            "body": {
                "id": final_body.body_id,
                "position_xyz": [final_body.position.x,
                                 final_body.position.y, final_body.position.z],
                "velocity_xyz": [final_body.velocity.x,
                                 final_body.velocity.y, final_body.velocity.z],
                "angular_velocity_xyz": [
                    final_body.angular_velocity.x,
                    final_body.angular_velocity.y,
                    final_body.angular_velocity.z],
                "mass_kg": final_body.mass_kg,
                "radius_m": final_body.radius_m,
                "restitution": final_body.restitution,
                "friction": final_body.friction,
            },
            "aero_coefficients": {
                "drag_coefficient": advanced_aero.drag_coefficient,
                "projected_area_m2": advanced_aero.projected_area_m2,
                "lift_coefficient": advanced_aero.lift_coefficient,
                "lift_area_m2": advanced_aero.lift_area_m2,
            },
            "airflow_velocity_xyz": [flow.wind.x, flow.wind.y, flow.wind.z],
            "terminal_velocity_mps": metrics.terminal_speed_mps,
            "relative_wind_mps": aero_step.relative_air_speed_mps,
            "air_density_kg_m3": flow.air_density_kg_m3,
            "draft_shelter_fraction": metrics.wake_shelter_fraction,
            "updraft_mps": flow.updraft_mps,
            "turbulence_xyz": [flow.turbulence.x,
                               flow.turbulence.y, flow.turbulence.z],
            "aerodynamic_drag_n_xyz": [
                aero_step.drag_force_n.x, aero_step.drag_force_n.y,
                aero_step.drag_force_n.z],
            "dissipated_drag_energy_j": aero_step.drag_dissipation_j,
            "traction": {
                "max_slope_degrees": grip.max_slope_degrees,
                "slope_degrees": grip.slope_degrees,
                "required_force_n": grip.required_uphill_force_n,
                "available_force_n": grip.available_climbing_force_n,
                "slip_risk": grip.slip_risk,
                "climbable": grip.climbing_possible,
                "gait": grip.recommended_gait,
                "speed_scale": grip.recommended_speed_scale,
            },
            "microclimate": ({
                "ground_temperature_c": terrain_step.state.terrain_temperature_c,
                "soil_water_fraction": terrain_step.state.soil_water_fraction,
                "ground_ice_fraction": terrain_step.state.ground_ice_fraction,
                "loose_sediment_fraction": terrain_step.state.loose_sediment_fraction,
                "pressure_wind_delta_xyz": [
                    terrain_step.pressure_wind_delta.x,
                    terrain_step.pressure_wind_delta.y,
                    terrain_step.pressure_wind_delta.z],
                "updraft_mps": terrain_step.terrain_updraft.vertical_velocity_mps,
                "rain_absorption_m": terrain_step.rain_absorption_m,
                "evaporation_m": terrain_step.evaporation_m,
                "freeze_thaw_transition": terrain_step.freeze_thaw_transition,
                "erosion_pressure": terrain_step.erosion_pressure,
            } if terrain_step else None),
            "impact": ({
                "impulse_ns": collision.normal_impulse_ns,
                "friction_impulse_ns": collision.friction_impulse_ns,
                "energy_loss_j": collision.energy_dissipated_j,
                "damage_a": collision.damage_a,
                "damage_b": collision.damage_b,
                "momentum_residual_ns": collision.momentum_residual_ns,
            } if collision else None),
            "realism_invariants": {
                "collision_energy_nonincreasing":
                    metrics.collision_energy_nonincreasing,
                "momentum_residual_ns": metrics.momentum_residual_ns,
                "climb_safe": metrics.climbing_safe,
                "evidence_digest": metrics.evidence_digest,
            },
            "authority": "candidate_only_no_native_mutation",
        }
    # Opt-in character suite: barycentric load, elastic mesh, simulated
    # instruments and RPG conditions. No event or physics execution.
    import math
    derived_signals = {
        "altitude_m": atmosphere.altitude_m,
        "pressure_pa": atmosphere.pressure_pa,
        "fog_visibility_m": atmosphere.meteorological_visibility_m,
        "humidity": air_conditions.relative_humidity,
        "temperature_c": (physical_weather.temperature_c if physical_weather
                          else air_conditions.temperature_c),
        "rain_mm_h": air_conditions.rain_mm_h,
        "wind_mps": math.sqrt(active_wind.dot(active_wind)),
    }
    if tide:
        derived_signals.update({
            "tide_height_m": tide.water_height_m,
            "moon_phase": tide.moon_phase,
            "solar_height": tide.sun_altitude_proxy,
            "daylight": 1. if tide.sun_altitude_proxy > 0 else 0.,
        })
    if liquid_step:
        derived_signals["water_depth_m"] = liquid_step.grid.water_depth_m[0]
    elif physical_weather:
        derived_signals["water_depth_m"] = physical_weather.water_depth_m
    if advanced_receipt:
        derived_signals["updraft_mps"] = advanced_receipt["updraft_mps"]
        gust = advanced_receipt["turbulence_xyz"]
        derived_signals["turbulence_mps"] = math.sqrt(sum(v*v for v in gust))
        derived_signals["fall_speed_mps"] = max(
            0., -advanced_receipt["body"]["velocity_xyz"][2])
        derived_signals["traction_slip_risk"] = advanced_receipt["traction"]["slip_risk"]
        derived_signals["climb_angle_deg"] = advanced_receipt["traction"]["slope_degrees"]
        if advanced_receipt["impact"]:
            derived_signals["impact_impulse_ns"] = advanced_receipt["impact"]["impulse_ns"]
            derived_signals["collision_energy_j"] = advanced_receipt["impact"]["energy_loss_j"]
        local_climate = advanced_receipt.get("microclimate")
        if local_climate:
            derived_signals["soil_wetness"] = local_climate["soil_water_fraction"]
            derived_signals["ground_ice_fraction"] = local_climate["ground_ice_fraction"]
            derived_signals["erosion"] = local_climate["erosion_pressure"]
    elif character_step:
        derived_signals["traction_slip_risk"] = character_step.awareness.slip_risk
    if traced:
        derived_signals["shadow_fraction"] = traced[0].geometric_shadow_fraction
    if audit_leaves:
        derived_signals["leaf_shadow_area_m2"] = audit_leaves[0].geometric_area_m2
    if environment_step:
        derived_signals.setdefault("erosion",environment_step.erosion)
        derived_signals.setdefault("soil_wetness",environment_step.soil_saturation)
    if structure_steps:
        derived_signals["building_integrity"] = structure_steps[0].integrity
    if variant_cell:
        derived_signals["sky_island_height_m"] = variant_cell.celestial_altitude
    if audio:
        derived_signals["sound_occlusion"] = float(bool(light_occluders))
        derived_signals["music_intensity"] = audio.gain
    character_suite_receipt = (compile_character_suite(
        character_suite, skeleton=skeleton, mesh=mesh,
        animation=animation, animation_time_ms=animation_time_ms,
        delta_s=delta_s, weather=physical_weather,
        derived_observations=derived_signals,
    ) if character_suite is not None else None)
    # Host permission and freshness are mandatory. Raw live/surveyed
    # coordinates never enter hashed, logged or exported scene manifests.
    if gps_fix is None and any((gps_consent is not None,
                               gps_now_ms is not None,
                               previous_gps_fix is not None)):
        raise ValueError("GPS authority fields require a live device fix")
    if bool(survey_controls) != bool(survey_sightings):
        raise ValueError("survey controls and sightings must be paired")
    live = None
    if gps_fix is not None:
        if gps_consent is None or gps_now_ms is None:
            raise ValueError("live GPS fix requires explicit host permission/time")
        live = ingest_host_gps(gps_fix, gps_consent, now_ms=gps_now_ms,
                               prior=previous_gps_fix)
    surveyed = (solve_control_survey(survey_controls, survey_sightings)
                if survey_sightings else None)
    position_receipt = ({
        "live": live.public_receipt() if live is not None else None,
        "surveyed": surveyed.public_receipt() if surveyed is not None else None,
        "coherence": (reconcile_live_and_survey(live, surveyed)
                      if live is not None and surveyed is not None else None),
        "coordinates_redacted": True,
        "authority": "optional_permissioned_observation_no_persistence",
    } if (live is not None or surveyed is not None) else None)
    frame_receipt = None
    frame_chunk_evidence = None
    if frame_gdd is None and any((
        frame_index is not None, frame_objects,
        previous_frame_receipt is not None, between_frame_notes,
        previous_frame_evidence is not None,
    )):
        raise ValueError("per-frame build requires a signed GDD")
    if frame_gdd is not None:
        if frame_index is None or not frame_objects:
            raise ValueError("per-frame build requires frame index and source objects")
        frame_receipt = advance_frame(
            frame_index=frame_index, fps=clock.fps, gdd=frame_gdd,
            objects=frame_objects, previous=previous_frame_receipt,
            notes=between_frame_notes)
        frame_chunk_evidence = build_frame_chunk_receipts(
            frame_receipt,frame_gdd,
            previous=previous_frame_receipt,
            previous_evidence=previous_frame_evidence)
    # Real OS positioning stays isolated behind explicit consent and redacted
    # receipts. Fictional game-map GPS NEVER uses that sensor/permission path.
    if virtual_navigation is not None and (gps_fix is not None or survey_controls):
        raise ValueError("do not mix virtual game positioning with physical GPS/survey")
    if previous_virtual_navigation is not None and virtual_navigation is None:
        raise ValueError("prior virtual GPS requires current virtual map observation")
    virtual_position = (compose_virtual_navigation(
        virtual_navigation, frame=frame_receipt,
        gdd=frame_gdd if frame_receipt is not None else None,
        previous_frame=previous_frame_receipt,
        previous_navigation=previous_virtual_navigation)
        if virtual_navigation is not None else None)
    prediction = None
    if speculative_input is not None:
        anticipated = anticipate_user_motion(speculative_input, horizon_ms=prediction_horizon_ms)
        prediction = {
            "x": anticipated.x, "y": anticipated.y,
            "horizon_ms": anticipated.prediction_horizon_ms,
            "confidence_upper_bound": anticipated.confidence_upper_bound,
            "evidence": anticipated.source_digest, "authority": anticipated.authority,
        }
    manifest = {
        "schema": FRONTIER_SCENE_SCHEMA, "model_status": FRONTIER_MODEL_STATUS,
        "world": {
            "seed": world_axes.seed,
            "axis": {"terrain": world_axes.terrain, "moisture": world_axes.moisture,
                     "temperature": world_axes.temperature, "verticality": world_axes.verticality,
                     "sky_islands": world_axes.sky_islands,
                     "weather_volatility": world_axes.weather_volatility},
            "cell": {"x": cell.x, "y": cell.y, "elevation": cell.elevation,
                     "humidity": cell.humidity, "temperature": cell.temperature,
                     "biome": cell.biome, "sky_island": cell.sky_island,
                     "gust_strength": cell.gust_strength},
        },
        "wind_configuration": {"seed": wind_field.seed,
                               "gust_period_s": wind_field.gust_period_s},
        "simulation_time_s": time_s + delta_s,
        "wind": [{"altitude_m": layer.altitude_m,
                  "east_mps": layer.base.east_mps, "north_mps": layer.base.north_mps,
                  "turbulence_mps": layer.turbulence_mps,
                  "cell_size_m": layer.cell_size_m}
                 for layer in wind_field.layers],
        "clouds": [
            {"id": c.cloud_id, "x_m": c.x_m, "y_m": c.y_m,
             "altitude_m": c.altitude_m, "opacity": c.opacity,
             "stretch": c.stretch, "orientation_rad": c.orientation_rad}
            for c in moved
        ],
        "render": {
            "era": era, "fps": clock.fps,
            "next_presentation_deadline_ns": clock.deadline(1),
            "triangle_count": mesh.triangle_count,
            "polygon_regression_ratio": mesh.regression_ratio,
            "rigged_mesh_digest": mesh.digest,
            "vertex_count": len(vertices),
        },
        "animation": {"clip": animation.name, "sample_ms": animation_time_ms,
                      "bone_count": len(skeleton.bones),
                      "collision_capsules": len(mesh.colliders)},
        "cognition": {
            "shot": cinematic.shot, "focus": cinematic.focus_object_id,
            "shot_reasons": list(cinematic.rationale),
            "shot_evidence": list(cinematic.evidence_digests),
            "suggested_action": next_action.action,
            "target": next_action.target,
            "action_reasons": list(next_action.rationale),
            "action_evidence": list(next_action.evidence_digests),
            "authority": "suggestions_only",
            "signed_gdd_digest": (frame_receipt.gdd_digest
                                  if frame_receipt is not None else None),
            "verified_frame_digest": (frame_receipt.receipt_digest
                                       if frame_receipt is not None else None),
            "frame_context_notes": [{
                "source_law_index": n.world_law_index,
                "source_law_text": frame_gdd.world_laws[n.world_law_index],
                "design_context": n.text,
                "review_status": n.author_kind,
            } for n in frame_receipt.note_from_previous]
            if frame_receipt is not None else [],
            "gdd_context_authority": "AI_proposal_no_auto_canon_promotion",
            "virtual_navigation_context": ({
                "world_id": virtual_position["world_id"],
                "realm_id": virtual_position["realm_id"],
                "map_tile_xy": virtual_position["map_tile_xy"],
                "world_xyz_m": virtual_position["world_xyz_m"],
                "uncertainty_m": virtual_position["horizontal_uncertainty_m"],
                "navigation_receipt_digest": virtual_position["receipt_digest"],
                "linked_frame_receipt_digest": (
                    frame_receipt.receipt_digest if frame_receipt else None),
                "linked_signed_gdd_digest": (
                    frame_gdd.source_digest if frame_receipt else None),
                "requires_human_design_approval": True,
                "authority": "fictional_navigation_design_context_not_canon",
            } if virtual_position is not None else None),
        },
        "preemptive_input": prediction,
        "world_variant": ({
            "family": world_variant.family.value,
            "element": world_variant.element, "intensity": world_variant.intensity,
            "source_coordinates": [variant_cell.source_x, variant_cell.source_y],
            "gravity_sign": variant_cell.gravity_sign,
            "character_collision_ethereal_pass_through": ethereal_collision_disabled,
            "energy": variant_cell.world_energy,
            "permeability": variant_cell.permeability,
            "luminance": variant_cell.luminance,
            "celestial_altitude": variant_cell.celestial_altitude,
            "elevation": variant_cell.elevation,
            "temperature": variant_cell.temperature,
            "humidity": variant_cell.humidity,
            "sky_island": variant_cell.sky_island,
        } if variant_cell else None),
        "projection": ({
            "mode": camera.mode.value,
            "camera_xyz": [camera.position.x, camera.position.y, camera.position.z],
            "projected_vertices": len(points),
            "visible_vertices": sum(1 for p in points if p.visible),
            "first_vertex": ([points[0].screen_x, points[0].screen_y]
                             if points else None),
        } if camera else None),
        "weather_physics": ({
            "temperature_c": physical_weather.temperature_c,
            "wind_xyz": [physical_weather.wind.x, physical_weather.wind.y,
                         physical_weather.wind.z],
            "rain_mm_h": physical_weather.precipitation_mm_h,
            "water_depth_m": physical_weather.water_depth_m,
            "snow_depth_m": physical_weather.snow_depth_m,
        } if physical_weather else None),
        "character_physics": ({
            "position": [character_step.state.position.x,
                         character_step.state.position.y,
                         character_step.state.position.z],
            "velocity": [character_step.state.velocity.x,
                         character_step.state.velocity.y,
                         character_step.state.velocity.z],
            "gait": character_step.state.gait,
            "core_temperature_c": character_step.state.core_temperature_c,
            "clothing_wetness": character_step.state.clothing_wetness,
            "hair_wetness": character_step.state.hair_wetness,
            "boot_wetness": character_step.state.boot_wetness,
            "traction": character_step.friction_coefficient,
            "awareness": {
                "cold_stress": character_step.awareness.cold_stress,
                "heat_stress": character_step.awareness.heat_stress,
                "wet_stress": character_step.awareness.wet_stress,
                "slip_risk": character_step.awareness.slip_risk,
                "protective_action": character_step.awareness.protective_action,
            },
            "impacts": [{"surface": i.surface_id, "impulse_ns": i.impulse_ns,
                         "damage": i.damage, "material": i.material}
                        for i in character_step.impacts],
        } if character_step else None),
        "soft_material_motion": [{
            "id": n.node_id, "material": n.material,
            "xyz": [n.position.x, n.position.y, n.position.z],
            "wetness": n.wetness, "temperature_c": n.temperature_c,
        } for n in simulated_soft],
        "environment_response": ({
            "soil_saturation": environment_step.soil_saturation,
            "erosion": environment_step.erosion,
            "foliage_bend": environment_step.foliage_bend,
            "vegetation_health": environment_step.vegetation_health,
            "puddle_depth_m": environment_step.puddle_depth_m,
            "snow_load": environment_step.snow_load,
            "debris_fraction": environment_step.debris_fraction,
        } if environment_step else None),
        "structures": [{
            "id": s.structure_id, "material": s.material,
            "built": s.complete, "construction_progress_days": s.construction_progress_days,
            "age_days": s.age_days, "integrity": s.integrity,
            "weathering": s.surface_weathering,
            "biological_growth": s.biological_growth,
            "water_infiltration": s.water_infiltration,
            "maintenance_debt": s.maintenance_debt,
        } for s in structure_steps],
        "ray_lighting": [{
            "object_id": l.object_id,
            "rgb": list(l.radiance_rgb),
            "shadow_fraction": l.shadow_occlusion,
            "character_occluders": list(l.character_occluders),
            "environment_occluders": list(l.source_occluders),
            "wet_specular": l.wet_specular,
        } for l in light_steps],
        "atmosphere": {
            "altitude_m": atmosphere.altitude_m,
            "altitude_ft": atmosphere.altitude_ft,
            "density_kg_m3": atmosphere.density_kg_m3,
            "pressure_pa": atmosphere.pressure_pa,
            "visibility_m": atmosphere.meteorological_visibility_m,
            "freshness": atmosphere.rain_washed_freshness,
            "wind_damping_game_factor": atmosphere.effective_wind_factor,
            "sound_speed_m_s": atmosphere.sound_speed_m_s,
        },
        "tides": ({
            "water_height_m": tide.water_height_m,
            "rise_rate_m_s": tide.rise_rate_m_s,
            "solar_altitude_proxy": tide.sun_altitude_proxy,
            "phase": tide.moon_phase,
            "alignment": tide.tidal_alignment,
        } if tide else None),
        "liquid": ({
            "volume_before_m3": liquid_step.initial_volume_m3,
            "volume_after_m3": liquid_step.final_volume_m3,
            "rain_added_m3": liquid_step.rain_added_m3,
            "mass_residual_m3": liquid_step.mass_residual_m3,
            "depths_m": list(liquid_step.grid.water_depth_m),
        } if liquid_step else None),
        "character_water": ({
            "immersion_fraction": water_response.immersion_fraction,
            "buoyancy_n": water_response.buoyant_force_n,
            "drag_xyz": [water_response.drag_force.x,
                         water_response.drag_force.y,
                         water_response.drag_force.z],
            "gait": water_response.suggested_gait,
            "splash": water_response.footstep_splash,
        } if water_response else None),
        "leaf_shadows": [{
            "id": a.leaf_id, "area_m2": a.geometric_area_m2,
            "predicted_area_m2": a.predicted_area_m2,
            "coherence_error_m2": a.area_error_m2,
            "ray_fraction": a.ray_shadow_coverage,
            "double_verified": a.verified,
            "polygon_xyz": [[v.x,v.y,v.z] for v in a.polygon],
        } for a in audit_leaves],
        "photometric_3d": [{
            "id": v.surface_id,
            "rgb": list(v.radiance_rgb),
            "source_unblocked": v.unoccluded_direct,
            "source_delivered": v.delivered_direct,
            "volumetric_transmission": v.volumetric_transmission,
            "shadow_fraction": v.geometric_shadow_fraction,
            "leaf_shadow_fraction": v.leaf_shadow_fraction,
            "source_occluders": list(v.occluder_ids),
        } for v in traced],
        "environment_audio": ({
            "delay_s": audio.delay_s, "gain": audio.gain,
            "low_pass_hz": audio.low_pass_hz,
            "rain_ambience": audio.rain_ambience,
            "tide_surf_ambience": audio.tide_surf_ambience,
            "cues": list(audio.cues),
        } if audio else None),
        "mesh_chunk_evidence": mesh_evidence,
        "chunk_verification": [{
            "era": c.era, "chunk_count": c.chunk_count,
            "sha256_valid": c.authenticated,
            "topology_valid": c.topology_reconstructed,
            "coverage_valid": c.full_coverage,
            "spatial_bounds_valid": c.bounds_valid,
            "passed_both": c.approved_by_both,
        } for c in chunk_reports],
        "biome_motion": {
            "shrubs": [{
                "id": obj.shrub_id,
                "tip": [obj.tip.x, obj.tip.y, obj.tip.z],
                "root": [obj.root.x, obj.root.y, obj.root.z],
                "radius_m": obj.radius_m,
                "health": obj.health,
            } for obj in biome_motion.shrubs],
            "rocks": [{
                "id": obj.rock_id,
                "position": [obj.position.x,obj.position.y,obj.position.z],
                "radius_m": obj.radius_m,
                "rotation_radians": obj.rolling_radians,
            } for obj in biome_motion.rocks],
            "character_contact_count": biome_motion.impact_count,
        },
        "old_new_assets": [{
            "era": m.era, "source_digest": m.source_digest,
            "triangles": m.triangle_count,
            "vertex_count": len(m.vertices),
            "original_source_preserved": m.source_preserved,
        } for m in old_new_meshes],
        "position_fix": position_receipt,
        "virtual_game_gps": virtual_position,
        "frame_chunk_evidence": frame_chunk_evidence,
        # Verified scene kinematics for optional native multi-actor reference
        # probes. The signed frame/GDD and chunk source ownership are unchanged.
        "frame_actor_sources": ([{
            "id": actor.entity_id,
            "source_digest": actor.source_digest,
            "position_xyz_m": [actor.position.x,actor.position.y,actor.position.z],
            "velocity_xyz_mps": [actor.velocity.x,actor.velocity.y,actor.velocity.z],
        } for chunk in frame_receipt.chunks for actor in chunk.objects]
            if frame_receipt is not None else []),
        "frame_progress": ({
            "frame_index": frame_receipt.frame_index,
            "timestamp_ns": frame_receipt.time_ns,
            "fps": frame_receipt.fps,
            "gdd_digest": frame_receipt.gdd_digest,
            "previous_receipt_digest": frame_receipt.previous_digest,
            "receipt_digest": frame_receipt.receipt_digest,
            "double_verified": frame_receipt.verified,
            "verifier_a": frame_receipt.verifier_a_integrity,
            "verifier_b": frame_receipt.verifier_b_coherence,
            "chunk_count": len(frame_receipt.chunks),
            "chunks": [{
                "cell": list(c.chunk_key),
                "digest": c.content_digest,
                "object_ids": [o.entity_id for o in c.objects],
            } for c in frame_receipt.chunks],
            "between_frame_notes": [{
                "gdd_world_law_index": n.world_law_index,
                "gdd_world_law": frame_gdd.world_laws[n.world_law_index],
                "category": n.category,
                "content": n.text,
                "review_status": n.author_kind,
            } for n in frame_receipt.note_from_previous],
            "ai_authority": "suggested_context_only_signed_gdd_unchanged",
        } if frame_receipt is not None else None),
        "advanced_physics": advanced_receipt,
        "character_suite": character_suite_receipt,
        "governance": {
            "neural_model_checkpoint_loaded": False,
            "gameplay_action_executed": False,
            "model_weights_modified": False,
            "runtime_admitted": False,
        },
    }
    # A separate observer recomputes cross-domain physical invariants from
    # manifest evidence. These checks do not elevate a candidate to authority.
    manifest["realism_audit"] = audit_scene_realism(manifest).manifest()
    digest = sha256(json.dumps(manifest, sort_keys=True,
                               separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return FrontierSceneCandidate(manifest, digest, vertices, moved,
                                  False, mesh.triangles, mesh.colliders)
