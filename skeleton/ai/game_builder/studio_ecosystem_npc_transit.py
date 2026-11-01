"""Source-replayed, operator-estimated NPC transit feasibility between authored sites.

This checks logical travel constraints, not physical distances, engine movement,
or measured elapsed time. Unknown routes are conflicts, never free travel.
"""
from __future__ import annotations

from heapq import heappop, heappush
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _ticks, _write_all,
    compile_scene_schedule, MAX_TOTAL_TICKS,
)
from .studio_ecosystem_temporal_windows import (
    replay_temporal_windows, compile_temporal_playable,
)

SCHEMA = "skeleton.game_builder.studio_npc_transit.v1"
PROMPT = "plan source-bound npc transit estimates"
FILENAME = "npc_transit.json"
MAX_EDGES = 256
MAX_SITES = 64
MAX_BYTES = 256 * 1024


def _validate_graph(graph: object, sites: set[str]) -> dict[str, object]:
    if (type(graph) is not dict or set(graph) != {"edges"}
            or type(graph["edges"]) is not list
            or len(graph["edges"]) > MAX_EDGES or len(sites) > MAX_SITES):
        raise StudioQuestError("invalid bounded NPC transit graph")
    if len(_canonical(graph)) > 32768:
        raise StudioQuestError("NPC transit graph exceeds authoring budget")
    seen: set[tuple[str, str]] = set()
    for edge in graph["edges"]:
        if (type(edge) is not dict
                or set(edge) != {"from_site", "to_site", "ticks"}
                or type(edge["from_site"]) is not str
                or type(edge["to_site"]) is not str
                or edge["from_site"] not in sites or edge["to_site"] not in sites
                or edge["from_site"] == edge["to_site"]):
            raise StudioQuestError("NPC transit edge must join distinct authored sites")
        _ticks(edge["ticks"], "NPC transit edge", maximum=MAX_TOTAL_TICKS)
        key = (edge["from_site"], edge["to_site"])
        if key in seen:
            raise StudioQuestError("duplicate directed NPC transit edge")
        seen.add(key)
    return graph


def _shortest(graph: dict[str, object], origin: str,
              destination: str) -> tuple[int, list[str]] | None:
    if origin == destination:
        return (0, [origin])
    edges: dict[str, list[tuple[str, int]]] = {}
    for item in graph["edges"]:
        edges.setdefault(item["from_site"], []).append(
            (item["to_site"], item["ticks"]))
    for values in edges.values():
        values.sort(key=lambda pair: (pair[0], pair[1]))
    # Lexical path tie-break makes identical authored graphs replay identically.
    frontier: list[tuple[int, tuple[str, ...], str]] = [(0, (origin,), origin)]
    best: dict[str, tuple[int, tuple[str, ...]]] = {origin: (0, (origin,))}
    while frontier:
        ticks, path, here = heappop(frontier)
        if best[here] != (ticks, path):
            continue
        if here == destination:
            return ticks, list(path)
        for neighbor, cost in edges.get(here, []):
            total = ticks + cost
            if total > MAX_TOTAL_TICKS:
                continue
            candidate = (total, path + (neighbor,))
            if neighbor not in best or candidate < best[neighbor]:
                best[neighbor] = candidate
                heappush(frontier, (total, candidate[1], neighbor))
    return None


