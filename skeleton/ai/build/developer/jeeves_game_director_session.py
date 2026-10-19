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
        try:
            selected.mkdir(exist_ok=False)
        except FileExistsError as exc:
            raise ValueError("Director session already exists; resume or select a new name") from exc
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
    expected = {"schema", "name", "source", "source_sha256",
                "director_world_sha256", "genesis_sha256", "receipt_sha256"}
    if "fork_origin" in manifest:
        expected.add("fork_origin")
    if set(manifest) != expected or manifest["schema"] != SCHEMA or manifest["name"] != name:
        raise ValueError("unsupported Director session manifest")
    if "fork_origin" in manifest:
        origin = manifest["fork_origin"]
        if (not isinstance(origin, dict)
                or set(origin) != {"parent_session", "parent_head_sha256", "fork_sequence"}
                or not isinstance(origin["parent_session"], str)
                or NAME.fullmatch(origin["parent_session"]) is None
                or origin["parent_session"] == name
                or not isinstance(origin["parent_head_sha256"], str)
                or re.fullmatch(r"[0-9a-f]{64}", origin["parent_head_sha256"]) is None
                or type(origin["fork_sequence"]) is not int
                or not 0 <= origin["fork_sequence"] <= 99999999):
            raise ValueError("Director branch contains invalid durable origin reference")
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
        elif option.kind == "transit" and world.dynamics is not None:
            passage = next(p for p in world.dynamics.passages
                           if p.key == option.key)
            destination = (passage.destination if state.scene == passage.source
                           else passage.source)
            description = passage.mode + ": " + passage.name + " → " + destination
        elif option.kind == "speak" and world.dynamics is not None:
            person = next(n for n in world.dynamics.society.residents
                          if n.key == option.key)
            description = "Speak with " + person.name
        elif option.kind == "discuss" and world.dynamics is not None:
            person, topic = next(
                (n, c) for n in world.dynamics.society.residents
                for c in n.dialogue if n.key + "_" + c.key == option.key
            )
            description = person.name + ": " + topic.prompt
        elif option.kind in {"buy", "sell"} and world.dynamics is not None:
            stock = next(
                good for shop in world.dynamics.society.shops for good in shop.goods
                if shop.key + "_" + good.key == option.key
            )
            price = stock.buy_price if option.kind == "buy" else stock.sell_price
            description = option.kind.title() + " " + stock.name + " (" + str(price) + " coins)"
        elif option.kind == "rest":
            description = "Rest until the next scheduled period"
        actions.append({**option.payload(), "choice": option.kind + ":" + option.key,
                        "description": description})
    world_state = state.world_state.payload() if state.world_state is not None else None
    society_status = None
    if (world.dynamics is not None and world.dynamics.society is not None
            and state.world_state.society is not None):
        from skeleton.ai.game_builder.quest_society import phase, residents_here
        rules = world.dynamics.society
        economy = state.world_state.society
        calendar = phase(rules, state.turn)
        people = residents_here(rules, state.scene, state.turn)
        allowed_dialogues = {
            option.key for option in available_director_actions(world, state)
            if option.kind == "discuss"
        }
        relationships = dict(economy.relationships)
        stock = {(sh, item): count for sh, item, count in economy.shop_stock}
        merchants = []
        for merchant in rules.shops:
            if merchant.scene != state.scene or merchant.keeper not in {
                    person.key for person in people}:
                continue
            merchants.append({
                "key": merchant.key, "name": merchant.name,
                "keeper": merchant.keeper, "products": [{
                    "key": g.key, "name": g.name,
                    "stock": stock[(merchant.key, g.key)],
                    "buy_price": g.buy_price, "sell_price": g.sell_price,
                    "owned": dict(economy.owned).get(g.key, 0),
                } for g in merchant.goods],
            })
        society_status = {
            "calendar": calendar,
            "wallet": economy.balance,
            "relationships": [list(x) for x in economy.relationships],
            "owned_goods": [list(x) for x in economy.owned],
            "redeemed_or_used_goods": [list(x) for x in economy.consumed_goods],
            "canonical_dialogue_history": [list(x)
                                           for x in economy.dialogue_history],
            "present_residents": [{
                "key": person.key, "name": person.name,
                "faction": person.faction,
                "trust": relationships[person.key],
                "greeting": person.greeting,
                "available_dialogue_topics": [{
                    "key": person.key + "_" + option.key,
                    "prompt": option.prompt,
                    "response_in_locked_content_hidden": True,
                } for option in person.dialogue
                    if person.key + "_" + option.key in allowed_dialogues],
            } for person in people],
            "open_merchants": merchants,
            "total_merchant_transactions": sum(
                count for _, _, _, count in economy.transactions),
        }
    blocked = []
    available_passages = []
    if world.dynamics is not None:
        from skeleton.ai.game_builder.quest_world_dynamics import (
            permits, gate_for, offered_passages,
        )
        for destination in here.links:
            gate = gate_for(world.dynamics, state.scene, destination)
            if gate is not None and not permits(gate.requirements, state):
                blocked.append({
                    "kind": "walk", "destination": destination,
                    "gate_label": gate.label,
                    "requirements": gate.requirements.payload(),
                })
        legal = {p.key for p in offered_passages(world.dynamics, state)}
        for passage in world.dynamics.passages:
            if (passage.source == state.scene or
                    passage.bidirectional and passage.destination == state.scene):
                dest = passage.destination if state.scene == passage.source else passage.source
                offered = passage.key in legal
                available_passages.append({
                    "key": passage.key, "mode": passage.mode,
                    "destination": dest, "cost_turns": passage.cost_turns,
                    "available": offered,
                    "requirements": passage.requirements.payload(),
                    "fare_item": passage.consume_item,
                })
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
        **({
            "world_state": world_state,
            "acquired": list(state.acquired),
            "conditional_walking_links_blocked": blocked,
            "transport_options": available_passages,
            **({"society": society_status} if society_status is not None else {}),
        } if world_state is not None else {}),
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


def choose(root: Path, *, session: str, choice: str,
           expected_sequence: int | None = None,
           expected_state_sha256: str | None = None) -> dict[str, Any]:
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
        # Optimistic concurrency checked AGAIN under the journal writer lock;
        # external CLI clients cannot race an HTTP status check into applying
        # an action against a different game state.
        if (expected_sequence is not None and (
                type(expected_sequence) is not int or expected_sequence != index)):
            raise ValueError("stale Director sequence")
        if (expected_state_sha256 is not None and (
                not isinstance(expected_state_sha256, str)
                or expected_state_sha256 != state.digest)):
            raise ValueError("stale Director state identity")
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
        from skeleton.developer.jeeves_game_quality import _read
        if _read(root, manifest["source"], 16 * 1024 * 1024)[1] != manifest["source_sha256"]:
            raise ValueError("Director authored source changed during interactive action")
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
