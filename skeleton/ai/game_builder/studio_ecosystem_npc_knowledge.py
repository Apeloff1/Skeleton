"""Source-bound NPC knowledge handoff for authored quest dialogue.

Facts are quotations from canonical authored cues, never generated testimony.
A reveal becomes earned only after its source and recipient quest scenes have
both completed in the same replay, with any required source choice selected.
"""
from __future__ import annotations

from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Any, Mapping

from .studio_ecosystem_dialogue_staging import compile_dialogue_staging
from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import _open_directory, _write_all

SCHEMA = "skeleton.game_builder.studio_npc_knowledge_handoff.v1"
REQUEST_SCHEMA = "skeleton.game_builder.studio_npc_knowledge_authoring.v1"
FILENAME = "studio_npc_knowledge.json"
MAX_BYTES = 256 * 1024
MAX_REVEALS = 128
KINDS = frozenset({"npc_knowledge", "scene_consequence"})
HEX = frozenset("0123456789abcdef")


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical NPC knowledge input") from exc


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def _lease(value: object, name: str) -> str:
    if type(value) is not str or len(value) != 64 or any(c not in HEX for c in value):
        raise StudioQuestError("invalid NPC knowledge " + name + " lease")
    return value


def _cards(documents: Mapping[str, Any], actions: list[list[str]],
           expected_source_digest: str, expected_session_digest: str | None):
    _lease(expected_source_digest, "source")
    if expected_session_digest is not None:
        _lease(expected_session_digest, "session")
    if type(actions) is not list or len(actions) > 64 or len(_canonical(actions)) > 16384:
        raise StudioQuestError("invalid bounded NPC knowledge action history")
    staging = compile_dialogue_staging(
        documents, actions, authorized=True,
        expected_source_digest=expected_source_digest)
    if (staging["source_digest"] != expected_source_digest or
            expected_session_digest is not None and
            staging["session_digest"] != expected_session_digest):
        raise StudioQuestError("stale NPC knowledge source or replay")
    cards = staging["cards"]
    if not 1 <= len(cards) <= 64:
        raise StudioQuestError("invalid NPC knowledge scene count")
    by_scene = {card["scene_id"]: (index, card)
                for index, card in enumerate(cards)}
    if len(by_scene) != len(cards):
        raise StudioQuestError("duplicate authored NPC knowledge scenes")
    return staging, cards, by_scene


def source_knowledge_facts(documents: Mapping[str, Any],
                           actions: list[list[str]], *, authorized: bool,
                           expected_source_digest: str,
                           expected_session_digest: str | None = None) -> dict[str, object]:
    """Expose exact provenance for possible reveals, never infer unknown facts."""
    if authorized is not True:
        raise PermissionError("NPC knowledge facts require operator authorization")
    staging, cards, _ = _cards(
        documents, actions, expected_source_digest, expected_session_digest)
    facts: list[dict[str, object]] = []
    for card in cards:
        for cue in card["authored_cues"]:
            if cue["kind"] in KINDS:
                facts.append({
                    "fact_id": card["scene_id"] + ":" + cue["kind"],
                    "scene_id": card["scene_id"], "npc_id": card["npc_id"],
                    "kind": cue["kind"], "source_ref": cue["source_ref"],
                    "source_text": cue["text"], "source_text_digest": _digest(cue["text"]),
                })
    result: dict[str, object] = {
        "schema": "skeleton.game_builder.studio_npc_knowledge_facts.v1",
        "project_id": staging["project_id"],
        "source_digest": staging["source_digest"],
        "session_digest": staging["session_digest"],
        "facts": facts, "file_write_performed": False,
        "native_genre_runtime_verified": False, "release_certified": False,
    }
    result["facts_digest"] = _digest(result)
    return result


