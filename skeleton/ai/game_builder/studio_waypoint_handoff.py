"""Verified, source-leased hazard-aware waypoint execution into a playable walk save.

Unlike a navigation hint, this contract replays every proposed movement through
both the authoritative collision engine and the authored health simulator.
It never chooses quest alternatives or claims device/native qualification.
"""
from __future__ import annotations

from html import escape
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
)
from .studio_ecosystem_walk_replay import (
    MAX_WALK_EVENTS, MAX_WALK_EVENT_BYTES, replay_walk,
    restore_walk_receipt, start_walk, validate_walk_events,
)
from .studio_ecosystem_encounters import replay_hazard_health
from .studio_waypoint_risk import compile_waypoint_risk

SCHEMA = "skeleton.game_builder.studio_waypoint_handoff.v1"
FILENAME = "studio_waypoint_handoff.json"
MAX_BYTES = 512 * 1024


def new_walk_receipt(documents: Mapping[str, Any], *, authorized: bool,
                     expected_source_digest: str) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("walk start requires operator authorization")
    _lease(expected_source_digest, "walk start source")
    session = start_walk(documents, authorized=True)
    if session.source_digest != expected_source_digest:
        raise StudioQuestError("stale walk start source lease")
    return session.receipt()




def _bounded_walk_receipt(value: object) -> bytes:
    """Preflight typed user data *before* JSON serialization or source replay.

    A malicious caller may supply an arbitrarily large nested Python object;
    neither serialization nor a client-supplied digest is a resource boundary.
    """
    fields = {
        "schema", "project_id", "source_digest", "events", "scene_index",
        "position", "choices", "accepted_moves", "session_digest",
        "external_evidence_verified", "native_genre_runtime_verified",
        "release_certified",
    }
    if type(value) is not dict or set(value) != fields:
        raise StudioQuestError("invalid typed walk receipt for handoff")
    if (value["schema"] != "skeleton.game_builder.studio_walk_replay.v1"
            or type(value["project_id"]) is not str
            or not 1 <= len(value["project_id"]) <= 128
            or type(value["source_digest"]) is not str
            or len(value["source_digest"]) != 64
            or type(value["session_digest"]) is not str
            or len(value["session_digest"]) != 64
            or any(value[key] is not False for key in (
                "external_evidence_verified", "native_genre_runtime_verified",
                "release_certified"))
            or type(value["scene_index"]) is not int
            or not 0 <= value["scene_index"] <= MAX_WALK_EVENTS
            or type(value["accepted_moves"]) is not int
            or not 0 <= value["accepted_moves"] <= MAX_WALK_EVENTS
            or type(value["position"]) is not list
            or len(value["position"]) != 2
            or any(type(n) is not int for n in value["position"])
            or type(value["events"]) is not list
            or type(value["choices"]) is not list
            or len(value["choices"]) > MAX_WALK_EVENTS):
        raise StudioQuestError("invalid bounded walk receipt contract")
    validate_walk_events(value["events"])
    for choice in value["choices"]:
        if (type(choice) is not list or len(choice) != 2
                or any(type(text) is not str
                       or len(text) > MAX_WALK_EVENT_BYTES
                       or len(text.encode("utf-8", "strict")) > MAX_WALK_EVENT_BYTES
                       for text in choice)):
            raise StudioQuestError("invalid bounded walk choice history")
    raw = _canonical(value)
    if len(raw) > MAX_BYTES:
        raise StudioQuestError("walk receipt exceeds handoff byte budget")
    return raw


def compile_waypoint_handoff(
    documents: Mapping[str, Any], session_receipt: object, *,
    waypoints: object, max_hazard_contacts: int, authorized: bool,
    expected_source_digest: str, expected_session_digest: str,
) -> dict[str, Any]:
    """Return a replay-proven post-movement save; do not write or choose."""
    if authorized is not True:
        raise PermissionError("waypoint handoff requires authorization")
    _lease(expected_source_digest, "waypoint handoff source")
    _lease(expected_session_digest, "waypoint handoff session")
    raw = _bounded_walk_receipt(session_receipt)
    before = restore_walk_receipt(documents, raw, authorized=True)
    if (before.source_digest != expected_source_digest
            or before.digest != expected_session_digest):
        raise StudioQuestError("stale walk handoff source or session lease")
    prior_health = replay_hazard_health(
        documents, before.events, authorized=True,
    )
    if prior_health["character_defeated"] or prior_health["remaining_health"] <= 0:
        raise StudioQuestError("defeated character cannot accept waypoint handoff")
    if (type(max_hazard_contacts) is not int or max_hazard_contacts < 0
            or max_hazard_contacts >= prior_health["remaining_health"]):
        raise StudioQuestError("handoff hazard budget must preserve remaining health")
    route = compile_waypoint_risk(
        documents, scene_index=before.scene_index, start=list(before.position),
        waypoints=waypoints, max_hazard_contacts=max_hazard_contacts,
        authorized=True, expected_source_digest=expected_source_digest,
    )
    if len(before.events) + route["accepted_steps"] > MAX_WALK_EVENTS:
        raise StudioQuestError("handoff exceeds authoritative walk event budget")
    proposed = before.events + tuple(("move", direction)
                                     for direction in route["directions"])
    after = replay_walk(documents, proposed, authorized=True)
    after_health = replay_hazard_health(documents, proposed, authorized=True)
    prior_hits = prior_health["hazard_contacts"]
    all_hits = after_health["hazard_contacts"]
    new_hits = all_hits[len(prior_hits):]
    if (all_hits[:len(prior_hits)] != prior_hits
            or [hit["position"] for hit in new_hits] != route["hazard_contacts"]
            or after_health["remaining_health"] != (
                prior_health["remaining_health"] - route["hazard_contact_count"])
            or after_health["character_defeated"]
            or after.source_digest != expected_source_digest
            or after.project_id != before.project_id
            or after.scene_index != before.scene_index
            or after.chosen != before.chosen
            or list(after.position) != route["finish"]
            or after.accepted_moves - before.accepted_moves != route["accepted_steps"]):
        raise StudioQuestError("waypoint route diverged from playable collision/health replay")
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": before.project_id,
        "source_digest": expected_source_digest,
        "prior_session_digest": before.digest,
        "post_session_digest": after.digest,
        "prior_walk_receipt": before.receipt(),
        "post_walk_receipt": after.receipt(),
        "route": route,
        "prior_health": prior_health["remaining_health"],
        "post_health": after_health["remaining_health"],
        "new_hazard_contacts": new_hits,
        "accepted_moves": route["accepted_steps"],
        "scene_index": before.scene_index,
        "collision_replay_verified": True,
        "health_replay_verified": True,
        "playable_handoff_allowed": True,
        "quest_choice_performed": False,
        "file_write_performed": False,
        "native_runtime_verified": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_BYTES - 128:
        raise StudioQuestError("waypoint handoff exceeds receipt budget")
    result["handoff_digest"] = _digest(result)
    return result


