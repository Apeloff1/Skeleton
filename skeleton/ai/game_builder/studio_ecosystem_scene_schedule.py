"""Deterministic source-leased NPC scene scheduling for original studio worlds.

A schedule is an editor rehearsal over authored scenes, not a simulation of
physical travel, actual dialogue, elapsed wall time or native engine execution.
Its duration inputs are explicitly operator-authored estimates. No clock,
network, model provider, or random state enters the replay.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
from typing import Any, Mapping

from .studio_ecosystem_dialogue_staging import compile_dialogue_staging
from .studio_ecosystem_quest import StudioQuestError, compile_quest_program, replay_quest

SCHEMA = "skeleton.game_builder.studio_scene_schedule.v1"
MAX_SCENES = 64
MAX_DURATION = 100_000
MAX_TOTAL_TICKS = 1_000_000
MAX_RECEIPT_BYTES = 256 * 1024
FILENAME = "scene_schedule.json"
HEX = frozenset("0123456789abcdef")


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical scene schedule") from exc


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def _lease(value: object, label: str) -> str:
    if type(value) is not str or len(value) != 64 or any(c not in HEX for c in value):
        raise StudioQuestError("invalid " + label + " lease")
    return value


def _ticks(value: object, label: str, *, minimum: int = 0,
           maximum: int = MAX_DURATION) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise StudioQuestError("invalid " + label + " ticks")
    return value


def _schedule_request(value: object, scene_ids: set[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != {
            "scene_ticks", "npc_turnaround_ticks", "min_start_ticks"}:
        raise StudioQuestError("scene schedule requires exact typed authoring fields")
    durations = value["scene_ticks"]
    earliest = value["min_start_ticks"]
    if (type(durations) is not dict or set(durations) != scene_ids
            or type(earliest) is not dict or not set(earliest).issubset(scene_ids)):
        raise StudioQuestError("schedule scene identifiers differ from authored source")
    for scene_id, ticks in durations.items():
        _ticks(ticks, "scene duration", minimum=1)
    for scene_id, ticks in earliest.items():
        _ticks(ticks, "minimum scene start", maximum=MAX_TOTAL_TICKS)
    _ticks(value["npc_turnaround_ticks"], "NPC turnaround")
    if len(_canonical(value)) > 16384:
        raise StudioQuestError("schedule authoring request exceeds byte budget")
    return value


def compile_scene_schedule(
    documents: Mapping[str, Any], actions: list[list[str]], schedule: object, *,
    authorized: bool, expected_source_digest: str,
    expected_session_digest: str | None = None,
) -> dict[str, object]:
    """Compile scene times and dependency proof against exact canonical replay.

    Quest predecessors and repeated NPC appearances impose lower bounds. The
    authored chronology is the only order; simultaneous unrelated scenes are
    allowed. A forward reference or impossible tick budget fails closed.
    """
    if authorized is not True:
        raise PermissionError("scene scheduling requires operator authorization")
    _lease(expected_source_digest, "schedule source")
    if expected_session_digest is not None:
        _lease(expected_session_digest, "schedule session")
    if type(actions) is not list or len(actions) > MAX_SCENES or len(_canonical(actions)) > 16384:
        raise StudioQuestError("invalid bounded schedule replay history")
    staging = compile_dialogue_staging(
        documents, actions, authorized=True, expected_source_digest=expected_source_digest)
    program = compile_quest_program(documents)
    session = replay_quest(documents, actions, authorized=True)
    if (session.digest != staging["session_digest"]
            or session.source_digest != staging["quest_source_digest"]):
        raise StudioQuestError("scene schedule replay diverged from quest source")
    if expected_session_digest is not None and session.digest != expected_session_digest:
        raise StudioQuestError("stale scene schedule session lease")
    cards = staging["cards"]
    if not 1 <= len(cards) <= MAX_SCENES:
        raise StudioQuestError("invalid authored scene schedule count")
    scene_ids = [card["scene_id"] for card in cards]
    if len(set(scene_ids)) != len(scene_ids):
        raise StudioQuestError("duplicate authored scene schedule identity")
    authored = _schedule_request(schedule, set(scene_ids))
    by_stage = {card["quest_stage"]: card["scene_id"] for card in cards}
    if len(by_stage) != len(cards):
        raise StudioQuestError("ambiguous authored stage-to-scene schedule mapping")
    program_stages = {stage.key: stage for stage in program.stages}
    completed_ends: dict[str, int] = {}
    previous_npc: dict[str, tuple[str, int]] = {}
    rows: list[dict[str, object]] = []
    for index, card in enumerate(cards):
        stage_id = card["quest_stage"]
        stage = program_stages.get(stage_id)
        if stage is None:
            raise StudioQuestError("scene schedule references unknown quest stage")
        predecessors: list[dict[str, object]] = []
        lower_bound = authored["min_start_ticks"].get(card["scene_id"], 0)
        for required in stage.prerequisites:
            parent = by_stage.get(required)
            if parent is None or parent not in completed_ends:
                raise StudioQuestError("scene schedule contains forward or missing prerequisite")
            lower_bound = max(lower_bound, completed_ends[parent])
            predecessors.append({"scene_id": parent, "end_tick": completed_ends[parent]})
        actor = card["npc_id"]
        prior = previous_npc.get(actor)
        if prior is not None:
            lower_bound = max(lower_bound, prior[1] + authored["npc_turnaround_ticks"])
        duration = authored["scene_ticks"][card["scene_id"]]
        end = lower_bound + duration
        if end > MAX_TOTAL_TICKS:
            raise StudioQuestError("scene schedule exceeds bounded timeline")
        row = {
            "scene_index": index, "scene_id": card["scene_id"],
            "quest_stage": stage_id, "npc_id": actor, "site": card["site"],
            "status": card["status"], "selected_alternative": card["selected_alternative"],
            "start_tick": lower_bound, "end_tick": end, "duration_ticks": duration,
            "prerequisite_scenes": predecessors,
            "prior_npc_scene": prior[0] if prior is not None else None,
            "authored_card_digest": card["card_digest"],
            "dialogue_spoken_verified": False,
            "native_time_verified": False,
        }
        row["scene_proof_digest"] = _digest(row)
        rows.append(row)
        completed_ends[card["scene_id"]] = end
        previous_npc[actor] = (card["scene_id"], end)
    payload: dict[str, object] = {
        "schema": SCHEMA, "project_id": program.project_id,
        "source_digest": staging["source_digest"],
        "quest_source_digest": program.source_digest,
        "session_digest": session.digest,
        "schedule_request": authored,
        "schedule_request_digest": _digest(authored),
        "scene_count": len(rows), "timeline": rows,
        "critical_path_ticks": max(completed_ends.values()),
        "source_unchanged": True, "replay_verified": True,
        "file_write_performed": False, "external_evidence_verified": False,
        "native_genre_runtime_verified": False, "release_certified": False,
    }
    if len(_canonical(payload)) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("scene schedule receipt exceeds byte budget")
    payload["schedule_digest"] = _digest(payload)
    return payload


def _open_directory(directory: Path) -> int:
    """Walk every parent by descriptor, rejecting symlinked ancestors."""
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise StudioQuestError("secure directory descriptor operations unavailable")
    absolute = Path(os.path.abspath(directory))
    if not absolute.is_absolute():
        raise StudioQuestError("schedule destination must be an existing directory")
    parts = absolute.parts
    if not parts:
        raise StudioQuestError("invalid schedule directory")
    fd = os.open(parts[0], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[1:]:
            new_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                             dir_fd=fd)
            os.close(fd)
            fd = new_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def _write_all(fd: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(fd, data[offset:])
        if written <= 0:
            raise OSError("short schedule publication")
        offset += written


def publish_scene_schedule(receipt: Mapping[str, Any], directory: Path, *,
                           authorized: bool) -> dict[str, object]:
    """Atomically publish a new private schedule; never replace an old one.

    A complete fsynced temporary file is hard-linked into its final name only
    after serialization, and existing final files remain immutable.
    """
    if authorized is not True:
        raise PermissionError("schedule publication requires operator authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid scene schedule receipt for publication")
    digest = receipt.get("schedule_digest")
    _lease(digest, "published schedule")
    without_digest = {key: value for key, value in receipt.items()
                      if key != "schedule_digest"}
    if _digest(without_digest) != digest:
        raise StudioQuestError("forged scene schedule receipt")
    raw = _canonical(receipt) + b"\n"
    if len(raw) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("schedule publication exceeds byte budget")
    fd = _open_directory(directory)
    temporary = ".scene-schedule-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        output = os.open(temporary, flags, 0o600, dir_fd=fd)
        created = True
        try:
            _write_all(output, raw)
            os.fsync(output)
        finally:
            os.close(output)
        os.link(temporary, FILENAME, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        os.fsync(fd)
    finally:
        if created:
            os.unlink(temporary, dir_fd=fd)
        os.close(fd)
    return {"path": str(Path(directory) / FILENAME), "schedule_digest": digest,
            "bytes": len(raw), "file_write_performed": True,
            "native_genre_runtime_verified": False, "release_certified": False}


def verify_scene_schedule(
    documents: Mapping[str, Any], actions: list[list[str]], directory: Path, *,
    authorized: bool, expected_source_digest: str,
) -> dict[str, object]:
    """Read a published receipt without following links, then replay it."""
    if authorized is not True:
        raise PermissionError("schedule restore requires operator authorization")
    fd = _open_directory(directory)
    try:
        handle = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
        try:
            import stat
            info = os.fstat(handle)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_RECEIPT_BYTES:
                raise StudioQuestError("invalid schedule receipt file")
            raw = os.read(handle, MAX_RECEIPT_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("invalid bounded schedule receipt")
    try:
        def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise StudioQuestError("duplicate schedule receipt JSON key")
                result[key] = value
            return result
        stored = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(
                                StudioQuestError("nonfinite schedule receipt")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid schedule receipt JSON") from exc
    if type(stored) is not dict or stored.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale or malformed schedule receipt")
    recomputed = compile_scene_schedule(
        documents, actions, stored.get("schedule_request"), authorized=True,
        expected_source_digest=expected_source_digest,
        expected_session_digest=stored.get("session_digest"))
    if stored != recomputed:
        raise StudioQuestError("schedule receipt does not match canonical replay")
    return recomputed
