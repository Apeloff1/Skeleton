"""Source-bound sky-island archipelagos with playable alternative routes.

Creates deterministic original geometry and authored travel links; it never
copies game maps or pretends generated coordinates were captured by a native
engine. All islands are reachable by at least one supported capability set.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
import random

from .game_frontier_expedition import (
    ExpeditionError, ExpeditionWeather, ExpeditionWorld,
    TravelEdge, Traveler, Waypoint, alternative_routes, find_route,
    verify_route, world_export,
)


@dataclass(frozen=True, slots=True)
class ArchipelagoProfile:
    seed: int
    islands: int = 12
    spacing_m: float = 60.0
    rise_m: float = 14.0
    branch_factor: int = 2
    caverns: int = 2
    include_underwater: bool = True
    include_portals: bool = True

    def __post_init__(self):
        if type(self.seed) is not int or not 0 <= self.seed <= 2**63-1:
            raise ExpeditionError("bounded deterministic world seed required")
        if type(self.islands) is not int or not 3 <= self.islands <= 256:
            raise ExpeditionError("islands must range from 3 to 256")
        if type(self.branch_factor) is not int or not 1 <= self.branch_factor <= 4:
            raise ExpeditionError("branch factor must range from 1 to 4")
        if type(self.caverns) is not int or not 0 <= self.caverns <= 16:
            raise ExpeditionError("cavern count must be bounded")
        if type(self.include_underwater) is not bool or type(self.include_portals) is not bool:
            raise ExpeditionError("optional realms must be boolean")
        for name, value, lo, hi in (
            ("spacing_m",self.spacing_m,10,5000),
            ("rise_m",self.rise_m,3,1000),
        ):
            if type(value) not in (int,float) or not math.isfinite(value) or not lo<=value<=hi:
                raise ExpeditionError(f"{name} must be bounded finite geometry")


def author_archipelago(
    project_id: str, source_digest: str, profile: ArchipelagoProfile,
    *, weather: ExpeditionWeather | None = None,
) -> ExpeditionWorld:
    """Author linked 3D sky, sea and cave regions as playable game geometry."""
    if not isinstance(profile,ArchipelagoProfile):
        raise ExpeditionError("typed world generation profile required")
    rng=random.Random(profile.seed)
    waypoints=[Waypoint("harbor",0.0,0.0,0.0,"settlement",
                        landmark="Departure harbor",safe_rest=True,
                        quest_flag="journey_started")]
    edges=[]
    for i in range(1,profile.islands+1):
        theta=2*math.pi*(i-1)/max(3,profile.islands)
        ring=(1+(i-1)//8)*profile.spacing_m
        x=round(math.cos(theta)*ring+rng.uniform(-10,10),3)
        y=round(math.sin(theta)*ring+rng.uniform(-10,10),3)
        z=round(profile.rise_m*(1+(i-1)//3)+rng.uniform(0,4),3)
        node_id=f"island_{i:03d}"
        waypoints.append(Waypoint(
            node_id,x,y,z,"sky_island",
            landmark=f"Original floating islet {i}",
            safe_rest=(i%3==0),
            collectible=f"sky_relic_{i:03d}" if i%4==0 else "",
            quest_flag=f"charted_islet_{i:03d}",
            discovery_score=20+(i%7)*3,
        ))
    def link(eid,source,target,mode,*,seconds=12,energy=4,risk=0.01,
             scenic=1,requires=(),grants=(),one_way=True):
        src=next(w for w in waypoints if w.waypoint_id==source)
        dst=next(w for w in waypoints if w.waypoint_id==target)
        length=math.sqrt((src.x_m-dst.x_m)**2+(src.y_m-dst.y_m)**2+
                         (src.altitude_m-dst.altitude_m)**2)
        edges.append(TravelEdge(
            eid,source,target,mode,max(.01,round(length,3)),
            seconds,energy,risk,scenic,
            tuple(requires),tuple(grants),one_way,
        ))
    # Guaranteed rising corridor, with optional short airship transit and
    # multiple lateral/scenic crosslinks. Ascents are explicit updrafts.
    first=waypoints[1]
    link("launch_updraft","harbor",first.waypoint_id,"updraft",
         seconds=45,energy=3,scenic=15,requires=("glider",))
    link("return_glide",first.waypoint_id,"harbor","glide",
         seconds=18,energy=2,scenic=20,requires=("glider",))
    for i in range(1,profile.islands):
        a=waypoints[i]
        b=waypoints[i+1]
        mode=("updraft" if b.altitude_m>a.altitude_m else
              "glide" if b.altitude_m<a.altitude_m else "rope_bridge")
        requires=("glider",) if mode in {"updraft","glide"} else ()
        link(f"main_{i:03d}",a.waypoint_id,b.waypoint_id,mode,
             seconds=8+rng.randrange(4,14),energy=2,
             scenic=12,requires=requires)
        # Canonical bidirectional bridge paths give an alternate traversal
        # that is independent of untrusted physics/GPS observations.
        link(f"cross_{i:03d}",a.waypoint_id,b.waypoint_id,"rope_bridge",
             seconds=25+rng.randrange(10,25),energy=2,scenic=35,
             risk=0.025,one_way=False)
    for i in range(1,profile.islands+1):
        if i+2<=profile.islands:
            a,b=waypoints[i],waypoints[i+2]
            link(f"bypass_{i:03d}",a.waypoint_id,b.waypoint_id,"airship",
                 seconds=13+i%3,energy=0,scenic=9,
                 requires=("airship_license",))
    # Player can take a different route from the harbor; the engine checks
    # actual ability flag and stamina before allowing it.
    link("harbor_airship","harbor",waypoints[2].waypoint_id,"airship",
         seconds=55,energy=0,scenic=10,requires=("airship_license",))
    for i in range(profile.caverns):
        surface=waypoints[1+i%profile.islands]
        cavern_id=f"cavern_{i:02d}"
        waypoints.append(Waypoint(
            cavern_id,surface.x_m+8,surface.y_m+5,surface.altitude_m-8,
            "cavern",landmark=f"Cavern passage {i}",
            quest_flag=f"cavern_chart_{i}",
            discovery_score=90,safe_rest=True,
        ))
        link(f"cave_descent_{i}",surface.waypoint_id,cavern_id,
             "climb",seconds=20,energy=3,scenic=50)
        link(f"cave_ascend_{i}",cavern_id,surface.waypoint_id,
             "climb",seconds=26,energy=4,scenic=35)
    if profile.include_underwater:
        waypoints.append(Waypoint("reef",15,-14,-12,"underwater",
                                  landmark="Original underwater reef",
                                  collectible="ancient_map",discovery_score=80))
        link("harbor_dive","harbor","reef","dive",seconds=28,
             energy=8,scenic=30,requires=("diving_gear",))
        link("reef_surface","reef","harbor","swim",seconds=24,
             energy=6,scenic=20)
    if profile.include_portals:
        waypoints.append(Waypoint("portal_spire",-25,30,1,"ruins",
                                  landmark="Ancient spire",
                                  quest_flag="spire_discovered",safe_rest=True))
        link("spire_footpath","harbor","portal_spire","walk",
             seconds=38,energy=2,one_way=False,scenic=40)
        link("spire_gateway","portal_spire",waypoints[profile.islands].waypoint_id,
             "portal",seconds=2,energy=0,risk=0.02,
             scenic=70,requires=("portal_key",))
    destination=f"island_{profile.islands:03d}"
    # Fix the terminal goal source explicitly; it cannot be an optional
    # cavern, reef, or unrelated side encounter.
    world=ExpeditionWorld(
        project_id,source_digest,tuple(waypoints),tuple(edges),
        "harbor",(destination,),weather or ExpeditionWeather(),
    )
    return world


def profile_capability_catalog() -> dict:
    return {
        "schema":"skeleton.game.expedition_authoring.v1",
        "world_kinds":(
            "sky_island","settlement","cavern","underwater","ruins",
            "canopy","volcano","ice","airship","ground",
        ),
        "movement_modes":(
            "walk","rope_bridge","updraft","glide","airship","climb",
            "swim","dive","portal","rail","boat",
        ),
        "generation_is_seeded":True,
        "native_engine_executed":False,
        "source_authority":"original_seeded_game_design",
    }


def playtest_archipelago(world: ExpeditionWorld, *, max_routes: int = 8) -> dict:
    """Execute valid routes in the real expedition state machine and retain proof."""
    if not isinstance(world,ExpeditionWorld):
        raise ExpeditionError("an actual typed authored game world is required")
    if type(max_routes) is not int or not 1<=max_routes<=16:
        raise ExpeditionError("route playtest budget must be bounded")
    player=Traveler(
        permitted_modes=frozenset((
            "walk","rope_bridge","updraft","glide","airship",
            "portal","climb","dive","swim",
        )),
        flags=frozenset(("glider","airship_license","diving_gear","portal_key")),
        equipment=frozenset(("instrument_navigation",)),
        max_stamina=1000,skill=0.8,
    )
    routes=alternative_routes(world,player,world.destinations[0],limit=max_routes)
    tested=[verify_route(world,player,route) for route in routes]
    if any(not item["final_state"]["won"] for item in tested):
        raise ExpeditionError("one or more generated route playthroughs did not win")
    proof={
        "schema":"skeleton.game.expedition_playthrough.v1",
        "world_digest":world.digest,
        "routes_executed":len(tested),
        "route_digests":[r.digest for r in routes],
        "final_game_receipts":[t["receipt_head"] for t in tested],
        "all_ended_at_destination":True,
        "authored_source_only":True,
        "requires_native_godot_playtest":True,
    }
    return {**proof,"receipt_digest":sha256(json.dumps(
        proof,sort_keys=True,separators=(",",":"),allow_nan=False,
    ).encode("utf-8")).hexdigest()}
