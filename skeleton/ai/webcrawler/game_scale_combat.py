"""Composable action-combat mechanics: capabilities 021–030.

Fixed-step deterministic combat, weapons, collision, projectiles and status
effects. Original parameters are gameplay defaults, not scraped truth.
"""
from __future__ import annotations
from dataclasses import dataclass,replace
from math import hypot
import random

@dataclass(frozen=True)
class Weapon:
    name: str
    damage: float
    range: float
    cooldown: float
    speed: float
    projectile: bool = False
    pierce: int = 0

@dataclass(frozen=True)
class Fighter:
    entity_id: str
    x: float
    y: float
    health: float
    maximum_health: float
    armor: float = 0.
    vx: float = 0.
    vy: float = 0.
    invulnerable: float = 0.
    stamina: float = 100.

@dataclass(frozen=True)
class Projectile:
    owner: str
    x: float
    y: float
    vx: float
    vy: float
    damage: float
    ttl: float
    pierce: int = 0

@dataclass(frozen=True)
class Status:
    effect: str
    seconds: float
    potency: float

@dataclass(frozen=True)
class CombatHit:
    attacker: str
    victim: str
    damage: float
    killed: bool
    knockback: tuple[float,float]

# 021 Construct bounded original melee/projectile weapons.
def configure_weapon(name: str, *, damage: float, reach: float,
                     cooldown: float, speed: float = 0.,
                     projectile: bool = False,pierce: int = 0) -> Weapon:
    if not isinstance(name,str) or not 1<=len(name)<=64 or not (
        0<damage<=10000 and 0<reach<=1000 and .02<=cooldown<=60 and
        0<=speed<=10000 and 0<=pierce<=20
    ):
        raise ValueError("invalid weapon configuration")
    if projectile and speed<=0: raise ValueError("projectiles require speed")
    return Weapon(name,float(damage),float(reach),float(cooldown),
                  float(speed),projectile,pierce)

# 022 Equip weapon slots and compute a valid interchangeable loadout.
def create_weapon_loadout(weapons: tuple[Weapon,...], *,
                          capacity: int = 4) -> tuple[Weapon,...]:
    if not 1<=capacity<=12 or not weapons or len(weapons)>capacity:
        raise ValueError("invalid weapon inventory")
    if len({w.name for w in weapons})!=len(weapons):
        raise ValueError("duplicate weapon slots")
    return tuple(weapons)

# 023 Reusable circle-versus-circle hit detection for enemies and projectiles.
def combat_overlap(a: tuple[float,float], ar: float,
                   b: tuple[float,float], br: float) -> bool:
    if min(ar,br)<0: raise ValueError("negative collider radius")
    return hypot(a[0]-b[0],a[1]-b[1]) <= ar+br

# 024 Directional melee attack selection (cone + reach + victim exclusion).
def melee_targets(attacker: Fighter, targets: tuple[Fighter,...],
                  weapon: Weapon, *, facing: tuple[float,float],
                  cone_cosine: float = .25) -> tuple[Fighter,...]:
    direction=hypot(*facing)
    if direction==0 or not -1<=cone_cosine<=1:
        raise ValueError("invalid melee direction")
    nx,ny=facing[0]/direction,facing[1]/direction
    result=[]
    for foe in targets:
        if foe.entity_id==attacker.entity_id or foe.health<=0:continue
        dx,dy=foe.x-attacker.x,foe.y-attacker.y
        length=hypot(dx,dy)
        if length<=weapon.range and (
            length==0 or (nx*dx+ny*dy)/length>=cone_cosine
        ):
            result.append(foe)
    return tuple(sorted(result,key=lambda t:(hypot(t.x-attacker.x,t.y-attacker.y),
                                            t.entity_id)))

