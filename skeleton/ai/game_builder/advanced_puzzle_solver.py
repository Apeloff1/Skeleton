"""Bounded, independent proof search for user-authored original puzzle scenes.

A complete search can prove a small scene has no solution. Search limits
cannot: budget exhaustion is 'unproven', never misrepresented as impossible.
The proof always replays the final answer through the authoritative engine.
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from hashlib import sha256
import json
from typing import Mapping

from .advanced_gameplay_runtime import run_advanced_session, verify_advanced_session
from .advanced_genre_engines import (
    GenreActionError, apply_genre_scene, puzzle_start, puzzle_step,
)
from .advanced_level_scenes import validate_advanced_scene, SceneError
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.advanced_puzzle_proof.v1"
ACTIONS=("north","south","east","west","interact","wait")
MAX_STATES=20000
MAX_DEPTH=96


def _identity(state):
    return (
        tuple(state["player"]),
        tuple(sorted(map(tuple,state["crates"]))),
        tuple(sorted(map(tuple,state["switches_on"]))),
        tuple(sorted(map(tuple,state["powered_nodes"]))),
        state["phase"],state["portal_visited"],
    )


def _digest(data):
    return sha256(json.dumps(data,sort_keys=True,separators=(",",":"),
                             ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def solve_advanced_puzzle(scene: Mapping[str,object],
                          settings: Mapping[str,object]|None = None,
                          *, max_states: int = MAX_STATES,
                          max_depth: int = MAX_DEPTH) -> dict:
    if type(max_states) is not int or not 1<=max_states<=MAX_STATES:
        raise SceneError("solver node bound violates reviewed scene search budget")
    if type(max_depth) is not int or not 1<=max_depth<=MAX_DEPTH:
        raise SceneError("solver depth violates original gameplay transcript budget")
    if type(scene) is not dict or scene.get("editor")!="puzzle":
        raise SceneError("bounded proof search applies to original puzzle scenes only")
    doc=validate_advanced_scene(scene,settings)
    config=make_editor_document("puzzle",settings)["settings"]
    initial=puzzle_start(config,doc["seed"])
    apply_genre_scene("puzzle",initial,doc["layout"])
    initial["history"]=[]
    initial["undo_available"]=0
    search_cfg={**config,"undo_depth":0}
    queue=deque([(initial,())])
    known={_identity(initial)}
    processed=0
    cutoff=False
    solution=None
    while queue and processed < max_states:
        current,path=queue.popleft()
        processed+=1
        if current["finished"]:
            solution=path
            break
        if len(path)>=max_depth:
            cutoff=True
            continue
        for action in ACTIONS:
            next_state=deepcopy(current)
            try:
                puzzle_step(next_state,search_cfg,action)
            except GenreActionError:
                continue
            identity=_identity(next_state)
            if identity in known:
                continue
            known.add(identity)
            queue.append((next_state,path+(action,)))
    if solution is not None:
        witness=run_advanced_session("puzzle",config,solution,
                                     seed=doc["seed"],scene=doc)
        if not witness["state"]["finished"] or not verify_advanced_session(witness,config):
            raise SceneError("candidate puzzle proof did not pass independent replay")
        status="solved"
        source={"commands":list(solution),"gameplay_digest":witness["digest"],
                "verified_by_authoritative_replay":True}
    elif queue or cutoff:
        status="unproven_search_budget"
        source={"commands":[],"gameplay_digest":None,
                "verified_by_authoritative_replay":False}
    else:
        status="unsatisfiable_exhaustive"
        source={"commands":[],"gameplay_digest":None,
                "verified_by_authoritative_replay":False}
    result={
        "schema":SCHEMA,"scene_digest":doc["digest"],
        "settings_digest":doc["settings_digest"],
        "status":status,"search_state_count":processed,
        "unique_states_discovered":len(known),
        "max_search_states":max_states,"max_search_depth":max_depth,
        "shortest_steps":len(solution) if solution is not None else None,
        **source,
        "publication_approved":False,
        "hardware_certified":False,
    }
    return {**result,"digest":_digest(result)}


__all__=["SCHEMA","MAX_STATES","MAX_DEPTH","solve_advanced_puzzle"]
