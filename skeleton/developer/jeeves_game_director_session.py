"""Durable, integrity-replayed local Director game sessions.

Every user-selected action is executed through the real Director transition
function. Sessions are append-only chained receipts; source/canonical world
changes invalidate resumed sessions. No game installation or model inference.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any

from skeleton.ai.game_builder.quest_scene_engine import (
    DirectorAction, DirectorWorld, available_director_actions, director_initial,
    director_step,
)
from skeleton.developer.jeeves_game_production_board import _load_world

SCHEMA = "skeleton.jeeves.director_session.v1"
EVENT_SCHEMA = "skeleton.jeeves.director_session_event.v1"
NAME = re.compile(r"[a-z][a-z0-9_-]{0,55}\Z")
MAX_ENTRY = 64 * 1024


def _hash(payload: object) -> str:
    return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True,
                             allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def _safe_dir(path: Path, *, missing_ok: bool = False) -> None:
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ValueError("unsafe Director session directory")
    if not missing_ok and not path.is_dir():
        raise ValueError("Director session directory missing")


def _folder(root: Path, name: str, *, create: bool = False) -> Path:
    from skeleton.developer.game_cli import _load
    _load(root)
    if root.is_symlink():
        raise ValueError("Director session project root must not be symlinked")
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise ValueError("session name must be a lowercase portable identifier")
    base = root / ".jeeves"
    parent = base / "director_sessions"
    selected = parent / name
    for folder in (base, parent, selected):
        _safe_dir(folder, missing_ok=create)
    if create:
        base.mkdir(exist_ok=True)
        parent.mkdir(exist_ok=True)
        selected.mkdir(exist_ok=False)
    return selected


def _read_doc(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ENTRY:
        raise ValueError("missing or unsafe Director action receipt")
    try:
        data = json.loads(path.read_text("utf-8"),
                          object_pairs_hook=_unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              ValueError("non-finite session receipt")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("invalid Director action receipt") from exc
    if not isinstance(data, dict):
        raise ValueError("Director session receipt must be an object")
    return data


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate Director session receipt field")
        result[key] = value
    return result


def _create(path: Path, data: dict[str, Any]) -> None:
    from skeleton.developer.jeeves_game_authoring import _create_only
    raw = (json.dumps(data, sort_keys=True, indent=2, ensure_ascii=True,
                      allow_nan=False) + "\n").encode()
    if len(raw) > MAX_ENTRY:
        raise ValueError("Director action receipt exceeds single-event capacity")
    _create_only(path, raw)


def _load(root: Path, *, name: str) -> tuple[Path, DirectorWorld, Any, dict, str, int]:
    from skeleton.developer.jeeves_game_quality import _read
    folder = _folder(root, name)
    manifest = _read_doc(folder / "00000000.json")
    if set(manifest) != {"schema", "name", "source", "source_sha256",
                         "director_world_sha256", "genesis_sha256", "receipt_sha256"
                        } or manifest["schema"] != SCHEMA or manifest["name"] != name:
        raise ValueError("unsupported Director session manifest")
    genesis = manifest["receipt_sha256"]
    if not isinstance(genesis, str) or _hash({k: v for k, v in manifest.items()
                                             if k != "receipt_sha256"}) != genesis:
        raise ValueError("Director session manifest was altered")
    world, identity = _load_world(root, manifest["source"])
    if identity != manifest["source_sha256"] or world.digest != manifest["director_world_sha256"]:
        raise ValueError("source Director campaign changed since session started")
    state = director_initial(world)
    if state.digest != manifest["genesis_sha256"]:
        raise ValueError("session genesis does not match canonical original world")
    entries = sorted(folder.iterdir(), key=lambda p: p.name)
    # An exclusive writer owns .lock while validating prior receipts.
    for lock_entry in entries:
        if lock_entry.name == ".lock" and (
                lock_entry.is_symlink() or not lock_entry.is_file()):
            raise ValueError("unsafe or modified Director session lock")
    entries = [p for p in entries if p.name != ".lock"]
    if len(entries) < 1 or entries[0].name != "00000000.json":
        raise ValueError("Director session genesis receipt absent")
    prior = genesis
    for index, path in enumerate(entries[1:], 1):
        if index > 99999999 or path.name != f"{index:08d}.json":
            raise ValueError("Director session receipts contain a gap or foreign file")
        item = _read_doc(path)
        if set(item) != {"schema", "sequence", "prior_sha256", "action",
                         "before_sha256", "after_sha256", "receipt_sha256"
                        } or item["schema"] != EVENT_SCHEMA:
            raise ValueError("Director session action envelope differs")
        if (type(item["sequence"]) is not int or item["sequence"] != index
                or item["prior_sha256"] != prior
                or item["before_sha256"] != state.digest):
            raise ValueError("Director session action chain or previous state differs")
        if item["receipt_sha256"] != _hash({
                k: v for k, v in item.items() if k != "receipt_sha256"}):
            raise ValueError("Director session action receipt digest differs")
        act = item["action"]
        if not isinstance(act, dict) or set(act) != {"kind", "key", "scene"}:
            raise ValueError("Director session action schema differs")
        action = DirectorAction(**act)
        state = director_step(world, state, action)
        if state.digest != item["after_sha256"]:
            raise ValueError("Director session action replay diverged")
        prior = item["receipt_sha256"]
    # This is an actual read-again witness of current source identity, not only
    # a comparison to a cached source digest at the start of an unbounded replay.
    if _read(root, manifest["source"], 16 * 1024 * 1024)[1] != identity:
        raise ValueError("Director campaign changed during session replay")
    return folder, world, state, manifest, prior, len(entries) - 1


def _view(world: DirectorWorld, state: Any, *, name: str,
          sequence: int, last_sha: str) -> dict[str, Any]:
    here = next(scene for scene in world.scenes if scene.key == state.scene)
    quests = []
    completed = set(state.complete)
    for quest in world.quests:
        stage = dict(state.stage_index)[quest.key]
        quests.append({
            "id": quest.key, "title": quest.name,
            "stage_index": stage, "stage_total": len(quest.stages),
            "completed": quest.key in completed,
            "blocked_by": sorted(set(quest.requires_quests) - completed),
        })
    affordances = {a.key: a for a in here.affordances}
    actions = []
    for option in available_director_actions(world, state):
        description = option.key.replace("_", " ")
        if option.kind == "use":
            af = affordances[option.key]
            description = af.kind + " " + af.target
        actions.append({**option.payload(), "choice": option.kind + ":" + option.key,
                        "description": description})
    return {
        "ok": True, "schema": SCHEMA, "session": name,
        "world_sha256": world.digest, "sequence": sequence,
        "current_state_sha256": state.digest, "last_receipt_sha256": last_sha,
        "scene": state.scene, "region": here.region, "scene_title": here.title,
        "scene_setting": here.setting, "cast": list(here.cast),
        "music_cue": here.music, "lighting": here.lighting, "weather": here.weather,
        "turn": state.turn, "quests": quests, "actions": actions,
        "complete": len(completed) == len(world.quests),
        "quest_stage_results": [r.payload() for r in state.results],
        "narrative_flags": list(state.narrative_flags),
        "real_player_or_hardware_test_verified": False,
        "actual_interactive_director_logic_executed": sequence > 0,
    }


def begin(root: Path, *, source: str, session: str) -> dict[str, Any]:
    world, identity = _load_world(root, source)
    state = director_initial(world)
    manifest = {
        "schema": SCHEMA, "name": session,
        "source": source, "source_sha256": identity,
        "director_world_sha256": world.digest,
        "genesis_sha256": state.digest,
    }
    manifest["receipt_sha256"] = _hash(manifest)
    folder = _folder(root, session, create=True)
    _create(folder / "00000000.json", manifest)
    return {"action": "director-session-begin", **_view(
        world, state, name=session, sequence=0, last_sha=manifest["receipt_sha256"])}


def inspect(root: Path, *, session: str) -> dict[str, Any]:
    folder, world, state, manifest, prior, index = _load(root, name=session)
    return {"action": "director-session-status",
            **_view(world, state, name=session, sequence=index, last_sha=prior)}


def choose(root: Path, *, session: str, choice: str) -> dict[str, Any]:
    if not isinstance(choice, str) or len(choice) > 140 or ":" not in choice:
        raise ValueError("choose an exact offered action, e.g. travel:scene_01")
    kind, key = choice.split(":", 1)
    folder = _folder(root, session)
    lock = folder / ".lock"
    if lock.is_symlink():
        raise ValueError("unsafe session write lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError("session write is in progress; no concurrent edits allowed") from exc
    try:
        os.close(fd)
        folder, world, state, manifest, prior, index = _load(root, name=session)
        action = DirectorAction(kind, key, state.scene)
        if action not in available_director_actions(world, state):
            raise ValueError("selected action is not currently available")
        next_state = director_step(world, state, action)
        item = {
            "schema": EVENT_SCHEMA, "sequence": index + 1,
            "prior_sha256": prior, "action": action.payload(),
            "before_sha256": state.digest, "after_sha256": next_state.digest,
        }
        item["receipt_sha256"] = _hash(item)
        _create(folder / f"{index + 1:08d}.json", item)
        return {"action": "director-session-step", "executed": action.payload(),
                **_view(world, next_state, name=session, sequence=index + 1,
                        last_sha=item["receipt_sha256"])}
    finally:
        lock.unlink(missing_ok=True)


def compare(root: Path, *, first: str, second: str) -> dict[str, Any]:
    _, left_world, left, _, lreceipt, la = _load(root, name=first)
    _, right_world, right, _, rreceipt, ra = _load(root, name=second)
    if left_world.digest != right_world.digest:
        raise ValueError("session comparison needs one identical original Director world")
    outcome_left = {(r.quest, r.stage): (r.approach, r.consequence) for r in left.results}
    outcome_right = {(r.quest, r.stage): (r.approach, r.consequence) for r in right.results}
    divergence = [
        {"quest": quest, "stage": stage,
         "left": list(outcome_left.get((quest, stage), ())),
         "right": list(outcome_right.get((quest, stage), ()))}
        for quest, stage in sorted(set(outcome_left) | set(outcome_right))
        if outcome_left.get((quest, stage)) != outcome_right.get((quest, stage))
    ]
    return {"ok": True, "action": "director-session-compare",
            "world_sha256": left_world.digest,
            "first": first, "second": second,
            "first_actions": la, "second_actions": ra,
            "first_receipt_sha256": lreceipt, "second_receipt_sha256": rreceipt,
            "different_outcomes": divergence, "material_divergence": bool(divergence),
            "first_all_quests_complete": len(left.complete) == len(left_world.quests),
            "second_all_quests_complete": len(right.complete) == len(right_world.quests),
            "real_playtest_or_player_preference_inferred": False}
