"""Batched wind- and collision-responsive shrub tips and small rocks.

Bounded deterministic candidate reference; game engine owns gameplay
collision, registered rigid bodies, particles and physically simulated cloth.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import math

from .game_frontier_production import Vec3
from .game_frontier_ecosystem import bounded, clamp


class BiomeMotionError(ValueError):
    pass


def length(v: Vec3) -> float:
    return math.sqrt(v.dot(v))


@dataclass(frozen=True)
class ShrubState:
    shrub_id: str
    root: Vec3
    tip: Vec3
    velocity: Vec3
    stiffness_n_m: float
    mass_kg: float
    radius_m: float
    health: float = 1.

    def __post_init__(self):
        if not self.shrub_id or len(self.shrub_id)>128:
            raise BiomeMotionError("shrub ID required")
        bounded(self.stiffness_n_m,"shrub stiffness",.01,1e5)
        bounded(self.mass_kg,"shrub mass",.0001,1e5)
        bounded(self.radius_m,"shrub radius",.001,100)
        bounded(self.health,"health",0,1)


@dataclass(frozen=True)
class SmallRockState:
    rock_id: str
    position: Vec3
    velocity: Vec3
    radius_m: float
    mass_kg: float
    restitution: float = .25
    rolling_radians: float = 0.

    def __post_init__(self):
        if not self.rock_id or len(self.rock_id)>128:
            raise BiomeMotionError("rock ID required")
        bounded(self.radius_m,"rock radius",.001,100)
        bounded(self.mass_kg,"rock mass",.001,1e6)
        bounded(self.restitution,"restitution",0,1)
        bounded(self.rolling_radians,"rotation",-1e9,1e9)


@dataclass(frozen=True)
class ContactForce:
    position: Vec3
    impulse_ns: Vec3
    radius_m: float

    def __post_init__(self):
        bounded(self.radius_m,"impact radius",0,100)
        if length(self.impulse_ns)>1e7:
            raise BiomeMotionError("impact exceeds limit")


@dataclass(frozen=True)
class BiomeMotion:
    shrubs: tuple[ShrubState, ...]
    rocks: tuple[SmallRockState, ...]
    impact_count: int
    authority: str = "reference_motion_not_engine_committed"


def advance_biome_objects(
    shrubs: tuple[ShrubState,...],
    rocks: tuple[SmallRockState,...],
    *, wind: Vec3, dt_s: float,
    contacts: tuple[ContactForce,...] = (),
    ground_z_m: float = 0.,
) -> BiomeMotion:
    dt=bounded(dt_s,"biome dt",0,.25)
    ground=bounded(ground_z_m,"ground",-1e5,1e5)
    if len(shrubs)>8192 or len(rocks)>8192 or len(contacts)>256:
        raise BiomeMotionError("biome object batch exceeded")
    if length(wind)>250:
        raise BiomeMotionError("reference wind exceeded")
    moved_shrubs,moved_rocks=[],[]
    impacts=0
    for shrub in shrubs:
        if not isinstance(shrub,ShrubState):
            raise BiomeMotionError("shrub type required")
        # Wind bends tip but trunk root is fixed. The original height of
        # the tip is an explicit restoring proxy instead of implicit state.
        displacement=shrub.tip-shrub.root
        restoring=Vec3(-displacement.x*.6,-displacement.y*.6,
                        -max(0,displacement.z-1)*.25).scaled(shrub.stiffness_n_m)
        drag=(wind-shrub.velocity).scaled(shrub.radius_m**2*.35)
        impulse=Vec3(0,0,0)
        for hit in contacts:
            if length(shrub.tip-hit.position)<=shrub.radius_m+hit.radius_m:
                impulse=impulse+hit.impulse_ns
                impacts+=1
        accelerated=(restoring+drag).scaled(dt/shrub.mass_kg)
        if dt>0: accelerated=accelerated+impulse.scaled(1/shrub.mass_kg)
        if length(accelerated)>15:
            accelerated=accelerated.scaled(15/length(accelerated))
        velocity=shrub.velocity.scaled(max(0,1-dt*.8))+accelerated
        new_tip=shrub.tip+velocity.scaled(dt)
        bent=min(1,length(new_tip-shrub.tip)/(max(shrub.radius_m,.01)))
        moved_shrubs.append(replace(shrub,tip=new_tip,velocity=velocity,
                                    health=clamp(shrub.health-bent*.0001)))
    for rock in rocks:
        if not isinstance(rock,SmallRockState):
            raise BiomeMotionError("rock type required")
        impulse=Vec3(0,0,0)
        for hit in contacts:
            if length(rock.position-hit.position)<=rock.radius_m+hit.radius_m:
                impulse=impulse+hit.impulse_ns
                impacts+=1
        horizontal=Vec3(rock.velocity.x,rock.velocity.y,0)
        wind_drag=wind.scaled(.0001*rock.radius_m**2)
        v=rock.velocity+impulse.scaled(1/rock.mass_kg)+wind_drag.scaled(dt)
        v=Vec3(v.x,v.y,v.z-9.81*dt)
        position=rock.position+v.scaled(dt)
        if position.z<ground+rock.radius_m:
            position=Vec3(position.x,position.y,ground+rock.radius_m)
            v=Vec3(v.x*.9,v.y*.9,max(0,-v.z*rock.restitution))
        rotation=rock.rolling_radians+math.hypot(v.x,v.y)*dt/rock.radius_m
        moved_rocks.append(replace(rock,position=position,velocity=v,
                                    rolling_radians=rotation))
    return BiomeMotion(tuple(moved_shrubs),tuple(moved_rocks),impacts)
