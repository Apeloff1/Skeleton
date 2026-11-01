"""Deterministic source-leased waypoint routes through original playable scenes.

A waypoint itinerary is a collision-checked *preview* for the authored grid,
not a record of player input, physical simulation, or native device evidence.
"""
from __future__ import annotations

from collections import deque
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
)
from skeleton.ai.game_builder.studio_ecosystem_walkable import playable_world_source
from skeleton.ai.game_builder.studio_ecosystem_walk_replay import DIRECTIONS

SCHEMA = "skeleton.game_builder.studio_waypoint_route.v1"
FILENAME = "studio_waypoint_route.json"
MAX_WAYPOINTS = 8
MAX_RECEIPT_BYTES = 128 * 1024


def _point(value: object, world: dict[str, Any], rows: list[str]) -> tuple[int, int]:
    if (type(value) not in (list, tuple) or len(value) != 2
            or any(type(n) is not int for n in value)):
        raise StudioQuestError("waypoint must be an exact integer coordinate")
    x, y = value
    if not (0 <= x < world["width"] and 0 <= y < world["height"]
            and rows[y][x] != "#"):
        raise StudioQuestError("waypoint crosses blocked or off-grid cell")
    return x, y


def _leg(
    rows: list[str], world: dict[str, Any], start: tuple[int, int],
    destinations: set[tuple[int, int]],
) -> tuple[tuple[int, int], list[str]]:
    queue = deque([start])
    previous: dict[tuple[int, int], tuple[tuple[int, int], str] | None] = {start: None}
    found = None
    while queue:
        here = queue.popleft()
        if here in destinations:
            found = here
            break
        for direction, (dx, dy) in DIRECTIONS.items():
            x, y = here[0] + dx, here[1] + dy
            point = x, y
            if (0 <= x < world["width"] and 0 <= y < world["height"]
                    and rows[y][x] != "#" and point not in previous):
                previous[point] = (here, direction)
                queue.append(point)
    if found is None:
        raise StudioQuestError("waypoint route is unreachable in authored scene")
    actions = []
    current = found
    while previous[current] is not None:
        parent, direction = previous[current]
        actions.append(direction)
        current = parent
    actions.reverse()
    return found, actions


