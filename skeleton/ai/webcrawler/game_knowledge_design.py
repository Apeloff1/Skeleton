"""Knowledge-guided original 2D game design and deterministic level synthesis.

Produces original specifications and traversable levels, not copies of
research game assets. Retrieved passages may influence mechanic selection,
while numeric defaults are documented *design choices*, not factual claims.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from hashlib import sha256
from math import sqrt
import json
import random

from .game_knowledge_index import GameKnowledgeIndex, GameKnowledgeHit

_DEPEND = {
    "jump": ("movement","collision"),
    "double_jump": ("jump",),
    "dash": ("movement","collision"),
    "camera": ("movement",),
    "combat": ("collision",),
    "enemy_ai": ("collision","movement"),
    "collectible": ("collision",),
    "checkpoint": ("collision",),
    "puzzle": ("collision",),
    "platform": ("jump",),
    "inventory": ("collectible",),
}
_PRESETS={
    "platformer": ("movement","collision","jump","camera","collectible","enemy_ai","checkpoint"),
    "action": ("movement","collision","combat","enemy_ai","camera","collectible"),
    "puzzle": ("movement","collision","puzzle","collectible"),
    "exploration": ("movement","collision","camera","collectible","checkpoint"),
}
_DESIGN={
    "move_speed": 4.5,
    "jump_speed": 15.0,
    "gravity": 25.,
    "acceleration": 32.,
    "friction": 26.,
    "enemy_speed": 1.2,
    "max_lives": 3.,
}
_WALL="#"
_EMPTY="."


@dataclass(frozen=True)
class GameBlueprint:
    title: str
    genre: str
    engine: str
    mechanics: tuple[str,...]
    width: int
    height: int
    grid: tuple[str,...]
    physics: tuple[tuple[str,float],...]
    source_evidence: tuple[str,...]
    seed: int
    fingerprint: str

    def physics_dict(self) -> dict[str,float]:
        return dict(self.physics)


@dataclass(frozen=True)
class LevelMetrics:
    shortest_route: int
    hazards: int
    enemies: int
    collectibles: int
    estimated_difficulty: float
    playable: bool


# 21: Assemble original blueprint from knowledge retrieval and requested genre.
def propose_game_blueprint(
    index: GameKnowledgeIndex, *, title: str, genre: str,
    engine: str = "web", seed: int = 0,
    width: int = 32, height: int = 14,
) -> GameBlueprint:
    if genre not in _PRESETS:
        raise ValueError("unsupported playable genre")
    if engine not in ("web","phaser","godot","unity"):
        raise ValueError("unsupported design target")
    if not isinstance(title,str) or not 1<=len(title.strip())<=80:
        raise ValueError("invalid game title")
    if not isinstance(seed,int) or not 0<=seed<=2**32-1:
        raise ValueError("invalid game seed")
    if not 16<=width<=128 or not 10<=height<=64 or width*height>4096:
        raise ValueError("invalid level dimensions")
    hits=index.search(f"{genre} movement collision game design",limit=12)
    candidates=select_game_mechanics(hits,genre=genre)
    mechanics=resolve_mechanic_dependencies(candidates)
    mechanics=budget_game_mechanics(mechanics,max_mechanics=12)
    grid=design_level_geometry(width,height,seed=seed,genre=genre)
    physics=design_player_physics(index,genre=genre)
    ids=tuple(sorted({h.passage_id for h in hits}))
    digest=sha256(json.dumps(
        [title,genre,engine,mechanics,grid,physics,ids,seed],
        separators=(",",":"),ensure_ascii=True,
    ).encode()).hexdigest()
    return GameBlueprint(title,genre,engine,mechanics,width,height,grid,
                         physics,ids,seed,digest)


# 22: Prefer mechanics for which retrieved implementation context exists.
def select_game_mechanics(
    evidence: tuple[GameKnowledgeHit,...], *, genre: str,
) -> tuple[str,...]:
    if genre not in _PRESETS:
        raise ValueError("unsupported mechanic genre")
    base=list(_PRESETS[genre])
    combined=" ".join(h.text.casefold() for h in evidence)
    for name, synonyms in (
        ("dash",("dash", "burst movement")),
        ("double_jump",("double jump","air jump")),
        ("inventory",("inventory","item slots")),
        ("puzzle",("pressure plate","puzzle")),
    ):
        if any(word in combined for word in synonyms) and name not in base:
            base.append(name)
    return tuple(base)


# 23: Correct dependency order, reject impossible/cyclic mechanic graphs.
def resolve_mechanic_dependencies(
    requested: tuple[str,...],
    dependencies: dict[str,tuple[str,...]] | None = None,
) -> tuple[str,...]:
    depends=_DEPEND if dependencies is None else dependencies
    state:dict[str,int]={}
    ordered=[]
    def visit(name: str) -> None:
        if state.get(name)==1:
            raise ValueError("cyclic mechanic dependency")
        if state.get(name)==2:
            return
        if not isinstance(name,str) or not name or len(name)>64:
            raise ValueError("invalid mechanic identity")
        if len(state)>128:
            raise ValueError("mechanic graph capacity exceeded")
        state[name]=1
        for dep in sorted(depends.get(name,())):
            visit(dep)
        state[name]=2
        ordered.append(name)
    for name in requested:
        visit(name)
    return tuple(ordered)


# 24: Select coherent subsets without deleting mandatory prerequisites.
def budget_game_mechanics(
    mechanics: tuple[str,...], *, max_mechanics: int,
) -> tuple[str,...]:
    if not 2<=max_mechanics<=64:
        raise ValueError("invalid mechanics budget")
    keep=[]
    for mechanic in mechanics:
        deps=resolve_mechanic_dependencies((mechanic,))
        if len(set(keep)|set(deps))<=max_mechanics:
            for item in deps:
                if item not in keep:
                    keep.append(item)
    return tuple(keep)


# 25: Derive bounded controllable tuning from source examples; defaults are design values.
def design_player_physics(
    index: GameKnowledgeIndex, *, genre: str,
) -> tuple[tuple[str,float],...]:
    if genre not in _PRESETS:
        raise ValueError("unknown physics genre")
    values=dict(_DESIGN)
    # Tuning from web sources requires independent validation. We do not
    # silently elevate a scraped number to a physics command. Instead use
    # grounded examples to set a conservative *reviewable* game design range.
    rows=index.db.execute("""SELECT unit, value FROM game_knowledge_parameters
       WHERE passage_id IN (SELECT passage_id FROM game_knowledge_passages
                            WHERE active=1) LIMIT 1000""").fetchall()
    frame_values=[float(v) for unit,v in rows if unit.casefold() in ("fps",)
                  and 20 <= float(v) <= 240]
    if frame_values:
        values["research_fps_reference"]=sorted(frame_values)[len(frame_values)//2]
    if genre=="puzzle":
        values["move_speed"]=3.
    elif genre=="action":
        values["move_speed"]=5.5
    return tuple(sorted(values.items()))


# 26: Generate original geometry with guaranteed unobstructed primary route.
def design_level_geometry(
    width: int, height: int, *, seed: int, genre: str = "platformer",
) -> tuple[str,...]:
    if not 16<=width<=128 or not 10<=height<=64 or width*height>4096:
        raise ValueError("invalid level size")
    if genre not in _PRESETS:
        raise ValueError("invalid level genre")
    rng=random.Random(seed)
    grid=[[ _EMPTY for _ in range(width)] for _ in range(height)]
    for x in range(width):
        grid[height-1][x]=_WALL
    # Never block the main walkway at y=h-2.
    for x in range(4,width-4,6):
        # Rise of the default jump controller exceeds this vertical gap.
        ledge_y=height-4-rng.randrange(0,2)
        span=min(3+rng.randrange(0,2),width-x-2)
        for col in range(x,x+span):
            grid[ledge_y][col]=_WALL
    grid[height-2][1]="P"
    grid[height-2][width-2]="G"
    return tuple("".join(row) for row in grid)


# 27: Determine physically reachable jump intervals from actual controller numbers.
def estimate_jump_reach(
    *, speed: float, jump_speed: float, gravity: float,
    delta_y: float = 0.0,
) -> tuple[float,float]:
    if speed<=0 or jump_speed<=0 or gravity<=0:
        raise ValueError("invalid jump controller")
    apex=jump_speed**2/(2*gravity)
    if delta_y>apex:
        return 0.,apex
    # Landing at starting elevation has total flight time 2*v/g.
    travel=2*jump_speed/gravity*speed
    return round(travel,4),round(apex,4)


# 28: Route-finding on a level's walkable grid (independent of rendering).
def find_level_route(
    grid: tuple[str,...], *, start: tuple[int,int] | None = None,
    goal: tuple[int,int] | None = None,
) -> tuple[tuple[int,int],...]:
    if not grid or len({len(x) for x in grid})!=1:
        raise ValueError("invalid level grid")
    height,width=len(grid),len(grid[0])
    if width*height>10000:
        raise ValueError("level route budget exceeded")
    def locate(symbol):
        return next(((x,y) for y,row in enumerate(grid)
                     for x,ch in enumerate(row) if ch==symbol),None)
    start=start or locate("P")
    goal=goal or locate("G")
    if start is None or goal is None:
        return ()
    q=deque([start])
    parent={start:None}
    while q:
        x,y=q.popleft()
        if (x,y)==goal:
            result=[]
            cursor=goal
            while cursor is not None:
                result.append(cursor)
                cursor=parent[cursor]
            return tuple(reversed(result))
        for dx,dy in ((0,-1),(-1,0),(1,0),(0,1)):
            xx,yy=x+dx,y+dy
            if not(0<=xx<width and 0<=yy<height) or grid[yy][xx]=="#":
                continue
            if (xx,yy) not in parent:
                parent[(xx,yy)]=(x,y)
                q.append((xx,yy))
    return ()


# 29: Populate original play objects without destroying guaranteed route.
def populate_game_level(
    blueprint: GameBlueprint, *, pickups: int = 7, enemies: int = 3,
) -> GameBlueprint:
    if not 0<=pickups<=50 or not 0<=enemies<=20:
        raise ValueError("invalid encounter budget")
    grid=[list(r) for r in blueprint.grid]
    rng=random.Random(blueprint.seed+381)
    # Scatter on safe ground corridor; enemies can be jumped over in runtime.
    spots=list(range(3,blueprint.width-3))
    rng.shuffle(spots)
    for x in spots[:pickups]:
        if grid[blueprint.height-2][x]==".":
            grid[blueprint.height-2][x]="C"
    for x in spots[pickups:pickups+enemies]:
        if grid[blueprint.height-2][x]==".":
            grid[blueprint.height-2][x]="E"
    updated=tuple("".join(r) for r in grid)
    digest=sha256(json.dumps(
        [blueprint.fingerprint,updated],separators=(",",":"),
    ).encode()).hexdigest()
    return replace(blueprint,grid=updated,fingerprint=digest)


# 30: Compute challenge measures from the generated game, not invented evaluations.
def analyze_level_playability(blueprint: GameBlueprint) -> LevelMetrics:
    route=find_level_route(blueprint.grid)
    enemies=sum(r.count("E") for r in blueprint.grid)
    items=sum(r.count("C") for r in blueprint.grid)
    hazards=sum(r.count("^") for r in blueprint.grid)
    playable=bool(route) and len(route)>=2
    # Difficulty is a design heuristic, not a result of real player testing.
    challenge=min(1.,(enemies*2+hazards*3+len(route)/12)/
                  max(8,blueprint.width))
    return LevelMetrics(len(route)-1 if route else -1,hazards,enemies,items,
                        round(challenge,4),playable)
