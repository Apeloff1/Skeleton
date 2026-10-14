"""Deterministic, measured variants of original native Sokoban levels.

The original author's hand-designed levels provide a known-solvable baseline.
This module adds novel route constraints and alternate safe floor geometry,
then requires the existing exact BFS solver to prove every accepted mutation.
No external ROM, map, imagery, language model or game database is accessed.

Difficulty changes search/maze complexity; it is not a guarantee of human
perceived difficulty and never changes the original win condition.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from hashlib import sha256
from typing import Callable
import json

MAX_TRIALS = 16
MAX_WALLS = 5

@dataclass(frozen=True)
class VariantEvidence:
    schema: str
    requested_walls: int
    added_walls: int
    base_solution_moves: int
    chosen_solution_moves: int
    examined_states: int
    base_digest: str
    chosen_digest: str
    search_trials: int
    difficulty: int
    status: str


def _digest(rows:tuple[str,...])->str:
    return sha256("\n".join(rows).encode("ascii")).hexdigest()


def _candidates(base:tuple[str,...],seed:int,stage:int)->list[tuple[int,int]]:
    """Stable scored floor cells, never a global nondeterministic RNG."""
    width=len(base[0])
    height=len(base)
    prohibited=set()
    for y,row in enumerate(base):
        for x,tile in enumerate(row):
            if tile in "@$o":
                for dy in (-1,0,1):
                    for dx in (-1,0,1):
                        prohibited.add((x+dx,y+dy))
    cells=[]
    for y in range(1,height-1):
        for x in range(1,width-1):
            if base[y][x]=="." and (x,y) not in prohibited:
                material=f"{seed}:{stage}:{x}:{y}:original_homebrew".encode("ascii")
                cells.append((sha256(material).hexdigest(),x,y))
    return [(x,y) for _,x,y in sorted(cells)]


def _edit(base:tuple[str,...],positions:list[tuple[int,int]])->tuple[str,...]:
    data=[list(row) for row in base]
    for x,y in positions:
        if data[y][x]!=".":
            raise ValueError("original route obstacle would destroy a game object")
        data[y][x]="#"
    return tuple("".join(row) for row in data)


def vary_original_level(
    base:tuple[str,...], *,
    seed:int,stage:int,difficulty:int,
    solve:Callable[[tuple[str,...]],tuple[str,int]],
) ->tuple[tuple[str,...],VariantEvidence]:
    """Optimize generated obstacles for new but solvable original game routes.

    All candidates use the exact authoritative BFS solver; failed candidates
    are ignored. Never returns unproved geometry. Baseline is a valid fallback,
    not a false claim that novel terrain was produced.
    """
    if type(seed) is not int or not 0<=seed<=0xffffffff:
        raise ValueError("variant seed must be uint32")
    if type(stage) is not int or not 0<=stage<8:
        raise ValueError("variant stage must fit native campaign")
    if type(difficulty) is not int or not 1<=difficulty<=10:
        raise ValueError("variant challenge must be 1 to 10")
    original_moves,original_states=solve(base)
    wanted = min(MAX_WALLS,max(0,(difficulty-2)//2))
    options=_candidates(base,seed,stage)
    best=base
    path=original_moves
    states=original_states
    tried=0
    best_score=(-1, -1)
    if wanted>0 and len(options)>=wanted:
        # Candidate windows explore distinct spatial distributions at bounded
        # cost. Zero global state, no randomized seed recurrence, no unbounded
        # Sudoku-like backtracking.
        for trial in range(min(MAX_TRIALS,len(options))):
            chosen=[options[(trial+i*7)%len(options)] for i in range(wanted)]
            if len(set(chosen))!=wanted:
                continue
            candidate=_edit(base,chosen)
            tried+=1
            try:
                solution,visited=solve(candidate)
            except ValueError:
                continue
            # Enforce actual solvability, exact path capacity and avoid
            # degenerating a difficult requested board into 1-step content.
            if not solution or len(solution)>350:
                continue
            score=(len(solution),min(visited,100_000))
            if score>best_score:
                best_score=score
                best=candidate
                path=solution
                states=visited
    actual=sum(a!=b for a,b in zip("".join(base),"".join(best)))
    return best, VariantEvidence(
        schema="skeleton.ai.dragon.original_puzzle_variant.v1",
        requested_walls=wanted,added_walls=actual,
        base_solution_moves=len(original_moves),
        chosen_solution_moves=len(path),
        examined_states=states,
        base_digest=_digest(base),chosen_digest=_digest(best),
        search_trials=tried,difficulty=difficulty,
        status="solvable_variant" if actual else "solvable_baseline",
    )


def variant_report(artifact:VariantEvidence)->dict:
    return asdict(artifact)
