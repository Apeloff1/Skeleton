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
    }
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    body["spec_id"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return body


def spec_digest(spec: Mapping[str, Any]) -> str:
    if not isinstance(spec, Mapping):
        raise ValueError("spec must be a mapping")
    encoded = json.dumps(dict(spec), sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
