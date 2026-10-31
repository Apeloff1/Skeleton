"""Jeeves-owned composition of skin, mass balance, instruments and RPG triggers.

The suite is optional; if present, it evaluates actual typed input sources.
It never executes a game event or installs an instrument as a location source.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

from .game_frontier_production import Vec3, CharacterSkeleton, SkinnedMesh, AnimationClip
from .game_frontier_motion import Weather
from .game_frontier_body_balance import BodyMass, SupportFoot, distribute_character_weight
from .game_frontier_elastic_skin3d import (
    ElasticBodySkin3D, ElasticSkinState, simulate_elastic_skin,
)
from .game_frontier_instruments import (
    NavigationEnvironment, Gyroscope, advance_gyroscope, sample_compass,
    sight_sextant, sight_bubble_sextant, barometric_altimeter,
    trigonometric_altimeter, instrument_manifest,
)
from skeleton.forge.game_frontier_rpg_events import (
    RPGEventPage, evaluate_environment_events, event_authoring_catalog,
)


class CharacterSuiteError(ValueError):
    pass


@dataclass(frozen=True)
class CharacterSuiteConfig:
    body_segments: tuple[BodyMass, ...] = ()
    support_feet: tuple[SupportFoot, ...] = ()
    acceleration_mps2: Vec3 = Vec3(0, 0, 0)
    velocity_mps: Vec3 = Vec3(0, 0, 0)
    elastic_skin: ElasticBodySkin3D | None = None
    prior_skin_state: ElasticSkinState | None = None
    pinned_skin_vertices: tuple[int, ...] = (0,)
    skin_impact_force_n: Vec3 = Vec3(0, 0, 0)
    navigation: NavigationEnvironment | None = None
    gyroscope: Gyroscope | None = None
    angular_rate_dps: Vec3 = Vec3(0, 0, 0)
    true_heading_deg: float = 0.
    celestial_target_enu: Vec3 | None = None
    eye_height_m: float = 2.
    horizontal_baseline_m: float | None = None
    target_elevation_angle_deg: float = 0.
    rpg_pages: tuple[RPGEventPage, ...] = ()
    trigger_observations: tuple[tuple[str,float], ...] = ()
    previous_trigger_observations: tuple[tuple[str,float], ...] = ()
    story_flags: tuple[tuple[str,bool], ...] = ()
    last_event_ms: tuple[tuple[str,int], ...] = ()
    completed_pages: frozenset[str] = frozenset()
    clock_ms: int = 0


def _validated_pairs(items: tuple, label: str) -> dict:
    data = dict(items)
    if len(data) != len(items):
        raise CharacterSuiteError(f"{label} contains duplicate keys")
    return data


def compile_character_suite(
    config: CharacterSuiteConfig,
    *, skeleton: CharacterSkeleton, mesh: SkinnedMesh,
    animation: AnimationClip, animation_time_ms: int,
    delta_s: float, weather: Weather | None = None,
    derived_observations: Mapping[str,float] | None = None,
) -> dict:
    """Produce a portable, deterministic set of inspector receipts."""
    if not isinstance(config, CharacterSuiteConfig):
        raise CharacterSuiteError("typed suite required")
    if not math.isfinite(delta_s) or delta_s < 0:
        raise CharacterSuiteError("invalid simulation step")
    if bool(config.body_segments) != bool(config.support_feet):
        raise CharacterSuiteError("segment and support sources must be paired")
    if config.prior_skin_state is not None and config.elastic_skin is None:
        raise CharacterSuiteError("skin state requires elasticity configuration")
    if config.gyroscope is not None and config.navigation is None:
        raise CharacterSuiteError("gyro measurement requires environment")
    if config.celestial_target_enu is not None and config.navigation is None:
        raise CharacterSuiteError("sextant requires navigation environment")
    if config.horizontal_baseline_m is not None and config.navigation is None:
        raise CharacterSuiteError("trig altitude requires reference origin")
    balance = (distribute_character_weight(
        config.body_segments, config.support_feet,
        acceleration_mps2=config.acceleration_mps2,
        velocity_mps=config.velocity_mps)
        if config.body_segments else None)
    skin = None
    if config.elastic_skin is not None:
        skin = simulate_elastic_skin(
            skeleton,mesh,animation,config.elastic_skin,
            time_ms=animation_time_ms,delta_s=delta_s,
            wind_mps=weather.wind if weather else Vec3(0,0,0),
            rainfall_mm_h=weather.precipitation_mm_h if weather else 0,
            air_temperature_c=weather.temperature_c if weather else 20,
            impact_force_n=config.skin_impact_force_n,
            state=config.prior_skin_state,pinned_vertices=config.pinned_skin_vertices,
        )
    readings = []
    gyro = None
    if config.navigation is not None:
        env = config.navigation
        if config.gyroscope is not None:
            gyro = advance_gyroscope(config.gyroscope,config.angular_rate_dps,
                                     delta_s=delta_s)
            readings.append(gyro)
        readings.append(sample_compass(config.true_heading_deg,env))
        # Barometric source is supplied by the local reference atmosphere.
        from .game_frontier_ecosystem import AirConditions, sample_atmosphere
        atmospheric=sample_atmosphere(AirConditions(
            altitude_m=env.altitude_m,temperature_c=env.air_temperature_c))
        pressure=atmospheric.pressure_pa*env.sea_level_pressure_pa/101325.
        readings.append(barometric_altimeter(
            pressure,sea_level_pressure_pa=env.sea_level_pressure_pa,
            temperature_c=env.air_temperature_c))
        if config.horizontal_baseline_m is not None:
            readings.append(trigonometric_altimeter(
                config.horizontal_baseline_m,
                config.target_elevation_angle_deg,
                observer_altitude_m=env.altitude_m,
                instrument_height_m=config.eye_height_m))
        if config.celestial_target_enu is not None:
            if not env.horizon_obscured:
                readings.append(sight_sextant(
                    config.celestial_target_enu,env,
                    eye_height_m=config.eye_height_m))
            readings.append(sight_bubble_sextant(
                config.celestial_target_enu,env,
                gyro_pitch_deg=gyro.pitch_deg if gyro else 0,
                gyro_roll_deg=gyro.roll_deg if gyro else 0))
    instruments = instrument_manifest(tuple(readings)) if readings else None
    current = _validated_pairs(config.trigger_observations,"environment")
    for name,value in (derived_observations or {}).items():
        if type(value) not in (int,float) or not math.isfinite(value):
            raise CharacterSuiteError("nonfinite environmental trigger observation")
        if name in current and not math.isclose(current[name],value,rel_tol=1e-9,abs_tol=1e-9):
            raise CharacterSuiteError("conflicting source-reported environmental signal: "+name)
        current[name]=value
    if weather is not None:
        current.setdefault("temperature_c",weather.temperature_c)
        current.setdefault("rain_mm_h",weather.precipitation_mm_h)
        current.setdefault("wind_mps",math.sqrt(weather.wind.dot(weather.wind)))
        current.setdefault("water_depth_m",weather.water_depth_m)
    if balance:
        current.setdefault("character_mass_kg",balance.total_mass_kg)
        current.setdefault("support_margin_m",balance.support_margin_m)
        current.setdefault("center_of_mass_offset_m",
                           math.hypot(balance.center_of_mass.x-balance.effective_balance_point.x,
                                      balance.center_of_mass.y-balance.effective_balance_point.y))
    if skin:
        current.setdefault("skin_strain",skin.max_measured_strain)
        current.setdefault("garment_wetness",skin.wetness)
    if instruments:
        for observation in readings:
            from .game_frontier_instruments import (
                GyroReading,CompassReading,SextantReading,AltimeterReading,
            )
            if isinstance(observation,GyroReading):
                current.setdefault("gyro_tilt_deg",observation.horizon_tilt_deg)
            elif isinstance(observation,CompassReading):
                current.setdefault("compass_heading_deg",observation.magnetic_heading_deg)
            elif isinstance(observation,SextantReading):
                key = ("bubble_sextant_altitude_deg" if observation.synthetic_horizon
                       else "sextant_altitude_deg")
                current.setdefault(key,observation.corrected_altitude_deg)
            elif isinstance(observation,AltimeterReading):
                key = ("barometric_altitude_m" if observation.source.startswith("hypsometric")
                       else "trigonometric_altitude_m")
                current.setdefault(key,observation.altitude_m)
    decisions = (evaluate_environment_events(
        config.rpg_pages,current=current,
        previous=_validated_pairs(config.previous_trigger_observations,"prior environment"),
        flags=_validated_pairs(config.story_flags,"story flags"),
        last_fired_ms=_validated_pairs(config.last_event_ms,"last event"),
        completed_once=config.completed_pages,now_ms=config.clock_ms)
                 if config.rpg_pages else None)
    return {
        "schema":"skeleton.jeeves.frontier_character_suite.v1",
        "weight_distribution": ({
            "total_mass_kg":balance.total_mass_kg,
            "carried_mass_kg":balance.carried_mass_kg,
            "center_of_mass_xyz":[balance.center_of_mass.x,balance.center_of_mass.y,
                                  balance.center_of_mass.z],
            "balance_point_xyz":[balance.effective_balance_point.x,
                                 balance.effective_balance_point.y,
                                 balance.effective_balance_point.z],
            "inertia_tensor_kg_m2":[list(v) for v in balance.inertia_tensor_kg_m2],
            "support_margin_m":balance.support_margin_m,
            "stable":balance.stable,
            "load_per_foot_n":[[name,force] for name,force in balance.load_per_foot_n],
            "available_grip_n":balance.available_tangential_grip_n,
            "required_grip_n":balance.required_tangential_force_n,
            "evidence_digest":balance.evidence_digest,
        } if balance else None),
        "elastic_skin3d": ({
            "vertex_count":len(skin.positions),
            "positions_xyz":[[p.x,p.y,p.z] for p in skin.positions],
            "pinned_vertices":list(config.pinned_skin_vertices),
            "wetness":skin.wetness,"temperature_c":skin.temperature_c,
            "max_strain":skin.max_measured_strain,
            "mean_displacement_m":skin.mean_anchor_displacement_m,
            "collisions":skin.collision_count,
            "mass_per_vertex_kg":config.elastic_skin.mass_per_vertex_kg,
            "anchor_stiffness":config.elastic_skin.anchor_stiffness_n_m,
            "shear_stiffness":config.elastic_skin.shear_stiffness_n_m,
            "damping":config.elastic_skin.damping_n_s_m,
            "mesh_digest":skin.mesh_digest,
            "evidence_digest":skin.evidence_digest,
            "authority":skin.authority,
        } if skin else None),
        "instruments":instruments,
        "environment_observations":current if config.rpg_pages else {},
        "rpg_events": ({
            "accepted":[{
                "page":d.page_id,"priority":d.priority,
                "source_evidence":d.evidence_digest,
                "actions":[a.__dict__ for a in d.actions],
            } for d in decisions.accepted],
            "suppressed":list(decisions.suppressed),
            "missing_signals":list(decisions.missing_signals),
            "catalog_version":event_authoring_catalog()["schema"],
            "executed":False,
        } if decisions else None),
        "authority":"candidate_only_no_gameplay_or_navigation_side_effect",
    }
