"""Constructive, certifiable ORIGINAL multi-route maze worlds.

The generator does not roll random doors and hope a solver eventually wins.
It creates a fully traversable zero-cost main corridor, attaches rewarding
doubleback chambers, then braids optional scenic, secret, shortcut, weather,
public-transit and fictional routes around the immutable winning backbone.

The admission certificate independently *replays* an actual win for every
cell from an ordinarily accessible prefix, in every supported climate.
Because graph play has a bounded action/time horizon, a global restart is
still necessary after deliberately exhausting those budgets. The certificate
states this precisely; it is not an impossible guarantee that any arbitrary
action history must be winnable without reset.

Grid layout and routes are original generator output. No commercial-game
maze or artwork is acquired by this module.
"""
from __future__ import annotations

from dataclasses import asdict,dataclass,replace
from hashlib import sha256
import json,random

from .dragon_route_world import (
    Place,Traverse,World,Traveller,replay,validate_world,experience,
    MAX_HOPS,
)
from .dragon_route_taxonomy import ENVIRONMENT_FLAGS

SCHEMA="skeleton.ai.dragon.constructive_maze.v1"
WEATHERS=("clear","rain","windy","storm","snow","high_tide")
BIOMES=("temperate","ruins","stone","forest","underground","wetlands")
MAX_MAZE_CELLS=48

@dataclass(frozen=True)
class MazeRequest:
    width:int=6
    height:int=6
    seed:int=1977
    scenic_density:int=55
    detour_density:int=60
    secret_count:int=2
    challenge:str="balanced"
    weather:str="clear"

@dataclass(frozen=True)
class MazeCertificate:
    schema:str
    world_digest:str
    source_seed:int
    dimensions:tuple[int,int]
    start:str
    goal:str
    backbone:tuple[str,...]
    backbone_locations:tuple[str,...]
    backbone_moves:int
    main_journey_digest:str
    all_climates_backbone_verified:tuple[str,...]
    location_recovery_verified:tuple[str,...]
    location_recovery_routes:tuple[tuple[str,...],...]
    location_recovery_count:int
    real_dead_ends:tuple[str,...]
    return_edges:tuple[str,...]
    doubleback_witnesses:tuple[tuple[str,...],...]
    impractical_witnesses:tuple[tuple[str,...],...]
    scenic_witnesses:tuple[tuple[str,...],...]
    secret_witnesses:tuple[tuple[str,...],...]
    optional_shapes:tuple[str,...]
    total_edges:int
    guarantee_scope:str
    certificate_digest:str

@dataclass(frozen=True)
class MazeCreation:
    request:MazeRequest
    world:World
    traveller:Traveller
    certificate:MazeCertificate


def _bounded(request:MazeRequest):
    if not isinstance(request,MazeRequest):
        raise ValueError("maze generator requires typed original design controls")
    for value,low,high,name in (
        (request.width,4,8,"width"),(request.height,4,6,"height"),
        (request.seed,0,2**32-1,"seed"),
        (request.scenic_density,0,100,"scenic density"),
        (request.detour_density,0,100,"detour density"),
        (request.secret_count,0,4,"secret count"),
    ):
        if type(value) is not int or not low<=value<=high:
            raise ValueError("maze "+name+" outside bounded original-world design limits")
    if request.width*request.height>MAX_MAZE_CELLS:
        raise ValueError("maze would exceed native game's 48-node source limit")
    if request.challenge not in ("gentle","balanced","challenging","spicy"):
        raise ValueError("maze challenge needs declared original difficulty intent")
    if request.weather not in WEATHERS:
        raise ValueError("unimplemented maze environmental conditions")


def _place(row:int,col:int)->str:
    return f"maze_{row}_{col}"


