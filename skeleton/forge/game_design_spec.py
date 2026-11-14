"""Natural-language game brief → versioned design spec.

The compiler is deterministic. A model may propose prose elsewhere; this
control plane is what the game builder commits. Same brief, same spec.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

SCHEMA_VERSION = "skeleton.game_design_spec.v1"
SPEC_VERSION = 1
BRIEF_MAX = 4000
GAMEPLAY_FIELDS = frozenset({"difficulty", "theme", "objective_label", "player_speed", "encounter_style"})
GAMEPLAY_ENUMS = {
    "difficulty": ("easy", "normal", "hard"),
    "theme": ("moss", "neon", "ember", "frost"),
    "encounter_style": ("swarm", "patrol", "ranged"),
}
_GENRE_OBJECTIVES = {
    "top_down_shooter": "Clear the encounters and reach the exit",
    "platformer": "Reach the far gate",
    "rpg_roguelike": "Recover the relic and return to the exit",
}


class GameplayValidationError(ValueError):
    """Bounded field-level errors; proposals never become executable code."""

    def __init__(self, violations: tuple[str, ...]) -> None:
        self.violations = violations
        super().__init__("invalid gameplay design: " + ", ".join(violations))


def default_gameplay(genre: str = "top_down_shooter") -> dict[str, Any]:
    """Deterministic projection for historical v1 specs without gameplay."""
    if not isinstance(genre, str) or genre not in _GENRE_OBJECTIVES:
        raise ValueError("unsupported gameplay genre")
    return {
        "difficulty": "normal", "theme": "moss",
        "objective_label": _GENRE_OBJECTIVES[genre],
        "player_speed": 230, "encounter_style": "patrol",
    }


def validate_gameplay(value: object, *, genre: str = "top_down_shooter") -> dict[str, Any]:
    """Validate a complete, closed data-only gameplay object without coercion.

    The field itself is optional for legacy spec v1. Once supplied, all five
    keys are mandatory. Neither unknown fields nor partial proposals may be
    silently turned into authority over generated scripts, paths or providers.
    """
    default_gameplay(genre)
    if not isinstance(value, Mapping):
        raise GameplayValidationError(("invalid:gameplay",))
    keys = set(value)
    errors: list[str] = []
    if keys - GAMEPLAY_FIELDS:
        errors.append("unknown:gameplay")
    for key in sorted(GAMEPLAY_FIELDS - keys):
        errors.append("missing:gameplay." + key)
    for key, allowed in GAMEPLAY_ENUMS.items():
        if key in value and (not isinstance(value[key], str) or value[key] not in allowed):
            errors.append("invalid:gameplay." + key)
    if "player_speed" in value and (
            type(value["player_speed"]) is not int or not 120 <= value["player_speed"] <= 360):
        errors.append("invalid:gameplay.player_speed")
    if "objective_label" in value:
        label = value["objective_label"]
        valid = isinstance(label, str) and 1 <= len(label) <= 100 and bool(label.strip())
        if valid:
            try:
                valid = (len(label.encode("utf-8", errors="strict")) <= 400
                         and not any(ord(ch) < 32 or ord(ch) == 127
                                     or ch in "\u2028\u2029" for ch in label))
            except UnicodeError:
                valid = False
        if not valid:
            errors.append("invalid:gameplay.objective_label")
    if errors:
        raise GameplayValidationError(tuple(errors))
    return {key: value[key] for key in sorted(GAMEPLAY_FIELDS)}


def gameplay_for_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Read validated gameplay, retaining legacy v1 specs' default behavior."""
    genre = str(spec.get("genre") or "top_down_shooter")
    return (validate_gameplay(spec["gameplay"], genre=genre) if "gameplay" in spec
            else default_gameplay(genre))


def gameplay_constraints(brief: str) -> dict[str, Any]:
    """Return validated explicit user labels that a model may not override."""
    if not isinstance(brief, str):
        raise ValueError("brief must be a string")
    brief = _clean(brief, BRIEF_MAX)
    selected: dict[str, Any] = {}
    labels = {
        "difficulty": r"difficulty", "theme": r"theme",
        "objective_label": r"objective(?: label)?",
        "player_speed": r"player[ _-]speed",
        "encounter_style": r"encounter[ _-]style",
    }
    for field, label in labels.items():
        for match in re.finditer(r"(?:^|[.;]\s*|\s)(?:" + label + r")\s*:\s*([^.;]*)", brief, re.I):
            raw = match.group(1).strip()
            if field == "player_speed":
                # No float, sign, scientific notation, booleans or coercion.
                if (re.fullmatch(r"[0-9]{1,3}", raw) is None
                        or re.match(r"\.\d", brief[match.end():])):
                    raise GameplayValidationError(("invalid:gameplay.player_speed",))
                parsed: Any = int(raw)
            else:
                parsed = raw.lower() if field in GAMEPLAY_ENUMS else raw
            if field in selected and selected[field] != parsed:
                raise GameplayValidationError(("conflicting:gameplay." + field,))
            selected[field] = parsed
    validated = validate_gameplay({**default_gameplay(_genre(brief)), **selected}, genre=_genre(brief))
    return {key: validated[key] for key in selected}


