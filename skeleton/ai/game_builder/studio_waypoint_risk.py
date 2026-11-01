"""Source-leased, health-bounded waypoint navigation for original playable worlds.

Plans against the same authored hazards as the offline encounter runtime. This
is a deterministic preview, not a claim that a player followed the route.
"""
from __future__ import annotations

from heapq import heappop, heappush
from html import escape
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_encounters import authored_hazards
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
)
from skeleton.ai.game_builder.studio_ecosystem_walk_replay import DIRECTIONS
from skeleton.ai.game_builder.studio_ecosystem_walkable import playable_world_source
from skeleton.ai.game_builder.studio_waypoint_route import (
    MAX_WAYPOINTS, compile_waypoint_route,
)

SCHEMA = "skeleton.game_builder.studio_waypoint_risk.v1"
FILENAME = "studio_waypoint_risk.json"
MAX_BYTES = 128 * 1024
MAX_HITS = 16
MAX_STATES = 18 * 12 * (MAX_HITS + 1)


def _safe_leg(
    rows: list[str], origin: tuple[int, int],
    goals: set[tuple[int, int]], hazards: set[tuple[int, int]],
    *, remaining_hits: int,
) -> tuple[tuple[int, int], list[str], list[list[int]]]:
    """Lexicographically minimize hazard contacts, then moves, with stable ties."""
    if not goals:
        raise StudioQuestError("risk route has no reachable interaction cell")
    queue: list[tuple[int, int, int, int, int]] = []
    heappush(queue, (0, 0, 0, origin[0], origin[1]))
    previous: dict[tuple[int, int, int], tuple[tuple[int, int, int], str] | None] = {
        (origin[0], origin[1], 0): None,
    }
    sequence = 0
    selected = None
    width, height = len(rows[0]), len(rows)
    while queue:
        hits, steps, _, x, y = heappop(queue)
        state = (x, y, hits)
        if (x, y) in goals:
            selected = state
            break
        for direction, (dx, dy) in DIRECTIONS.items():
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height) or rows[ny][nx] == "#":
                continue
            new_hits = hits + int((nx, ny) in hazards)
            next_state = (nx, ny, new_hits)
            if new_hits > remaining_hits or next_state in previous:
                continue
            if len(previous) >= MAX_STATES:
                raise StudioQuestError("risk route state budget exceeded")
            previous[next_state] = (state, direction)
            sequence += 1
            heappush(queue, (new_hits, steps + 1, sequence, nx, ny))
    if selected is None:
        raise StudioQuestError("no survivable authored waypoint route within risk budget")
    actions: list[str] = []
    contacts: list[list[int]] = []
    current = selected
    while previous[current] is not None:
        parent, direction = previous[current]
        actions.append(direction)
        if (current[0], current[1]) in hazards:
            contacts.append([current[0], current[1]])
        current = parent
    actions.reverse()
    contacts.reverse()
    return (selected[0], selected[1]), actions, contacts


