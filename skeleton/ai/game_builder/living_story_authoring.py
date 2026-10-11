"""Human-authored original living worlds: safe, real data-only RPG editing.

Author full NPC rosters, region links, schedules, role/faction identity and
quest premises in an offline JSON blueprint. The exact document is checked
against the typed StoryWorld graph and independently solvable before any code
or consumer output is generated. No arbitrary scripts, art, URLs or plugins
are ever deserialized as executable game instructions.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from .contracts import canonical_digest, canonical_json
from .living_story_runtime import (
    StoryIntent, StoryWorld, Region, Citizen, Quest, StoryError,
    original_story_world, demonstrate_story,
)
from .authored_tiles import _no_duplicate_keys, _json_number_reject


class StoryAuthoringError(ValueError):
    """Authored story input is incomplete, unsafe, or unplayable."""


AUTHORED_STORY_SCHEMA = "skeleton.game_builder.original_story_blueprint.v1"
MAX_DOCUMENT_BYTES = 180_000
MAX_TEXT_LENGTH = 200


@dataclass(frozen=True, slots=True)
class AuthoredStory:
    world: StoryWorld
    source_sha256: str
    proof_digest: str
    proof_steps: int

    def evidence(self) -> dict[str, object]:
        return {
            "schema": "skeleton.game_builder.authored_story_handoff.v1",
            "world_digest": self.world.digest,
            "story_intent_digest": canonical_digest(self.world.intent.payload()),
            "source_sha256": self.source_sha256,
            "proof_digest": self.proof_digest,
            "proof_steps": self.proof_steps,
            "original_human_reviewed_text": True,
            "scripts_imported": False,
            "media_imported": False,
            "model_training": False,
            "legally_cleared_for_publication": False,
        }


def blueprint_document(world: StoryWorld, *, authorized: bool) -> dict[str, object]:
    if not authorized:
        raise PermissionError("authoring template generation requires an operator")
    if not isinstance(world, StoryWorld):
        raise StoryAuthoringError("typed original game required")
    return {**world.payload(), "schema": AUTHORED_STORY_SCHEMA}


def _text(value: Any, *, limit: int, field: str) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= limit
            or value != value.strip() or any(ord(ch) < 32 for ch in value)):
        raise StoryAuthoringError("invalid authoring text: " + field)
    try:
        value.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise StoryAuthoringError("invalid Unicode in story blueprint") from exc
    return value


def _row(value: object, required: tuple[str, ...], title: str) -> dict:
    if not isinstance(value, dict) or set(value) != set(required):
        raise StoryAuthoringError(f"{title} must use the exact supported fields")
    return value


def _rows(value: object, length: int, fields: tuple[str, ...], title: str):
    if not isinstance(value, list) or len(value) != length:
        raise StoryAuthoringError(f"{title} count differs from story budget")
    return [_row(item, fields, title) for item in value]


def compile_authored_story(
    intent: StoryIntent,
    document: dict[str, object],
    *,
    human_reviewed: bool,
    authorized: bool,
    source_digest: str | None = None,
) -> AuthoredStory:
    if not authorized:
        raise PermissionError("custom NPC world execution requires operator authorization")
    if human_reviewed is not True:
        raise StoryAuthoringError("custom NPCs, stories and quests require human review")
    if not isinstance(intent, StoryIntent):
        raise StoryAuthoringError("typed original story intent required")
    _row(document, ("schema", "intent", "regions", "citizens", "quests"),
         "original story document")
    if document["schema"] != AUTHORED_STORY_SCHEMA or document["intent"] != intent.payload():
        raise StoryAuthoringError("custom NPC blueprint changes original project identity")
    regions_raw = _rows(document["regions"], intent.regions,
                        ("key", "name", "neighbors", "atmosphere"), "region")
    citizens_raw = _rows(document["citizens"], intent.population,
                         ("key", "name", "role", "faction", "home",
                          "workplace", "lookout", "temperament"), "citizen")
    quests_raw = _rows(document["quests"], 3,
                       ("key", "giver", "item", "source_region", "faction",
                        "reward", "premise"), "quest")
    regions = []
    for index, row in enumerate(regions_raw):
        if row["key"] != f"region_{index:02d}":
            raise StoryAuthoringError("stable original region identity required")
        if (not isinstance(row["neighbors"], list)
                or not 1 <= len(row["neighbors"]) <= intent.regions - 1
                or any(not isinstance(x, str) or not re.fullmatch(r"region_\d\d", x)
                       for x in row["neighbors"])
                or len(set(row["neighbors"])) != len(row["neighbors"])):
            raise StoryAuthoringError("invalid original region graph connections")
        regions.append(Region(
            row["key"], _text(row["name"], limit=80, field="region name"),
            tuple(row["neighbors"]),
            _text(row["atmosphere"], limit=100, field="atmosphere"),
        ))
    citizens = []
    for index, row in enumerate(citizens_raw):
        if row["key"] != f"npc_{index:03d}":
            raise StoryAuthoringError("stable NPC identity required")
        if not isinstance(row["faction"], str):
            raise StoryAuthoringError("invalid NPC faction")
        citizens.append(Citizen(
            row["key"],
            _text(row["name"], limit=80, field="citizen name"),
            _text(row["role"], limit=30, field="citizen occupation"),
            row["faction"], row["home"], row["workplace"], row["lookout"],
            _text(row["temperament"], limit=30, field="NPC disposition"),
        ))
    quests = []
    for index, row in enumerate(quests_raw):
        if row["key"] != f"quest_{index:02d}" or row["item"] != f"artifact_{index:02d}":
            raise StoryAuthoringError("quest identity and original collectible identity are stable")
        if type(row["reward"]) is not int or not 1 <= row["reward"] <= 200:
            raise StoryAuthoringError("original quest reward outside bounded economy")
        quests.append(Quest(
            row["key"], row["giver"], row["item"], row["source_region"],
            row["faction"], row["reward"],
            _text(row["premise"], limit=MAX_TEXT_LENGTH, field="original quest premise"),
        ))
    try:
        world = StoryWorld(intent, tuple(regions), tuple(citizens), tuple(quests))
        proof = demonstrate_story(world, authorized=True)
    except StoryError as exc:
        raise StoryAuthoringError("custom NPC/quest scenario violates graph or playability") from exc
    if source_digest is None:
        source_digest = sha256((canonical_json(document) + "\n").encode()).hexdigest()
    if not isinstance(source_digest, str) or not re.fullmatch("[a-f0-9]{64}", source_digest):
        raise StoryAuthoringError("source identity must be a SHA-256 content digest")
    return AuthoredStory(world, source_digest, proof.digest, proof.final.turn)


def read_story_blueprint(
    intent: StoryIntent, source: str | Path,
    *, human_reviewed: bool, authorized: bool,
) -> AuthoredStory:
    if not authorized:
        raise PermissionError("custom story import requires authorization")
    file = Path(source)
    if file.is_symlink() or not file.is_file() or file.stat().st_size > MAX_DOCUMENT_BYTES:
        raise StoryAuthoringError("original blueprint must be a regular file below 180 KB")
    data = file.read_bytes()
    if len(data) > MAX_DOCUMENT_BYTES:
        raise StoryAuthoringError("custom story document exceeds input budget")
    try:
        payload = json.loads(
            data.decode("utf-8", "strict"),
            object_pairs_hook=_no_duplicate_keys,
            parse_constant=_json_number_reject,
        )
    except (ValueError, UnicodeError, TypeError) as exc:
        raise StoryAuthoringError("custom story JSON ambiguous or corrupt") from exc
    if not isinstance(payload, dict):
        raise StoryAuthoringError("blueprint JSON object required")
    return compile_authored_story(
        intent, payload, human_reviewed=human_reviewed,
        authorized=True, source_digest=sha256(data).hexdigest(),
    )


__all__ = [
    "StoryAuthoringError", "AuthoredStory", "AUTHORED_STORY_SCHEMA",
    "blueprint_document", "compile_authored_story", "read_story_blueprint",
]
