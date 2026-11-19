"""Strict bounded input for the coupled frontier CPU reference environment."""
from __future__ import annotations

from dataclasses import dataclass
import math

from skeleton.app.recovered_evidence import EvidenceError,array,fields,identifier,integer,canonical
from skeleton.jeeves.game_frontier_production import Vec3
from skeleton.jeeves.game_frontier_dynamics import PresentationClock
from skeleton.jeeves.game_frontier_motion import Weather
from skeleton.jeeves.game_frontier_ecosystem import AirConditions
from skeleton.jeeves.game_frontier_weather_physics import Microclimate
from skeleton.jeeves.game_frontier_advanced_physics import TractionSurface,Climber
from skeleton.jeeves.game_frontier_body_balance import BodyMass,SupportFoot
from skeleton.jeeves.game_frontier_biome_motion import ShrubState,SmallRockState,ContactForce
from skeleton.jeeves.game_frontier_photometry import LeafPose
from skeleton.jeeves.game_frontier_lighting import SurfaceSample,LightSource,RayOccluder

MAX_FRAMES=10_000
MAX_RAY_TESTS=5_000_000
MAX_MOTION_OBJECT_STEPS=1_000_000
MAX_CHECKPOINTS=256
ZERO=Vec3(0,0,0)
UP=Vec3(0,0,1)


def number(v,lo,hi):
    if type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=hi:
        raise EvidenceError("numeric value outside reference envelope")
    return float(v)


def vec(v,limit=10_000):
    return Vec3(*(number(n,-limit,limit) for n in array(v,3,3)))


def rgb(v):
    return tuple(number(n,0,1) for n in array(v,3,3))


def unit(v):
    result=vec(v,1)
    if abs(result.dot(result)-1)>1e-5:
        raise EvidenceError("unit direction required")
    return result


def sequence(raw,limit,builder,min_count=0):
    return tuple(builder(row) for row in array(raw,min_count,limit))


def row(raw,keys):
    return fields(raw,set(keys.split()))


@dataclass(frozen=True)
class WeatherBlock:
    frames:int
    weather:Weather
    air:AirConditions
    cloud:float
    acceleration:Vec3
    velocity:Vec3


def weather_block(value):
    x=row(value,"frames wind temperature humidity rain sunlight altitude fog cloud acceleration velocity")
    temp=number(x["temperature"],-80,70)
    wet=number(x["humidity"],0,1)
    rain=number(x["rain"],0,1000)
    velocity=vec(x["velocity"],100)
    if velocity.dot(velocity)>100**2:
        raise EvidenceError("motion speed exceeds traction envelope")
    return WeatherBlock(integer(x["frames"],1,MAX_FRAMES),
        Weather(vec(x["wind"],150),temp,rain,wet,sunlight=number(x["sunlight"],0,1)),
        AirConditions(altitude_m=number(x["altitude"],-500,11000),temperature_c=temp,
                      relative_humidity=wet,fog_liquid_g_m3=number(x["fog"],0,3),rain_mm_h=rain),
        number(x["cloud"],0,1),vec(x["acceleration"],50),velocity)


def micro(x):
    row(x,"temperature soil_water ice sediment roughness vegetation pressure_gradient heat_flux")
    return Microclimate(number(x["temperature"],-120,120),number(x["soil_water"],0,1),
        number(x["ice"],0,1),number(x["sediment"],0,1),number(x["roughness"],0,1),
        number(x["vegetation"],0,1),vec(x["pressure_gradient"],20),
        number(x["heat_flux"],-2000,3000))


def traction(x):
    row(x,"normal static_friction dynamic_friction foothold")
    return TractionSurface(unit(x["normal"]),number(x["static_friction"],0,3),
                           number(x["dynamic_friction"],0,3),foothold_quality=number(x["foothold"],0,1))


def mass(x):
    row(x,"id kg location radius carried")
    if type(x["carried"]) is not bool:
        raise EvidenceError("explicit cargo selection required")
    return BodyMass(identifier(x["id"]),number(x["kg"],.001,500),vec(x["location"]),
                    number(x["radius"],.001,100),x["carried"])


def foot(x):
    row(x,"id position capacity friction")
    return SupportFoot(identifier(x["id"]),vec(x["position"]),number(x["capacity"],0,1e7),
                       number(x["friction"],0,3))


def shrub(x):
    row(x,"id root tip stiffness mass radius")
    return ShrubState(identifier(x["id"]),vec(x["root"]),vec(x["tip"]),ZERO,
                      number(x["stiffness"],.01,10000),number(x["mass"],.01,1000),
                      number(x["radius"],.001,10))


def rock(x):
    row(x,"id position radius mass")
    return SmallRockState(identifier(x["id"]),vec(x["position"]),ZERO,
                          number(x["radius"],.001,10),number(x["mass"],.001,10000))


