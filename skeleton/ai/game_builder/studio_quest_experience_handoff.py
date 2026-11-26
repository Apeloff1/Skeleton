"""Cross-feature original quest experience compilation with exact replay parity.

Binds localization, sandbox achievements, pacing and content advisories to
one canonical authored session. Never upgrades presentation metadata into
native runtime, player consent, provenance or release evidence.
"""
from __future__ import annotations

from html import escape
import os
from pathlib import Path
import secrets
from typing import Any, Mapping

from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, replay_quest,
)
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
)
from .studio_quest_private_io import read_studio_private_json
from .studio_quest_presentation_bundle import (
    compile_quest_presentation_bundle, compile_quest_presentation_handoff,
)
from .studio_quest_pacing import replay_quest_pacing, compile_pacing_handoff
from .studio_quest_advisories import (
    TOPICS, replay_quest_advisories, evaluate_player_advisories,
    compile_advisory_handoff,
)

SCHEMA = "skeleton.game_builder.studio_quest_experience_bundle.v1"
HANDOFF_SCHEMA = "skeleton.game_builder.studio_quest_experience_handoff.v1"
FILENAME = "studio_quest_experience.json"
MAX_SOURCE_BYTES = 256 * 1024
MAX_BUNDLE_BYTES = 256 * 1024
MAX_HTML_BYTES = 256 * 1024


def _accepted(value: object) -> list[str]:
    if (type(value) is not list or len(value) > len(TOPICS)
            or any(type(x) is not str or x not in TOPICS for x in value)
            or value != sorted(set(value))):
        raise StudioQuestError("invalid bounded experience consent topics")
    return list(value)


def compile_quest_experience_bundle(
    documents: Mapping[str, Any], localization: object, achievements: object,
    pacing: object, advisories: object, accepted_topics: object, *,
    authorized: bool,
) -> dict[str, Any]:
    """Preview exact-source compatibility and every unresolved user-facing hold."""
    if authorized is not True:
        raise PermissionError("experience assembly requires authorization")
    before = _canonical(documents)
    if len(before) > MAX_SOURCE_BYTES:
        raise StudioQuestError("experience source exceeds byte budget")
    accepted = _accepted(accepted_topics)
    presentation = compile_quest_presentation_bundle(
        documents, localization, achievements, authorized=True)
    timing = replay_quest_pacing(documents, pacing, authorized=True)
    warnings = replay_quest_advisories(documents, advisories, authorized=True)
    program = compile_quest_program(documents)
    source = program.source_digest
    session = presentation["session_digest"]
    initial = presentation["initial_session_digest"]
    target = presentation["target_ending"]
    # Every authoring record must bind to the same canonical action history,
    # not merely to a coincidentally equal summary or forged receipt flag.
    a = localization["authoring"]["actions"]
    if (any(x["project_id"] != program.project_id
            or x["source_digest"] != source
            or x["session_digest"] != session
            or x["initial_session_digest"] != initial
            or x["target_ending"] != target
            for x in (timing, warnings))
            or timing["authoring"]["actions"] != a
            or warnings["authoring"]["actions"] != a):
        raise StudioQuestError("experience receipts refer to different quest sessions")
    checked_session = replay_quest(documents, a, authorized=True)
    if checked_session.digest != session:
        raise StudioQuestError("experience canonical replay differs")
    consent = None
    if warnings["all_stages_reviewed"]:
        consent = evaluate_player_advisories(
            documents, advisories, accepted, authorized=True)
        if consent["session_digest"] != session:
            raise StudioQuestError("experience consent session differs")
    blockers: list[str] = []
    if not presentation["playable_handoff_allowed"]:
        blockers.append("presentation_not_reviewed_or_ending_ineligible")
    if not timing["played_beats_reviewed"]:
        blockers.append("pacing_played_beats_unreviewed")
    if not timing["within_estimated_budget"]:
        blockers.append("pacing_estimate_exceeds_budget")
    if not timing["target_ending_eligible"]:
        blockers.append("pacing_target_ending_ineligible")
    if not warnings["all_stages_reviewed"]:
        blockers.append("advisory_stage_review_incomplete")
    if not warnings["target_ending_eligible"]:
        blockers.append("advisory_target_ending_ineligible")
    if consent is not None and not consent["can_continue"]:
        blockers.append("player_has_not_accepted_current_warnings")
    if _canonical(documents) != before:
        raise StudioQuestError("experience source changed during assembly")
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "project_id": program.project_id,
        "source_digest": source,
        "initial_session_digest": initial,
        "session_digest": session,
        "target_ending": target,
        "localization_digest": presentation["localization_digest"],
        "achievement_digest": presentation["achievement_digest"],
        "pacing_digest": timing["pacing_digest"],
        "advisory_digest": warnings["advisory_digest"],
        "accepted_topics": accepted,
        "consent_digest": consent["consent_digest"] if consent else None,
        "unaccepted_topics": consent["unaccepted_topics"] if consent else [],
        "estimated_play_seconds": timing["estimated_play_seconds"],
        "sandbox_points": presentation["sandbox_points"],
        "reviewed_locale_rows": presentation["reviewed_row_count"],
        "total_locale_rows": presentation["localized_row_count"],
        "reviewed_advisory_stages": warnings["reviewed_stage_count"],
        "total_advisory_stages": len(program.stages),
        "blocking_reasons": blockers,
        "playable_handoff_allowed": not blockers,
        "duration_is_author_estimate": True,
        "content_safety_inferred": False,
        "external_account_awards_verified": False,
        "canonical_quest_replay_verified": True,
        "native_gameplay_verified": False,
        "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_BUNDLE_BYTES - 128:
        raise StudioQuestError("experience bundle exceeds byte budget")
    result["bundle_digest"] = _digest(result)
    return result


