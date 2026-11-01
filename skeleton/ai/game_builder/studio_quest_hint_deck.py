"""Source-leased, spoiler-bounded quest accessibility hints for playable handoff.

Only currently available or already completed authored stages may receive a
hint. A hint cannot unlock a stage, invent evidence, or certify a native game.
"""
from __future__ import annotations

from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any, Mapping

from .studio_ecosystem_catalog import compile_preview
from .studio_ecosystem_canon_proof import audit_canon_source
from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, replay_quest, available_stages,
)
from .studio_ecosystem_scene_schedule import _canonical, _digest, _lease, _open_directory, _write_all

SCHEMA = "skeleton.game_builder.studio_quest_hint_deck.v1"
PROMPT = "plan spoiler-safe original quest accessibility hints"
FILENAME = "quest_hint_deck.json"
MAX_HINTS = 64
MAX_BYTES = 256 * 1024
AUDIENCES = frozenset(("available", "completed"))


def _text(value: object) -> str:
    if (type(value) is not str or not 1 <= len(value) <= 240
            or value != value.strip()
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)):
        raise StudioQuestError("invalid authored quest hint text")
    return value


def compile_quest_hint_deck(
    documents: Mapping[str, Any], actions: object, authoring: object, *,
    authorized: bool, expected_source_digest: str,
    expected_session_digest: str | None = None,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("quest hint compilation requires authorization")
    _lease(expected_source_digest, "quest hint source")
    if expected_session_digest is not None:
        _lease(expected_session_digest, "quest hint session")
    if (type(actions) is not list or len(actions) > 64
            or len(_canonical(actions)) > 16384):
        raise StudioQuestError("invalid bounded quest hint replay history")
    proof = audit_canon_source(documents, authorized=True)
    if not proof["canon_consistent"] or proof["source_digest"] != expected_source_digest:
        raise StudioQuestError("stale or contradictory quest hint source")
    session = replay_quest(documents, actions, authorized=True)
    if (expected_session_digest is not None
            and session.digest != expected_session_digest):
        raise StudioQuestError("stale quest hint session lease")
    program = compile_quest_program(documents)
    completed = set(session.completed)
    available = set(available_stages(session, documents))
    by_id = {stage.key: stage for stage in program.stages}
    # Exact hidden identifiers must never be embedded in an available hint.
    # This is an identifier leak guard, not a semantic spoiler classifier.
    hidden_ids = {
        stage.key.casefold() for stage in program.stages
        if stage.key not in completed and stage.key not in available
    }
    hidden_ids.update(ending_id.casefold() for ending_id, _ in program.endings)
    if (type(authoring) is not dict or set(authoring) != {"hints"}
            or type(authoring["hints"]) is not list
            or len(authoring["hints"]) > MAX_HINTS
            or len(_canonical(authoring)) > 32768):
        raise StudioQuestError("invalid bounded quest hint authoring")
    seen: set[str] = set()
    cards: list[dict[str, Any]] = []
    for item in authoring["hints"]:
        if (type(item) is not dict or set(item) != {
                "stage_id", "text", "audience"}
                or type(item["stage_id"]) is not str
                or item["stage_id"] not in by_id
                or item["stage_id"] in seen
                or type(item["audience"]) is not str
                or item["audience"] not in AUDIENCES):
            raise StudioQuestError("invalid or duplicate quest hint stage")
        key = item["stage_id"]
        audience = item["audience"]
        if ((audience == "available" and key not in available)
                or (audience == "completed" and key not in completed)):
            raise StudioQuestError("quest hint attempts to reveal locked or unearned stage")
        seen.add(key)
        stage = by_id[key]
        hint_text = _text(item["text"])
        if any(secret and secret in hint_text.casefold() for secret in hidden_ids):
            raise StudioQuestError("quest hint reveals a hidden stage or ending identifier")
        card: dict[str, Any] = {
            "stage_id": key, "audience": audience, "text": hint_text,
            "prerequisites": list(stage.prerequisites),
            "stage_source_digest": _digest({
                "stage_id": key, "prerequisites": stage.prerequisites,
                "alternatives": stage.alternatives, "reward": stage.reward,
                "choice_effects": stage.choice_effects,
            }),
            "status": "available_in_sandbox" if audience == "available"
                      else "completed_in_sandbox",
            "quest_unlock_performed": False,
            "external_evidence_verified": False,
        }
        card["card_digest"] = _digest(card)
        cards.append(card)
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": session.project_id,
        "source_digest": expected_source_digest,
        "quest_source_digest": session.source_digest,
        "session_digest": session.digest,
        "actions": actions, "authoring": authoring,
        "hints": cards, "hint_count": len(cards),
        "available_stage_count": len(available),
        "completed_stage_count": len(completed),
        "locked_stage_count": len(program.stages) - len(available) - len(completed),
        "source_replay_verified": True,
        "spoiler_visibility_bound_to_replay": True,
        "semantic_spoiler_review_verified": False,
        "quest_unlock_performed": False, "file_write_performed": False,
        "native_genre_runtime_verified": False, "release_certified": False,
    }
    if len(_canonical(result)) > MAX_BYTES - 128:
        raise StudioQuestError("quest hint deck exceeds receipt budget")
    result["hint_deck_digest"] = _digest(result)
    return result