def compile_npc_knowledge(documents: Mapping[str, Any], actions: list[list[str]],
                          request: object, *, authorized: bool,
                          expected_source_digest: str,
                          expected_session_digest: str | None = None) -> dict[str, object]:
    """Compile typed authoring to deterministic, causal NPC dialogue cues."""
    if authorized is not True:
        raise PermissionError("NPC knowledge compilation requires operator authorization")
    staging, cards, by_scene = _cards(
        documents, actions, expected_source_digest, expected_session_digest)
    if (type(request) is not dict or set(request) != {"schema", "reveals"} or
            request["schema"] != REQUEST_SCHEMA or type(request["reveals"]) is not list or
            len(request["reveals"]) > MAX_REVEALS or len(_canonical(request)) > 65536):
        raise StudioQuestError("invalid bounded NPC knowledge authoring")
    facts = source_knowledge_facts(
        documents, actions, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_session_digest=staging["session_digest"])
    by_fact = {fact["fact_id"]: fact for fact in facts["facts"]}
    received: dict[str, list[dict[str, object]]] = {card["scene_id"]: [] for card in cards}
    planned: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for reveal in request["reveals"]:
        if type(reveal) is not dict or set(reveal) != {
                "fact_id", "recipient_scene_id", "required_alternative"}:
            raise StudioQuestError("invalid NPC knowledge reveal fields")
        fact_id, target, alternative = (
            reveal["fact_id"], reveal["recipient_scene_id"],
            reveal["required_alternative"])
        if type(fact_id) is not str or type(target) is not str:
            raise StudioQuestError("invalid NPC knowledge reveal identity")
        fact = by_fact.get(fact_id)
        destination = by_scene.get(target)
        if fact is None or destination is None:
            raise StudioQuestError("NPC knowledge reveal references unowned source")
        source_index, source_card = by_scene[fact["scene_id"]]
        target_index, target_card = destination
        if source_index >= target_index:
            raise StudioQuestError("NPC knowledge cannot travel backward or self-reveal")
        if (alternative is not None and
                (type(alternative) is not str or
                 alternative not in source_card["authored_alternatives"])):
            raise StudioQuestError("NPC knowledge reveal uses unowned choice")
        identity = (fact_id, target)
        if identity in seen:
            raise StudioQuestError("duplicate NPC knowledge reveal")
        seen.add(identity)
        earned = (
            source_card["status"] == "completed" and
            target_card["status"] == "completed" and
            (alternative is None or source_card["selected_alternative"] == alternative)
        )
        cue: dict[str, object] = {
            "fact_id": fact_id, "source_scene_id": fact["scene_id"],
            "source_npc_id": fact["npc_id"], "recipient_scene_id": target,
            "recipient_npc_id": target_card["npc_id"],
            "required_alternative": alternative,
            "source_ref": fact["source_ref"],
            "source_text_digest": fact["source_text_digest"],
            "source_text": fact["source_text"],
            "status": "earned_in_sandbox_replay" if earned else "pending",
            "npc_speech_verified": False,
        }
        cue["cue_digest"] = _digest(cue)
        planned.append(cue)
        if earned:
            received[target].append(cue)
    scenes: list[dict[str, object]] = []
    for card in cards:
        scene = {
            "scene_id": card["scene_id"], "npc_id": card["npc_id"],
            "quest_stage": card["quest_stage"], "status": card["status"],
            "authored_card_digest": card["card_digest"],
            "received_facts": received[card["scene_id"]],
            "knowledge_cue_count": len(received[card["scene_id"]]),
            "dialogue_spoken_verified": False,
        }
        scene["scene_knowledge_digest"] = _digest(scene)
        scenes.append(scene)
    result: dict[str, object] = {
        "schema": SCHEMA, "project_id": staging["project_id"],
        "source_digest": staging["source_digest"],
        "session_digest": staging["session_digest"],
        "staging_digest": staging["staging_digest"],
        "authoring": request, "authoring_digest": _digest(request),
        "reveals": planned, "scenes": scenes,
        "earned_count": sum(row["status"] == "earned_in_sandbox_replay"
                            for row in planned),
        "pending_count": sum(row["status"] == "pending" for row in planned),
        "replay_verified": True, "source_unchanged": True,
        "file_write_performed": False, "external_evidence_verified": False,
        "npc_speech_verified": False, "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_BYTES:
        raise StudioQuestError("NPC knowledge receipt exceeds budget")
    result["knowledge_digest"] = _digest(result)
    return result


def render_npc_knowledge_html(receipt: Mapping[str, Any]) -> bytes:
    """Accessible script-free companion for the offline director scene editor."""
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid NPC knowledge HTML handoff")
    claimed = _lease(receipt.get("knowledge_digest"), "render")
    if _digest({k: v for k, v in receipt.items() if k != "knowledge_digest"}) != claimed:
        raise StudioQuestError("NPC knowledge HTML receipt tampered")
    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; "
        "base-uri 'none'; form-action 'none'\">",
        "<title>Original NPC knowledge director companion</title></head><body>",
        "<main><h1>Original NPC knowledge director companion</h1>",
        "<p>Source-verified authoring preview; not spoken dialogue or a native runtime.</p>",
        "<p>Project: " + escape(receipt["project_id"], quote=True) + "</p>",
    ]
    for scene in receipt["scenes"]:
        parts.append("<section><h2>" + escape(scene["scene_id"], quote=True) + "</h2>")
        parts.append("<p>NPC: " + escape(scene["npc_id"], quote=True) +
                     " — " + escape(scene["status"], quote=True) + "</p>")
        parts.append("<ul>")
        for cue in scene["received_facts"]:
            parts.append("<li>" + escape(cue["source_text"], quote=True) +
                         " (authored: " + escape(cue["source_ref"], quote=True) +
                         ")</li>")
        parts.append("</ul></section>")
    parts.append("</main></body></html>")
    output = "".join(parts).encode("utf-8", "strict")
    if len(output) > MAX_BYTES:
        raise StudioQuestError("NPC knowledge HTML exceeds budget")
    return output