def compile_npc_transit(
    documents: Mapping[str, Any], temporal_receipt: object,
    graph: object, *, authorized: bool,
) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("NPC transit proof requires operator authorization")
    temporal = replay_temporal_windows(
        documents, temporal_receipt, authorized=True)
    schedule = compile_scene_schedule(
        documents, temporal["actions"],
        temporal["authoring"]["schedule_request"], authorized=True,
        expected_source_digest=temporal["source_digest"],
        expected_session_digest=temporal["session_digest"])
    if (schedule["schedule_digest"] != temporal["schedule_digest"]
            or schedule["project_id"] != temporal["project_id"]):
        raise StudioQuestError("NPC transit source schedule drift")
    rows = schedule["timeline"]
    sites = {row["site"] for row in rows}
    checked = _validate_graph(graph, sites)
    last_seen: dict[str, dict[str, object]] = {}
    transitions: list[dict[str, object]] = []
    for row in rows:
        npc = row["npc_id"]
        previous = last_seen.get(npc)
        if previous is not None:
            path = _shortest(checked, previous["site"], row["site"])
            if path is None:
                reason = "unknown-site-route"
                distance, route = None, []
                slack = None
            else:
                distance, route = path
                slack = row["start_tick"] - previous["end_tick"] - distance
                reason = "feasible" if slack >= 0 else "insufficient-travel-time"
            item: dict[str, object] = {
                "npc_id": npc,
                "from_scene_id": previous["scene_id"],
                "to_scene_id": row["scene_id"],
                "from_site": previous["site"], "to_site": row["site"],
                "departure_tick": previous["end_tick"],
                "arrival_deadline_tick": row["start_tick"],
                "travel_ticks": distance, "route_sites": route,
                "slack_ticks": slack, "reason": reason,
                "feasible": reason == "feasible",
            }
            item["transition_digest"] = _digest(item)
            transitions.append(item)
        last_seen[npc] = row
    conflict_count = sum(not item["feasible"] for item in transitions)
    result: dict[str, object] = {
        "schema": SCHEMA, "project_id": temporal["project_id"],
        "source_digest": temporal["source_digest"],
        "quest_source_digest": temporal["quest_source_digest"],
        "session_digest": temporal["session_digest"],
        "temporal_digest": temporal["temporal_digest"],
        "temporal_receipt": temporal,
        "graph": checked, "site_count": len(sites),
        "transition_count": len(transitions), "transitions": transitions,
        "conflict_count": conflict_count,
        "all_transitions_feasible": conflict_count == 0,
        "source_replay_verified": True, "operator_estimates_only": True,
        "physical_travel_verified": False, "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_BYTES - 128:
        raise StudioQuestError("NPC transit receipt exceeds byte budget")
    result["transit_digest"] = _digest(result)
    return result


def propose_npc_transit(
    documents: Mapping[str, Any], temporal_receipt: object, prompt: str, *,
    authorized: bool,
) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("NPC transit proposal requires authorization")
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported NPC transit prompt")
    # No fabricated distance or travel-time measurements: operator must add
    # directed edges before any cross-site journey can be accepted.
    result = compile_npc_transit(
        documents, temporal_receipt, {"edges": []}, authorized=True)
    result["model_inference_performed"] = False
    # Preserve the proof's canonical digest after the typed proposal marker.
    result["transit_digest"] = _digest({
        key: value for key, value in result.items() if key != "transit_digest"})
    return result


def replay_npc_transit(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("NPC transit replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid NPC transit receipt")
    replay = compile_npc_transit(
        documents, receipt.get("temporal_receipt"), receipt.get("graph"),
        authorized=True)
    if receipt.get("model_inference_performed") is False:
        replay["model_inference_performed"] = False
        replay["transit_digest"] = _digest({
            key: value for key, value in replay.items() if key != "transit_digest"})
    if replay != receipt:
        raise StudioQuestError("NPC transit receipt failed canonical replay")
    return replay


def compile_transit_playable(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, object]:
    replay = replay_npc_transit(documents, receipt, authorized=authorized)
    if not replay["all_transitions_feasible"]:
        raise StudioQuestError("NPC transit conflicts block playable handoff")
    manifest, payload = compile_temporal_playable(
        documents, replay["temporal_receipt"], authorized=True)
    result: dict[str, object] = {
        "schema": "skeleton.game_builder.studio_npc_transit_handoff.v1",
        "transit_digest": replay["transit_digest"],
        "temporal_digest": replay["temporal_digest"],
        "bundle_sha256": manifest["bundle_sha256"],
        "bundle_bytes": len(payload),
        "canonical_html5_quest_included": manifest["canonical_html5_quest_included"],
        "physical_travel_verified": False, "release_certified": False,
    }
    result["handoff_digest"] = _digest(result)
    return result


def publish_npc_transit(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool,
) -> dict[str, object]:
    replay = replay_npc_transit(documents, receipt, authorized=authorized)
    raw = _canonical(replay) + b"\n"
    if len(raw) > MAX_BYTES:
        raise StudioQuestError("NPC transit publication exceeds byte budget")
    fd = _open_directory(directory)
    temporary = ".npc-transit-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         os.O_NOFOLLOW, 0o600, dir_fd=fd)
        created = True
        try:
            _write_all(handle, raw)
            os.fsync(handle)
        finally:
            os.close(handle)
        os.link(temporary, FILENAME, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        os.fsync(fd)
    finally:
        try:
            if created:
                os.unlink(temporary, dir_fd=fd)
        finally:
            os.close(fd)
    return {"path": str(Path(directory) / FILENAME),
            "transit_digest": replay["transit_digest"],
            "bytes": len(raw), "file_write_performed": True,
            "release_certified": False}


def restore_npc_transit(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("NPC transit restore requires authorization")
    _lease(expected_source_digest, "NPC transit restore source")
    fd = _open_directory(directory)
    try:
        handle = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            info = os.fstat(handle)
            if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BYTES
                    or (os.name == "posix" and
                        (info.st_uid != os.getuid() or info.st_mode & 0o077
                         or info.st_nlink != 1))):
                raise StudioQuestError("NPC transit receipt must be private")
            raw = os.read(handle, MAX_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_BYTES:
        raise StudioQuestError("invalid NPC transit receipt size")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate NPC transit receipt key")
            result[key] = value
        return result
    try:
        receipt = json.loads(raw.decode("utf-8", "strict"),
                             object_pairs_hook=unique,
                             parse_constant=lambda _: (_ for _ in ()).throw(
                                 StudioQuestError("nonfinite NPC transit receipt")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid NPC transit receipt JSON") from exc
    if type(receipt) is not dict or receipt.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale NPC transit source lease")
    return replay_npc_transit(documents, receipt, authorized=True)
