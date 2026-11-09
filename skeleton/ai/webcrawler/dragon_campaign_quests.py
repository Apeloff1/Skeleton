"""Original native quest-encounter compiler for multi-stage games.

Real game objectives (key -> door/portal, chest, caretaker, guardian) are
placed in spawn-reachable locations of an actual generated 2D map. The
quest graph is deterministic, bounded, and mechanically executable by the
native SDL engine. Completeness checks are static route/progression checks,
not proof that a human beat the encounter.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass,asdict
from hashlib import sha256
import json
from .dragon_game_blueprints import W,H,PRNG

QUEST_MODES=frozenset(("adventure","dungeon","tactics"))
BLOCKED=frozenset("#^~")
QUEST_SYMBOLS=frozenset(("K","D","C","N","B"))

@dataclass(frozen=True)
class QuestPlacement:
    chapter:int
    mode:str
    gate_requires_key:bool
    chests:int
    caretakers:int
    guardians:int
    key_locations:tuple[tuple[int,int],...]
    door_locations:tuple[tuple[int,int],...]
    guardian_locations:tuple[tuple[int,int],...]
    evidence_hash:str
    accessible_without_key:bool
    notes:tuple[str,...]

def _area(grid:list[list[str]],start:tuple[int,int],*,locked:bool)->set[tuple[int,int]]:
    q=deque((start,))
    reached={start}
    while q:
        x,y=q.popleft()
        for nx,ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
            if (nx,ny) in reached or not(0<=nx<W and 0<=ny<H):
                continue
            c=grid[ny][nx]
            if c in BLOCKED or (locked and c=="D"):
                continue
            reached.add((nx,ny));q.append((nx,ny))
    return reached

def place_quests(grid:list[list[str]],*,rng:PRNG,chapter:int,mode:str,
                 start:tuple[int,int],goal:tuple[int,int])->QuestPlacement:
    if not isinstance(rng,PRNG) or not 0<=chapter<8:
        raise ValueError("invalid native quest seed or chapter")
    if len(grid)!=H or any(len(row)!=W for row in grid):
        raise ValueError("quest source map dimensions invalid")
    if mode not in ("arena","platform","adventure","dungeon","tactics","racer"):
        raise ValueError("invalid engine quest mode")
    # Landmarks remain separate from spawn/exit and all collectible locations.
    candidates=[(x,y) for x,y in sorted(_area(grid,start,locked=False))
                if grid[y][x]=="." and
                min(abs(x-start[0])+abs(y-start[1]),
                    abs(x-goal[0])+abs(y-goal[1]))>=3]
    def take(*,towards:tuple[int,int]|None=None)->tuple[int,int]|None:
        if not candidates:return None
        # Order biases role placement by distance; deterministic shuffle is
        # applied only among the best few positions.
        if towards:
            ranked=sorted(candidates,key=lambda pos:(
                abs(pos[0]-towards[0])+abs(pos[1]-towards[1]),pos))
            loc=ranked[rng.pick(min(5,len(ranked)))]
        else:
            loc=candidates[rng.pick(len(candidates))]
        candidates.remove(loc)
        return loc
    key_locations=[];door_locations=[];boss_locations=[]
    chests=caretakers=0
    if mode in QUEST_MODES:
        spot=take()
        if spot:
            grid[spot[1]][spot[0]]="C";chests=1
        if chapter>=1:
            # Door near goal is a meaningful lock; the key is put in the
            # spawn-accessible region when doors are treated as solid.
            door=take(towards=goal)
            if door:grid[door[1]][door[0]]="D";door_locations.append(door)
            areas=_area(grid,start,locked=True)
            keys=[loc for loc in candidates if loc in areas]
            if keys:
                k=keys[rng.pick(len(keys))]
                candidates.remove(k);grid[k[1]][k[0]]="K";key_locations.append(k)
            elif door:
                grid[door[1]][door[0]]="."
                door_locations.clear()
        if chapter>=2:
            boss=take(towards=goal)
            if boss:
                grid[boss[1]][boss[0]]="B";boss_locations.append(boss)
        if mode=="adventure" and chapter>=2:
            friend=take(towards=start)
            if friend:
                grid[friend[1]][friend[0]]="N";caretakers=1
    # A key-gated chapter must be solvable without passing the door to obtain
    # the key. Otherwise the generation is rejected as a soft lock.
    without=_area(grid,start,locked=True)
    accessible=all(k in without for k in key_locations)
    if not accessible:raise ValueError("quest key is behind a locked gate")
    if bool(door_locations)!=bool(key_locations):
        raise ValueError("a lock has no accessible key")
    symbols=[grid[y][x] for y in range(H) for x in range(W)]
    if any(s not in ".#^*GE~=+DSKCNB" for s in symbols):
        raise ValueError("invalid quest terrain")
    evidence={
        "chapter":chapter,"mode":mode,
        "doors":door_locations,"keys":key_locations,"bosses":boss_locations,
        "chests":chests,"friends":caretakers,
        "key_without_gate":accessible,
    }
    checksum=sha256(json.dumps(evidence,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return QuestPlacement(chapter,mode,bool(key_locations),chests,caretakers,
                          len(boss_locations),tuple(key_locations),
                          tuple(door_locations),tuple(boss_locations),
                          checksum,accessible,
                          ("Static pre-gate key reachability only; combat unverified",))

def quest_record(q:QuestPlacement)->dict:
    return asdict(q)
