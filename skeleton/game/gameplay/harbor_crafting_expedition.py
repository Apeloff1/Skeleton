"""Complete original playable expedition: survey + weather + earned NPC dialogue.

One canonical source and one legal action history power all three gameplay
systems. A dialogue action advances canonical time, survey locations come from
actual movement, and weather enforces energy before a result is exportable.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, _identifier, _keys, canonical, digest,
    validate_source,
)
from .harbor_crafting_dialogue import (
    build_dialogue_game, validate_dialogue_board, verify_dialogue_game,
)
from .harbor_crafting_survey import build_survey, validate_board, verify_survey
from .harbor_crafting_weather import (
    build_weather_game, validate_weather, verify_weather_game, weather_at,
)

SCHEMA = "skeleton.game.harbor.expedition.v1"
PACKAGE_SCHEMA = "skeleton.game.harbor.expedition-package.v1"
PLAY_SCHEMA = "skeleton.game.harbor.expedition-play.v1"
MAX_REPORT_BYTES = MAX_BUNDLE_BYTES * 10
MAX_PACKAGE_BYTES = 65536
MAX_PLAY_BYTES = MAX_REPORT_BYTES + MAX_PACKAGE_BYTES + 8192
FIELDS = {
    "schema", "source", "survey_board", "weather_board", "dialogue_board",
    "input_actions", "dialogue", "survey", "weather", "complete",
    "expedition_digest",
}
PACKAGE_FIELDS = {
    "schema", "id", "source", "survey_board", "weather_board",
    "dialogue_board", "package_digest",
}


def build_expedition(source: Any, survey_board: Any, weather_board: Any,
                     dialogue_board: Any, actions: Any, *,
                     require_complete: bool = False) -> dict[str, Any]:
    world = validate_source(source)
    survey_rules = validate_board(survey_board, world)
    weather_rules = validate_weather(weather_board, world)
    dialogue_rules = validate_dialogue_board(dialogue_board, world)
    dialogue = build_dialogue_game(world, dialogue_rules, actions)
    canonical_actions = [event["action"] for event in dialogue["bundle"]["events"]]
    survey = build_survey(world, survey_rules, canonical_actions)
    weather = build_weather_game(world, weather_rules, canonical_actions)
    if (survey["bundle"] != dialogue["bundle"]
            or weather["bundle"] != dialogue["bundle"]):
        raise HarborError("expedition canonical gameplay divergence")
    complete = (
        survey["complete"]
        and dialogue["bundle"]["state"]["ending"] is not None
        and dialogue_rules["required_flag_for_delivery"] in dialogue["flags"]
    )
    if require_complete and not complete:
        raise HarborError("expedition victory not earned")
    report = {
        "schema": SCHEMA, "source": world,
        "survey_board": survey_rules, "weather_board": weather_rules,
        "dialogue_board": dialogue_rules,
        "input_actions": deepcopy(dialogue["input_actions"]),
        "dialogue": dialogue, "survey": survey, "weather": weather,
        "complete": complete,
    }
    report["expedition_digest"] = digest(report)
    if len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("expedition report exceeds byte limit")
    return report


def verify_expedition(report: Any, *, require_complete: bool = False) -> dict[str, Any]:
    _keys(report, FIELDS, "expedition report")
    if report["schema"] != SCHEMA or len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("unsupported or oversized expedition report")
    if report["expedition_digest"] != digest({
        key: value for key, value in report.items() if key != "expedition_digest"
    }):
        raise HarborError("expedition digest mismatch")
    verify_dialogue_game(report["dialogue"])
    verify_survey(report["survey"])
    verify_weather_game(report["weather"])
    rebuilt = build_expedition(
        report["source"], report["survey_board"], report["weather_board"],
        report["dialogue_board"], report["input_actions"],
        require_complete=require_complete,
    )
    if rebuilt != report:
        raise HarborError("expedition replay mismatch")
    return {
        "complete": rebuilt["complete"],
        "ending": rebuilt["dialogue"]["bundle"]["state"]["ending"],
        "score": rebuilt["survey"]["score"],
        "energy": rebuilt["weather"]["energy"],
        "flags": deepcopy(rebuilt["dialogue"]["flags"]),
        "expedition_digest": rebuilt["expedition_digest"],
    }


def resume_expedition(report: Any, actions: Any, *,
                      expected_digest: str, require_complete: bool = False) -> dict[str, Any]:
    status = verify_expedition(report)
    if type(expected_digest) is not str or expected_digest != status["expedition_digest"]:
        raise HarborError("stale expedition checkpoint")
    if report["dialogue"]["bundle"]["state"]["ending"] is not None:
        raise HarborError("expedition already complete")
    if not isinstance(actions, list):
        raise HarborError("expedition continuation must be a list")
    advanced = build_expedition(
        report["source"], report["survey_board"], report["weather_board"],
        report["dialogue_board"], report["input_actions"] + actions,
        require_complete=require_complete,
    )
    for key, field in (("dialogue", "events"), ("survey", "bundle"), ("weather", "events")):
        old = report[key][field]
        new = advanced[key][field]
        if key == "survey":
            old, new = old["events"], new["events"]
        if new[:len(old)] != old:
            raise HarborError("expedition continuation rewrote history")
    return advanced


def expedition_status(report: Any) -> dict[str, Any]:
    status = verify_expedition(report)
    visited = {entry["id"] for entry in report["survey"]["visits"]}
    pending = [
        site["id"] for site in report["survey_board"]["sites"]
        if site["required"] and site["id"] not in visited
    ]
    tick = report["dialogue"]["bundle"]["state"]["tick"]
    next_tick = min(tick + 1, report["source"]["max_ticks"])
    return {
        "complete": status["complete"], "ending": status["ending"],
        "tick": tick, "energy": status["energy"], "score": status["score"],
        "required_sites_remaining": pending,
        "delivery_permit": report["dialogue_board"]["required_flag_for_delivery"]
                           in status["flags"],
        "next_weather": weather_at(report["weather_board"], next_tick),
        "expedition_digest": status["expedition_digest"],
    }


def build_expedition_package(identifier: str, source: Any, survey_board: Any,
                             weather_board: Any, dialogue_board: Any) -> dict[str, Any]:
    world = validate_source(source)
    package = {
        "schema": PACKAGE_SCHEMA, "id": _identifier(identifier, "expedition id"),
        "source": world,
        "survey_board": validate_board(survey_board, world),
        "weather_board": validate_weather(weather_board, world),
        "dialogue_board": validate_dialogue_board(dialogue_board, world),
    }
    package["package_digest"] = digest(package)
    if len(canonical(package)) > MAX_PACKAGE_BYTES:
        raise HarborError("expedition package exceeds byte limit")
    return package


def verify_expedition_package(package: Any) -> dict[str, Any]:
    _keys(package, PACKAGE_FIELDS, "expedition package")
    if package["schema"] != PACKAGE_SCHEMA or len(canonical(package)) > MAX_PACKAGE_BYTES:
        raise HarborError("unsupported or oversized expedition package")
    if package["package_digest"] != digest({
        key: value for key, value in package.items() if key != "package_digest"
    }):
        raise HarborError("expedition package digest mismatch")
    rebuilt = build_expedition_package(
        package["id"], package["source"], package["survey_board"],
        package["weather_board"], package["dialogue_board"],
    )
    if rebuilt != package:
        raise HarborError("expedition package replay mismatch")
    return {"id": rebuilt["id"], "package_digest": rebuilt["package_digest"]}


def play_expedition_package(package: Any, actions: Any, *,
                            require_complete: bool = False) -> dict[str, Any]:
    verify_expedition_package(package)
    report = build_expedition(
        package["source"], package["survey_board"], package["weather_board"],
        package["dialogue_board"], actions, require_complete=require_complete,
    )
    play = {"schema": PLAY_SCHEMA, "package": deepcopy(package), "report": report}
    play["play_digest"] = digest(play)
    if len(canonical(play)) > MAX_PLAY_BYTES:
        raise HarborError("expedition package play exceeds byte limit")
    return play


def verify_expedition_package_play(play: Any, *,
                                   require_complete: bool = False) -> dict[str, Any]:
    _keys(play, {"schema", "package", "report", "play_digest"}, "expedition package play")
    if play["schema"] != PLAY_SCHEMA or len(canonical(play)) > MAX_PLAY_BYTES:
        raise HarborError("unsupported or oversized expedition package play")
    if play["play_digest"] != digest({
        key: value for key, value in play.items() if key != "play_digest"
    }):
        raise HarborError("expedition package play digest mismatch")
    verify_expedition(play["report"], require_complete=require_complete)
    rebuilt = play_expedition_package(
        play["package"], play["report"]["input_actions"],
        require_complete=require_complete,
    )
    if rebuilt != play:
        raise HarborError("expedition package play replay mismatch")
    return {
        "complete": rebuilt["report"]["complete"],
        "expedition_digest": rebuilt["report"]["expedition_digest"],
        "package_digest": rebuilt["package"]["package_digest"],
    }