# 025 Spawn direction-normalized projectiles with finite life.
def fire_projectile(fighter: Fighter, weapon: Weapon, *,
                    direction: tuple[float,float], lifetime: float = 3.
                    ) -> Projectile:
    if not weapon.projectile or not 0<lifetime<=30:
        raise ValueError("weapon not projectile-capable")
    norm=hypot(*direction)
    if norm<=0:raise ValueError("zero projectile direction")
    return Projectile(fighter.entity_id,fighter.x,fighter.y,
                      direction[0]/norm*weapon.speed,
                      direction[1]/norm*weapon.speed,weapon.damage,lifetime,
                      weapon.pierce)

# 026 Advance projectiles with exact bounded timestep and expiration.
def advance_projectiles(projectiles: tuple[Projectile,...], *,
                        delta: float, bounds: tuple[float,float,float,float]
                        ) -> tuple[Projectile,...]:
    if not 0<delta<=.25 or len(projectiles)>10000:
        raise ValueError("invalid projectile simulation step")
    x0,y0,x1,y1=bounds
    if not x0<x1 or not y0<y1:raise ValueError("invalid world bounds")
    result=[]
    for p in projectiles:
        q=replace(p,x=p.x+p.vx*delta,y=p.y+p.vy*delta,ttl=p.ttl-delta)
        if q.ttl>0 and x0<=q.x<=x1 and y0<=q.y<=y1:result.append(q)
    return tuple(result)

# 027 Apply resistance, invulnerability and lethal checks consistently.
def apply_combat_damage(target: Fighter, raw: float, *,
                        armor_pierce: float = 0.) -> tuple[Fighter,float]:
    if not 0<=raw<=1e6 or not 0<=armor_pierce<=1:
        raise ValueError("invalid damage packet")
    if target.health<=0 or target.invulnerable>0:return target,0.
    defense=max(0.,target.armor*(1-armor_pierce))
    amount=max(0.,raw-defense)
    remaining=max(0.,target.health-amount)
    return replace(target,health=remaining),round(target.health-remaining,6)

# 028 Apply finite knockback consistent with direction and target mass.
def apply_knockback(fighter: Fighter, *, direction: tuple[float,float],
                    impulse: float, mass: float = 1.) -> Fighter:
    magnitude=hypot(*direction)
    if magnitude<=0 or not 0<=impulse<=10000 or not .01<=mass<=10000:
        raise ValueError("invalid knockback")
    return replace(fighter,vx=fighter.vx+direction[0]/magnitude*impulse/mass,
                   vy=fighter.vy+direction[1]/magnitude*impulse/mass)

# 029 Tick burning, poison, healing and slow effects over real time.
def advance_combat_status(fighter: Fighter,statuses: tuple[Status,...], *,
                          delta: float) -> tuple[Fighter,tuple[Status,...]]:
    if not 0<delta<=.25 or len(statuses)>32:
        raise ValueError("invalid status step")
    result=fighter;remaining=[]
    for status in statuses:
        if status.effect not in ("burn","poison","heal","slow") or not (
            0<=status.potency<=10000 and 0<status.seconds<=3600
        ):
            raise ValueError("invalid status effect")
        active=min(delta,status.seconds)
        if status.effect in ("burn","poison"):
            result=replace(result,health=max(0.,result.health-status.potency*active))
        elif status.effect=="heal":
            result=replace(result,health=min(result.maximum_health,
                result.health+status.potency*active))
        rest=status.seconds-delta
        if rest>0:remaining.append(replace(status,seconds=rest))
    return result,tuple(remaining)

# 030 Simulate actual multi-wave arena progression with a seeded encounter budget.
def generate_combat_wave(*, wave: int,seed: int,capacity: int = 32,
                         base_health: float = 30.) -> tuple[Fighter,...]:
    if not 1<=wave<=1000 or not 1<=capacity<=256 or not 1<=base_health<=100000:
        raise ValueError("invalid encounter wave")
    rng=random.Random(seed+wave*104729)
    count=min(capacity,2+wave//2)
    result=[]
    for i in range(count):
        hp=base_health*(1+.08*wave)*(1+rng.random()*.2)
        result.append(Fighter(f"wave-{wave}-foe-{i}",rng.uniform(2,32),
                              rng.uniform(2,16),hp,hp,armor=min(20,wave*.15)))
    return tuple(result)
