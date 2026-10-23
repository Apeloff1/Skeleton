"""Twenty-five environmental simulation event composers (226–250).

The first fifteen author concrete typed environmental sensor/response pages,
which are consumed by the existing deterministic RPG event evaluator.
The remaining ten perform real immutable condition/action/flag rewrites.
No new sensor readings are fabricated; native engine support stays explicit.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from .game_frontier_studio import StudioError, StudioProject
from .game_frontier_rpg_events import (
    RPGEventPage, EnvironmentalTrigger, RPGEventAction,
    RPG_ENVIRONMENT_SIGNALS, COMPARISONS,
)
from .game_frontier_studio_map_edit import _integer, _name
from .game_frontier_studio_environment_edit import _trigger, _action

SENSOR_ACTIONS = (
    "sensor_wind_gust", "sensor_rain_onset", "sensor_visibility_warning",
    "sensor_flood_tide", "sensor_updraft_boost", "sensor_turbulence_alarm",
    "sensor_low_traction", "sensor_fast_fall", "sensor_collision_impact",
    "sensor_instrument_heading", "sensor_sextant_fix", "sensor_gyro_tilt",
    "sensor_island_altitude", "sensor_pressure_change", "sensor_party_morale",
)
PAGE_COMPOSER_ACTIONS = (
    "page_condition_copy", "page_action_copy", "page_condition_swap",
    "page_action_swap", "page_condition_rotate", "page_action_rotate",
    "page_threshold_shift", "page_threshold_scale",
    "page_duplicate_signal", "page_dual_threshold_branches",
)
ENVIRONMENT_COMPOSER_ACTIONS = SENSOR_ACTIONS + PAGE_COMPOSER_ACTIONS
SENSORS = {
    "sensor_wind_gust":("wind_mps","above",12,"set_flag","world","strong_wind","true"),
    "sensor_rain_onset":("rain_mm_h","cross_up",1,"set_flag","world","rain_started","true"),
    "sensor_visibility_warning":("fog_visibility_m","below",150,"set_flag","world","fog_warning","true"),
    "sensor_flood_tide":("tide_height_m","above",2,"change_tide","environment","port","flood"),
    "sensor_updraft_boost":("updraft_mps","above",5,"apply_gameplay_effect","character","updraft","lift"),
    "sensor_turbulence_alarm":("turbulence_mps","above",10,"set_flag","world","turbulence","true"),
    "sensor_low_traction":("traction_slip_risk","above",.8,"set_flag","world","slippery","true"),
    "sensor_fast_fall":("fall_speed_mps","above",16,"apply_gameplay_effect","character","fall_damage","high"),
    "sensor_collision_impact":("collision_energy_j","above",250,"trigger_impact_fx","environment","impact","sparks"),
    "sensor_instrument_heading":("compass_heading_deg","above",180,"inspect_instrument","ui","compass","west"),
    "sensor_sextant_fix":("sextant_altitude_deg","above",25,"inspect_instrument","ui","sextant","observed"),
    "sensor_gyro_tilt":("gyro_tilt_deg","above",30,"set_flag","world","unstable","true"),
    "sensor_island_altitude":("sky_island_height_m","above",100,"set_flag","world","sky_island_reached","true"),
    "sensor_pressure_change":("pressure_pa","below",99000,"set_flag","world","low_pressure","true"),
    "sensor_party_morale":("party_morale","below",.3,"set_npc_emotion","character","party","anxious"),
}


def _page(project,args,field="page_id"):
    name=_name(args,field)
    for i,page in enumerate(project.environmental_pages):
        if page.page_id==name:
            return i,page
    raise StudioError("environmental page ID not found")


def _replace(items,index,value):
    return items[:index]+(value,)+items[index+1:]


def _float(args,key,low=-1e9,high=1e9,default=None):
    import math
    value=args.get(key,default)
    if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:
        raise StudioError("RPG environment transform requires finite bounded "+key)
    return float(value)


def _new_page(project,entry):
    if (entry.page_id in {x.page_id for x in project.environmental_pages} or
            entry.page_id in {x.event_id for x in project.events}):
        raise StudioError("RPG sensor identity already occupied by another event")
    return replace(project,environmental_pages=project.environmental_pages+(entry,))


def edit_environment_composer(project: StudioProject, operation: str,
                              args: Mapping[str,Any]) -> StudioProject:
    if not isinstance(project,StudioProject) or operation not in ENVIRONMENT_COMPOSER_ACTIONS or not isinstance(args,Mapping):
        raise StudioError("unsupported real RPG sensor/event composer")
    if operation in SENSOR_ACTIONS:
        signal,comparison,default,kind,channel,target,value=SENSORS[operation]
        threshold=_float(args,"threshold",default=default)
        priority=_integer(args,"priority",-100,100) if "priority" in args else 0
        cond=EnvironmentalTrigger(signal,comparison,threshold)
        response=RPGEventAction(
            args.get("kind",kind),args.get("channel",channel),
            args.get("target",target),args.get("value",value))
        page=RPGEventPage(_name(args,"page_id"),priority,(cond,),(response,))
        return _new_page(project,page)
    index,page=_page(project,args)
    if operation in ("page_condition_copy","page_action_copy"):
        field="conditions" if operation=="page_condition_copy" else "actions"
        existing=getattr(page,field)
        source=_integer(args,"source_index",0,len(existing)-1)
        if len(existing)>=32:
            raise StudioError("RPG event page action/condition capacity exhausted")
        pos=_integer(args,"position",0,len(existing)) if "position" in args else len(existing)
        page=replace(page,**{field:existing[:pos]+(existing[source],)+existing[pos:]})
    elif operation in ("page_condition_swap","page_action_swap"):
        field="conditions" if operation=="page_condition_swap" else "actions"
        existing=list(getattr(page,field))
        a=_integer(args,"a",0,len(existing)-1)
        b=_integer(args,"b",0,len(existing)-1)
        if a==b:
            raise StudioError("sensor/action swap requires distinct entries")
        existing[a],existing[b]=existing[b],existing[a]
        page=replace(page,**{field:tuple(existing)})
    elif operation in ("page_condition_rotate","page_action_rotate"):
        field="conditions" if operation=="page_condition_rotate" else "actions"
        existing=getattr(page,field)
        if len(existing)<2:
            raise StudioError("rotation requires at least two authored entries")
        count=_integer(args,"offset",-31,31)
        shift=count%len(existing)
        if shift==0:
            raise StudioError("rotation must change action ordering")
        page=replace(page,**{field:existing[-shift:]+existing[:-shift]})
    elif operation in ("page_threshold_shift","page_threshold_scale"):
        values=[]
        for cond in page.conditions:
            if operation=="page_threshold_shift":
                delta=_float(args,"delta",-1e6,1e6)
                threshold=cond.threshold+delta
                upper=None if cond.upper_threshold is None else cond.upper_threshold+delta
            else:
                factor=_float(args,"factor",.001,1000)
                threshold=cond.threshold*factor
                upper=None if cond.upper_threshold is None else cond.upper_threshold*factor
            values.append(replace(cond,threshold=threshold,upper_threshold=upper))
        page=replace(page,conditions=tuple(values))
    elif operation=="page_duplicate_signal":
        ident=_name(args,"new_page_id")
        signal=_name(args,"signal")
        if signal not in RPG_ENVIRONMENT_SIGNALS:
            raise StudioError("RPG event sensor not registered in canonical signals")
        comparison=args.get("comparison",page.conditions[0].comparison)
        if comparison not in COMPARISONS:
            raise StudioError("event clone comparator invalid")
        threshold=_float(args,"threshold")
        upper=_float(args,"upper_threshold") if "upper_threshold" in args else None
        conditions=(EnvironmentalTrigger(signal,comparison,threshold,upper),)
        clone=replace(page,page_id=ident,conditions=conditions)
        return _new_page(project,clone)
    elif operation=="page_dual_threshold_branches":
        low=_float(args,"low")
        high=_float(args,"high")
        if not low<high:
            raise StudioError("sensor split needs ordered low/high thresholds")
        low_id=_name(args,"low_page_id")
        high_id=_name(args,"high_page_id")
        if low_id==high_id:
            raise StudioError("sensor split needs independent response IDs")
        cond=page.conditions[0]
        low_event=replace(page,page_id=low_id,conditions=(
            replace(cond,comparison="below",threshold=low,
                    upper_threshold=None),))
        high_event=replace(page,page_id=high_id,conditions=(
            replace(cond,comparison="above",threshold=high,
                    upper_threshold=None),))
        return _new_page(_new_page(project,low_event),high_event)
    else:
        raise StudioError("unknown RPG environment authoring feature")
    if page==project.environmental_pages[index]:
        raise StudioError("environment composition produced no source change")
    return replace(project,environmental_pages=_replace(project.environmental_pages,index,page))