def compile_quest_experience_handoff(
    documents: Mapping[str, Any], localization: object, achievements: object,
    pacing: object, advisories: object, accepted_topics: object, *,
    authorized: bool,
) -> dict[str, Any]:
    bundle = compile_quest_experience_bundle(
        documents, localization, achievements, pacing, advisories,
        accepted_topics, authorized=authorized)
    if not bundle["playable_handoff_allowed"]:
        raise StudioQuestError(
            "experience handoff blocked: " + ",".join(bundle["blocking_reasons"]))
    presentation = compile_quest_presentation_handoff(
        documents, localization, achievements, authorized=True)
    timing = compile_pacing_handoff(documents, pacing, authorized=True)
    warnings = compile_advisory_handoff(documents, advisories, authorized=True)
    consent = evaluate_player_advisories(
        documents, advisories, bundle["accepted_topics"], authorized=True)
    if (not consent["can_continue"]
            or any(x["source_digest"] != bundle["source_digest"]
                   or x["session_digest"] != bundle["session_digest"]
                   for x in (presentation, timing, warnings, consent))):
        raise StudioQuestError("experience handoff source/session/consent diverged")
    result: dict[str, Any] = {
        "schema": HANDOFF_SCHEMA,
        "project_id": bundle["project_id"],
        "source_digest": bundle["source_digest"],
        "session_digest": bundle["session_digest"],
        "bundle_digest": bundle["bundle_digest"],
        "target_ending": bundle["target_ending"],
        "localized_display_rows": presentation["localized_display_rows"],
        "canonical_choices": presentation["canonical_choices"],
        "unlocked_achievements": presentation["unlocked_achievements"],
        "sandbox_points": presentation["sandbox_points"],
        "pacing_timeline": timing["timeline"],
        "estimated_play_seconds": timing["estimated_play_seconds"],
        "advisory_descriptors": warnings["advisories"],
        "current_consent": consent,
        "duration_is_author_estimate": True,
        "content_safety_inferred": False,
        "external_account_awards_verified": False,
        "canonical_quest_replay_verified": True,
        "native_gameplay_verified": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_BUNDLE_BYTES - 128:
        raise StudioQuestError("experience handoff exceeds byte budget")
    result["handoff_digest"] = _digest(result)
    return result


def render_quest_experience_review_html(
    documents: Mapping[str, Any], localization: object, achievements: object,
    pacing: object, advisories: object, accepted_topics: object, *,
    authorized: bool,
) -> bytes:
    bundle = compile_quest_experience_bundle(
        documents, localization, achievements, pacing, advisories,
        accepted_topics, authorized=authorized)
    # A preview does not expose unreviewed advisory text.
    timing = replay_quest_pacing(documents, pacing, authorized=True)
    warnings = replay_quest_advisories(documents, advisories, authorized=True)
    timeline = "".join(
        "<li>" + escape(row["label"]) + " — estimated " +
        str(row["end_seconds"] - row["start_seconds"]) +
        " seconds</li>" for row in timing["timeline"] if row["reviewed"])
    advisory_rows = "".join(
        "<li>" + escape(row["stage_id"]) + ": " +
        escape(row["summary"] or "No declared topics") + "</li>"
        for row in warnings["authoring"]["advisories"] if row["reviewed"])
    holds = "".join("<li>" + escape(x) + "</li>" for x in bundle["blocking_reasons"])
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; connect-src 'none'; base-uri 'none'; form-action 'none'; "
        'object-src \'none\'">'
        '<title>Original quest experience review</title></head><body><main>'
        '<h1>Source-replayed quest experience</h1>'
        '<p>Estimated duration: ' + str(bundle["estimated_play_seconds"]) +
        ' seconds; sandbox points: ' + str(bundle["sandbox_points"]) + '</p>'
        '<h2>Reviewed pacing beats</h2><ol>' + timeline + '</ol>'
        '<h2>Reviewed content advisories</h2><ul>' + advisory_rows + '</ul>'
        '<h2>Blocking conditions</h2><ul>' + holds + '</ul>'
        '<p>No native runtime, safety, account award or release claim.</p>'
        '</main></body></html>'
    ).encode("utf-8")
    if len(html) > MAX_HTML_BYTES:
        raise StudioQuestError("experience preview exceeds HTML budget")
    return html


