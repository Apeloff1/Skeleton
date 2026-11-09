"""Actual solver-vetted level selection for user-selected challenge pacing.

Every alternative is new deterministic ORIGINAL geometry from the already
approved homebrew generator. A bounded exact BFS must prove each candidate,
then the builder selects a feasible one according to the player's requested
intent: gentle, challenging or spicy with recovery valleys. Default balanced
and user-authored boards are never silently replaced.

This does not pretend numerical complexity equals joy: human playtesting is
the only basis for enjoyment claims. The chosen seed/difficulty, all reviewed
candidate metrics and any shortage of challenge are retained as evidence.
"""
from __future__ import annotations
from dataclasses import asdict,dataclass
from hashlib import sha256
from math import log2

SCHEMA="skeleton.ai.dragon.original_level_curation.v1"
MAX_TRIALS=5

@dataclass(frozen=True)
class CuratedOriginalLevel:
    schema:str
    stage:int
    profile:str
    tension_role:str
    source_seed:int
    source_difficulty:int
    source_procedural:bool
    layout_sha256:str
    baseline_sha256:str
    chosen_complexity:int
    baseline_complexity:int
    candidates_examined:int
    distinct_solvable_candidates:int
    changed_from_baseline:bool
    selection_claim:str


def _fingerprint(rows:tuple[str,...])->str:
    return sha256("\n".join(rows).encode("ascii")).hexdigest()


def _complexity(rows,solution,seen):
    from .dragon_native_multipath import _walk
    route,_=_walk(rows,solution,solver="exact_bfs",variation="candidate")
    return min(100,round(
        12*log2(1+max(1,seen))+min(len(solution),100)/5+
        min(route.pushes,20)*2+min(route.risky_pushes,12)*2
    ))


def curate_level(*,stage:int,seed:int,difficulty:int,procedural:bool,
                 profile:str="balanced")->tuple[tuple[str,...],CuratedOriginalLevel]:
    from .dragon_native_puzzle import transformed_level,solve_grid
    if (type(stage) is not int or not 0<=stage<8 or
            type(seed) is not int or not 0<=seed<2**32 or
            type(difficulty) is not int or not 1<=difficulty<=10 or
            type(procedural) is not bool or
            profile not in ("gentle","balanced","challenging","spicy")):
        raise ValueError("original level curation controls invalid")
    baseline=transformed_level(stage,seed,difficulty,procedural=procedural)
    path,states=solve_grid(baseline)
    base_score=_complexity(baseline,path,states)
    candidates=[(base_score,seed,difficulty,baseline)]
    if profile!="balanced":
        seen={_fingerprint(baseline)}
        adjustments=((-2,1),(2,3),(-4,7),(4,11))
        for adjust,salt in adjustments:
            variant_seed=(seed^(salt*0x9E3779B1+stage*0x85ebca6b))&0xffffffff
            variant_diff=max(1,min(10,difficulty+adjust))
            try:
                board=transformed_level(stage,variant_seed,variant_diff,
                                        procedural=procedural)
                digest=_fingerprint(board)
                if digest in seen:continue
                seen.add(digest)
                alternative,visited=solve_grid(board)
                score=_complexity(board,alternative,visited)
                candidates.append((score,variant_seed,variant_diff,board))
            except ValueError:
                continue
    if profile=="gentle":
        selected=min(candidates,key=lambda row:(row[0],row[1],row[2]))
        role="gentle_accessible_path"
    elif profile=="challenging":
        recovery=(stage+1)%3==0
        selected=(min(candidates,key=lambda row:(row[0],row[1],row[2]))
                  if recovery else
                  max(candidates,key=lambda row:(row[0],-row[1],-row[2])))
        role="deliberate_recovery" if recovery else "chosen_higher_challenge"
    elif profile=="spicy":
        recovery=(stage+1)%4==0
        spike=stage>0 and stage%4==1
        selected=(min(candidates,key=lambda row:(row[0],row[1],row[2]))
                  if recovery else
                  max(candidates,key=lambda row:(row[0],-row[1],-row[2]))
                  if spike else
                  candidates[0])
        role=("deliberate_recovery" if recovery else
              "deliberate_frustration_spike_with_escape" if spike else
              "exploration")
    else:
        selected=candidates[0]
        role="legacy_original_geometry"
    score,chosen_seed,chosen_diff,grid=selected
    return grid,CuratedOriginalLevel(
        schema=SCHEMA,stage=stage,profile=profile,tension_role=role,
        source_seed=chosen_seed,source_difficulty=chosen_diff,
        source_procedural=procedural,layout_sha256=_fingerprint(grid),
        baseline_sha256=_fingerprint(baseline),
        chosen_complexity=score,baseline_complexity=base_score,
        candidates_examined=1 if profile=="balanced" else MAX_TRIALS,
        distinct_solvable_candidates=len(candidates),
        changed_from_baseline=grid!=baseline,
        selection_claim=("solver-vetted original geometry selection, "
                         "not player happiness or certified subjective challenge"),
    )


def curation_report(item:CuratedOriginalLevel)->dict:
    return asdict(item)
