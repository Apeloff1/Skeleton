"""Typed prompt-to-original-quest authoring with immutable private revisions.

The model or operator supplies a *typed* original plan; this compiler does not
pretend to infer arbitrary quest facts from prose or certify copyright.
"""
from __future__ import annotations

from copy import deepcopy
from html import escape
import json
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Any, Mapping

from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, quest_progress, start_quest,
)
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
)

PLAN_SCHEMA = "skeleton.game_builder.studio_prompt_quest_plan.v1"
RECEIPT_SCHEMA = "skeleton.game_builder.studio_prompt_quest_compilation.v1"
FILENAME = "studio_prompt_quest_compilation.json"
MAX_BYTES = 256 * 1024
PLAN_KEYS = frozenset({
    "schema", "project_id", "prompt", "stages", "endings",
    "originality_attested",
})
STAGE_KEYS = frozenset({
    "id", "prerequisites", "alternatives", "reward", "choice_effects",
})
ENDING_KEYS = frozenset({"id", "requires"})


def _text(value: object, label: str, *, maximum: int = 256) -> str:
    if (type(value) is not str or not 1 <= len(value) <= maximum
            or value.strip() != value or any(ord(char) < 32 for char in value)):
        raise StudioQuestError("invalid original quest " + label)
    return value


def _plan(value: object) -> dict[str, Any]:
    if type(value) is not dict or set(value) != PLAN_KEYS:
        raise StudioQuestError("invalid typed original quest plan")
    if value["schema"] != PLAN_SCHEMA or value["originality_attested"] is not True:
        raise StudioQuestError("original quest plan requires explicit origin attestation")
    project_id = _text(value["project_id"], "project ID", maximum=64)
    if re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", project_id) is None:
        raise StudioQuestError("invalid original quest project slug")
    _text(value["prompt"], "prompt", maximum=4096)
    stages, endings = value["stages"], value["endings"]
    if (type(stages) is not list or not 1 <= len(stages) <= 16
            or type(endings) is not list or not 1 <= len(endings) <= 8):
        raise StudioQuestError("invalid original quest plan stage or ending count")
    for stage in stages:
        if type(stage) is not dict or set(stage) != STAGE_KEYS:
            raise StudioQuestError("invalid typed original quest stage")
        _text(stage["id"], "stage ID")
        _text(stage["reward"], "reward")
        if (type(stage["prerequisites"]) is not list
                or type(stage["alternatives"]) is not list
                or type(stage["choice_effects"]) is not dict):
            raise StudioQuestError("invalid original quest stage dependencies")
    for ending in endings:
        if type(ending) is not dict or set(ending) != ENDING_KEYS:
            raise StudioQuestError("invalid typed original quest ending")
        _text(ending["id"], "ending ID")
        if type(ending["requires"]) is not list:
            raise StudioQuestError("invalid original quest ending requirements")
    if len(_canonical(value)) > 64 * 1024:
        raise StudioQuestError("original quest plan exceeds budget")
    return deepcopy(value)


def compile_prompt_quest_plan(
    plan: object, *, authorized: bool, expected_plan_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("original quest compilation requires authoring authority")
    _lease(expected_plan_digest, "original quest plan")
    authored = _plan(plan)
    if _digest(authored) != expected_plan_digest:
        raise StudioQuestError("stale original quest plan digest")
    documents = {
        "quest": {
            "project_id": authored["project_id"],
            "release_certified": False,
            "stage_graph": deepcopy(authored["stages"]),
        },
        "narrative": {
            "project_id": authored["project_id"],
            "release_certified": False,
            "endings": deepcopy(authored["endings"]),
        },
    }
    program = compile_quest_program(documents)
    initial = start_quest(documents, authorized=True)
    preview = quest_progress(initial, documents)
    payload: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "project_id": program.project_id,
        "plan": authored,
        "plan_digest": expected_plan_digest,
        "prompt_digest": _digest(authored["prompt"]),
        "documents": documents,
        "quest_source_digest": program.source_digest,
        "initial_quest_session_digest": initial.digest,
        "initial_quest_progress": preview,
        "typed_plan_compiled": True,
        "sandbox_quest_handoff_verified": True,
        "originality_attested_not_verified": True,
        "native_gameplay_verified": False,
        "file_write_performed": False, "release_certified": False,
    }
    if len(_canonical(payload)) > MAX_BYTES - 128:
        raise StudioQuestError("original quest compilation exceeds budget")
    payload["receipt_digest"] = _digest(payload)
    return payload