def compile_waypoint_route(
    documents: Mapping[str, Any], *, scene_index: int,
    start: object, waypoints: object, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("waypoint planning requires authorization")
    _lease(expected_source_digest, "waypoint source")
    if (type(scene_index) is not int or scene_index < 0
            or type(waypoints) is not list or len(waypoints) > MAX_WAYPOINTS
            or len(_canonical({"start": start, "waypoints": waypoints})) > 4096):
        raise StudioQuestError("invalid bounded waypoint request")
    world = playable_world_source(documents)
    if world["source_digest"] != expected_source_digest:
        raise StudioQuestError("stale waypoint source lease")
    if scene_index >= len(world["maps"]):
        raise StudioQuestError("unknown authored waypoint scene")
    rows = world["maps"][scene_index]
    origin = _point(start, world, rows)
    stops = [_point(point, world, rows) for point in waypoints]
    if len(set(stops)) != len(stops):
        raise StudioQuestError("duplicate waypoint coordinate")
    tx, ty = world["target"]
    interaction = {
        (x, y) for x, y in (
            (tx, ty), (tx - 1, ty), (tx + 1, ty),
            (tx, ty - 1), (tx, ty + 1),
        )
        if (0 <= x < world["width"] and 0 <= y < world["height"]
            and rows[y][x] != "#")
    }
    if not interaction:
        raise StudioQuestError("authored marker has no interaction cell")
    cursor = origin
    legs: list[dict[str, Any]] = []
    all_directions: list[str] = []
    for index, waypoint in enumerate(stops):
        finish, directions = _leg(rows, world, cursor, {waypoint})
        legs.append({
            "kind": "waypoint", "index": index,
            "start": list(cursor), "finish": list(finish),
            "directions": directions, "accepted_steps": len(directions),
        })
        all_directions.extend(directions)
        cursor = finish
    finish, directions = _leg(rows, world, cursor, interaction)
    legs.append({
        "kind": "interaction", "index": len(stops),
        "start": list(cursor), "finish": list(finish),
        "directions": directions, "accepted_steps": len(directions),
    })
    all_directions.extend(directions)
    if len(all_directions) > 4096:
        raise StudioQuestError("waypoint route exceeds walk replay budget")
    payload: dict[str, Any] = {
        "schema": SCHEMA, "project_id": world["project_id"],
        "source_digest": world["source_digest"],
        "scene_index": scene_index, "start": list(origin),
        "waypoints": [list(point) for point in stops],
        "finish": list(finish), "legs": legs,
        "directions": all_directions, "accepted_steps": len(all_directions),
        "collision_checked": True, "source_replay_verified": True,
        "file_write_performed": False, "physical_world_qualified": False,
        "release_certified": False,
    }
    if len(_canonical(payload)) > MAX_RECEIPT_BYTES - 128:
        raise StudioQuestError("waypoint route receipt exceeds budget")
    payload["route_digest"] = _digest(payload)
    return payload


def replay_waypoint_route(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("waypoint replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid waypoint route receipt")
    verified = compile_waypoint_route(
        documents, scene_index=receipt.get("scene_index"),
        start=receipt.get("start"), waypoints=receipt.get("waypoints"),
        authorized=True, expected_source_digest=expected_source_digest,
    )
    if verified != receipt:
        raise StudioQuestError("waypoint route failed canonical replay")
    return verified


def render_waypoint_route_html(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
    expected_source_digest: str,
) -> bytes:
    verified = replay_waypoint_route(
        documents, receipt, authorized=authorized,
        expected_source_digest=expected_source_digest,
    )
    rows = "".join(
        "<li>" + escape(leg["kind"], quote=True) + ": " +
        escape(", ".join(leg["directions"]), quote=True) + "</li>"
        for leg in verified["legs"]
    )
    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; "
        "base-uri 'none'; form-action 'none'; object-src 'none'\">"
        "<title>Original world waypoint itinerary</title></head><body><main>"
        "<h1>Collision-checked original world waypoint itinerary</h1>"
        "<p>Authoring preview only; no player traversal or native device proof.</p>"
        "<ol>" + rows + "</ol><p>Route SHA-256: " +
        escape(verified["route_digest"]) + "</p></main></body></html>"
    ).encode("utf-8")
    if len(html) > 64 * 1024:
        raise StudioQuestError("waypoint route HTML exceeds budget")
    return html


def publish_waypoint_route(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool, expected_source_digest: str,
) -> dict[str, Any]:
    verified = replay_waypoint_route(
        documents, receipt, authorized=authorized,
        expected_source_digest=expected_source_digest,
    )
    raw = _canonical(verified) + b"\n"
    fd = _open_directory(directory)
    temp = ".waypoint-route-" + secrets.token_hex(16) + ".tmp"
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
    return {
        "path": str(Path(directory) / FILENAME), "bytes": len(raw),
        "route_digest": verified["route_digest"],
        "file_write_performed": True, "release_certified": False,
    }


def restore_waypoint_route(
    documents: Mapping[str, Any], directory: Path, *,
    authorized: bool, expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("waypoint restore requires authorization")
    _lease(expected_source_digest, "waypoint restore source")
    fd = _open_directory(directory)
    try:
        handle = os.open(
            FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd,
        )
        try:
            info = os.fstat(handle)
            if (
                not stat.S_ISREG(info.st_mode)
                or not 0 < info.st_size <= MAX_RECEIPT_BYTES
                or (os.name == "posix" and (
                    info.st_uid != os.getuid()
                    or info.st_mode & 0o077 or info.st_nlink != 1
                ))
            ):
                raise StudioQuestError("waypoint receipt must be private")
            raw = os.read(handle, MAX_RECEIPT_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("invalid waypoint receipt size")

    def unique(pairs):
        output = {}
        for key, value in pairs:
            if key in output:
                raise StudioQuestError("duplicate waypoint JSON key")
            output[key] = value
        return output

    try:
        record = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite waypoint JSON")),
        )
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid waypoint JSON") from exc
    if type(record) is not dict or record.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale or invalid waypoint source lease")
    return replay_waypoint_route(
        documents, record, authorized=True,
        expected_source_digest=expected_source_digest,
    )
