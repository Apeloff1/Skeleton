"""Canonical 2–30-game comparative study contract for existing Jeeves libretro owners.

One study can cover large series and non-contiguous installments, but can run
no more than ten games concurrently. Releases and gameplay checkpoints are
different axes. No ROM bytes, bios files or copied gameplay expression are part
of a study manifest.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from typing import Any

SCHEMA = "skeleton.game.comparative_study.v1"
MAX_GAMES = 30
MAX_ACTIVE = 10
MAX_PAIRS = MAX_GAMES * (MAX_GAMES - 1) // 2
MAX_NOTES = 1500
MAX_MANIFEST_BYTES = 1024 * 1024
ID = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
PHASES = ("earlier", "middle", "after")
DIMENSIONS = frozenset({
    "movement", "input", "combat", "navigation", "story", "dialogue",
    "camera", "cutscene", "character", "npc", "environment", "pacing",
    "challenge", "reward", "audio", "music", "ambience", "visuals",
    "interface", "accessibility", "emergence", "economy", "physics",
    "mission", "level_design", "consequence", "world_design", "other",
})
AUTHORS = frozenset({"viewer", "user", "jeeves", "dragon", "reviewer"})
CLAIMS = frozenset({"observation", "interpretation", "hypothesis"})
REVIEW = frozenset({"pending", "reviewed", "rejected"})
NOTES_CAP = 1000
MAX_TEXT = 1200
MAX_TAPE = 64


class ComparativeStudyError(ValueError):
    """Study metadata violates bounded identity, chronology or provenance."""


def _fail(reason: str) -> None:
    raise ComparativeStudyError(reason)


def _text(value: object, field: str, *, limit: int = MAX_TEXT, empty: bool = False) -> str:
    if type(value) is not str or len(value.encode("utf-8")) > limit or (not empty and not value.strip()):
        _fail("Invalid bounded " + field)
    if any(ord(c) < 32 and c not in "\t" for c in value):
        _fail("Control characters are forbidden in " + field)
    return value.strip()


def _id(value: object, field: str) -> str:
    if type(value) is not str or not ID.fullmatch(value):
        _fail(field + " must be a normalized short identifier")
    return value


def _sha(value: object, field: str) -> str:
    if type(value) is not str or not SHA.fullmatch(value):
        _fail(field + " requires an exact lowercase SHA-256")
    return value


def canonical(value: object) -> bytes:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    if len(encoded) > 32 * 1024 * 1024:
        _fail("Comparative study evidence exceeds bounded JSON capacity")
    return encoded


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def parse_json(raw: bytes, *, limit: int = MAX_MANIFEST_BYTES) -> Any:
    if type(raw) is not bytes or len(raw) > limit:
        _fail("Study JSON exceeds its exact byte limit")

    def pairs(items):
        result = {}
        for name, value in items:
            if name in result:
                _fail("Duplicate JSON keys are forbidden")
            result[name] = value
        return result

    def constant(_):
        _fail("Nonfinite JSON constants are forbidden")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ComparativeStudyError("Invalid study JSON") from exc


def _questions(value: object) -> list[str]:
    if not isinstance(value, list) or len(value) > 12:
        _fail("Comparison questions exceed twelve bounded entries")
    return [_text(x, "comparison question", limit=240) for x in value]


def validate_study(raw: object) -> dict[str, Any]:
    """Fail closed before any emulator is loaded; return normalized JSON metadata."""
    if not isinstance(raw, dict):
        _fail("Comparative study must be a JSON object")
    fields = {"schema_version", "study_id", "title", "games", "pairs", "notes", "max_active"}
    if set(raw) != fields or raw["schema_version"] != SCHEMA:
        _fail("Comparative study schema differs")
    study_id = _id(raw["study_id"], "study_id")
    title = _text(raw["title"], "study title", limit=200)
    games = raw["games"]
    if not isinstance(games, list) or not 2 <= len(games) <= MAX_GAMES:
        _fail("Comparative study requires 2–30 distinct game variants")
    active = raw["max_active"]
    if type(active) is not int or not 1 <= active <= MAX_ACTIVE:
        _fail("At most ten active emulators are allowed")
    from .game_emulator_host import _ACTIONS, _KEY_ACTIONS, _controller_ports
    from .game_emulator_catalog import canonical_targets, _CORE_TARGET_GROUPS

    allowed_actions = set((*_ACTIONS, *_KEY_ACTIONS))
    allowed_targets = canonical_targets()
    normalized = []
    seen = set()
    for index, game in enumerate(games):
        fields = {
            "id", "title", "series_id", "release_order", "release_year",
            "series_phase", "target_id", "core_id", "source_path",
            "source_sha256", "rights_evidence_digest", "actions",
            "seed", "frames_per_step", "controller_devices",
        }
        if not isinstance(game, dict) or set(game) != fields:
            _fail("Game row must contain the exact pinned manifest fields")
        identity = _id(game["id"], "game id")
        if identity in seen:
            _fail("Game IDs must be distinct")
        seen.add(identity)
        series_id = _id(game["series_id"], "series_id")
        order = game["release_order"]
        year = game["release_year"]
        if type(order) is not int or not 1 <= order <= 1000000:
            _fail("Release order must be a positive indexed series position")
        if year is not None and (type(year) is not int or not 1950 <= year <= 2200):
            _fail("Optional release year must be bounded and historically plausible")
        if game["series_phase"] not in PHASES:
            _fail("Series phase must be earlier, middle or after")
        target = _id(game["target_id"], "hardware target")
        core = _id(game["core_id"], "libretro core")
        if target not in allowed_targets or target not in _CORE_TARGET_GROUPS.get(core, ()):
            _fail("Game core is not declared for its canonical hardware target")
        path = _text(game["source_path"], "operator ROM path", limit=2048)
        if not path.startswith("/") or "\x00" in path:
            _fail("Operator ROM source must use an absolute local file path")
        sha = _sha(game["source_sha256"], "expected original ROM content")
        rights = game["rights_evidence_digest"]
        if rights is not None:
            _sha(rights, "operator rights record")
        actions = game["actions"]
        if not isinstance(actions, list) or not 3 <= len(actions) <= MAX_TAPE:
            _fail("A game requires 3–64 actual input actions for three observations")
        if any(type(action) is not str or action not in allowed_actions for action in actions):
            _fail("Unknown policy action in game tape")
        seed = game["seed"]
        frames = game["frames_per_step"]
        if type(seed) is not int or not 0 <= seed < 2**63:
            _fail("Game seed is outside the bounded native episode domain")
        if type(frames) is not int or not 1 <= frames <= 8:
            _fail("Game frame cadence exceeds eight frames per policy action")
        devices = _controller_ports(game["controller_devices"])
        normalized.append({
            "id": identity, "title": _text(game["title"], "game title", limit=240),
            "series_id": series_id, "release_order": order, "release_year": year,
            "series_phase": game["series_phase"], "target_id": target, "core_id": core,
            "source_path": path, "source_sha256": sha,
            "rights_evidence_digest": rights, "actions": list(actions),
            "seed": seed, "frames_per_step": frames,
            "controller_devices": list(devices),
        })
    # Multiple core/edition variants of one installment are valid distinct
    # game rows; chronology remains ordered by release_order, then game id.
    chronological = {}
    for game in normalized:
        key = (game["series_id"], game["release_order"])
        previous = chronological.get(key)
        if previous and previous["release_year"] != game["release_year"]:
            _fail("Variants of one series installment must agree on release year")
        chronological[key] = game
    # Series phase is an operator-declared ordinal grouping, not automatically
    # derived from years. Reject chronology going backwards within a series.
    priority = {"earlier": 0, "middle": 1, "after": 2}
    for series_id in {g["series_id"] for g in normalized}:
        installments = sorted((g for g in normalized if g["series_id"] == series_id), key=lambda g: g["release_order"])
        stages = [priority[g["series_phase"]] for g in installments]
        if stages != sorted(stages):
            _fail("Series phases contradict declared release ordering")
        years = [g["release_year"] for g in installments]
        if all(x is not None for x in years) and years != sorted(years):
            _fail("Series release years contradict release order")
    pairs = raw["pairs"]
    if not isinstance(pairs, list) or len(pairs) > MAX_PAIRS:
        _fail("Comparison pairs exceed the 30-title capacity")
    pair_seen = set()
    checked_pairs = []
    for pair in pairs:
        if not isinstance(pair, dict) or set(pair) != {"left_id", "right_id", "questions"}:
            _fail("Comparisons require two game identities and review questions")
        left, right = _id(pair["left_id"], "left game"), _id(pair["right_id"], "right game")
        if left not in seen or right not in seen or left == right:
            _fail("Comparisons must reference distinct games present in this study")
        pair_id = tuple(sorted((left, right)))
        if pair_id in pair_seen:
            _fail("The same unordered game comparison may not repeat")
        pair_seen.add(pair_id)
        checked_pairs.append({"left_id": left, "right_id": right, "questions": _questions(pair["questions"])})
    if not checked_pairs:
        # All-pairs review is metadata-only and bounded at 435 pairs for 30 games.
        # It does not launch 435 extra emulator sessions.
        checked_pairs = [
            {"left_id": left["id"], "right_id": right["id"], "questions": []}
            for position, left in enumerate(normalized)
            for right in normalized[position + 1:]
        ]
    notes = raw["notes"]
    if not isinstance(notes, list) or len(notes) > MAX_NOTES:
        _fail("Notes exceed bounded study note capacity")
    clean_notes = [validate_note(note, game_ids=seen) for note in notes]
    if len({n["note_id"] for n in clean_notes}) != len(clean_notes):
        _fail("Note IDs must be unique")
    return {
        "schema_version": SCHEMA, "study_id": study_id, "title": title,
        "games": normalized, "pairs": checked_pairs, "notes": clean_notes,
        "max_active": active,
    }


def validate_note(note: object, *, game_ids: set[str]) -> dict[str, Any]:
    fields = {"note_id", "author", "game_ids", "checkpoint", "dimension", "claim_type", "text", "review_status", "build_parameter"}
    if not isinstance(note, dict) or set(note) != fields:
        _fail("Viewer/Dragon note must have the exact bounded schema")
    ids = note["game_ids"]
    if not isinstance(ids, list) or not 1 <= len(ids) <= 30 or any(_id(i, "note game") not in game_ids for i in ids):
        _fail("Note must link to identified games, not an unauthenticated freeform reference")
    if len(ids) != len(set(ids)):
        _fail("Note cannot repeat a game identifier")
    if note["author"] not in AUTHORS or note["checkpoint"] not in (*PHASES, "series"):
        _fail("Note author or observational timepoint is unknown")
    if note["dimension"] not in DIMENSIONS or note["claim_type"] not in CLAIMS or note["review_status"] not in REVIEW:
        _fail("Notes must classify dimension, epistemic status and review")
    parameter = note["build_parameter"]
    if parameter is not None:
        if (not isinstance(parameter, dict) or set(parameter) != {"name", "value", "units"}
            or type(parameter["value"]) not in (float, int)
            or not math.isfinite(parameter["value"])
            or abs(parameter["value"]) > 1_000_000):
            _fail("Build parameter is a bounded numeric hypothesis, not an executable change")
        parameter = {
            "name": _id(parameter["name"], "candidate build parameter"),
            "value": parameter["value"],
            "units": _text(parameter["units"], "build parameter units", limit=64),
        }
    return {
        "note_id": _id(note["note_id"], "note identity"),
        "author": note["author"], "game_ids": list(ids),
        "checkpoint": note["checkpoint"], "dimension": note["dimension"],
        "claim_type": note["claim_type"],
        "text": _text(note["text"], "annotated viewer note", limit=NOTES_CAP),
        "review_status": note["review_status"],
        "build_parameter": parameter,
    }


def plan_study(study: Mapping[str, Any]) -> dict[str, Any]:
    """Build a viewable, non-executing plan; per-game series order survives 30-game slices."""
    model = validate_study(dict(study))
    games = model["games"]
    batches = []
    for index in range(0, len(games), model["max_active"]):
        batches.append({
            "batch_index": len(batches),
            "game_ids": [g["id"] for g in games[index:index + model["max_active"]]],
            "max_simultaneous_games": min(model["max_active"], len(games) - index),
            "status": "not_executed",
        })
    series = {}
    for game in games:
        series.setdefault(game["series_id"], []).append({
            "game_id": game["id"],
            "release_order": game["release_order"],
            "release_year": game["release_year"],
            "series_phase": game["series_phase"],
        })
    for installments in series.values():
        installments.sort(key=lambda row: row["release_order"])
    return {
        "schema_version": "skeleton.game.comparative_study_plan.v1",
        "study_id": model["study_id"],
        "study_digest": digest(model),
        "title": model["title"],
        "game_count": len(games), "concurrent_limit": model["max_active"],
        "batches": batches, "series": series,
        "pair_count": len(model["pairs"]), "comparisons": model["pairs"],
        "user_and_dragon_note_count": len(model["notes"]),
        "real_emulation_executed": False,
        "model_training_performed": False,
        "large_series_policy": "Use stable series_id and release_order across independently bounded studies; no claimed automatic acquisition of every installment.",
    }
