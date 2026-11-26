"""Exact-session presentation assembly for original quest localization and awards.

Combines two independently replayed authored receipts. Neither display
translations nor achievement text can change the canonical quest history.
"""
from __future__ import annotations

from html import escape
from typing import Any, Mapping

from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, replay_quest,
)
from .studio_ecosystem_scene_schedule import _canonical, _digest
from .studio_quest_localization import (
    replay_quest_localization, compile_localized_handoff,
)
from .studio_quest_achievements import (
    replay_quest_achievements, compile_achievement_handoff,
)

SCHEMA = "skeleton.game_builder.studio_quest_presentation_bundle.v1"
HANDOFF_SCHEMA = "skeleton.game_builder.studio_quest_presentation_handoff.v1"
MAX_BUNDLE_BYTES = 512 * 1024
MAX_HTML_BYTES = 256 * 1024


def compile_quest_presentation_bundle(
    documents: Mapping[str, Any], localization: object, achievements: object,
    *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("quest presentation assembly requires authorization")
    source_before = _canonical(documents)
    locale = replay_quest_localization(documents, localization, authorized=True)
    awards = replay_quest_achievements(documents, achievements, authorized=True)
    program = compile_quest_program(documents)
    if (locale["source_digest"] != program.source_digest
            or awards["source_digest"] != program.source_digest
            or locale["project_id"] != awards["project_id"]
            or locale["initial_session_digest"] != awards["initial_session_digest"]
            or locale["session_digest"] != awards["session_digest"]
            or locale["authoring"]["actions"] != awards["authoring"]["actions"]
            or locale["authoring"]["target_ending"] != awards["authoring"]["target_ending"]
            or locale["target_ending_eligible"] != awards["target_ending_eligible"]
            or locale["unmet_target_predicates"] != awards["unmet_target_predicates"]):
        raise StudioQuestError("quest presentation receipts refer to different sessions")
    session = replay_quest(
        documents, locale["authoring"]["actions"], authorized=True)
    if session.digest != locale["session_digest"]:
        raise StudioQuestError("quest presentation canonical session diverged")
    if _canonical(documents) != source_before:
        raise StudioQuestError("quest presentation source changed during assembly")
    ready = locale["playable_handoff_allowed"]
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": program.project_id,
        "source_digest": program.source_digest,
        "session_digest": session.digest,
        "initial_session_digest": locale["initial_session_digest"],
        "target_ending": locale["authoring"]["target_ending"],
        "locale": locale["authoring"]["locale"],
        "localization_digest": locale["localization_digest"],
        "achievement_digest": awards["achievement_digest"],
        "localized_row_count": locale["row_count"],
        "reviewed_row_count": locale["reviewed_count"],
        "unlocked_achievement_ids": [row["id"] for row in awards["unlocked"]],
        "sandbox_points": awards["sandbox_points"],
        "unmet_target_predicates": locale["unmet_target_predicates"],
        "playable_handoff_allowed": ready,
        "canonical_quest_replay_verified": True,
        "translation_provenance_verified": False,
        "external_account_awards_verified": False,
        "native_gameplay_verified": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_BUNDLE_BYTES - 128:
        raise StudioQuestError("quest presentation bundle exceeds byte budget")
    result["bundle_digest"] = _digest(result)
    return result


def compile_quest_presentation_handoff(
    documents: Mapping[str, Any], localization: object, achievements: object,
    *, authorized: bool,
) -> dict[str, Any]:
    bundle = compile_quest_presentation_bundle(
        documents, localization, achievements, authorized=authorized)
    if not bundle["playable_handoff_allowed"]:
        raise StudioQuestError("quest presentation needs reviewed locale and eligible ending")
    locale = compile_localized_handoff(documents, localization, authorized=True)
    awards = compile_achievement_handoff(documents, achievements, authorized=True)
    if (locale["session_digest"] != awards["session_digest"]
            or locale["source_digest"] != awards["source_digest"]
            or locale["session_digest"] != bundle["session_digest"]
            or locale["source_digest"] != bundle["source_digest"]):
        raise StudioQuestError("quest presentation handoff source/session mismatch")
    result: dict[str, Any] = {
        "schema": HANDOFF_SCHEMA,
        "project_id": bundle["project_id"],
        "source_digest": bundle["source_digest"],
        "session_digest": bundle["session_digest"],
        "bundle_digest": bundle["bundle_digest"],
        "locale": locale["locale"],
        "localized_display_rows": locale["display_rows"],
        "canonical_choices": locale["canonical_choices"],
        "achievement_definitions": awards["definitions"],
        "unlocked_achievements": awards["unlocked"],
        "sandbox_points": awards["sandbox_points"],
        "target_ending": bundle["target_ending"],
        "canonical_quest_replay_verified": True,
        "native_gameplay_verified": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_BUNDLE_BYTES:
        raise StudioQuestError("quest presentation handoff exceeds byte budget")
    result["handoff_digest"] = _digest(result)
    return result


def render_quest_presentation_preview_html(
    documents: Mapping[str, Any], localization: object, achievements: object,
    *, authorized: bool,
) -> bytes:
    bundle = compile_quest_presentation_bundle(
        documents, localization, achievements, authorized=authorized)
    locale = replay_quest_localization(documents, localization, authorized=True)
    awards = replay_quest_achievements(documents, achievements, authorized=True)
    # Read-only preview deliberately excludes unreviewed translations.
    translations = "".join(
        "<li>" + escape(row["source"]) + " → " +
        escape(row["translation"]) + "</li>"
        for row in locale["authoring"]["rows"] if row["reviewed"])
    unlocked = set(bundle["unlocked_achievement_ids"])
    milestones = "".join(
        "<li>" + escape(row["title"]) + " — " +
        ("unlocked" if row["id"] in unlocked else "locked") + "</li>"
        for row in awards["authoring"]["achievements"])
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; base-uri 'none'; form-action 'none'; object-src 'none'" '">'
        '<title>Original quest presentation review</title></head><body><main>'
        '<h1>Source-replayed quest presentation</h1><p>Locale: ' +
        escape(bundle["locale"]) + '</p><p>Handoff allowed: ' +
        ("yes" if bundle["playable_handoff_allowed"] else "no") +
        '</p><h2>Reviewed display labels</h2><ul>' + translations +
        '</ul><h2>Canonical sandbox milestones</h2><ul>' + milestones +
        '</ul><p>Offline review is not native gameplay or release evidence.</p>'
        '</main></body></html>'
    ).encode("utf-8")
    if len(html) > MAX_HTML_BYTES:
        raise StudioQuestError("quest presentation HTML exceeds byte budget")
    return html