def propose_quest_hint_deck(
    documents: Mapping[str, Any], actions: object, prompt: str, *,
    authorized: bool, expected_source_digest: str,
) -> dict[str, Any]:
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported quest accessibility prompt")
    if authorized is not True:
        raise PermissionError("quest hint proposal requires authorization")
    session = replay_quest(documents, actions, authorized=True)
    available = set(available_stages(session, documents))
    program = compile_quest_program(documents)
    hints = [{
        "stage_id": stage.key,
        "text": "Review the available stage " + stage.key + " and its authored choices.",
        "audience": "available",
    } for stage in program.stages if stage.key in available]
    return compile_quest_hint_deck(
        documents, actions, {"hints": hints}, authorized=True,
        expected_source_digest=expected_source_digest)


def replay_quest_hint_deck(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("quest hint replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid quest hint deck receipt")
    verified = compile_quest_hint_deck(
        documents, receipt.get("actions"), receipt.get("authoring"),
        authorized=True, expected_source_digest=receipt.get("source_digest"),
        expected_session_digest=receipt.get("session_digest"))
    if verified != receipt:
        raise StudioQuestError("quest hint deck failed canonical source replay")
    return verified


def render_quest_hint_html(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> bytes:
    verified = replay_quest_hint_deck(documents, receipt, authorized=authorized)
    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; ",
        "base-uri 'none'; form-action 'none'\">",
        "<title>Original quest accessibility hints</title></head><body><main>",
        "<h1>Available original quest hints</h1>",
        "<p>Only source-replayed available or completed stages are shown.</p>",
        "<ol>",
    ]
    for card in verified["hints"]:
        parts.append(
            "<li><strong>" + escape(card["stage_id"], quote=True) +
            "</strong> (" + escape(card["audience"], quote=True) +
            ")<p>" + escape(card["text"], quote=True) + "</p></li>")
    parts.extend(["</ol></main></body></html>"])
    html = "".join(parts).encode("utf-8")
    if len(html) > 128 * 1024:
        raise StudioQuestError("quest hint HTML exceeds budget")
    return html


def compile_quest_hint_playable(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    verified = replay_quest_hint_deck(documents, receipt, authorized=authorized)
    # The existing compiler supplies actual offline 2D gameplay proof.
    compiled = compile_preview(verified["project_id"], authorized=True)
    game = compiled.playable.html.encode("utf-8", "strict")
    proof = compiled.receipt()
    if (proof.get("project_id") != verified["project_id"]
            or proof.get("validated_gameplay_proof") is not True
            or sha256(game).hexdigest() != proof.get("html_sha256")):
        raise StudioQuestError("quest hint playable source proof mismatch")
    html = render_quest_hint_html(documents, verified, authorized=True)
    result = {
        "schema": "skeleton.game_builder.studio_quest_hint_handoff.v1",
        "hint_deck_digest": verified["hint_deck_digest"],
        "game_html_sha256": sha256(game).hexdigest(),
        "canonical_html5_quest_included": True,
        "companion_html_sha256": sha256(html).hexdigest(),
        "companion_html_bytes": len(html),
        "native_hint_ui_integrated": False,
        "release_certified": False,
    }
    result["handoff_digest"] = _digest(result)
    return result


def publish_quest_hint_deck(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool,
) -> dict[str, Any]:
    verified = replay_quest_hint_deck(documents, receipt, authorized=authorized)
    raw = _canonical(verified) + b"\n"
    if len(raw) > MAX_BYTES:
        raise StudioQuestError("quest hint publication exceeds budget")
    fd = _open_directory(directory)
    temporary = ".quest-hint-" + secrets.token_hex(16) + ".tmp"
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
    return {
        "path": str(Path(directory) / FILENAME),
        "hint_deck_digest": verified["hint_deck_digest"],
        "bytes": len(raw), "file_write_performed": True,
        "release_certified": False,
    }


def restore_quest_hint_deck(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("quest hint restore requires authorization")
    _lease(expected_source_digest, "quest hint restore source")
    fd = _open_directory(directory)
    try:
        handle = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            info = os.fstat(handle)
            if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BYTES
                    or (os.name == "posix" and (info.st_uid != os.getuid()
                        or info.st_mode & 0o077 or info.st_nlink != 1))):
                raise StudioQuestError("quest hint receipt must be private")
            raw = os.read(handle, MAX_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_BYTES:
        raise StudioQuestError("invalid quest hint receipt size")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise StudioQuestError("duplicate quest hint JSON key")
            out[key] = value
        return out
    try:
        receipt = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=unique,
                             parse_constant=lambda _: (_ for _ in ()).throw(
                                 StudioQuestError("nonfinite quest hint JSON")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid quest hint JSON") from exc
    if type(receipt) is not dict or receipt.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale quest hint source lease")
    return replay_quest_hint_deck(documents, receipt, authorized=True)
