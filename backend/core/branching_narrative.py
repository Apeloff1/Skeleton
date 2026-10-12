"""Bounded, replayable, choice-driven RPG/adventure narrative planning engine.

A plan is not a live-game write. It is an author-reviewed DAG with guards,
typed consequences, character/place lore and ending receipts. Each player
choice records changed state and active story obligations; endings are
conditionally selected AND checked against all promises in that playthrough.

No eval, arbitrary predicates, executable content, implicit favorable endings,
unbounded cycles, hidden state mutation or false exhaustiveness claim.
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from hashlib import sha256
import json
import re
from typing import Any, Mapping, Sequence

from core.chapter_continuity import chapter_for_act

SCHEMA = "jeeves.branching-narrative.v1"
RECEIPT_SCHEMA = "jeeves.branching-playthrough.v1"
SLUG = re.compile(r"^[A-Za-z0-9:_-]{1,96}$")
SCOPES = frozenset({"region", "city", "person", "faction", "gang",
                    "government", "law", "citizens", "community"})
QUEST_STATES = frozenset({"unknown", "available", "active", "completed", "failed", "missed"})
METER_TYPES = frozenset({"karma", "reputation", "relationship", "law_heat"})
GOOD_NEUTRAL_EVIL = frozenset({"good", "neutral", "evil", "mixed"})
BEAT_ACTIONS = frozenset({"setup", "promise", "cliffhanger", "red_herring",
                          "foreshadow", "payoff", "resolution", "false_lead_disclosed"})
CLOSURES = frozenset({"payoff", "resolution", "false_lead_disclosed"})
MAX_NODES = 2000
MAX_ENDINGS = 200
MAX_OPTIONS = 24
MAX_WALK_STEPS = 2000
MAX_AUDIT_PATHS = 10000
MAX_CHARACTERS = 1000
MAX_PLACES = 1000


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def receipt(value: Any) -> str:
    return sha256(canonical(value).encode("utf-8")).hexdigest()


def identifier(value: Any, *, kind: str = "identifier") -> str:
    if not isinstance(value, str) or not SLUG.fullmatch(value):
        raise ValueError(kind + " requires a stable ID.")
    return value


def _plain(value: Any, path: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(path + " must be an object.")
    return value


def _exact(record: Mapping[str, Any], allowed: set[str], *, location: str):
    extra = set(record) - allowed
    if extra:
        raise ValueError(location + " has unrecognized fields: " + ",".join(sorted(extra)))


def _integer(value: Any, minimum: int, maximum: int, label: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(label + " is outside its valid bounds.")
    return value


def _text(value: Any, label: str, maximum: int = 1200, minimum: int = 1) -> str:
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        raise ValueError(label + " needs human-readable source text.")
    return value.strip()


def meter_key(kind: str, scope: str | None = None, subject: str | None = None) -> str:
    if kind == "karma":
        if scope is not None or subject is not None:
            raise ValueError("Karma is a global meter.")
        return "karma"
    if kind not in METER_TYPES:
        raise ValueError("Unknown narrative influence meter.")
    if kind == "law_heat":
        if scope not in ("region", "city", "government", "law"):
            raise ValueError("Law heat requires a territorial or legal scope.")
    elif kind == "relationship":
        if scope != "person":
            raise ValueError("Relationships are keyed to a person.")
    elif scope not in SCOPES:
        raise ValueError("Reputation requires a region/city/person/faction/gang/government/law/citizens/community scope.")
    return kind + ":" + str(scope) + ":" + identifier(subject, kind="meter subject")


def validate_condition(condition: Any, depth: int = 0, budget: list[int] | None = None) -> dict:
    """Unambiguous declarative conditions, without dynamic expressions."""
    if budget is None:
        budget = [0]
    budget[0] += 1
    if budget[0] > 128 or depth > 8:
        raise ValueError("Choice condition is too deep or expensive.")
    item = _plain(condition, "condition")
    op = item.get("op")
    if op in ("all", "any"):
        _exact(item, {"op", "items"}, location="condition")
        children = item.get("items")
        if not isinstance(children, list) or not 1 <= len(children) <= 20:
            raise ValueError("Boolean conditions require 1..20 clauses.")
        return {"op": op, "items": [
            validate_condition(c, depth + 1, budget) for c in children]}
    if op == "not":
        _exact(item, {"op", "item"}, location="condition")
        return {"op": op, "item": validate_condition(item.get("item"), depth + 1, budget)}
    if op in ("quest", "flag", "choice", "lore"):
        _exact(item, {"op", "id", "state"} if op == "quest" else {"op", "id"}, location="condition")
        key = identifier(item.get("id"), kind=op)
        if op == "quest":
            state = item.get("state")
            if state not in QUEST_STATES:
                raise ValueError("Unrecognized quest status condition.")
            return {"op": op, "id": key, "state": state}
        return {"op": op, "id": key}
    if op == "meter":
        _exact(item, {"op", "kind", "scope", "subject", "comparison", "value"}, location="condition")
        kind = item.get("kind")
        key = meter_key(kind, item.get("scope"), item.get("subject"))
        cmp = item.get("comparison")
        if cmp not in ("gte", "lte", "eq"):
            raise ValueError("Meter comparison must be gte/lte/eq.")
        val = _integer(item.get("value"), -100, 100, "meter threshold")
        return {"op": "meter", "key": key, "comparison": cmp, "value": val}
    if op == "always":
        _exact(item, {"op"}, location="condition")
        return {"op": "always"}
    raise ValueError("Unsupported choice guard: " + str(op))


def holds(condition: Mapping[str, Any], state: Mapping[str, Any]) -> bool:
    op = condition["op"]
    if op == "always":
        return True
    if op == "all":
        return all(holds(x, state) for x in condition["items"])
    if op == "any":
        return any(holds(x, state) for x in condition["items"])
    if op == "not":
        return not holds(condition["item"], state)
    if op == "quest":
        return state["quests"].get(condition["id"], "unknown") == condition["state"]
    if op in ("flag", "choice", "lore"):
        category = {"flag": "flags", "choice": "choices", "lore": "known_lore"}[op]
        return condition["id"] in state[category]
    if op == "meter":
        current = state["meters"].get(condition["key"], 0)
        if condition["comparison"] == "gte":
            return current >= condition["value"]
        if condition["comparison"] == "lte":
            return current <= condition["value"]
        return current == condition["value"]
    raise ValueError("Malformed prevalidated guard.")


def initial_state(raw: Mapping[str, Any] | None = None) -> dict:
    raw = raw or {}
    _exact(raw, {"quests", "meters", "flags", "choices", "known_lore"}, location="initial state")
    quests = _plain(raw.get("quests", {}), "initial quests")
    meters = _plain(raw.get("meters", {}), "initial meters")
    normalized = {
        "quests": {}, "meters": {}, "flags": [], "choices": [], "known_lore": [],
    }
    if len(quests) > 1000 or len(meters) > 5000:
        raise ValueError("Initial state exceeds bounded state limits.")
    for key, value in quests.items():
        identifier(key, kind="quest")
        if value not in QUEST_STATES:
            raise ValueError("Invalid initial quest status.")
        normalized["quests"][key] = value
    for key, value in meters.items():
        if key != "karma":
            parts = key.split(":")
            if len(parts) != 3 or meter_key(*parts) != key:
                raise ValueError("Malformed initial reputation/relationship/law key.")
        _integer(value, -100, 100, "initial meter")
        normalized["meters"][key] = value
    for source, field in (("flags", "flags"), ("choices", "choices"), ("known_lore", "known_lore")):
        values = raw.get(source, [])
        if not isinstance(values, list) or len(values) > 2000:
            raise ValueError("Initial tags must be bounded lists.")
        normalized[field] = sorted({identifier(x, kind=source) for x in values})
    return normalized


def validate_effect(effect: Any) -> dict:
    row = _plain(effect, "choice effect")
    kind = row.get("op")
    if kind == "meter_delta":
        _exact(row, {"op", "kind", "scope", "subject", "delta"}, location="meter consequence")
        key = meter_key(row.get("kind"), row.get("scope"), row.get("subject"))
        value = _integer(row.get("delta"), -100, 100, "meter consequence")
        return {"op": "meter_delta", "key": key, "delta": value}
    if kind == "quest_set":
        _exact(row, {"op", "id", "state"}, location="quest consequence")
        key = identifier(row.get("id"), kind="quest")
        status = row.get("state")
        if status not in QUEST_STATES - {"unknown"}:
            raise ValueError("Quest consequence must name a real status.")
        return {"op": "quest_set", "id": key, "state": status}
    if kind in ("flag_set", "lore_discover"):
        _exact(row, {"op", "id"}, location="tag consequence")
        return {"op": kind, "id": identifier(row.get("id"), kind=kind)}
    if kind == "thread":
        _exact(row, {"op", "id", "role", "plot_id"}, location="story thread")
        thread = identifier(row.get("id"), kind="thread")
        plot = identifier(row.get("plot_id"), kind="anchored plot point")
        role = row.get("role")
        if role not in BEAT_ACTIONS:
            raise ValueError("Unknown story-obligation transition.")
        return {"op": "thread", "id": thread, "role": role, "plot_id": plot}
    raise ValueError("Unsupported narrative consequence: " + str(kind))


def apply_effects(state: dict, obligations: dict, effects: Sequence[Mapping[str, Any]],
                  *, scene: int, plot_ids: set[str]) -> tuple[dict, dict, list[dict]]:
    updated = deepcopy(state)
    threads = deepcopy(obligations)
    events: list[dict] = []
    for effect in effects:
        op = effect["op"]
        if op == "meter_delta":
            key = effect["key"]
            previous = updated["meters"].get(key, 0)
            current = max(-100, min(100, previous + effect["delta"]))
            updated["meters"][key] = current
            events.append({"op": op, "key": key, "before": previous, "after": current})
        elif op == "quest_set":
            previous = updated["quests"].get(effect["id"], "unknown")
            # Any quest may be made available/active; final completed, failed or
            # missed states cannot silently reverse without a new quest ID.
            if previous in {"completed", "failed", "missed"} and previous != effect["state"]:
                raise ValueError("Terminal quest " + effect["id"] + " cannot be silently rewritten.")
            updated["quests"][effect["id"]] = effect["state"]
            events.append({"op": op, "id": effect["id"], "before": previous, "after": effect["state"]})
        elif op in ("flag_set", "lore_discover"):
            container = "flags" if op == "flag_set" else "known_lore"
            updated[container] = sorted(set(updated[container]) | {effect["id"]})
            events.append({"op": op, "id": effect["id"]})
        elif op == "thread":
            if effect["plot_id"] not in plot_ids:
                raise ValueError("Plot consequence has no exact highlighted scene anchor.")
            old = threads.get(effect["id"])
            role = effect["role"]
            if role in CLOSURES:
                if not old or old["status"] != "open":
                    raise ValueError("Thread payoff without an earlier unresolved setup.")
                if old["opened_scene"] >= scene:
                    raise ValueError("Thread cannot resolve in its introduction scene.")
                if old["opening_role"] == "red_herring" and role != "false_lead_disclosed":
                    raise ValueError("A red herring must explicitly be disclosed.")
                if old["opening_role"] != "red_herring" and role == "false_lead_disclosed":
                    raise ValueError("False lead disclosure needs a planted red herring.")
                old.update({"status": "closed", "closed_scene": scene,
                            "closure_role": role, "closure_plot_id": effect["plot_id"]})
            else:
                if old and old["status"] == "closed":
                    raise ValueError("Closed plot thread cannot reopen under the same ID.")
                if not old:
                    threads[effect["id"]] = {
                        "status": "open", "opened_scene": scene,
                        "opening_role": role, "opening_plot_id": effect["plot_id"],
                    }
            events.append({"op": op, "id": effect["id"], "role": role,
                           "scene": scene, "plot_id": effect["plot_id"]})
        else:
            raise ValueError("Unknown prevalidated consequence")
    return updated, threads, events


def _normalize_lore(entries: Any, kind: str) -> dict[str, dict]:
    if not isinstance(entries, list) or len(entries) > (
        MAX_CHARACTERS if kind == "character" else MAX_PLACES
    ):
        raise ValueError("Character/place lore must be a bounded array.")
    result = {}
    for x in entries:
        x = _plain(x, kind)
        allowed = ({"id", "name", "backstory", "goals", "relationships",
                    "factions", "known_secrets", "plot_threads", "dialogue_style",
                    "personal_ending", "source_scene"} if kind == "character" else
                   {"id", "name", "kind", "history", "culture", "regional_conflicts",
                    "factions", "plot_threads", "discovered_by", "source_scene"})
        _exact(x, allowed, location=kind + " lore")
        key = identifier(x.get("id"), kind=kind)
        if key in result:
            raise ValueError("Duplicate " + kind + " lore ID.")
        normalized = {"id": key, "name": _text(x.get("name"), kind + " name", 120),
                      "source_scene": _integer(x.get("source_scene"), 1, 9999, "lore source")}
        required = (("backstory", "goals", "dialogue_style", "personal_ending")
                    if kind == "character" else
                    ("kind", "history", "culture", "regional_conflicts"))
        for field in required:
            normalized[field] = _text(x.get(field), kind + "." + field, 3000)
        optional = ("relationships", "factions", "known_secrets", "plot_threads"
                    ) if kind == "character" else ("factions", "plot_threads", "discovered_by")
        for field in optional:
            values = x.get(field, [])
            if not isinstance(values, list) or len(values) > 100:
                raise ValueError("Lore cross-references must be bounded lists.")
            normalized[field] = sorted({identifier(v, kind="lore reference") for v in values})
        result[key] = normalized
    return result


def validate_plan(raw: Mapping[str, Any]) -> dict:
    plan = _plain(raw, "narrative plan")
    _exact(plan, {"schema_version", "entry_node", "nodes", "endings", "characters",
                  "places", "initial_state", "title", "branch_id"}, location="narrative plan")
    if plan.get("schema_version") != SCHEMA:
        raise ValueError("Unsupported branching narrative schema.")
    title = _text(plan.get("title"), "story title", 150)
    branch_id = identifier(plan.get("branch_id", "main"), kind="story branch")
    characters = _normalize_lore(plan.get("characters", []), "character")
    places = _normalize_lore(plan.get("places", []), "place")
    nodes = plan.get("nodes")
    ends = plan.get("endings")
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= MAX_NODES:
        raise ValueError("Narrative graph requires 1..2000 decision scenes.")
    if not isinstance(ends, list) or not 2 <= len(ends) <= MAX_ENDINGS:
        raise ValueError("Multibrach game requires 2..200 meaningful endings.")
    end_map: dict[str, dict] = {}
    for entry in ends:
        item = _plain(entry, "ending")
        _exact(item, {"id", "title", "tone", "epilogue", "consequences",
                      "character_conclusions", "place_conclusions", "required_lore"},
               location="ending")
        key = identifier(item.get("id"), kind="ending")
        if key in end_map:
            raise ValueError("Duplicate ending ID.")
        tone = item.get("tone")
        if tone not in GOOD_NEUTRAL_EVIL:
            raise ValueError("Ending morality must be good, neutral, evil or mixed.")
        conclusions = {}
        for field, catalog in (("character_conclusions", characters),
                               ("place_conclusions", places)):
            rows = _plain(item.get(field, {}), field)
            if set(rows) - set(catalog):
                raise ValueError("Ending references an unknown " + field + " identity.")
            conclusions[field] = {
                k: _text(v, "conclusion", 1500) for k, v in rows.items()}
        end_map[key] = {
            "id": key, "title": _text(item.get("title"), "ending title", 150),
            "tone": tone, "epilogue": _text(item.get("epilogue"), "epilogue", 6000, 40),
            "consequences": _text(item.get("consequences"), "lasting consequences", 3000, 20),
            "required_lore": sorted({
                identifier(x, kind="required lore") for x in item.get("required_lore", [])
            }),
            **conclusions,
        }
    node_map = {}
    for record in nodes:
        item = _plain(record, "scene node")
        _exact(item, {"id", "scene", "act", "chapter", "kind", "speaker",
                      "place", "text", "plot_points", "options"}, location="scene node")
        key = identifier(item.get("id"), kind="node")
        if key in node_map:
            raise ValueError("Duplicate decision node ID.")
        scene = _integer(item.get("scene"), 1, 9999, "scene")
        act = _integer(item.get("act"), 1, 1000, "act")
        chapter = _integer(item.get("chapter"), 1, 100, "chapter")
        if chapter_for_act(act) != chapter:
            raise ValueError("Choice scene act belongs to the wrong chapter.")
        kind = item.get("kind")
        if kind not in ("dialogue", "quest", "exploration", "combat", "world_event"):
            raise ValueError("Unsupported game-story interaction kind.")
        speaker = item.get("speaker")
        if speaker is not None and identifier(speaker, kind="speaker") not in characters:
            raise ValueError("Dialogue speaker must have a character backstory.")
        place = item.get("place")
        if place is not None and identifier(place, kind="location") not in places:
            raise ValueError("Choice location lacks a place lore entry.")
        if kind == "dialogue" and not speaker:
            raise ValueError("Dialogue must cite a named character and backstory.")
        text = _text(item.get("text"), "scene dialogue/story", 16000)
        points = item.get("plot_points", [])
        if not isinstance(points, list) or not 1 <= len(points) <= 200:
            raise ValueError("Every decision scene needs highlighted plot evidence.")
        ids = set()
        for point in points:
            _exact(_plain(point, "plot point"), {"id", "anchor"}, location="plot highlight")
            pid = identifier(point.get("id"), kind="plot point")
            phrase = _text(point.get("anchor"), "plot anchor", 500, 2)
            if pid in ids or text.count(phrase) != 1:
                raise ValueError("Plot anchors must have distinct IDs and match once.")
            ids.add(pid)
        options = item.get("options")
        if not isinstance(options, list) or not 1 <= len(options) <= MAX_OPTIONS:
            raise ValueError("Decision node needs 1..24 authored choice alternatives.")
        compiled = []
        selected: set[str] = set()
        for option in options:
            op = _plain(option, "choice")
            _exact(op, {"id", "label", "guard", "effects", "next_node", "ending",
                        "dialogue", "intent", "emotional_consequence"}, location="choice")
            oid = identifier(op.get("id"), kind="choice")
            if oid in selected:
                raise ValueError("Choice IDs must be distinct in a node.")
            selected.add(oid)
            dest, ending = op.get("next_node"), op.get("ending")
            if bool(dest) == bool(ending):
                raise ValueError("Choice leads to exactly one next node or ending.")
            if dest:
                identifier(dest, kind="next node")
            if ending:
                identifier(ending, kind="ending")
            effects = op.get("effects", [])
            if not isinstance(effects, list) or len(effects) > 40:
                raise ValueError("Consequences require at most 40 effects.")
            parsed_effects = [validate_effect(x) for x in effects]
            for effect in parsed_effects:
                if effect["op"] == "thread" and effect["plot_id"] not in ids:
                    raise ValueError("Thread effect must cite a highlighted plot point.")
            compiled.append({
                "id": oid, "label": _text(op.get("label"), "choice label", 240),
                "dialogue": _text(op.get("dialogue", op.get("label")), "spoken response", 800),
                "intent": _text(op.get("intent"), "choice's causal motive", 600),
                "emotional_consequence": _text(op.get("emotional_consequence"),
                                               "player emotion consequence", 600),
                "guard": validate_condition(op.get("guard", {"op": "always"})),
                "effects": parsed_effects,
                "next_node": dest, "ending": ending,
            })
        node_map[key] = {"id": key, "scene": scene, "act": act, "chapter": chapter,
                         "kind": kind, "speaker": speaker, "place": place,
                         "text": text, "plot_points": deepcopy(points), "options": compiled}
    entry = identifier(plan.get("entry_node"), kind="entry")
    if entry not in node_map:
        raise ValueError("Unknown entry decision node.")
    for node in node_map.values():
        for option in node["options"]:
            if option["next_node"] and option["next_node"] not in node_map:
                raise ValueError("Choice points to nonexistent node.")
            if option["ending"] and option["ending"] not in end_map:
                raise ValueError("Choice points to nonexistent ending.")
            next_node = node_map.get(option["next_node"])
            if next_node and (next_node["scene"] <= node["scene"] or
                              next_node["act"] < node["act"]):
                raise ValueError("Decision edges must follow chronology; cycles are prohibited.")
    # Every node must connect to an ending through some structurally valid path.
    reverse = {n: set() for n in node_map}
    viable = set()
    ending_refs = set()
    for node in node_map.values():
        for option in node["options"]:
            if option["ending"]:
                viable.add(node["id"])
                ending_refs.add(option["ending"])
            else:
                reverse[option["next_node"]].add(node["id"])
    queue = deque(viable)
    while queue:
        for parent in reverse[queue.popleft()]:
            if parent not in viable:
                viable.add(parent)
                queue.append(parent)
    if len(viable) != len(node_map):
        raise ValueError("One or more choices lead to a structurally dead story path.")
    if ending_refs != set(end_map):
        raise ValueError("Every authored ending must be reachable from a decision edge.")
    # All nodes also need to be reachable from the actual chapter opening.
    seen = {entry}
    queue = deque([entry])
    while queue:
        key = queue.popleft()
        for option in node_map[key]["options"]:
            nxt = option["next_node"]
            if nxt and nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    if seen != set(node_map):
        raise ValueError("Disconnected authored nodes cannot become canon.")
    return {"schema_version": SCHEMA, "title": title, "branch_id": branch_id,
            "entry_node": entry, "nodes": node_map, "endings": end_map,
            "characters": characters, "places": places,
            "initial_state": initial_state(plan.get("initial_state")),
            "source_digest": receipt(plan)}


def available_options(plan: Mapping[str, Any], node_id: str, state: Mapping[str, Any]) -> list[dict]:
    node = plan["nodes"][node_id]
    return [{
        "id": opt["id"], "label": opt["label"], "dialogue": opt["dialogue"],
        "intent": opt["intent"], "emotional_consequence": opt["emotional_consequence"],
        "next_node": opt["next_node"], "ending": opt["ending"],
    } for opt in node["options"] if holds(opt["guard"], state)]


def simulate(plan: Mapping[str, Any], choices: Sequence[str]) -> dict:
    """Pure, bounded replay with an evidence receipt after every authored choice."""
    if len(choices) > MAX_WALK_STEPS:
        raise ValueError("Excessive choice history.")
    state = deepcopy(plan["initial_state"])
    threads: dict[str, dict] = {}
    current = plan["entry_node"]
    steps: list[dict] = []
    terminal = None
    for chosen in choices:
        node = plan["nodes"][current]
        options = [x for x in node["options"] if x["id"] == chosen and holds(x["guard"], state)]
        if len(options) != 1:
            raise ValueError("Player selected an unavailable, unrecognized or expired choice.")
        opt = options[0]
        state, threads, consequences = apply_effects(
            state, threads, opt["effects"], scene=node["scene"],
            plot_ids={p["id"] for p in node["plot_points"]},
        )
        state["choices"] = sorted(set(state["choices"]) | {chosen})
        step = {
            "node": current, "scene": node["scene"], "character": node["speaker"],
            "place": node["place"], "choice": chosen, "intent": opt["intent"],
            "emotional_consequence": opt["emotional_consequence"],
            "consequences": consequences, "next_node": opt["next_node"],
            "ending": opt["ending"],
        }
        step["receipt_digest"] = receipt({"prior": steps[-1]["receipt_digest"] if steps else
                                          plan["source_digest"], "step": step,
                                          "state": state, "threads": threads})
        steps.append(step)
        if opt["ending"]:
            terminal = opt["ending"]
            break
        current = opt["next_node"]
    if terminal and len(steps) < len(choices):
        raise ValueError("Cannot choose further actions after an ending.")
    incomplete = [k for k, t in threads.items() if t["status"] == "open"]
    ending = plan["endings"].get(terminal) if terminal else None
    missing_lore = (sorted(set(ending["required_lore"]) -
                           set(state["known_lore"])) if ending else [])
    is_closed = bool(terminal and not incomplete and not missing_lore)
    return {
        "schema_version": RECEIPT_SCHEMA, "plan_digest": plan["source_digest"],
        "state": state, "threads": threads, "steps": steps,
        "position": None if terminal else current,
        "available_options": [] if terminal else available_options(plan, current, state),
        "ending": deepcopy(ending), "ending_id": terminal,
        "unresolved_threads": sorted(incomplete),
        "missing_ending_lore": missing_lore,
        "ending_accepted": is_closed,
        "story_quality_guaranteed": False,
        "receipt_digest": receipt({"plan": plan["source_digest"], "steps": steps,
                                  "state": state, "threads": threads,
                                  "ending": terminal}),
    }


def audit_outcomes(plan: Mapping[str, Any], *, max_paths: int = MAX_AUDIT_PATHS) -> dict:
    """Enumerate actual enabled choices under evolving state, with hard budget.

    Does not assert full assurance if any route exceeded its budget. A bounded
    audit can find counterexamples; it cannot certify the reader's enjoyment.
    """
    if not 1 <= max_paths <= MAX_AUDIT_PATHS:
        raise ValueError("Path budget outside 1..10000")
    visited = 0
    truncated = False
    reachable = set()
    fail_examples = []
    dead_ends = 0
    unchecked = deque([()])
    while unchecked:
        if visited >= max_paths:
            truncated = True
            break
        picks = unchecked.popleft()
        visited += 1
        try:
            history = simulate(plan, picks)
        except ValueError as problem:
            fail_examples.append({"path": picks[-20:], "error": str(problem)})
            continue
        if history["ending_id"]:
            reachable.add(history["ending_id"])
            if not history["ending_accepted"]:
                fail_examples.append({"path": picks[-20:],
                                      "error": "Ending has unresolved threads or undiscovered lore",
                                      "open_threads": history["unresolved_threads"],
                                      "missing_lore": history["missing_ending_lore"]})
            continue
        if not history["available_options"]:
            dead_ends += 1
            fail_examples.append({"path": picks[-20:], "error": "No available choice at this story node"})
            continue
        for option in history["available_options"]:
            unchecked.append((*picks, option["id"]))
        if len(unchecked) > max_paths * MAX_OPTIONS:
            truncated = True
            break
    missing_endings = sorted(set(plan["endings"]) - reachable)
    return {
        "schema_version": "jeeves.branching-outcome-audit.v1",
        "plan_digest": plan["source_digest"], "paths_inspected": visited,
        "path_budget": max_paths, "complete": not truncated,
        "reachable_endings": sorted(reachable),
        "unreachable_endings": missing_endings,
        "dead_end_paths": dead_ends, "issue_count": len(fail_examples),
        "issues": fail_examples[:100],
        "all_paths_verified": not truncated and not fail_examples and not missing_endings,
        "literary_perfection_guaranteed": False,
    }