def publish_npc_knowledge(receipt: Mapping[str, Any], directory: Path, *,
                          authorized: bool, documents: Mapping[str, Any],
                          actions: list[list[str]]) -> dict[str, object]:
    """Publish a replay-checked private immutable JSON handoff, never overwrite."""
    if authorized is not True:
        raise PermissionError("NPC knowledge publication requires operator authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid NPC knowledge publication")
    verified = compile_npc_knowledge(
        documents, actions, receipt.get("authoring"), authorized=True,
        expected_source_digest=receipt.get("source_digest"),
        expected_session_digest=receipt.get("session_digest"))
    if receipt != verified:
        raise StudioQuestError("NPC knowledge publication lacks source replay proof")
    raw = _canonical(verified) + b"\n"
    if len(raw) > MAX_BYTES:
        raise StudioQuestError("NPC knowledge publication exceeds budget")
    fd = _open_directory(directory)
    temporary = ".studio-knowledge-" + secrets.token_hex(16) + ".tmp"
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
    return {
        "path": str(Path(directory) / FILENAME), "knowledge_digest": verified["knowledge_digest"],
        "bytes": len(raw), "file_write_performed": True, "release_certified": False,
    }


def verify_npc_knowledge(documents: Mapping[str, Any], actions: list[list[str]],
                         directory: Path, *, authorized: bool,
                         expected_source_digest: str) -> dict[str, object]:
    """Read only an owned regular private file and replay every derived claim."""
    if authorized is not True:
        raise PermissionError("NPC knowledge restore requires operator authorization")
    _lease(expected_source_digest, "restore source")
    fd = _open_directory(directory)
    try:
        handle = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            info = os.fstat(handle)
            if (not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES or
                    os.name == "posix" and
                    (info.st_uid != os.getuid() or info.st_mode & 0o077)):
                raise StudioQuestError("NPC knowledge file must be regular, owned, private")
            raw = os.read(handle, MAX_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_BYTES:
        raise StudioQuestError("invalid NPC knowledge restore size")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate NPC knowledge JSON key")
            result[key] = value
        return result
    try:
        stored = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(
                                StudioQuestError("nonfinite NPC knowledge JSON")))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StudioQuestError("invalid NPC knowledge restore JSON") from exc
    if type(stored) is not dict or stored.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale NPC knowledge source")
    verified = compile_npc_knowledge(
        documents, actions, stored.get("authoring"), authorized=True,
        expected_source_digest=expected_source_digest,
        expected_session_digest=stored.get("session_digest"))
    if stored != verified:
        raise StudioQuestError("NPC knowledge restore differs from canonical replay")
    return verified
