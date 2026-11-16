"""Actual coupled CPU reference simulation and independent deterministic replay.

All resulting motion, climate, balance, visibility and ray measurements are
computed by the pre-existing frontier owners. The input describes a scene,
not a recorded engine capture or a physically qualified environment.
"""
from __future__ import annotations

from dataclasses import asdict,replace
import math

from skeleton.app.recovered_evidence import EvidenceError,digest,seal
from skeleton.app.frontier_environment_model import load_order,ZERO
from skeleton.jeeves.game_frontier_dynamics import PresentationClock
from skeleton.jeeves.game_frontier_ecosystem import sample_atmosphere
from skeleton.jeeves.game_frontier_weather_physics import evolve_microclimate
from skeleton.jeeves.game_frontier_advanced_physics import evaluate_climbing
from skeleton.jeeves.game_frontier_body_balance import distribute_character_weight
from skeleton.jeeves.game_frontier_biome_motion import advance_biome_objects
from skeleton.jeeves.game_frontier_photometry import (
    move_leaf,verify_leaf_shadow,illuminate_atmosphere_3d,LightClimate,PhotometryError,
)
from skeleton.jeeves.game_frontier_lighting import RayOccluder

GENESIS="0"*64


def _length(v):
    return math.sqrt(v.dot(v))


def _fold(previous,event):
    return digest({"previous":previous,"event":event})


def _motion_samples(shrubs_before,shrubs_after,leaves,wind,contacts,dt):
    previous={x.shrub_id:x for x in shrubs_before}
    newest={x.shrub_id:x for x in shrubs_after}
    moved=[]
    for name,leaf in leaves:
        displacement=newest[name].tip-previous[name].tip
        # Move the attachment anchor with the actual simulated shrub tip.
        # Leaf motion then responds to the same wind and contact impulses.
        anchor=leaf.anchor+displacement
        attached=replace(leaf,anchor=anchor)
        impulse=ZERO
        for contact in contacts:
            if _length(leaf.center-contact.position)<=contact.radius_m+max(leaf.width_m,leaf.length_m):
                impulse=impulse+contact.impulse_ns
        moved.append((name,move_leaf(attached,wind_mps=wind,dt_s=dt,impact_impulse_ns=impulse)))
    return tuple(moved)