def compile_waypoint_risk(
    documents: Mapping[str, Any], *, scene_index: int, start: object,
    waypoints: object, max_hazard_contacts: int, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("risk-aware navigation requires authorization")
    _lease(expected_source_digest, "waypoint risk source")
    if type(max_hazard_contacts) is not int or not 0 <= max_hazard_contacts <= MAX_HITS:
        raise StudioQuestError("invalid bounded hazard contact budget")
    if type(waypoints) is not list or len(waypoints) > MAX_WAYPOINTS:
        raise StudioQuestError("invalid bounded waypoint list")
    if len(_canonical({"start": start, "waypoints": waypoints})) > 4096:
        raise StudioQuestError("risk waypoint request exceeds byte budget")
    # Reuse the canonical collision, scene, point and source lease validation.
    baseline = compile_waypoint_route(
        documents, scene_index=scene_index, start=start,
        waypoints=waypoints, authorized=True,
        expected_source_digest=expected_source_digest,
    )
    world = playable_world_source(documents)
    hazard_manifest = authored_hazards(documents)
    if (world["source_digest"] != expected_source_digest
            or hazard_manifest.get("source_digest") != expected_source_digest
            or hazard_manifest.get("project_id") != world["project_id"]):
        raise StudioQuestError("hazard manifest and waypoint source custody diverged")
    if type(hazard_manifest.get("hazards_by_stage")) is not list or (
        len(hazard_manifest["hazards_by_stage"]) != len(world["maps"])
    ):
        raise StudioQuestError("invalid authored hazard scene count")
    health = hazard_manifest.get("starting_health")
    damage = hazard_manifest.get("hazard_damage")
    if type(health) is not int or not 1 <= health <= 100000 or damage != 1 or type(damage) is not int:
        raise StudioQuestError("invalid authored health or hazard damage")
    if max_hazard_contacts >= health:
        raise StudioQuestError("risk budget permits a fatal encounter")
    rows = world["maps"][scene_index]
    if (not rows or any(type(row) is not str or len(row) != len(rows[0]) for row in rows)
            or len(rows) > 12 or len(rows[0]) > 18):
        raise StudioQuestError("authored risk map exceeds bounded dimensions")
    raw_hazards = hazard_manifest["hazards_by_stage"][scene_index]
    if type(raw_hazards) is not list or len(raw_hazards) > 18 * 12:
        raise StudioQuestError("invalid authored hazard coordinates")
    hazards: set[tuple[int, int]] = set()
    for item in raw_hazards:
        if (type(item) is not list or len(item) != 2
                or any(type(value) is not int for value in item)):
            raise StudioQuestError("malformed authored hazard coordinate")
        x, y = item
        if not (0 <= x < len(rows[0]) and 0 <= y < len(rows) and rows[y][x] != "#"):
            raise StudioQuestError("hazard occupies an invalid authored cell")
        if (x, y) in hazards:
            raise StudioQuestError("duplicate authored hazard cell")
        hazards.add((x, y))
    cursor = tuple(baseline["start"])
    goals = [set([tuple(point)]) for point in baseline["waypoints"]]
    tx, ty = world["target"]
    interaction = {
        (x, y) for x, y in (
            (tx, ty), (tx - 1, ty), (tx + 1, ty), (tx, ty - 1), (tx, ty + 1),
        ) if 0 <= x < len(rows[0]) and 0 <= y < len(rows) and rows[y][x] != "#"
    }
    goals.append(interaction)
    directions: list[str] = []
    contacts: list[list[int]] = []
    legs: list[dict[str, Any]] = []
    for index, destinations in enumerate(goals):
        finish, commands, hits = _safe_leg(
            rows, cursor, destinations, hazards,
            remaining_hits=max_hazard_contacts - len(contacts),
        )
        legs.append({
            "kind": "interaction" if index == len(goals) - 1 else "waypoint",
            "index": index, "start": list(cursor), "finish": list(finish),
            "directions": commands, "hazard_contacts": hits,
        })
        directions.extend(commands)
        contacts.extend(hits)
        cursor = finish
    if len(directions) > 4096:
        raise StudioQuestError("risk route exceeds playable walk event budget")
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": world["project_id"],
        "source_digest": expected_source_digest, "scene_index": scene_index,
        "start": baseline["start"], "waypoints": baseline["waypoints"],
        "max_hazard_contacts": max_hazard_contacts,
        "hazard_manifest_digest": _digest(hazard_manifest),
        "hazard_cells": sorted([list(point) for point in hazards]),
        "starting_health": health, "remaining_health": health - len(contacts),
        "finish": list(cursor), "legs": legs, "directions": directions,
        "accepted_steps": len(directions), "hazard_contacts": contacts,
        "hazard_contact_count": len(contacts),
        "collision_checked": True, "source_replay_verified": True,
        "file_write_performed": False, "native_runtime_verified": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_BYTES - 128:
        raise StudioQuestError("risk route receipt exceeds byte budget")
    result["risk_digest"] = _digest(result)
    return result


def replay_waypoint_risk(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("risk route replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid risk route receipt")
    verified = compile_waypoint_risk(
        documents, scene_index=receipt.get("scene_index"),
        start=receipt.get("start"), waypoints=receipt.get("waypoints"),
        max_hazard_contacts=receipt.get("max_hazard_contacts"),
        authorized=True, expected_source_digest=expected_source_digest,
    )
    if verified != receipt:
        raise StudioQuestError("risk route failed canonical replay")
    return verified


def render_waypoint_risk_html(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
    expected_source_digest: str,
) -> bytes:
    verified = replay_waypoint_risk(
        documents, receipt, authorized=authorized,
        expected_source_digest=expected_source_digest,
    )
    rows = "".join(
        "<li>" + escape(leg["kind"], quote=True) + ": " +
        escape(", ".join(leg["directions"]), quote=True) +
        " (hazard contacts: " + str(len(leg["hazard_contacts"])) + ")</li>"
        for leg in verified["legs"]
    )
    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; "
        "base-uri 'none'; form-action 'none'; object-src 'none'\">"
        "<title>Original world risk-aware navigation</title></head><body><main>"
        "<h1>Authored risk-aware waypoint preview</h1>"
        "<p>Offline planning only; no physical traversal or device qualification.</p>"
        "<ol>" + rows + "</ol><p>Remaining simulated health: " +
        str(verified["remaining_health"]) + "</p><p>SHA-256: " +
        escape(verified["risk_digest"]) + "</p></main></body></html>"
    ).encode("utf-8")
    if len(html) > 64 * 1024:
        raise StudioQuestError("risk route HTML exceeds budget")
    return html


def publish_waypoint_risk(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool, expected_source_digest: str,
) -> dict[str, Any]:
    verified = replay_waypoint_risk(
        documents, receipt, authorized=authorized,
        expected_source_digest=expected_source_digest,
    )
    raw = _canonical(verified) + b"\n"
    fd = _open_directory(directory)
    temp = ".waypoint-risk-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        handle = os.open(
            temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=fd,
        )
        created = True
        try:
            _write_all(handle, raw)
            os.fsync(handle)
        finally:
            os.close(handle)
        os.link(temp, FILENAME, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
        os.fsync(fd)
    finally:
        try:
            if created:
                os.unlink(temp, dir_fd=fd)
        finally:
            os.close(fd)
    return {"path": str(Path(directory) / FILENAME), "bytes": len(raw),
            "risk_digest": verified["risk_digest"], "file_write_performed": True,
            "release_certified": False}


def restore_waypoint_risk(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("risk route restore requires authorization")
    _lease(expected_source_digest, "risk route restore source")
    fd = _open_directory(directory)
    try:
        handle = os.open(
            FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd,
        )
        try:
            info = os.fstat(handle)
            if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BYTES
                    or (os.name == "posix" and (
                        info.st_uid != os.getuid() or info.st_mode & 0o077
                        or info.st_nlink != 1
                    ))):
                raise StudioQuestError("risk route receipt must be private")
            raw = os.read(handle, MAX_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_BYTES:
        raise StudioQuestError("invalid risk route receipt size")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate risk route JSON key")
            result[key] = value
        return result
    try:
        record = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite risk route JSON")),
        )
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid risk route JSON") from exc
    if type(record) is not dict or record.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale risk route source lease")
    return replay_waypoint_risk(
        documents, record, authorized=True,
        expected_source_digest=expected_source_digest,
    )
