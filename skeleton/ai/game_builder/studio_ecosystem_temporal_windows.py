"""Source-leased temporal windows and cast-exclusion proof for authored scenes.

All ticks are operator estimates, not physical travel, simulated elapsed time,
or verified native-engine timing. Only canonical quest/source replay grants a
temporal receipt; no model provider or clock is consulted.
"""
from __future__ import annotations

from base64 import b64encode
from hashlib import sha256
from html import escape
from io import BytesIO
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any, Mapping
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import (
    MAX_SCENES, MAX_TOTAL_TICKS, _canonical, _digest, _lease,
    _open_directory, _ticks, _write_all, compile_scene_schedule,
)
from .studio_ecosystem_story_html import render_story_html

SCHEMA = "skeleton.game_builder.studio_temporal_windows.v1"
PROMPT = "plan source-bound temporal windows"
FILENAME = "temporal_windows.json"
MAX_BYTES = 256 * 1024


def _validate(authoring: object, scene_ids: set[str]) -> dict[str, object]:
    if type(authoring) is not dict or set(authoring) != {
            "schedule_request", "windows", "exclusive_groups"}:
        raise StudioQuestError("temporal authoring requires exact typed fields")
    windows = authoring["windows"]
    groups = authoring["exclusive_groups"]
    if type(windows) is not dict or set(windows) != scene_ids:
        raise StudioQuestError("temporal windows must cover exactly the authored scenes")
    if type(groups) is not list or len(groups) > MAX_SCENES:
        raise StudioQuestError("invalid temporal exclusion groups")
    for scene, window in windows.items():
        if type(window) is not dict or set(window) != {"earliest", "latest"}:
            raise StudioQuestError("invalid temporal window")
        start = _ticks(window["earliest"], "earliest scene tick",
                       maximum=MAX_TOTAL_TICKS)
        end = _ticks(window["latest"], "latest scene tick",
                     maximum=MAX_TOTAL_TICKS)
        if end <= start:
            raise StudioQuestError("temporal window has no duration")
    seen: set[tuple[str, ...]] = set()
    for group in groups:
        if (type(group) is not list or not 2 <= len(group) <= MAX_SCENES
                or any(type(s) is not str or s not in scene_ids for s in group)
                or len(set(group)) != len(group)):
            raise StudioQuestError("invalid temporal exclusion membership")
        canonical_group = tuple(sorted(group))
        if canonical_group in seen:
            raise StudioQuestError("duplicate temporal exclusion group")
        seen.add(canonical_group)
    if len(_canonical(authoring)) > 32768:
        raise StudioQuestError("temporal authoring exceeds byte budget")
    return authoring


