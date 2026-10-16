"""Transactional, declarative narrative/scene revisions for reviewed Director worlds.

No arbitrary Python expressions or game scripts in authoring patches. Every
revision is tied to its base candidate and remains replay-admitted by the typed
Director compiler before it can be promoted.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

SCHEMA = "skeleton.jeeves.director_revision.v1"
MAX_REVISIONS = 1000
ALLOWED = {
    "bible": {"theme", "opening", "invariant_goal",
              "canonical_facts", "ending_outcomes", "lore_epochs"},
    "scene": {"title", "setting", "camera", "lighting", "weather", "music",
              "style", "cast", "props", "links"},
    "quest": {"name", "theme", "premise", "narrative_cause", "consequences",
              "ending_axis", "requires_quests", "placement"},
    "stage": {"title", "lore", "scene_ids", "time_target"},
    "cutscene": {"title", "skippable", "trigger"},
    "cue": {"value", "at", "duration", "easing", "kind", "target"},
}
LISTS = {"canonical_facts", "ending_outcomes", "lore_epochs", "cast", "props",
         "links", "requires_quests", "scene_ids"}
NUMERIC = {"time_target", "at", "duration"}
BOOLEAN = {"skippable"}


def _locate(sequence: list[dict[str, Any]], key: str) -> dict[str, Any]:
    matches = [item for item in sequence if item.get("key") == key]
    if len(matches) != 1:
        raise ValueError("Director revision references absent or duplicate identifier: " + str(key))
    return matches[0]


def _edit(world: dict[str, Any], edit: dict[str, Any]) -> None:
    target = edit.get("target")
    if target not in ALLOWED or edit.get("field") not in ALLOWED[target]:
        raise ValueError("unsupported Director authored field")
    selector = {
        "bible": {"target", "field", "value"},
        "scene": {"target", "key", "field", "value"},
        "quest": {"target", "key", "field", "value"},
        "stage": {"target", "quest", "key", "field", "value"},
        "cutscene": {"target", "scene", "key", "field", "value"},
        "cue": {"target", "scene", "cutscene", "index", "field", "value"},
    }[target]
    if set(edit) != selector:
        raise ValueError("Director revision selector has unrecognized or missing fields")
    field = edit["field"]
    value = edit["value"]
    if field in LISTS:
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item or len(item) > 1200 for item in value
        ):
            raise ValueError("Director revision requires a list of authored text")
    elif field in NUMERIC:
        if type(value) is not int:
            raise ValueError("Director timing or stage pacing needs integer value")
    elif field in BOOLEAN:
        if type(value) is not bool:
            raise ValueError("Director cutscene skip requires boolean value")
    elif not isinstance(value, str) or not value or len(value) > 1200:
        raise ValueError("Director authoring needs nonempty text")
    if target == "bible":
        row = world["bible"]
    elif target == "scene":
        row = _locate(world["scenes"], edit["key"])
    elif target == "quest":
        row = _locate(world["quests"], edit["key"])
    elif target == "stage":
        quest = _locate(world["quests"], edit["quest"])
        row = _locate(quest["stages"], edit["key"])
    elif target == "cutscene":
        scene = _locate(world["scenes"], edit["scene"])
        row = _locate(scene["cutscenes"], edit["key"])
    else:
        scene = _locate(world["scenes"], edit["scene"])
        cutscene = _locate(scene["cutscenes"], edit["cutscene"])
        index = edit["index"]
        if type(index) is not int or not 0 <= index < len(cutscene["cues"]):
            raise ValueError("Director timeline cue index outside reviewed source")
        row = cutscene["cues"][index]
    row[field] = value


def revise(root: Path, *, source: str, revision: str) -> dict[str, Any]:
    from skeleton.developer.jeeves_game_director_factory import (
        _candidate, _digest, _safe_design, MAX_CANDIDATE_BYTES
    )
    from skeleton.developer.jeeves_game_quality import _read
    from skeleton.developer.jeeves_game_authoring import _create_only
    from skeleton.ai.game_builder.quest_scene_forge import compile_director_blueprint
    base, source_sha, world = _candidate(root, source)
    packet, revision_sha = _read(root, revision, 256 * 1024)
    if (set(packet) != {"schema", "project", "base_candidate_sha256", "edits"}
            or packet.get("schema") != SCHEMA
            or packet["project"] != base["project"]
            or packet["base_candidate_sha256"] != base["receipt_sha256"]):
        raise ValueError("Director revision does not match exact authored candidate")
    edits = packet["edits"]
    if not isinstance(edits, list) or not 1 <= len(edits) <= MAX_REVISIONS:
        raise ValueError("Director revision requires bounded declarative edits")
    changed = json.loads(json.dumps(world.payload(), ensure_ascii=True))
    for edit in edits:
        if not isinstance(edit, dict):
            raise ValueError("Director revision operation must be an object")
        _edit(changed, edit)
    rewritten = compile_director_blueprint(changed, human_reviewed=True)
    if rewritten.project_id != world.project_id or rewritten.payload() != changed:
        raise ValueError("Director scene edit failed canonical payload verification")
    history = list(base.get("revision_history", []))
    history.append({"path": revision, "sha256": revision_sha})
    result = {
        "schema": "skeleton.jeeves.director_candidate.v2",
        "project": base["project"],
        "config_sha256": base["config_sha256"],
        "director_world": rewritten.payload(),
        "dragon_handoff_sha256": base["dragon_handoff_sha256"],
        "generator": "canonical-reviewed-director-revision-v1",
        "revision_history": history,
    }
    result["receipt_sha256"] = _digest(result)
    encoded = (json.dumps(result, sort_keys=True, indent=2,
                          ensure_ascii=True, allow_nan=False) + "\n").encode()
    if len(encoded) > MAX_CANDIDATE_BYTES:
        raise ValueError("Director revised world exceeds canonical source capacity")
    if _read(root, source, MAX_CANDIDATE_BYTES)[1] != source_sha or (
        _read(root, revision, 256 * 1024)[1] != revision_sha
    ):
        raise ValueError("Director revision inputs changed during editing")
    destination = _safe_design(root) / ("director_candidate_" +
                                       result["receipt_sha256"][:16] + ".json")
    _create_only(destination, encoded)
    return {
        "ok": True, "action": "director-revise",
        "source": "design/" + destination.name,
        "candidate_sha256": result["receipt_sha256"],
        "director_world_sha256": rewritten.digest,
        "revision_edits": len(edits), "revision_depth": len(history),
        "operator_approved": False, "native_game_rendered": False,
    }