def _brief_gameplay(brief: str, genre: str) -> dict[str, Any]:
    return validate_gameplay({**default_gameplay(genre), **gameplay_constraints(brief)}, genre=genre)

_WORD = re.compile(r"[a-z0-9][a-z0-9'+-]*", re.I)
_FANTASY = re.compile(r"fantasy:\s*([^.]{1,180})", re.I)
_LOOP = re.compile(r"core loop:\s*([^.]{1,180})", re.I)

# Earliest keyword in the brief wins a tie. Stems are closed; free text never
# names an engine class.
_GENRES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("top_down_shooter", ("top-down", "topdown", "twin-stick", "twinstick", "shooter", "shoot", "bullet", "horde")),
    ("platformer", ("platformer", "platform", "side-scroll", "sidescroll", "jump", "ledge")),
    ("rpg_roguelike", ("roguelike", "rogue-like", "roguelite", "rpg", "dungeon", "permadeath", "quest")),
)

_LOOP_TEXT = {
    "top_down_shooter": "Move, aim, and clear encounters, then spend the salvage.",
    "platformer": "Run and jump across the gaps until the goal.",
    "rpg_roguelike": "Enter rooms, resolve encounters, pay the sink, and follow the narrative hook.",
}

_STOP = frozenset({
    "a", "an", "the", "and", "or", "of", "in", "on", "with", "for", "to", "from",
    "small", "medium", "large", "prototype", "game", "brief", "fantasy", "core",
    "loop", "scope", "set",
})

GOLDEN_BRIEFS: tuple[dict[str, str], ...] = (
    {
        "id": "top_down_shooter",
        "genre": "top_down_shooter",
        "brief": (
            "A small top-down shooter. Fantasy: ash-choked service tunnels under a silent city. "
            "Core loop: move, aim, and clear enemy packs, then spend salvage. Scope: small prototype."
        ),
    },
    {
        "id": "platformer",
        "genre": "platformer",
        "brief": (
            "A small platformer. Fantasy: rain-slick ledges above a drowned switchyard. "
            "Core loop: run and jump from ledge to ledge until the far gate. Scope: small prototype."
        ),
    },
    {
        "id": "rpg_roguelike",
        "genre": "rpg_roguelike",
        "brief": (
            "A small roguelike RPG. Fantasy: a cinder delve that forgets dead explorers. "
            "Core loop: enter rooms, fight, pay the vendor, and follow the quest hook. Scope: small prototype."
        ),
    },
)


def _clean(text: str, limit: int) -> str:
    collapsed = " ".join(text.split())
    return collapsed[:limit].strip()


def _genre(brief: str) -> str:
    lowered = brief.lower()
    best_at = len(lowered) + 1
    best = "top_down_shooter"
    found = False
    for name, stems in _GENRES:
        positions = [lowered.find(stem) for stem in stems if stem in lowered]
        if not positions:
            continue
        at = min(position for position in positions if position >= 0)
        if not found or at < best_at:
            best = name
            best_at = at
            found = True
    return best


def _scope(brief: str) -> str:
    lowered = brief.lower()
    if "large" in lowered or "campaign" in lowered:
        return "large"
    if "medium" in lowered:
        return "medium"
    return "small"


def _title(brief: str, genre: str, fantasy: str) -> str:
    source = fantasy or brief
    words = []
    for raw in _WORD.findall(source):
        token = raw.strip("'+-").lower()
        if len(token) < 3 or token in _STOP:
            continue
        words.append(token)
        if len(words) == 4:
            break
    if not words:
        words = genre.split("_")[:3]
    return _clean(" ".join(word.capitalize() for word in words), 48)


def compile_brief(brief: str, *, era: str = "") -> dict[str, Any]:
    """Compile one brief into ``skeleton.game_design_spec.v1``."""
    if not isinstance(brief, str):
        raise ValueError("brief must be a string")
    text = _clean(brief, BRIEF_MAX)
    if not text:
        raise ValueError("brief is required")
    if not isinstance(era, str):
        raise ValueError("era must be a string")
    genre = _genre(text)
    fantasy_match = _FANTASY.search(text)
    loop_match = _LOOP.search(text)
    fantasy = _clean(fantasy_match.group(1) if fantasy_match else text, 180)
    core_loop = _clean(loop_match.group(1) if loop_match else _LOOP_TEXT[genre], 180)
    body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "version": SPEC_VERSION,
        "title": _title(text, genre, fantasy),
        "genre": genre,
        "fantasy": fantasy,
        "core_loop": core_loop,
        "scope": _scope(text),
        "era": _clean(era, 80),
        "brief": text,
        "systems": [
            "levels",
            "encounters",
            "economy",
            "combat",
            "narrative",
            "animation",
            "vfx",
            "physics",
        ],
        "engine": "godot4",
        "gameplay": _brief_gameplay(text, genre),
    }
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    body["spec_id"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return body


def spec_digest(spec: Mapping[str, Any]) -> str:
    if not isinstance(spec, Mapping):
        raise ValueError("spec must be a mapping")
    encoded = json.dumps(dict(spec), sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