def compile_temporal_windows(
    documents: Mapping[str, Any], actions: list[list[str]], authoring: object, *,
    authorized: bool, expected_source_digest: str,
    expected_session_digest: str | None = None,
) -> dict[str, object]:
    """Prove authored scene deadlines and exclusive occupancy without side effects."""
    if authorized is not True:
        raise PermissionError("temporal compilation requires operator authorization")
    _lease(expected_source_digest, "temporal source")
    if expected_session_digest is not None:
        _lease(expected_session_digest, "temporal session")
    if type(authoring) is not dict:
        raise StudioQuestError("missing temporal authoring")
    schedule = compile_scene_schedule(
        documents, actions, authoring.get("schedule_request"),
        authorized=True, expected_source_digest=expected_source_digest,
        expected_session_digest=expected_session_digest)
    rows = schedule["timeline"]
    scene_ids = {row["scene_id"] for row in rows}
    if len(scene_ids) != len(rows):
        raise StudioQuestError("duplicate temporal scene identities")
    _validate(authoring, scene_ids)
    by_id = {row["scene_id"]: row for row in rows}
    proofs: list[dict[str, object]] = []
    for row in rows:
        window = authoring["windows"][row["scene_id"]]
        if (row["start_tick"] < window["earliest"]
                or row["end_tick"] > window["latest"]):
            raise StudioQuestError("authored temporal window cannot be satisfied")
        proofs.append({
            "scene_id": row["scene_id"], "quest_stage": row["quest_stage"],
            "npc_id": row["npc_id"], "start_tick": row["start_tick"],
            "end_tick": row["end_tick"], "earliest": window["earliest"],
            "latest": window["latest"],
            "start_slack": row["start_tick"] - window["earliest"],
            "deadline_slack": window["latest"] - row["end_tick"],
            "schedule_scene_proof_digest": row["scene_proof_digest"],
        })
    exclusions: list[dict[str, object]] = []
    for group in authoring["exclusive_groups"]:
        ordered = sorted((by_id[s] for s in group),
                         key=lambda row: (row["start_tick"], row["scene_id"]))
        for previous, following in zip(ordered, ordered[1:]):
            if previous["end_tick"] > following["start_tick"]:
                raise StudioQuestError("exclusive scenes overlap in authored timeline")
        exclusions.append({
            "scene_ids": list(group),
            "ordered_by_start": [row["scene_id"] for row in ordered],
            "overlap_proven_absent": True,
        })
    result: dict[str, object] = {
        "schema": SCHEMA, "project_id": schedule["project_id"],
        "source_digest": schedule["source_digest"],
        "quest_source_digest": schedule["quest_source_digest"],
        "session_digest": schedule["session_digest"],
        "schedule_digest": schedule["schedule_digest"],
        "actions": [list(a) for a in actions],
        "authoring": authoring, "scene_count": len(proofs),
        "window_proofs": proofs, "exclusion_proofs": exclusions,
        "critical_path_ticks": schedule["critical_path_ticks"],
        "source_replay_verified": True, "operator_estimates_only": True,
        "native_time_verified": False, "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_BYTES - 128:
        raise StudioQuestError("temporal receipt exceeds byte budget")
    result["temporal_digest"] = _digest(result)
    return result


def propose_temporal_windows(
    documents: Mapping[str, Any], actions: list[list[str]], prompt: str, *,
    authorized: bool, expected_source_digest: str,
    expected_session_digest: str | None = None,
) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("temporal proposal requires operator authorization")
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported temporal prompt; no inference claimed")
    from .studio_ecosystem_dialogue_staging import compile_dialogue_staging
    staging = compile_dialogue_staging(
        documents, actions, authorized=True,
        expected_source_digest=expected_source_digest)
    cards = staging["cards"]
    request = {
        "scene_ticks": {card["scene_id"]: 1 for card in cards},
        "npc_turnaround_ticks": 0, "min_start_ticks": {},
    }
    schedule = compile_scene_schedule(
        documents, actions, request, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_session_digest=expected_session_digest)
    windows = {
        row["scene_id"]: {"earliest": row["start_tick"],
                          "latest": min(MAX_TOTAL_TICKS, row["end_tick"] + 20)}
        for row in schedule["timeline"]
    }
    authoring = {"schedule_request": request, "windows": windows,
                 "exclusive_groups": []}
    detail = compile_temporal_windows(
        documents, actions, authoring, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_session_digest=expected_session_digest)
    proposal: dict[str, object] = {
        "schema": "skeleton.game_builder.studio_temporal_prompt.v1",
        "prompt": prompt, "authoring": authoring, "detail": detail,
        "model_inference_performed": False, "release_certified": False,
    }
    proposal["proposal_digest"] = _digest(proposal)
    return proposal


def replay_temporal_windows(documents: Mapping[str, Any], receipt: object, *,
                            authorized: bool) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("temporal replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid temporal receipt")
    replay = compile_temporal_windows(
        documents, receipt.get("actions"), receipt.get("authoring"),
        authorized=True, expected_source_digest=receipt.get("source_digest"),
        expected_session_digest=receipt.get("session_digest"))
    if replay != receipt:
        raise StudioQuestError("temporal receipt failed canonical replay")
    return replay


def publish_temporal_windows(
    documents: Mapping[str, Any], receipt: dict[str, object],
    directory: Path, *, authorized: bool,
) -> dict[str, object]:
    replay = replay_temporal_windows(documents, receipt, authorized=authorized)
    raw = _canonical(replay) + b"\n"
    if len(raw) > MAX_BYTES:
        raise StudioQuestError("temporal publication exceeds byte budget")
    fd = _open_directory(directory)
    temporary = ".temporal-" + secrets.token_hex(16) + ".tmp"
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
            "temporal_digest": replay["temporal_digest"],
            "bytes": len(raw), "file_write_performed": True,
            "release_certified": False}