def _simulate(order):
    s=load_order(order)
    clock=PresentationClock(s.fps)
    micro=s.micro
    shrubs,rocks,leaves=s.shrubs,s.rocks,s.leaves
    prior=GENESIS
    index=0
    checkpoints=[]
    counters={"frames":0,"leaf_shadow_checks":0,"leaf_shadow_failures":0,
              "unstable_balance_frames":0,"impossible_climb_frames":0,"contact_hits":0,
              "surface_samples":0,"light_transport_invalid_frames":0}
    extreme={"max_wind_mps":0.,"max_soil_water":0.,"max_ice":0.,"max_shadow_error_m2":0.,
             "min_balance_margin_m":None,"min_visibility_m":None,"max_slip_risk":0.,
             "max_leaf_displacement_m":0.,"min_volumetric_transmission":1.}
    original_leaves={leaf.leaf_id:leaf.center for _,leaf in leaves}
    for block in s.weather:
        air=sample_atmosphere(block.air)
        climate=LightClimate(air,block.weather.precipitation_mm_h,block.cloud)
        for _ in range(block.frames):
            frame=clock.next_frame()
            dt=(clock.deadline(frame.index+1)-frame.deadline_ns)/1_000_000_000
            terrain=evolve_microclimate(micro,block.weather,block.air,s.traction,delta_s=dt)
            micro=terrain.state
            wind=block.weather.wind.scaled(air.effective_wind_factor)+terrain.pressure_wind_delta
            if _length(wind)>250:
                wind=wind.scaled(250/_length(wind))
            grip=evaluate_climbing(terrain.traction_surface,s.climber,wind=wind,
                                   motion_mps=_length(block.velocity))
            support=tuple(replace(foot,friction_coefficient=min(foot.friction_coefficient,
                                                   grip.effective_static_friction)) for foot in s.feet)
            balance=distribute_character_weight(s.segments,support,
                acceleration_mps2=block.acceleration,velocity_mps=block.velocity,ground_z_m=s.ground)
            contacts=tuple(s.contacts.get(index,()))
            biome=advance_biome_objects(shrubs,rocks,wind=wind,dt_s=dt,contacts=contacts,ground_z_m=s.ground)
            leaves=_motion_samples(shrubs,biome.shrubs,leaves,wind,contacts,dt)
            shrubs,rocks=biome.shrubs,biome.rocks
            shadows=[]
            for _,leaf in leaves:
                counters["leaf_shadow_checks"]+=1
                try:
                    shadow=verify_leaf_shadow(leaf,sun_toward=s.sun,receiver_z_m=s.ground)
                    shadows.append(asdict(shadow))
                    extreme["max_shadow_error_m2"]=max(extreme["max_shadow_error_m2"],shadow.area_error_m2)
                    if not shadow.verified:
                        counters["leaf_shadow_failures"]+=1
                except PhotometryError:
                    counters["leaf_shadow_failures"]+=1
                    shadows.append({"leaf_id":leaf.leaf_id,"verified":False,"geometry_unqualified":True})
                extreme["max_leaf_displacement_m"]=max(extreme["max_leaf_displacement_m"],
                    _length(leaf.center-original_leaves[leaf.leaf_id]))
            # The moving objects and leaves used for this frame are the same
            # geometry consumed by the ray transport, not static screenshots.
            occluders=s.occluders+tuple(RayOccluder(obj.rock_id,"object",obj.position,"sphere",
                radius_m=obj.radius_m) for obj in rocks)+tuple(RayOccluder(obj.shrub_id,"foliage",
                obj.root,"sphere",radius_m=obj.radius_m,opacity=.3) for obj in shrubs)
            light_rows=[]
            invalid=False
            for surface in s.surfaces:
                wet=replace(surface,wetness=micro.soil_water_fraction)
                result=illuminate_atmosphere_3d(wet,s.lights,occluders,
                    tuple(leaf for _,leaf in leaves),climate,area_samples=s.area_samples)
                light_rows.append(asdict(result))
                counters["surface_samples"]+=1
                vals=(*result.radiance_rgb,result.unoccluded_direct,result.delivered_direct,
                      result.volumetric_transmission,result.geometric_shadow_fraction,result.leaf_shadow_fraction)
                if (any(not math.isfinite(n) or n<0 for n in vals)
                    or result.delivered_direct>result.unoccluded_direct+1e-8
                    or any(n>1+1e-8 for n in (result.volumetric_transmission,
                          result.geometric_shadow_fraction,result.leaf_shadow_fraction))):
                    invalid=True
                extreme["min_volumetric_transmission"]=min(extreme["min_volumetric_transmission"],
                                                            result.volumetric_transmission)
            counters["light_transport_invalid_frames"]+=invalid
            counters["frames"]+=1
            counters["unstable_balance_frames"]+=not balance.stable
            counters["impossible_climb_frames"]+=not grip.climbing_possible
            counters["contact_hits"]+=biome.impact_count
            extreme["max_wind_mps"]=max(extreme["max_wind_mps"],_length(wind))
            extreme["max_soil_water"]=max(extreme["max_soil_water"],micro.soil_water_fraction)
            extreme["max_ice"]=max(extreme["max_ice"],micro.ground_ice_fraction)
            extreme["max_slip_risk"]=max(extreme["max_slip_risk"],grip.slip_risk)
            for key,value in (("min_balance_margin_m",balance.support_margin_m),
                              ("min_visibility_m",air.meteorological_visibility_m)):
                extreme[key]=value if extreme[key] is None else min(extreme[key],value)
            record={"frame":index,"deadline_ns":frame.deadline_ns,"micro":asdict(micro),
                    "wind":asdict(wind),"traction":asdict(grip),"balance":asdict(balance),
                    "biome":asdict(biome),"leaves":[asdict(leaf) for _,leaf in leaves],
                    "shadow_receipts":shadows,"photometry":light_rows}
            frame_digest=digest(record)
            prior=_fold(prior,frame_digest)
            index+=1
            if index%s.stride==0 or index==s.frames:
                checkpoints.append({"frames":index,"head":prior,"frame_digest":frame_digest,
                                    "soil_water":micro.soil_water_fraction,
                                    "ground_ice":micro.ground_ice_fraction,
                                    "balance_stable":balance.stable,
                                    "leaf_shadow_failures_so_far":counters["leaf_shadow_failures"]})
    if index!=s.frames or counters["surface_samples"]!=s.frames*len(s.surfaces) or counters["leaf_shadow_checks"]!=s.frames*len(s.leaves):
        raise EvidenceError("coupled owner frame accounting diverged")
    return {"frames":index,"fps":s.fps,"head":prior,"counts":counters,"extrema":extreme,
            "checkpoint_receipts":checkpoints,"ray_test_ceiling":s.ray_test_ceiling,
            "reference_invariants_passed":counters["leaf_shadow_failures"]==0 and
                                         counters["light_transport_invalid_frames"]==0}


def qualify_environment(order,*,authorized):
    if authorized is not True:
        raise PermissionError("explicit CPU reference simulation operator required")
    first=_simulate(order)
    second=_simulate(order)
    if first!=second:
        raise EvidenceError("deterministic source replay diverged")
    return seal({"schema":"skeleton.frontier-environment-replay.report.v1",
                 "order_digest":digest(order),"simulation":first,"independent_source_replay_matched":True,
                 "source_frames_executed":first["frames"]*2,
                 "host_engine_frames_rendered":0,"gpu_raytracing_executed":False,
                 "physical_device_tested":False,"native_model_tested":False,
                 "animation_quality_certified":False,"release_certified":False})