def _main_spine(width:int,height:int)->tuple[tuple[int,int],...]:
    # In each even row: serpentine main corridor across every column.
    # Adjacent odd-row connector joins the next serpentine floor. Remaining
    # odd-row cells are side chambers, each with its own recoverable return.
    coords=[]
    for row in range(0,height,2):
        columns=range(width) if (row//2)%2==0 else range(width-1,-1,-1)
        coords.extend((row,col) for col in columns)
        if row+2<height:
            last=coords[-1][1]
            coords.append((row+1,last))
    return tuple(coords)


def _name(prefix:str,from_id:str,to_id:str)->str:
    return prefix+"_"+from_id[5:]+"_"+to_id[5:]


def _canonical(obj)->bytes:
    return json.dumps(obj,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True).encode("ascii")


def _fingerprint(world:World)->str:
    return sha256(_canonical(asdict(world))).hexdigest()


def _final_digest(cert:dict)->str:
    return sha256(_canonical(cert)).hexdigest()


def build_maze(request:MazeRequest=MazeRequest())->MazeCreation:
    _bounded(request)
    rng=random.Random(request.seed)
    # Challenge is an actual graph-construction choice, not merely a label.
    # Gentle introduces more interchanges/early shortcuts; higher challenge
    # makes the trusted main passage longer and detours more deceptive.
    braid_density=max(0,min(100,request.detour_density+
        {"gentle":25,"balanced":0,"challenging":-20,"spicy":-35}[request.challenge]))
    corridor_minutes={
        "gentle":3,"balanced":4,"challenging":6,"spicy":8
    }[request.challenge]
    backbone=_main_spine(request.width,request.height)
    base_ids=tuple(_place(*xy) for xy in backbone)
    indexed={xy:number for number,xy in enumerate(backbone)}
    all_cells=[(row,col) for row in range(request.height)
               for col in range(request.width)]
    side=[xy for xy in all_cells if xy not in indexed]
    places=[]
    clue_at={}
    # Select clues from early side chambers, which require physical travel
    # down a dead end and then reversing direction to rejoin the main spine.
    def secret_eligible(cell):
        row,col=cell
        neighbors=((row-1,col),(row+1,col),(row,col-1),(row,col+1))
        indices=[indexed[x] for x in neighbors if x in indexed]
        return indices and min(indices)<=len(backbone)-3
    early=sorted((room for room in side if secret_eligible(room)),
                 key=lambda xy:(xy[0],xy[1]))
    choices=early[:min(request.secret_count,len(early))]
    for number,cell in enumerate(choices):
        clue_at[cell]=f"maze_clue_{number}"
    for row,col in all_cells:
        side_room=(row,col) not in indexed
        clue=clue_at.get((row,col))
        scenery=(35+rng.randrange(66) if side_room else rng.randrange(36))
        biome=BIOMES[(row+col+request.seed)%len(BIOMES)]
        places.append(Place(
            _place(row,col),region="maze",biome=biome,
            gifts=((clue,) if clue else ()),
            energy_refill=0,money_pickup=0,scenic_value=scenery,
            tags=("scenic","detour","reward") if side_room else ("spine",),
        ))
    edges=[]
    main=[]
    back=[]
    parent={}
    side_forward={}
    side_reverse={}
    def add(prefix,a,b,mode,minutes,*,shapes=(),price=0,fatigue=0,
            danger=0,spectacle=0,requires=(),discover="",
            weather_any=(),weather_none=(),fuel=0,oxygen=0,mana=0,
            departures=()):
        edge=Traverse(
            id=_name(prefix,a,b),origin=a,destination=b,
            mode=mode,minutes=minutes,price=price,fatigue=fatigue,
            danger=danger,spectacle=spectacle,
            shapes=tuple(shapes),requires=tuple(requires),
            secret_token=discover,weather_any=tuple(weather_any),
            weather_none=tuple(weather_none),fuel=fuel,oxygen=oxygen,mana=mana,
            departures=tuple(departures),
        )
        if any(x.id==edge.id for x in edges):
            raise ValueError("original maze emitted a duplicate directed passage")
        edges.append(edge)
        return edge.id
    for before,after in zip(backbone,backbone[1:]):
        origin,destination=_place(*before),_place(*after)
        forward=add("spine",origin,destination,"walk",corridor_minutes,
                    shapes=("critical","spine","guided"))
        reverse=add("reverse",destination,origin,"walk",corridor_minutes,
                    shapes=("doubleback","backtrack","safe_return","recovery"))
        main.append(forward)
        back.append(reverse)
    for row,col in side:
        # A side chamber always returns directly to the proven backbone.
        # No deadend is gratuitous: it contains scenery, discovery, and an
        # unconditionally usable return path.
        candidates=[(row-1,col),(row+1,col),(row,col-1),(row,col+1)]
        neighbors=[x for x in candidates if x in indexed]
        if not neighbors:
            raise ValueError("maze construction placed a disconnected side chamber")
        attach=min(neighbors,key=lambda xy:(indexed[xy],xy))
        parent[(row,col)]=attach
        origin,destination=_place(*attach),_place(row,col)
        outward=add("branch",origin,destination,"trail",5+rng.randrange(6),
                    shapes=("detour","scenic","dead_end","branch","free_roam",
                            "impractical","long_way"),
                    spectacle=35+rng.randrange(51))
        returning=add("doubleback",destination,origin,"trail",4,
                      shapes=("doubleback","retrace","recovery","return_only"))
        side_forward[(row,col)]=outward
        side_reverse[(row,col)]=returning
    # Optional braid routes always connect existing traversable backbone
    # nodes; removing every braid therefore cannot break completion.
    braid=[]
    used={(e.origin,e.destination) for e in edges}
    for index in range(len(base_ids)-4):
        if rng.randrange(100)>=braid_density:
            continue
        jump=2+rng.randrange(3)
        to=index+jump
        if to>=len(base_ids):continue
        a,b=base_ids[index],base_ids[to]
        if (a,b) in used:continue
        used.add((a,b))
        name=add("scenic",a,b,"trail",
                 10+jump*7+rng.randrange(19),
                 shapes=("scenic","vista","detour","braid","alternate"),
                 spectacle=55+rng.randrange(46))
        braid.append((index,to,name))
    # Genuine scenic circular tours require visiting a side chamber and
    # returning. A loop itself may be longer than any direct win.
    scenic_witnesses=[]
    for room in side:
        if rng.randrange(100)>=request.scenic_density:
            continue
        connector=parent[room]
        index=indexed[connector]
        scenic_witnesses.append(tuple(
            main[:index]+[side_forward[room],side_reverse[room]]+main[index:]
        ))
    # Deliberately inefficient yet *real* journeys repeat an explored
    # chamber and return several times before winning. These certify long,
    # frustrating or scenic circuit choices are possible without corrupting
    # the safe, direct completion corridor.
    impractical=[]
    for room in side[:min(3,len(side))]:
        at=indexed[parent[room]]
        laps=3 if request.challenge in ("gentle","balanced") else 5
        route=tuple(
            main[:at]+
            [side_forward[room],side_reverse[room]]*laps+
            main[at:]
        )
        if len(route)<=MAX_HOPS:
            if not replay(
                World(tuple(places),tuple(edges),base_ids[0],base_ids[-1],
                      (request.weather,),True,"generated_original",10080),
                route,Traveller(),objective="deliberate_long_way",
            ).success:
                raise ValueError("original maze long-route witness not executable")
            impractical.append(route)
    # Secret shortcut requires the clue physically obtained in a chamber,
    # then a doubleback before the route can be discovered.
    secret_witnesses=[]
    for number,(room,clue) in enumerate(clue_at.items()):
        attach=parent[room]
        from_index=indexed[attach]
        source_index=min(len(base_ids)-3,from_index+2)
        dest_index=min(len(base_ids)-1,source_index+3)
        if dest_index<=source_index:continue
        secret_origin,secret_destination=base_ids[source_index],base_ids[dest_index]
        secret_id=add("secret",secret_origin,secret_destination,"hidden_passage",2,
                      shapes=("secret","secret_unlockable","hidden","shortcut",
                              "unlockable","knowledge_gate","optional"),
                      requires=(clue,),discover=clue)
        secret_witnesses.append(tuple(
            main[:from_index]+[side_forward[room],side_reverse[room]]+
            main[from_index:source_index]+[secret_id]+main[dest_index:]
        ))
    # Environment and transport add physically conditional routes but
    # NEVER gate the permanent spine / return corridors.
    opts=[
        ("rain","rain_route","rain",("rain","storm")),
        ("wind","updraft","windy",("windy",)),
        ("snow","ice_bridge","snow",("snow",)),
        ("sea","ferry","high_tide",("high_tide",)),
        ("transit","tram","clear",()),
        ("taxi","taxi","clear",()),
        ("dream","magic_gate","clear",()),
    ]
    for number,(prefix,mode,weather,climates) in enumerate(opts):
        a_index=min(len(base_ids)-3,1+number*2)
        b_index=min(len(base_ids)-1,a_index+3)
        if a_index>=b_index:continue
        add(prefix,base_ids[a_index],base_ids[b_index],mode,
            2+number*3,price=(6 if mode in ("ferry","tram","taxi") else 0),
            shapes=("alternate","shortcut","weather_gated") if climates else
                   ("alternate","shortcut"),
            weather_any=climates,
            spectacle=15+number*8)
    world=World(
        tuple(places),tuple(edges),base_ids[0],base_ids[-1],
        (request.weather,),True,"generated_original",10080,
    )
    traveller=Traveller(tokens=frozenset(),cash=200,energy=100,
                        start_minute=480,oxygen=60,fuel=60,mana=60)
    validate_world(world)
    completed=replay(world,tuple(main),traveller,objective="constructive_backbone")
    recovery=[]
    recovery_routes=[]
    for cell in all_cells:
        if cell in indexed:
            i=indexed[cell]
            trace=tuple(main[:i]+main[i:])
        else:
            i=indexed[parent[cell]]
            trace=tuple(main[:i]+[side_forward[cell],side_reverse[cell]]+main[i:])
        result=replay(world,trace,traveller,objective="location_recovery_proof")
        if not result.success:
            raise ValueError("constructed maze has an unfinishable room")
        recovery.append(_place(*cell))
        recovery_routes.append(trace)
    for witness in (*scenic_witnesses,*secret_witnesses):
        if not replay(world,witness,traveller).success:
            raise ValueError("constructed optional route fails actual game mechanics")
    doublebacks=tuple(tuple(main[:indexed[parent[room]]]+
                       [side_forward[room],side_reverse[room]]+
                       main[indexed[parent[room]]:])
                      for room in side)
    weather_verified=[]
    for climate in WEATHERS:
        changed=replace(world,environment=(climate,))
        result=replay(changed,tuple(main),traveller)
        if not result.success:
            raise ValueError("constructed world lost its safe route in "+climate)
        weather_verified.append(climate)
    deadends=tuple(sorted(_place(*x) for x in side))
    report={
        "schema":SCHEMA,"world_digest":_fingerprint(world),
        "source_seed":request.seed,
        "dimensions":(request.width,request.height),
        "start":world.start,"goal":world.goal,
        "backbone":tuple(main),"backbone_locations":base_ids,
        "backbone_moves":len(main),
        "main_journey_digest":completed.digest,
        "all_climates_backbone_verified":tuple(weather_verified),
        "location_recovery_verified":tuple(recovery),
        "location_recovery_routes":tuple(recovery_routes),
        "location_recovery_count":len(recovery),
        "real_dead_ends":deadends,
        "return_edges":tuple(side_reverse[x] for x in side),
        "doubleback_witnesses":doublebacks[:12],
        "impractical_witnesses":tuple(impractical),
        "scenic_witnesses":tuple(scenic_witnesses[:12]),
        "secret_witnesses":tuple(secret_witnesses),
        "optional_shapes":tuple(sorted({shape for edge in edges
                                        for shape in edge.shapes})),
        "total_edges":len(edges),
        "guarantee_scope":(
            "Constructive all-weather backbone and replayed recovery from every "
            "normally reachable location; gameplay reset remains required after "
            "arbitrary resource/time/action exhaustion. Vehicle-specific physics "
            "and player enjoyment are not certified."),
    }
    return MazeCreation(request,world,traveller,MazeCertificate(
        **report,certificate_digest=_final_digest(report),
    ))


def recover_maze(
    creation:MazeCreation,history:tuple[str,...]=(),
)->dict:
    """Proof-directed recovery from the ACTUAL current original game state.

    Only zero-cost unconditional spine/return edges are considered. Their
    suffix is replayed *after* all real previous decisions, so depleted
    action/time limits are detected rather than papered over with a
    physically impossible "everything is fine" result.
    """
    if not isinstance(creation,MazeCreation):
        raise ValueError("current maze recovery requires a proven world")
    if not isinstance(history,tuple) or len(history)>MAX_HOPS or any(
            type(token) is not str or not 1<=len(token)<=48
            for token in history):
        raise ValueError("current original maze history exceeds playable bounds")
    state=experience(
        creation.world,creation.traveller,path=history,
    )
    start=state["world_position"]
    if start==creation.world.goal:
        return {
            "schema":SCHEMA,"current":start,"goal":creation.world.goal,
            "reachable_now":True,"next_move":None,
            "recovery_suffix":[],"remaining_actions":0,
            "reset_required":False,
            "proof":"actual already completed game-state journey",
        }
    from collections import deque
    protected={}
    for edge in creation.world.connections:
        if "spine" not in edge.shapes and "recovery" not in edge.shapes:
            continue
        if (edge.price!=0 or edge.fatigue!=0 or edge.fuel!=0 or
                edge.oxygen!=0 or edge.mana!=0 or edge.requires or
                edge.requires_one or edge.secret_token or
                edge.weather_any or edge.weather_none or edge.departures):
            raise ValueError("supposedly guaranteed maze return changed into a locked passage")
        protected.setdefault(edge.origin,[]).append(edge)
    queue=deque([(start,())])
    seen={start}
    safe=None
    while queue:
        here,steps=queue.popleft()
        if here==creation.world.goal:
            safe=steps
            break
        for edge in protected.get(here,()):
            if edge.destination not in seen:
                seen.add(edge.destination)
                queue.append((edge.destination,steps+(edge.id,)))
    if safe is None:
        raise ValueError("protected original maze goal is disconnected")
    try:
        original=replay(
            creation.world,history+safe,creation.traveller,
            objective="actual_player_state_recovery",
        )
        if not original.success:
            raise ValueError("maze recovery route did not finish")
        possible=True
    except ValueError:
        # A depleted 80-move/time budget cannot be repaired by pretending
        # to mint energy or rewind the clock. Restart restores the
        # constructively guaranteed original player state.
        possible=False
    return {
        "schema":SCHEMA,"current":start,"goal":creation.world.goal,
        "reachable_now":possible,
        "next_move":safe[0] if possible and safe else None,
        "recovery_suffix":list(safe) if possible else [],
        "remaining_actions":len(safe) if possible else 0,
        "reset_required":not possible,
        "proof":(
            "independent exact movement replay from current position"
            if possible else
            "restart required after resource, time or bounded action exhaustion"
        ),
    }


def verify_maze(creation:MazeCreation)->dict:
    """Never trust receipt claims; re-execute every route and climate."""
    if not isinstance(creation,MazeCreation):
        raise ValueError("original maze certification record missing")
    world,traveller,cert=creation.world,creation.traveller,creation.certificate
    validate_world(world)
    if cert.schema!=SCHEMA or cert.world_digest!=_fingerprint(world):
        raise ValueError("maze identity differs from claimed world")
    _bounded(creation.request)
    if (cert.source_seed!=creation.request.seed or
            cert.dimensions!=(creation.request.width,creation.request.height) or
            world.environment!=(creation.request.weather,)):
        raise ValueError("maze design configuration differs from its completion proof")
    # Regeneration is deliberately independent of the claimed certificate.
    # A changed door, missing dead end, shortened path, consumed clue or
    # reclassified scenic route cannot pass merely by updating its digest.
    original=build_maze(creation.request)
    if (asdict(world)!=asdict(original.world) or
            asdict(traveller)!=asdict(original.traveller) or
            asdict(cert)!=asdict(original.certificate)):
        raise ValueError("maze world, difficulty, topology or witnesses were modified")
    # No trust is placed in claimed certificates, including a source-only
    # graph with the same route labels but different gates or time costs.
    witnesses=(
        (cert.backbone,)+cert.location_recovery_routes+
        cert.doubleback_witnesses+cert.impractical_witnesses+
        cert.scenic_witnesses+
        cert.secret_witnesses
    )
    for trace in witnesses:
        journey=replay(world,trace,traveller)
        if not journey.success or journey.places[-1]!=world.goal:
            raise ValueError("maze route evidence does not reach the goal")
    if cert.all_climates_backbone_verified!=WEATHERS:
        raise ValueError("maze did not certify every supported environmental condition")
    for climate in cert.all_climates_backbone_verified:
        if climate not in WEATHERS:
            raise ValueError("maze claims unknown climate evidence")
        if not replay(replace(world,environment=(climate,)),
                      cert.backbone,traveller).success:
            raise ValueError("maze backbone no longer valid across weather")
    if len(cert.location_recovery_verified)!=len(world.places) or (
        set(cert.location_recovery_verified)!={x.id for x in world.places}
    ):
        raise ValueError("maze completion evidence omits a chamber")
    if cert.main_journey_digest!=replay(
            world,cert.backbone,traveller,
            objective="constructive_backbone").digest:
        raise ValueError("maze baseline winner digest changed")
    proof=asdict(cert)
    supplied_digest=proof.pop("certificate_digest")
    if supplied_digest!=_final_digest(proof):
        raise ValueError("maze completion certificate was altered")
    return {
        "schema":SCHEMA,"status":"constructively_complete",
        "rooms":len(world.places),"edges":len(world.connections),
        "all_climates":list(cert.all_climates_backbone_verified),
        "verified_winning_witnesses":len(witnesses),
        "claim":cert.guarantee_scope,
    }