def replay_waypoint_handoff(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
    expected_source_digest: str, expected_session_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("waypoint handoff replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid waypoint handoff receipt")
    route = receipt.get("route")
    if type(route) is not dict:
        raise StudioQuestError("missing waypoint handoff route")
    verified = compile_waypoint_handoff(
        documents, receipt.get("prior_walk_receipt"),
        waypoints=route.get("waypoints"),
        max_hazard_contacts=route.get("max_hazard_contacts"),
        authorized=True, expected_source_digest=expected_source_digest,
        expected_session_digest=expected_session_digest,
    )
    if verified != receipt:
        raise StudioQuestError("waypoint handoff failed canonical replay")
    return verified


def render_waypoint_handoff_html(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
    expected_source_digest: str, expected_session_digest: str,
) -> bytes:
    proof = replay_waypoint_handoff(
        documents, receipt, authorized=authorized,
        expected_source_digest=expected_source_digest,
        expected_session_digest=expected_session_digest,
    )
    steps = "".join("<li>" + escape(step) + "</li>"
                    for step in proof["route"]["directions"])
    page = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; "
        "base-uri 'none'; form-action 'none'; object-src 'none'\">"
        "<title>Source-verified playable route handoff</title></head><body><main>"
        "<h1>Verified original-world playable movement handoff</h1>"
        "<p>Collision and authored health were replayed. Quest choices were not made.</p>"
        "<p>Remaining health: " + str(proof["post_health"]) + "</p><ol>" +
        steps + "</ol><p>SHA-256: " + escape(proof["handoff_digest"]) +
        "</p></main></body></html>"
    ).encode("utf-8")
    if len(page) > 128 * 1024:
        raise StudioQuestError("handoff HTML exceeds budget")
    return page


def publish_waypoint_handoff(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool, expected_source_digest: str,
    expected_session_digest: str,
) -> dict[str, Any]:
    verified = replay_waypoint_handoff(
        documents, receipt, authorized=authorized,
        expected_source_digest=expected_source_digest,
        expected_session_digest=expected_session_digest,
    )
    raw = _canonical(verified) + b"\n"
    if len(raw) > MAX_BYTES:
        raise StudioQuestError("handoff publication exceeds budget")
    fd = _open_directory(directory)
    temp = ".waypoint-handoff-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        handle = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=fd)
        created = True
        try:
            _write_all(handle, raw)
            os.fsync(handle)
        finally:
            os.close(handle)
        os.link(temp, FILENAME, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        os.fsync(fd)
    finally:
        try:
            if created:
                os.unlink(temp, dir_fd=fd)
        finally:
            os.close(fd)
    return {"path": str(Path(directory) / FILENAME), "bytes": len(raw),
            "handoff_digest": verified["handoff_digest"],
            "file_write_performed": True, "release_certified": False}


def restore_waypoint_handoff(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str, expected_session_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("waypoint handoff restore requires authorization")
    _lease(expected_source_digest, "waypoint restore source")
    _lease(expected_session_digest, "waypoint restore session")
    fd = _open_directory(directory)
    try:
        handle = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            info = os.fstat(handle)
            if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BYTES
                    or (os.name == "posix" and (
                        info.st_uid != os.getuid() or info.st_mode & 0o077
                        or info.st_nlink != 1))):
                raise StudioQuestError("waypoint handoff receipt must be private")
            raw = os.read(handle, MAX_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_BYTES:
        raise StudioQuestError("invalid handoff receipt size")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        record: dict[str, Any] = {}
        for key, value in pairs:
            if key in record:
                raise StudioQuestError("duplicate handoff JSON key")
            record[key] = value
        return record

    try:
        receipt = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite waypoint handoff JSON")),
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StudioQuestError("invalid handoff JSON") from exc
    return replay_waypoint_handoff(
        documents, receipt, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_session_digest=expected_session_digest,
    )