def publish_quest_experience(
    documents: Mapping[str, Any], localization: object, achievements: object,
    pacing: object, advisories: object, accepted_topics: object, directory: Path,
    *, authorized: bool,
) -> dict[str, Any]:
    bundle = compile_quest_experience_bundle(
        documents, localization, achievements, pacing, advisories,
        accepted_topics, authorized=authorized)
    raw = _canonical(bundle) + b"\n"
    if len(raw) > MAX_BUNDLE_BYTES:
        raise StudioQuestError("experience publication exceeds byte budget")
    fd = _open_directory(directory)
    temporary = ".quest-experience-" + secrets.token_hex(16) + ".tmp"
    created = False
    linked = False
    try:
        before = os.fstat(fd)
        out = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=fd)
        created = True
        try:
            _write_all(out, raw)
            os.fsync(out)
        finally:
            os.close(out)
        os.link(temporary, FILENAME, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        linked = True
        os.fsync(fd)
        verify_fd = _open_directory(directory)
        try:
            after = os.fstat(verify_fd)
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise StudioQuestError("experience output directory changed")
        finally:
            os.close(verify_fd)
    except BaseException:
        if linked:
            os.unlink(FILENAME, dir_fd=fd)
            os.fsync(fd)
        raise
    finally:
        try:
            if created:
                os.unlink(temporary, dir_fd=fd)
        finally:
            os.close(fd)
    return {"path": str(Path(directory) / FILENAME),
            "bundle_digest": bundle["bundle_digest"], "bytes": len(raw),
            "file_write_performed": True, "release_certified": False}


def restore_quest_experience(
    documents: Mapping[str, Any], localization: object, achievements: object,
    pacing: object, advisories: object, accepted_topics: object, directory: Path,
    *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("experience restore requires authorization")
    stored = read_studio_private_json(
        Path(directory) / FILENAME, MAX_BUNDLE_BYTES)
    _lease(stored.get("source_digest"), "experience restore source")
    current = compile_quest_experience_bundle(
        documents, localization, achievements, pacing, advisories,
        accepted_topics, authorized=True)
    if _canonical(current) != _canonical(stored):
        raise StudioQuestError("experience restore differs from canonical replay")
    return current