def replay_prompt_quest_plan(receipt: object, *, authorized: bool) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("original quest replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != RECEIPT_SCHEMA:
        raise StudioQuestError("invalid original quest compilation receipt")
    checked = compile_prompt_quest_plan(
        receipt.get("plan"), authorized=True,
        expected_plan_digest=receipt.get("plan_digest"))
    if _canonical(checked) != _canonical(receipt):
        raise StudioQuestError("original quest receipt failed canonical replay")
    return checked


def revise_prompt_quest_plan(
    receipt: object, edit: object, *, authorized: bool,
    expected_receipt_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("original quest revision requires authoring authority")
    _lease(expected_receipt_digest, "original quest revision")
    checked = replay_prompt_quest_plan(receipt, authorized=True)
    if checked["receipt_digest"] != expected_receipt_digest:
        raise StudioQuestError("stale original quest revision lease")
    if type(edit) is not dict or set(edit) != {"kind", "id", "value"}:
        raise StudioQuestError("invalid typed original quest edit")
    plan = deepcopy(checked["plan"])
    kind, identity, value = edit["kind"], edit["id"], edit["value"]
    if kind == "prompt":
        if identity != "prompt":
            raise StudioQuestError("invalid original quest prompt edit target")
        plan["prompt"] = _text(value, "prompt", maximum=4096)
    elif kind == "stage_reward":
        target = next((s for s in plan["stages"] if s["id"] == identity), None)
        if target is None:
            raise StudioQuestError("unknown original quest stage edit target")
        target["reward"] = _text(value, "reward")
    elif kind == "ending_requirements":
        target = next((e for e in plan["endings"] if e["id"] == identity), None)
        if target is None or type(value) is not list:
            raise StudioQuestError("invalid original quest ending edit target")
        target["requires"] = deepcopy(value)
    else:
        raise StudioQuestError("unknown original quest edit operation")
    return compile_prompt_quest_plan(
        plan, authorized=True, expected_plan_digest=_digest(plan))


def render_prompt_quest_html(receipt: object, *, authorized: bool) -> bytes:
    checked = replay_prompt_quest_plan(receipt, authorized=authorized)
    stages = "".join(
        "<li>" + escape(stage["id"], quote=True) + ": "
        + escape(stage["reward"], quote=True) + "</li>"
        for stage in checked["plan"]["stages"])
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'none'; style-src 'none'; img-src 'none'; "
        "form-action 'none'; base-uri 'none'">"
        '<title>Original quest plan</title></head><body><main>'
        '<h1>Original authored quest</h1><p>'
        + escape(checked["plan"]["prompt"], quote=True)
        + '</p><ol>' + stages + '</ol>'
        '<p>Typed plan and sandbox quest compilation only; no rights, '
        'native gameplay or release qualification.</p></main></body></html>'
    ).encode("utf-8")
    if len(html) > MAX_BYTES:
        raise StudioQuestError("original quest HTML exceeds budget")
    return html


def publish_prompt_quest_plan(
    receipt: object, directory: Path, *, authorized: bool,
) -> dict[str, Any]:
    checked = replay_prompt_quest_plan(receipt, authorized=authorized)
    raw = _canonical(checked) + b"\n"
    fd = _open_directory(directory)
    temporary = ".prompt-quest-" + secrets.token_hex(16) + ".tmp"
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
        try:
            os.fsync(fd)
        except OSError:
            os.unlink(FILENAME, dir_fd=fd)
            raise
    finally:
        try:
            if created:
                os.unlink(temporary, dir_fd=fd)
        finally:
            os.close(fd)
    return {
        "path": str(Path(directory) / FILENAME), "bytes": len(raw),
        "receipt_digest": checked["receipt_digest"],
        "file_write_performed": True, "release_certified": False,
    }


def restore_prompt_quest_plan(directory: Path, *, authorized: bool) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("original quest restore requires authorization")
    fd = _open_directory(directory)
    try:
        handle = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            before = os.fstat(handle)
            if (not stat.S_ISREG(before.st_mode)
                    or not 0 < before.st_size <= MAX_BYTES
                    or (os.name == "posix" and
                        (before.st_uid != os.getuid()
                         or before.st_mode & 0o077 or before.st_nlink != 1))):
                raise StudioQuestError("original quest receipt must be private")
            raw = os.read(handle, MAX_BYTES + 1)
            after = os.fstat(handle)
            if (len(raw) != before.st_size or
                    (after.st_size, after.st_mtime_ns, after.st_ctime_ns,
                     after.st_ino) !=
                    (before.st_size, before.st_mtime_ns, before.st_ctime_ns,
                     before.st_ino)):
                raise StudioQuestError("original quest receipt changed during read")
        finally:
            os.close(handle)
    finally:
        os.close(fd)

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate original quest JSON key")
            result[key] = value
        return result

    try:
        parsed = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite original quest JSON")))
    except StudioQuestError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StudioQuestError("invalid original quest JSON") from exc
    return replay_prompt_quest_plan(parsed, authorized=True)