def restore_temporal_windows(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("temporal restoration requires authorization")
    _lease(expected_source_digest, "temporal restore source")
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
                raise StudioQuestError("temporal receipt must be private regular file")
            raw = os.read(handle, MAX_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_BYTES:
        raise StudioQuestError("invalid temporal receipt size")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate temporal receipt key")
            result[key] = value
        return result
    try:
        record = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(
                                StudioQuestError("nonfinite temporal JSON")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid temporal receipt JSON") from exc
    if type(record) is not dict or record.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale temporal receipt")
    return replay_temporal_windows(documents, record, authorized=True)


def compile_temporal_playable(
    documents: Mapping[str, Any], receipt: dict[str, object], *,
    authorized: bool,
) -> tuple[dict[str, object], bytes]:
    """Deterministic HTML5 quest plus read-only temporal authoring evidence."""
    replay = replay_temporal_windows(documents, receipt, authorized=authorized)
    playable = render_story_html(documents)
    if len(playable) > 512 * 1024:
        raise StudioQuestError("temporal playable exceeds byte budget")
    style = ("body{max-width:65rem;margin:auto;padding:2rem;font:1rem system-ui;"
             "background:#101b28;color:#eef6ff}table{border-collapse:collapse}"
             "th,td{border:1px solid #8db0ca;padding:.5rem}a{color:#c3e7ff}")
    csp = ("default-src 'none'; style-src 'sha256-" +
           b64encode(sha256(style.encode()).digest()).decode("ascii") +
           "'; base-uri 'none'; object-src 'none'")
    table = "".join(
        "<tr><th scope='row'>" + escape(str(row["scene_id"]), quote=True) +
        "</th><td>" + str(row["start_tick"]) + "</td><td>" +
        str(row["end_tick"]) + "</td><td>" +
        str(row["deadline_slack"]) + "</td></tr>"
        for row in replay["window_proofs"])
    viewer = ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
              "<meta http-equiv='Content-Security-Policy' content=\"" + csp +
              "\"><title>Temporal scene proof</title><style>" + style +
              "</style></head><body><main><h1>Source-replayed scene windows</h1>"
              "<p>Editorial tick estimates only; no physical runtime certification.</p>"
              "<table><caption>Authored timeline</caption><thead><tr><th>Scene</th>"
              "<th>Start</th><th>End</th><th>Deadline slack</th></tr></thead>"
              "<tbody>" + table + "</tbody></table>"
              "<p><a href='index.html'>Open playable authored quest</a></p>"
              "</main></body></html>").encode("utf-8")
    public = {"schema": "skeleton.game_builder.studio_temporal_handoff.v1",
              "project_id": replay["project_id"],
              "source_digest": replay["source_digest"],
              "session_digest": replay["session_digest"],
              "temporal_digest": replay["temporal_digest"],
              "window_proofs": replay["window_proofs"],
              "exclusion_proofs": replay["exclusion_proofs"],
              "native_time_verified": False, "release_certified": False}
    files = {"index.html": playable, "timeline.html": viewer,
             "timeline.json": _canonical(public) + b"\n"}
    buf = BytesIO()
    with ZipFile(buf, "w", compression=ZIP_STORED) as archive:
        for name, data in sorted(files.items()):
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_STORED
            info.external_attr = 0o600 << 16
            archive.writestr(info, data)
    payload = buf.getvalue()
    manifest = {"schema": "skeleton.game_builder.studio_temporal_playable.v1",
                "project_id": replay["project_id"],
                "source_digest": replay["source_digest"],
                "temporal_digest": replay["temporal_digest"],
                "files": {name: sha256(data).hexdigest() for name, data in files.items()},
                "bundle_sha256": sha256(payload).hexdigest(),
                "canonical_html5_quest_included": True,
                "native_timeline_runtime_integrated": False,
                "release_certified": False}
    return manifest, payload
