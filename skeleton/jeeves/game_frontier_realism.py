"""Cross-domain reference-physics realism aggregation and fail-closed coherence.

Reports actual derived quantities and check results from Jeeves scene candidates.
It is not a quality grade and cannot certify GPU, native Godot or model output.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Mapping


class RealismAuditError(ValueError):
    pass


@dataclass(frozen=True)
class RealismMeasurement:
    domain: str
    metric: str
    value: float
    unit: str


@dataclass(frozen=True)
class RealismInvariant:
    domain: str
    check: str
    passed: bool
    evidence: str


@dataclass(frozen=True)
class RealismAudit:
    measurements: tuple[RealismMeasurement, ...]
    invariants: tuple[RealismInvariant, ...]
    participating_domains: tuple[str, ...]
    missing_domains: tuple[str, ...]
    evidence_digest: str
    reference_checks_passed: bool
    authority: str = "candidate_checks_only_not_native_validation"

    def manifest(self) -> dict:
        return {
            "schema": "skeleton.jeeves.frontier_realism_audit.v1",
            "measurements": [m.__dict__ for m in self.measurements],
            "invariants": [m.__dict__ for m in self.invariants],
            "participating_domains": list(self.participating_domains),
            "missing_domains": list(self.missing_domains),
            "evidence_digest": self.evidence_digest,
            "reference_checks_passed": self.reference_checks_passed,
            "authority": self.authority,
        }


_DOMAINS = (
    "aerodynamics", "climbing", "collision", "atmosphere",
    "liquid", "tides", "light", "leaf_shadow", "characters",
    "environment", "structures", "biome", "audio", "chunks",
    "balance", "elastic_skin", "instruments", "rpg_events",
    "position_fix", "gdd_frame",
)


def audit_scene_realism(manifest: Mapping) -> RealismAudit:
    if not isinstance(manifest, Mapping):
        raise RealismAuditError("scene manifest mapping required")
    readings: list[RealismMeasurement] = []
    checks: list[RealismInvariant] = []
    used: set[str] = set()

    def measurement(domain: str, key: str, value: object,
                    unit: str = "1") -> float:
        if type(value) not in (int, float) or not math.isfinite(value):
            raise RealismAuditError(f"{domain}.{key} must be finite numeric")
        number = float(value)
        if abs(number) > 1e12:
            raise RealismAuditError("unbounded aggregate sample")
        readings.append(RealismMeasurement(domain, key, number, unit))
        used.add(domain)
        return number

    def check(domain: str, rule: str, passed: object, evidence: str) -> None:
        if type(passed) is not bool:
            raise RealismAuditError("invariant check requires boolean")
        checks.append(RealismInvariant(domain, rule, passed, evidence))
        used.add(domain)

    adv = manifest.get("advanced_physics")
    if isinstance(adv, Mapping):
        tv = measurement("aerodynamics", "terminal_velocity",
                         adv["terminal_velocity_mps"], "m/s")
        drag = measurement("aerodynamics", "drag_energy_dissipated",
                           adv["dissipated_drag_energy_j"], "J")
        density = measurement("aerodynamics", "air_density",
                              adv["air_density_kg_m3"], "kg/m3")
        wake = measurement("aerodynamics", "draft_shelter",
                           adv["draft_shelter_fraction"])
        up = measurement("aerodynamics", "updraft",
                         adv["updraft_mps"], "m/s")
        check("aerodynamics", "physical_terminal_speed",
              tv >= 0 and density > 0 and drag >= 0, "reference_kinematics")
        check("aerodynamics", "wake_fraction_bounded",
              0 <= wake <= 1, "wake_receipt")
        traction = adv.get("traction") or {}
        if isinstance(traction, Mapping):
            slip = measurement("climbing", "slip_risk", traction["slip_risk"])
            slope = measurement("climbing", "slope", traction["slope_degrees"], "deg")
            check("climbing", "friction_probability_bounds",
                  0 <= slip <= 1 and 0 <= slope <= 180,
                  "traction_constraint")
            measurement("climbing", "available_force",
                        traction["available_force_n"], "N")
            measurement("climbing", "required_force",
                        traction["required_force_n"], "N")
        micro = adv.get("microclimate")
        if isinstance(micro, Mapping):
            wet_soil = measurement("environment", "micro_soil_water",
                                   micro["soil_water_fraction"])
            ground_ice = measurement("environment", "micro_ground_ice",
                                    micro["ground_ice_fraction"])
            heat_flux = measurement("environment", "micro_updraft",
                                    micro["updraft_mps"], "m/s")
            erosion = measurement("environment", "micro_erosion",
                                  micro["erosion_pressure"])
            check("environment", "microclimate_bounded",
                  0 <= wet_soil <= 1 and 0 <= ground_ice <= 1
                  and 0 <= erosion <= 1 and abs(heat_flux) <= 100,
                  "freeze_thaw_rain_heat_reference")
        impact = adv.get("impact")
        if isinstance(impact, Mapping):
            residual = measurement("collision", "momentum_residual",
                                   impact["momentum_residual_ns"], "N*s")
            impulse = measurement("collision", "normal_impulse",
                                  impact["impulse_ns"], "N*s")
            loss = measurement("collision", "energy_dissipated",
                               impact["energy_loss_j"], "J")
            check("collision", "nonnegative_impulse_loss",
                  impulse >= 0 and loss >= 0, "rigid_body_contact_receipt")
            check("collision", "bounded_momentum_residual",
                  residual <= max(.000001, impulse * 1e-8),
                  "dynamic_momentum_only_static_ground_excluded")
        metrics = adv.get("realism_invariants") or {}
        if isinstance(metrics, Mapping):
            check("collision", "nonincreasing_impact_energy",
                  bool(metrics.get("collision_energy_nonincreasing", False)),
                  "reference_contact_energy")

    atmosphere = manifest.get("atmosphere")
    if isinstance(atmosphere, Mapping):
        air = measurement("atmosphere", "air_density",
                          atmosphere["density_kg_m3"], "kg/m3")
        pressure = measurement("atmosphere", "pressure",
                               atmosphere["pressure_pa"], "Pa")
        visibility = measurement("atmosphere", "visibility",
                                 atmosphere["visibility_m"], "m")
        measurement("atmosphere", "altitude",
                    atmosphere["altitude_m"], "m")
        check("atmosphere", "positive_pressure_and_density",
              air > 0 and pressure > 0 and visibility >= 0,
              "hydrostatic_ideal_gas_and_fog")

    water = manifest.get("liquid")
    if isinstance(water, Mapping):
        prior = measurement("liquid", "volume_before",
                            water["volume_before_m3"], "m3")
        after = measurement("liquid", "volume_after",
                            water["volume_after_m3"], "m3")
        rain = measurement("liquid", "rain_added",
                           water["rain_added_m3"], "m3")
        residual = measurement("liquid", "mass_balance_residual",
                               water["mass_residual_m3"], "m3")
        check("liquid", "nonnegative_volume",
              prior >= 0 and after >= 0, "liquid_source_ledger")
        check("liquid", "mass_conserved",
              abs(residual) <= max(1e-8, abs(after) * 1e-8),
              "closed_grid_internal_flux_and_external_rain")
        measurement("liquid", "cell_count", len(water["depths_m"]), "cells")
        check("liquid", "nonnegative_cell_depth",
              all(type(d) in (float, int) and math.isfinite(d) and d >= 0
                  for d in water["depths_m"]), "shallow_water_cell_state")
        measurement("liquid", "rain_fraction",
                    rain / max(1, prior + rain))

    tide = manifest.get("tides")
    if isinstance(tide, Mapping):
        measurement("tides", "water_height", tide["water_height_m"], "m")
        measurement("tides", "rise_rate", tide["rise_rate_m_s"], "m/s")
        phase = measurement("tides", "moon_phase", tide["phase"])
        check("tides", "phase_bounded", 0 <= phase < 1,
              "solar_lunar_harmonic_reference")

    photo = manifest.get("photometric_3d") or []
    for index, source in enumerate(photo):
        factor = measurement("light", f"transmission_{index}",
                             source["volumetric_transmission"])
        obscured = measurement("light", f"shadow_fraction_{index}",
                               source["shadow_fraction"])
        check("light", f"light_attenuation_bounds_{index}",
              0 <= factor <= 1 and 0 <= obscured <= 1,
              "ray_aerosol_shadow_source")

    leaves = manifest.get("leaf_shadows") or []
    for index, leaf in enumerate(leaves):
        discrepancy = measurement("leaf_shadow", f"area_error_{index}",
                                  leaf["coherence_error_m2"], "m2")
        check("leaf_shadow", f"double_verified_{index}",
              leaf["double_verified"] is True and discrepancy <= 1e-4,
              "analytic_projection_and_independent_ray_probes")

    actor = manifest.get("character_physics")
    if isinstance(actor, Mapping):
        traction = measurement("characters", "traction", actor["traction"])
        check("characters", "traction_bounded",
              0 <= traction <= 1, "existing_character_reference")
        measurement("characters", "core_temperature",
                    actor["core_temperature_c"], "degC")

    environment = manifest.get("environment_response")
    if isinstance(environment, Mapping):
        soil = measurement("environment", "soil_saturation",
                           environment["soil_saturation"])
        erosion = measurement("environment", "erosion",
                              environment["erosion"])
        check("environment", "soil_and_erosion_bounds",
              0 <= soil <= 1 and 0 <= erosion <= 1,
              "weather_environment_response")

    structures = manifest.get("structures") or []
    for i, item in enumerate(structures):
        integrity = measurement("structures", f"integrity_{i}",
                                item["integrity"])
        age = measurement("structures", f"age_{i}",
                          item["age_days"], "days")
        check("structures", f"integrity_bounds_{i}",
              0 <= integrity <= 1 and age >= 0,
              "construction_deterioration_receipt")

    biome = manifest.get("biome_motion")
    if isinstance(biome, Mapping):
        measurement("biome", "shrub_count", len(biome.get("shrubs", [])), "count")
        measurement("biome", "rock_count", len(biome.get("rocks", [])), "count")
        measurement("biome", "impact_count", biome["character_contact_count"], "count")

    sound = manifest.get("environment_audio")
    if isinstance(sound, Mapping):
        delay = measurement("audio", "propagation_delay",
                            sound["delay_s"], "s")
        gain = measurement("audio", "gain", sound["gain"])
        check("audio", "nonnegative_delay_gain",
              delay >= 0 and gain >= 0, "sound_propagation_receipt")

    chunks = manifest.get("chunk_verification") or []
    for i, item in enumerate(chunks):
        measurement("chunks", f"chunk_count_{i}", item["chunk_count"])
        check("chunks", f"dual_verified_{i}",
              item["passed_both"] is True and
              item["sha256_valid"] is True and
              item["topology_valid"] is True and
              item["coverage_valid"] is True and
              item["spatial_bounds_valid"] is True,
              "digest_and_topology_bounded_seam_proof")

    suite = manifest.get("character_suite")
    if isinstance(suite, Mapping):
        balance = suite.get("weight_distribution")
        if isinstance(balance, Mapping):
            total=measurement("balance","total_mass",balance["total_mass_kg"],"kg")
            cargo=measurement("balance","carried_mass",balance["carried_mass_kg"],"kg")
            margin=measurement("balance","support_margin",balance["support_margin_m"],"m")
            loads=balance.get("load_per_foot_n",[])
            if not isinstance(loads,(list,tuple)):
                raise RealismAuditError("balance foot loads must be a sequence")
            share=sum(measurement("balance",f"foot_load_{i}",item[1],"N")
                      for i,item in enumerate(loads))
            check("balance","mass_and_foot_load_conservation",
                  total>0 and 0<=cargo<=total and
                  abs(share-total*9.80665)<=max(1e-5,total*9.80665*1e-7),
                  "segmented_mass_and_support_foot_sum")
            inertia=balance.get("inertia_tensor_kg_m2",[])
            symmetric=(isinstance(inertia,(list,tuple)) and len(inertia)==3 and
                       all(isinstance(row,(list,tuple)) and len(row)==3
                           for row in inertia))
            if symmetric:
                symmetric=all(
                    type(inertia[i][j]) in (float,int) and
                    type(inertia[j][i]) in (float,int) and
                    math.isfinite(inertia[i][j]) and
                    math.isclose(inertia[i][j],inertia[j][i],abs_tol=1e-7)
                    for i in range(3) for j in range(3))
                symmetric=symmetric and all(inertia[i][i]>0 for i in range(3))
            check("balance","inertia_tensor_symmetric_positive_diagonal",
                  bool(symmetric),"3d_mass_distribution")
            check("balance","stability_label_consistency",
                  not balance.get("stable",False) or margin>=-1e-8,
                  "support_polygon_candidate_not_native_contact")
        elastic=suite.get("elastic_skin3d")
        if isinstance(elastic,Mapping):
            n=measurement("elastic_skin","vertex_count",elastic["vertex_count"],"count")
            strain=measurement("elastic_skin","max_strain",elastic["max_strain"])
            wetness=measurement("elastic_skin","wetness",elastic["wetness"])
            temperature=measurement("elastic_skin","temperature",
                                    elastic["temperature_c"],"degC")
            coordinates=elastic.get("positions_xyz",[])
            pinned=elastic.get("pinned_vertices",[])
            check("elastic_skin","rig_and_pin_topology_consistent",
                  type(elastic["vertex_count"]) is int and
                  1<=elastic["vertex_count"]<=16384 and
                  len(coordinates)==n and
                  all(isinstance(point,(list,tuple)) and len(point)==3 and
                      all(type(v) in (float,int) and math.isfinite(v)
                          for v in point) for point in coordinates) and
                  bool(pinned) and len(set(pinned))==len(pinned) and
                  all(type(i) is int and 0<=i<n for i in pinned),
                  "rigged_deformed_mesh_source")
            check("elastic_skin","wetness_temperature_strain_bounds",
                  0<=wetness<=1 and -120<=temperature<=120 and
                  0<=strain<=10,
                  "bounded_skin_reference_thermomechanics")
        instruments=suite.get("instruments")
        if isinstance(instruments,Mapping):
            entries=instruments.get("readings",[])
            measurement("instruments","reading_count",len(entries),"count")
            check("instruments","simulated_custody_only",
                  instruments.get("authority")==
                  "simulation_only_no_location_fix" and
                  type(instruments.get("digest")) is str and
                  len(instruments.get("digest",""))==64 and
                  len(entries)<=32,
                  "instrument_derived_not_live_geolocation")
        events=suite.get("rpg_events")
        if isinstance(events,Mapping):
            admitted=events.get("accepted",[])
            measurement("rpg_events","proposal_count",len(admitted),"count")
            check("rpg_events","proposals_never_executed",
                  events.get("executed") is False and
                  all(type(x.get("source_evidence")) is str and
                      len(x["source_evidence"])==64
                      for x in admitted),
                  "canonical_authority_must_dispatch")

    position=manifest.get("position_fix")
    if isinstance(position,Mapping):
        check("position_fix","precise_coordinates_redacted",
              position.get("coordinates_redacted") is True and
              "latitude_deg" not in position and
              "longitude_deg" not in position and
              "altitude_m" not in position,
              "consent_bound_device_gnss_and_control_survey")
        gps=position.get("live")
        if isinstance(gps,Mapping):
            uncertainty=measurement("position_fix","horizontal_accuracy",
                                    gps["accuracy_m"],"m")
            check("position_fix","location_quality_and_custody",
                  0<uncertainty<=75 and gps.get("retains_coordinates") is False,
                  "foreground_session_only")
        control=position.get("surveyed")
        if isinstance(control,Mapping):
            survey_uncertainty=measurement(
                "position_fix","survey_uncertainty",
                control["horizontal_uncertainty_m"],"m")
            check("position_fix","survey_geometry_quality",
                  0<survey_uncertainty and control.get("retains_coordinates") is False and
                  int(control.get("control_count",0))>=2,
                  "independent_user_verified_wgs84_controls")
    frame=manifest.get("frame_progress")
    if isinstance(frame,Mapping):
        frame_no=measurement("gdd_frame","frame_index",frame["frame_index"],"frames")
        count=measurement("gdd_frame","chunk_count",frame["chunk_count"],"chunks")
        frame_checks_ok=(frame.get("double_verified") is True and
                frame.get("verifier_a") is True and
                frame.get("verifier_b") is True and
                type(frame.get("gdd_digest")) is str and
                len(frame["gdd_digest"])==64 and
                type(frame.get("receipt_digest")) is str and
                len(frame["receipt_digest"])==64 and
                frame_no>=0 and count>=1 and
                len(frame.get("chunks",[]))==count)
        check("gdd_frame","scene_has_double_verified_frame_receipt",
              bool(frame_checks_ok),"independent_chunk_hash_and_temporal_gdd_verifiers")
        check("gdd_frame","context_authority_remains_provisional",
              frame.get("ai_authority")==
              "suggested_context_only_signed_gdd_unchanged",
              "signed_story_bible_no_ai_auto_promotion")

    payload = {
        "measurements": [m.__dict__ for m in readings],
        "invariants": [i.__dict__ for i in checks],
        "participating_domains": sorted(used),
    }
    digest = sha256(json.dumps(payload, sort_keys=True,
                               separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return RealismAudit(tuple(readings), tuple(checks),
                        tuple(sorted(used)),
                        tuple(sorted(set(_DOMAINS) - used)), digest,
                        bool(checks) and all(c.passed for c in checks))
