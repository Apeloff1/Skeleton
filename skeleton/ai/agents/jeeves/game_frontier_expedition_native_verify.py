"""Independent replay of candidate Godot 4 expedition observation streams.

This validates native-reported game transitions against the original Python
authoring runtime, source fingerprint, traveler capabilities and stamina/quest
rules. Output from an engine process is data, never an approval, and a
synthetic fixture is not independent proof that Godot actually ran.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
import re
from typing import Mapping

from .game_frontier_expedition import (
    ExpeditionAction, ExpeditionEpisode, ExpeditionError,
    ExpeditionWorld, Traveler, _digest, _json,
)

SCHEMA = "skeleton.game.expedition_native_observation.v1"
PREFIX = "EXPEDITION_OBSERVATION "
_HEX = re.compile(r"^[0-9a-f]{64}$")
_MAX_LOG_BYTES = 4_000_000
_MAX_OBSERVATIONS = 4096


class NativeExpeditionError(ValueError):
    """The candidate native trace is partial, stale, forged or contradictory."""


def _json_unique(pairs):
    out={}
    for key,value in pairs:
        if key in out:
            raise NativeExpeditionError("duplicate JSON field in native observation")
        out[key]=value
    return out


def _decode(line: str) -> dict:
    if len(line.encode("utf-8"))>65_536:
        raise NativeExpeditionError("native observation exceeds bounded record size")
    try:
        payload=json.loads(
            line,object_pairs_hook=_json_unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                NativeExpeditionError("nonfinite native observation")
            ),
        )
    except NativeExpeditionError:
        raise
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise NativeExpeditionError("native observation has invalid JSON") from exc
    if type(payload) is not dict or set(payload)!={
        "schema","source_digest","world_digest","traveler_digest",
        "project_id","action","evidence","state","receipt_head",
        "native_authority",
    }:
        raise NativeExpeditionError("native observation has incomplete data")
    if payload["schema"]!=SCHEMA or payload["native_authority"]!=(
        "untrusted_native_candidate_for_independent_review"
    ):
        raise NativeExpeditionError("unsupported native source authority")
    if type(payload["action"]) is not str or payload["action"] not in {"spawn","travel","rest"}:
        raise NativeExpeditionError("native observation claims unimplemented action")
    if not isinstance(payload["state"],dict) or set(payload["state"])!={
        "position","stamina","health","seconds","visited",
        "flags","inventory","won","failed","actions",
    }:
        raise NativeExpeditionError("native state fields differ from gameplay contract")
    if not isinstance(payload["receipt_head"],str) or not _HEX.fullmatch(payload["receipt_head"]):
        raise NativeExpeditionError("native observation lacks bounded receipt")
    if type(payload["evidence"]) is not str or not 0<len(payload["evidence"])<=128:
        raise NativeExpeditionError("unbounded native action evidence")
    for field in ("flags","inventory","visited"):
        values=payload["state"][field]
        if (not isinstance(values,list) or len(values)>8192 or
                any(type(value) is not str or len(value)>128 for value in values)
                or len(set(values))!=len(values)):
            raise NativeExpeditionError("native game set is incomplete or duplicated")
    return payload


def _equivalent_state(native: dict,episode: ExpeditionEpisode,
                      traveler: Traveler) -> None:
    expected=episode.state()
    state=native["state"]
    if (state["position"]!=expected["position"]
            or type(state["stamina"]) is not int
            or state["stamina"]!=expected["stamina"]
            or type(state["health"]) is not int
            or state["health"]!=expected["health"]
            or type(state["won"]) is not bool or state["won"]!=expected["won"]
            or type(state["failed"]) is not bool
            or state["failed"]!=(expected["health"]<=0)
            or type(state["actions"]) is not int
            or state["actions"]!=expected["actions"]):
        raise NativeExpeditionError("native progression contradicts authored gameplay")
    seconds=state["seconds"]
    if (type(seconds) not in (float,int) or not math.isfinite(seconds)
            or abs(seconds-expected["seconds"])>0.0011):
        raise NativeExpeditionError("native traversal time differs from replay")
    if (set(state["visited"])!=set(expected["visited"])
            or set(state["inventory"])!=set(expected["inventory"])
            or set(state["flags"])!=(set(expected["flags"])|set(traveler.equipment))):
        raise NativeExpeditionError("native quest, source or inventory continuity mismatch")


def inspect_native_expedition_trace(
    stdout: str, world: ExpeditionWorld, traveler: Traveler, *,
    expected_complete: bool = False,
) -> dict:
    """Audit every exact candidate native game action against actual source.

    Results are explicitly untrusted as engine-origin proof until independently
    linked to the tested Godot executable, captured process and signed job.
    """
    if not isinstance(world, ExpeditionWorld) or not isinstance(traveler, Traveler):
        raise NativeExpeditionError("typed original world/player sources required")
    if type(expected_complete) is not bool:
        raise NativeExpeditionError("completion policy must be explicit")
    if not isinstance(stdout,str) or len(stdout.encode("utf-8"))>_MAX_LOG_BYTES:
        raise NativeExpeditionError("native log exceeds bounded source budget")
    records=[]
    for line in stdout.splitlines():
        if line.startswith(PREFIX):
            records.append(_decode(line[len(PREFIX):]))
            if len(records)>_MAX_OBSERVATIONS:
                raise NativeExpeditionError("native game history exceeds replay budget")
    if not records:
        raise NativeExpeditionError("native process emitted no game observation")
    episode=ExpeditionEpisode(world,traveler)
    seen=set()
    expected_source=(
        world.source_digest,world.digest,episode.traveler_digest,world.project_id
    )
    prior=None
    for index,record in enumerate(records):
        if tuple(record[k] for k in (
            "source_digest","world_digest","traveler_digest","project_id",
        ))!=expected_source:
            raise NativeExpeditionError("native game uses foreign source or player")
        action=record["action"]
        evidence=record["evidence"]
        if index==0:
            if action!="spawn" or evidence!="start":
                raise NativeExpeditionError("gameplay history lacks initial spawn")
            expected_head=sha256((
                world.source_digest+":"+world.project_id+":"+world.arrival
            ).encode()).hexdigest()
            if record["receipt_head"]!=expected_head:
                raise NativeExpeditionError("native spawn receipt does not bind original game")
        else:
            if action=="spawn":
                raise NativeExpeditionError("native game restarted within one session")
            try:
                episode.step(ExpeditionAction(
                    "travel" if action=="travel" else "rest",
                    evidence if action=="travel" else "",
                ))
            except ExpeditionError as exc:
                raise NativeExpeditionError(
                    "native action not playable on original source graph"
                ) from exc
            if action=="rest" and evidence!=episode.position:
                raise NativeExpeditionError("native rest recorded at unrelated location")
        if record["receipt_head"] in seen:
            raise NativeExpeditionError("native game receipt repeated without new action")
        seen.add(record["receipt_head"])
        _equivalent_state(record,episode,traveler)
        prior=record["receipt_head"]
    if expected_complete and not episode.won:
        raise NativeExpeditionError("native playthrough never reached destination")
    report={
        "schema":"skeleton.game.expedition_native_replay_audit.v1",
        "world_digest":world.digest,
        "traveler_digest":episode.traveler_digest,
        "source_digest":world.source_digest,
        "observations":len(records),
        "executed_actions":len(episode.actions),
        "won":episode.won,
        "replay_final_state_digest":_digest(episode.state()),
        "replay_receipt_head":episode._head,
        "native_candidate_receipt_head":prior,
        "device_location_used":False,
        "verified_source_gameplay":True,
        "native_process_origin_independently_attested":False,
        "authority":"candidate_trace_replayed_against_original_game_logic",
    }
    return {**report,"receipt_digest":sha256(_json(report)).hexdigest()}