def leaf(x):
    row(x,"id shrub anchor center normal width length opacity mass stiffness")
    return (identifier(x["shrub"]),LeafPose(identifier(x["id"]),vec(x["anchor"]),vec(x["center"]),
        ZERO,unit(x["normal"]),number(x["width"],.001,5),number(x["length"],.001,5),
        number(x["opacity"],0,1),number(x["mass"],.001,2),number(x["stiffness"],.01,10000)))


def light(x):
    row(x,"id position intensity radius color")
    return LightSource(identifier(x["id"]),vec(x["position"]),number(x["intensity"],0,1e7),
                       number(x["radius"],0,100),rgb(x["color"]))


def surface(x):
    row(x,"id position normal albedo roughness")
    return SurfaceSample(identifier(x["id"]),vec(x["position"]),unit(x["normal"]),
                         rgb(x["albedo"]),number(x["roughness"],0,1))


def occluder(x):
    row(x,"id center radius opacity")
    return RayOccluder(identifier(x["id"]),"object",vec(x["center"]),"sphere",
                       radius_m=number(x["radius"],.001,100),opacity=number(x["opacity"],0,1))


@dataclass(frozen=True)
class Scenario:
    fps:int
    frames:int
    stride:int
    area_samples:int
    ground:float
    sun:Vec3
    micro:Microclimate
    traction:TractionSurface
    climber:Climber
    segments:tuple
    feet:tuple
    shrubs:tuple
    rocks:tuple
    leaves:tuple
    surfaces:tuple
    lights:tuple
    occluders:tuple
    weather:tuple
    contacts:dict
    ray_test_ceiling:int


def load_order(x):
    row(x,"schema fps checkpoint_stride area_samples ground sun microclimate traction segments feet shrubs rocks leaves surfaces lights occluders weather contacts")
    if x["schema"]!="skeleton.frontier-environment-replay.order.v1":
        raise EvidenceError("unsupported reference environment")
    canonical(x)
    fps=PresentationClock(integer(x["fps"],1,120)).fps
    stride=integer(x["checkpoint_stride"],1,MAX_FRAMES)
    area_samples=integer(x["area_samples"],1,8)
    ground=number(x["ground"],-10000,10000)
    sun=unit(x["sun"])
    if sun.z<=.02:
        raise EvidenceError("sun direction above reference receiver required")
    m=micro(x["microclimate"])
    tr=traction(x["traction"])
    segments=sequence(x["segments"],64,mass,1)
    feet=sequence(x["feet"],16,foot,3)
    shrubs=sequence(x["shrubs"],32,shrub)
    rocks=sequence(x["rocks"],32,rock)
    leaves=sequence(x["leaves"],64,leaf)
    surfaces=sequence(x["surfaces"],16,surface,1)
    lights=sequence(x["lights"],8,light,1)
    occluders=sequence(x["occluders"],32,occluder)
    weather=sequence(x["weather"],128,weather_block,1)
    frames=sum(w.frames for w in weather)
    if frames>MAX_FRAMES or (frames+stride-1)//stride>MAX_CHECKPOINTS:
        raise EvidenceError("frame or checkpoint ceiling")
    ids=[s.shrub_id for s in shrubs]+[r.rock_id for r in rocks]+[l.leaf_id for _,l in leaves]+[
        s.object_id for s in surfaces]+[l.light_id for l in lights]+[o.object_id for o in occluders]
    if len(set(ids))!=len(ids):
        raise EvidenceError("duplicate scene object identity")
    if any(name not in {s.shrub_id for s in shrubs} for name,_ in leaves):
        raise EvidenceError("leaf attachment outside shrub catalogue")
    rays=frames*(len(surfaces)*len(lights)*area_samples*(len(occluders)+len(rocks)+len(shrubs)+len(leaves)+1)
                +5*len(leaves))
    if rays>MAX_RAY_TESTS or frames*(len(shrubs)+len(rocks)+20*len(leaves))>MAX_MOTION_OBJECT_STEPS:
        raise EvidenceError("coupled scene work ceiling")
    contacts={}
    for value in array(x["contacts"],0,128):
        row(value,"frame position impulse radius")
        index=integer(value["frame"],0,frames-1)
        contact=ContactForce(vec(value["position"]),vec(value["impulse"],1000),
                             number(value["radius"],0,20))
        contacts.setdefault(index,[]).append(contact)
        if len(contacts[index])>16:
            raise EvidenceError("per-frame contact ceiling")
    body=sum(s.mass_kg for s in segments if not s.carried)
    carried=sum(s.mass_kg for s in segments if s.carried)
    climber=Climber(body,800,.7,.8,1.,load_kg=carried)
    return Scenario(fps,frames,stride,area_samples,ground,sun,m,tr,climber,segments,feet,
                    shrubs,rocks,leaves,surfaces,lights,occluders,weather,contacts,rays)
