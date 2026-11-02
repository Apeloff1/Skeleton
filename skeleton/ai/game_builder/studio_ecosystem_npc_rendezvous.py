"""Source-leased NPC rendezvous planning against canonical scene and transit replay.

This is a logical meeting feasibility compiler, not physical movement simulation.
Meetings are inserted as reservations into an immutable authored timeline. A
missing route, an occupied NPC, or insufficient time is a blocked proof.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import (
    MAX_TOTAL_TICKS, _canonical, _digest, _lease, _open_directory,
    _write_all, compile_scene_schedule,
)
from .studio_ecosystem_npc_transit import (
    _shortest, replay_npc_transit, compile_transit_playable,
)

SCHEMA = "skeleton.game_builder.studio_npc_rendezvous.v1"
PROMPT = "plan source-bound npc rendezvous"
FILENAME = "npc_rendezvous.json"
MAX_MEETINGS = 16
MAX_BYTES = 256 * 1024
_ID = re.compile(r"[a-z][a-z0-9_-]{0,47}\Z")


def _checked_meetings(value: object, npcs: set[str], sites: set[str]) -> list[dict[str, Any]]:
    if type(value) is not list or len(value) > MAX_MEETINGS:
        raise StudioQuestError("NPC rendezvous requires at most 16 typed meetings")
    if len(_canonical(value)) > 32768:
        raise StudioQuestError("NPC rendezvous authoring exceeds byte budget")
    ids: set[str] = set()
    checked = []
    for item in value:
        if type(item) is not dict or set(item) != {
            "id", "npc_ids", "site", "earliest_tick", "latest_tick", "duration_ticks"
        }:
            raise StudioQuestError("invalid NPC rendezvous fields")
        name, cast, site = item["id"], item["npc_ids"], item["site"]
        if (type(name) is not str or not _ID.fullmatch(name) or name in ids
                or type(cast) is not list or len(cast) != 2
                or any(type(npc) is not str or npc not in npcs for npc in cast)
                or cast[0] == cast[1] or type(site) is not str or site not in sites):
            raise StudioQuestError("NPC rendezvous must name two known distinct NPCs and site")
        first, last, duration = (item["earliest_tick"], item["latest_tick"],
                                 item["duration_ticks"])
        if (type(first) is not int or type(last) is not int
                or type(duration) is not int or first < 0 or duration < 1
                or last > MAX_TOTAL_TICKS or last - first < duration):
            raise StudioQuestError("invalid NPC rendezvous time window")
        ids.add(name)
        checked.append({
            "id": name, "npc_ids": list(cast), "site": site,
            "earliest_tick": first, "latest_tick": last,
            "duration_ticks": duration,
        })
    return checked


def _npc_slots(
    reservations: list[dict[str, Any]], graph: dict[str, Any],
    site: str, earliest: int, latest_start: int, duration: int,
) -> list[tuple[int, int, dict[str, Any]]]:
    """Return start ranges with both travel boundaries witnessed.

    A reservation occupies [start,end). Travel to/from it uses the directed
    graph and cannot be silently treated as zero-distance teleportation.
    """
    slots: list[tuple[int, int, dict[str, Any]]] = []
    ordered = sorted(reservations, key=lambda row: (row["start_tick"], row["id"]))
    for i in range(len(ordered) + 1):
        before = ordered[i - 1] if i else None
        after = ordered[i] if i < len(ordered) else None
        lower, upper = earliest, latest_start
        arriving = None
        leaving = None
        if before is not None:
            arriving = _shortest(graph, before["site"], site)
            if arriving is None:
                continue
            lower = max(lower, before["end_tick"] + arriving[0])
        if after is not None:
            leaving = _shortest(graph, site, after["site"])
            if leaving is None:
                continue
            upper = min(upper, after["start_tick"] - leaving[0] - duration)
        if lower <= upper:
            slots.append((lower, upper, {
                "prior_id": before["id"] if before else None,
                "next_id": after["id"] if after else None,
                "incoming_route": arriving[1] if arriving else [site],
                "outgoing_route": leaving[1] if leaving else [site],
                "incoming_ticks": arriving[0] if arriving else 0,
                "outgoing_ticks": leaving[0] if leaving else 0,
            }))
    return slots


def compile_npc_rendezvous(
    documents: Mapping[str, Any], transit_receipt: object,
    meetings: object, *, authorized: bool, expected_source_digest: str,
    expected_session_digest: str | None = None,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC rendezvous requires operator authorization")
    _lease(expected_source_digest, "NPC rendezvous source")
    if expected_session_digest is not None:
        _lease(expected_session_digest, "NPC rendezvous session")
    transit = replay_npc_transit(documents, transit_receipt, authorized=True)
    if transit["source_digest"] != expected_source_digest:
        raise StudioQuestError("stale NPC rendezvous source lease")
    if expected_session_digest is not None and transit["session_digest"] != expected_session_digest:
        raise StudioQuestError("stale NPC rendezvous session lease")
    temporal = transit["temporal_receipt"]
    schedule = compile_scene_schedule(
        documents, temporal["actions"], temporal["authoring"]["schedule_request"],
        authorized=True, expected_source_digest=expected_source_digest,
        expected_session_digest=transit["session_digest"])
    if schedule["schedule_digest"] != temporal["schedule_digest"]:
        raise StudioQuestError("NPC rendezvous temporal schedule drift")
    rows = schedule["timeline"]
    npcs = {row["npc_id"] for row in rows}
    sites = {row["site"] for row in rows}
    checked = _checked_meetings(meetings, npcs, sites)
    reservations: dict[str, list[dict[str, Any]]] = {npc: [] for npc in npcs}
    for row in rows:
        reservations[row["npc_id"]].append({
            "id": "scene:" + row["scene_id"], "site": row["site"],
            "start_tick": row["start_tick"], "end_tick": row["end_tick"],
        })
    results: list[dict[str, Any]] = []
    for item in checked:
        first, second = item["npc_ids"]
        latest_start = item["latest_tick"] - item["duration_ticks"]
        slots_a = _npc_slots(
            reservations[first], transit["graph"], item["site"],
            item["earliest_tick"], latest_start, item["duration_ticks"])
        slots_b = _npc_slots(
            reservations[second], transit["graph"], item["site"],
            item["earliest_tick"], latest_start, item["duration_ticks"])
        candidates = [
            (max(a, b), proof_a, proof_b)
            for a, end_a, proof_a in slots_a
            for b, end_b, proof_b in slots_b
            if max(a, b) <= min(end_a, end_b)
        ]
        candidates.sort(key=lambda row: (
            row[0], _canonical(row[1]), _canonical(row[2])))
        if candidates and transit["all_transitions_feasible"]:
            start, proof_a, proof_b = candidates[0]
            end = start + item["duration_ticks"]
            for npc in (first, second):
                reservations[npc].append({
                    "id": "meeting:" + item["id"], "site": item["site"],
                    "start_tick": start, "end_tick": end,
                })
            result = {
                "id": item["id"], "status": "accepted", "reason": "feasible",
                "start_tick": start, "end_tick": end,
                "npc_proofs": {first: proof_a, second: proof_b},
                "source_replay_verified": True,
            }
        else:
            result = {
                "id": item["id"], "status": "blocked",
                "reason": ("baseline-transit-conflict"
                           if not transit["all_transitions_feasible"]
                           else "unreachable-or-occupied"),
                "start_tick": None, "end_tick": None, "npc_proofs": {},
                "source_replay_verified": True,
            }
        result["meeting_digest"] = _digest(result)
        results.append(result)
    accepted = sum(row["status"] == "accepted" for row in results)
    payload: dict[str, Any] = {
        "schema": SCHEMA, "project_id": transit["project_id"],
        "source_digest": transit["source_digest"],
        "session_digest": transit["session_digest"],
        "temporal_digest": transit["temporal_digest"],
        "transit_digest": transit["transit_digest"],
        "transit_receipt": transit, "meetings": checked, "outcomes": results,
        "accepted_count": accepted, "blocked_count": len(results) - accepted,
        "playable_handoff_allowed": bool(checked) and accepted == len(checked)
                                    and transit["all_transitions_feasible"],
        "source_replay_verified": True, "operator_estimates_only": True,
        "physical_travel_verified": False, "model_inference_performed": False,
        "file_write_performed": False, "release_certified": False,
    }
    if len(_canonical(payload)) > MAX_BYTES - 128:
        raise StudioQuestError("NPC rendezvous receipt exceeds byte budget")
    payload["rendezvous_digest"] = _digest(payload)
    return payload


def propose_npc_rendezvous(
    documents: Mapping[str, Any], transit_receipt: object,
    prompt: str, *, authorized: bool, expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC rendezvous proposal requires authorization")
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported NPC rendezvous prompt")
    transit = replay_npc_transit(documents, transit_receipt, authorized=True)
    temporal = transit["temporal_receipt"]
    schedule = compile_scene_schedule(
        documents, temporal["actions"], temporal["authoring"]["schedule_request"],
        authorized=True, expected_source_digest=transit["source_digest"])
    rows = schedule["timeline"]
    cast = sorted({row["npc_id"] for row in rows})
    sites = sorted({row["site"] for row in rows})
    meetings = [{
        "id": "first-encounter", "npc_ids": cast[:2], "site": sites[0],
        "earliest_tick": 0,
        "latest_tick": min(MAX_TOTAL_TICKS, max(row["end_tick"] for row in rows) + 20),
        "duration_ticks": 1,
    }] if len(cast) >= 2 and sites else []
    return compile_npc_rendezvous(
        documents, transit, meetings, authorized=True,
        expected_source_digest=expected_source_digest)


def replay_npc_rendezvous(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC rendezvous replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid NPC rendezvous receipt")
    replay = compile_npc_rendezvous(
        documents, receipt.get("transit_receipt"), receipt.get("meetings"),
        authorized=True, expected_source_digest=receipt.get("source_digest"),
        expected_session_digest=receipt.get("session_digest"))
    if _canonical(replay) != _canonical(receipt):
        raise StudioQuestError("NPC rendezvous failed canonical replay")
    return replay


def compile_rendezvous_playable(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    replay = replay_npc_rendezvous(documents, receipt, authorized=authorized)
    if not replay["playable_handoff_allowed"]:
        raise StudioQuestError("unproved NPC rendezvous blocks playable handoff")
    manifest = compile_transit_playable(
        documents, replay["transit_receipt"], authorized=True)
    result = {
        "schema": "skeleton.game_builder.studio_npc_rendezvous_handoff.v1",
        "rendezvous_digest": replay["rendezvous_digest"],
        "transit_digest": replay["transit_digest"],
        "canonical_html5_quest_included": manifest["canonical_html5_quest_included"],
        "bundle_sha256": manifest["bundle_sha256"],
        "rendezvous_scene_rendered": False,
        "operator_estimates_only": True, "release_certified": False,
    }
    result["handoff_digest"] = _digest(result)
    return result


def publish_npc_rendezvous(
    documents: Mapping[str, Any], receipt: object,
    directory: Path, *, authorized: bool,
) -> dict[str, Any]:
    replay = replay_npc_rendezvous(documents, receipt, authorized=authorized)
    raw = _canonical(replay) + b"\n"
    if len(raw) > MAX_BYTES:
        raise StudioQuestError("NPC rendezvous publication exceeds byte budget")
    fd = _open_directory(directory)
    temporary = ".npc-rendezvous-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        out = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                      os.O_NOFOLLOW, 0o600, dir_fd=fd)
        created = True
        try:
            _write_all(out, raw)
            os.fsync(out)
        finally:
            os.close(out)
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
            "rendezvous_digest": replay["rendezvous_digest"],
            "bytes": len(raw), "file_write_performed": True,
            "release_certified": False}


def restore_npc_rendezvous(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC rendezvous restore requires authorization")
    _lease(expected_source_digest, "NPC rendezvous restore source")
    fd = _open_directory(directory)
    try:
        handle = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            info = os.fstat(handle)
            if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BYTES
                    or (os.name == "posix"
                        and (info.st_uid != os.getuid() or info.st_mode & 0o077
                             or info.st_nlink != 1))):
                raise StudioQuestError("NPC rendezvous receipt must be private")
            raw = os.read(handle, MAX_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_BYTES:
        raise StudioQuestError("invalid NPC rendezvous receipt size")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise StudioQuestError("duplicate NPC rendezvous receipt key")
            out[key] = value
        return out
    try:
        receipt = json.loads(raw.decode("utf-8", "strict"),
                             object_pairs_hook=unique,
                             parse_constant=lambda _: (_ for _ in ()).throw(
                                 StudioQuestError("nonfinite NPC rendezvous receipt")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid NPC rendezvous JSON") from exc
    if type(receipt) is not dict or receipt.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale NPC rendezvous source lease")
    return replay_npc_rendezvous(documents, receipt, authorized=True)
