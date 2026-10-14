"""Bounded authored scene hierarchy/timelines and deterministic typed rules.

This is a data interpreter for original design scenes. It never evaluates
source, invokes providers, grants rights, or claims native hardware behavior.
"""

from __future__ import annotations

import hashlib
import json
import math
import operator
import re
from collections.abc import Mapping

GRAPH_SCHEMA = "skeleton.console_scene_graph.v1"
GRAPH_PATH = "game/editor/graph.json"
MAX_GRAPH_BYTES = 512 * 1024
_METRICS = {"health", "money", "crops", "fish", "seeds", "score", "tick"}
_MUTABLE_METRICS = _METRICS - {"tick"}
_ACTIONS = {"idle", "left", "right", "up", "down", "jump", "attack", "interact", "water", "plant", "fish"}
_COMPARE = {
    "eq": operator.eq,
    "ne": operator.ne,
    "lt": operator.lt,
    "le": operator.le,
    "gt": operator.gt,
    "ge": operator.ge,
}
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")


class SceneGraphError(ValueError):
    def __init__(self, code, message, status_code=422):
        super().__init__(message)
        self.code, self.status_code = code, status_code


def _json(value):
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    except (TypeError, ValueError, RecursionError, UnicodeError) as exc:
        raise SceneGraphError("editor_graph_json", "Scene graph must be finite bounded JSON") from exc
    if len(encoded) > MAX_GRAPH_BYTES:
        raise SceneGraphError("editor_graph_limit", "Scene graph exceeds512KiB")
    return encoded


def _digest(value):
    return hashlib.sha256(_json(value)).hexdigest()


def _num(value, low=-65536, high=65536):
    if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
        raise SceneGraphError("editor_graph_bounds", "Graph number exceeds its finite declared bounds")
    return value


def _int(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise SceneGraphError("editor_graph_bounds", "Graph integer exceeds its declared bounds")
    return value


def _bool(value):
    if type(value) is not bool:
        raise SceneGraphError("editor_graph_type", "Graph boolean must be an exact JSON boolean")
    return value


def _id(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise SceneGraphError("editor_graph_identity", "Graph identity is absent or malformed")
    return value


def _member(value, allowed):
    if not isinstance(value, str) or value not in allowed:
        raise SceneGraphError("editor_graph_reference", "Typed graph name or reference is absent")
    return value


def _shape(value, fields):
    if not isinstance(value, Mapping) or set(value) != set(fields):
        raise SceneGraphError("editor_graph_shape", "Typed graph fields differ from the declared record")


def _rows(value, maximum):
    if not isinstance(value, list) or len(value) > maximum:
        raise SceneGraphError("editor_graph_limit", "Graph record sequence exceeds its bounded capacity")
    seen = set()
    for row in value:
        if not isinstance(row, Mapping):
            raise SceneGraphError("editor_graph_shape", "Graph record must be an object")
        key = _id(row.get("id"))
        if key in seen:
            raise SceneGraphError("editor_graph_duplicate", "Graph record identity is duplicated")
        seen.add(key)
    return value


def empty_scene_graph(project_id):
    return {
        "schema_version": GRAPH_SCHEMA,
        "project_id": _id(project_id),
        "tick_hz": 60,
        "nodes": [],
        "animations": [],
        "variables": [],
        "rules": [],
    }


class ConsoleSceneGraph:
    """Validated immutable JSON with references checked against its scene."""

    def __init__(self, graph, scene):
        value = json.loads(_json(graph))
        _shape(
            value, {"schema_version", "project_id", "tick_hz", "nodes", "animations", "variables", "rules"}
        )
        if (
            value["schema_version"] != GRAPH_SCHEMA
            or value["tick_hz"] != 60
            or type(value["tick_hz"]) is not int
            or value["project_id"] != scene["project_id"]
        ):
            raise SceneGraphError("editor_graph_foreign", "Graph schema, project or fixed tick rate differs")
        entities = {row["id"]: row for row in scene["entities"]}
        assets = {row["id"]: row for row in scene["assets"]}
        cues = {row["id"] for row in scene["audio"]["cues"]}
        nodes = _rows(value["nodes"], 256)
        by_node = {row["id"]: row for row in nodes}
        bound_entities = set()
        for row in nodes:
            _shape(row, {"id", "parent_id", "entity_id", "x", "y", "visible", "frames"})
            if row["parent_id"] is not None and (
                not isinstance(row["parent_id"], str) or row["parent_id"] not in by_node
            ):
                raise SceneGraphError("editor_graph_reference", "Scene parent node is absent")
            entity = row["entity_id"]
            if entity is not None:
                if not isinstance(entity, str) or entity not in entities or entity in bound_entities:
                    raise SceneGraphError(
                        "editor_graph_reference", "Entity graph binding is absent or duplicated"
                    )
                if entities[entity]["kind"] == "player":
                    raise SceneGraphError(
                        "editor_graph_player",
                        "Player movement belongs to its controller, not a graph transform",
                    )
                bound_entities.add(entity)
            _num(row["x"])
            _num(row["y"])
            _bool(row["visible"])
            if not isinstance(row["frames"], list) or len(row["frames"]) > 128:
                raise SceneGraphError("editor_graph_limit", "Sprite frame sequence exceeds128frames")
            for frame in row["frames"]:
                _shape(frame, {"asset_id", "x", "y", "width", "height"})
                asset = assets.get(_member(frame["asset_id"], assets))
                if (
                    asset is None
                    or asset["kind"] != "image"
                    or asset["codec"] not in {"png", "rgba8888", "ps1_tim"}
                ):
                    raise SceneGraphError(
                        "editor_graph_frame", "Atlas frame requires an actual decoded original image"
                    )
                meta = asset["metadata"]
                x, y = _int(frame["x"], 0, 1023), _int(frame["y"], 0, 1023)
                w, h = _int(frame["width"], 1, 1024), _int(frame["height"], 1, 1024)
                if x + w > meta["width"] or y + h > meta["height"]:
                    raise SceneGraphError("editor_graph_frame", "Atlas frame exceeds decoded source geometry")
        depths = {}
        for node in nodes:
            chain, key = set(), node["id"]
            while key is not None:
                if key in chain or len(chain) >= 32:
                    raise SceneGraphError("editor_graph_cycle", "Hierarchy is cyclic or exceeds depth32")
                chain.add(key)
                key = by_node[key]["parent_id"]
            depths[node["id"]] = len(chain)
        variables = _rows(value["variables"], 32)
        by_var = {row["id"]: row for row in variables}
        for row in variables:
            _shape(row, {"id", "initial", "min", "max"})
            if len(row["id"]) > 60:
                raise SceneGraphError(
                    "editor_graph_identity",
                    "Variable ID exceeds60characters for bounded policy feature identity",
                )
            _num(row["min"], -1000000, 1000000)
            _num(row["max"], -1000000, 1000000)
            if row["min"] >= row["max"]:
                raise SceneGraphError("editor_graph_variable", "Variable minimum must be below maximum")
            _num(row["initial"], row["min"], row["max"])
        animations = _rows(value["animations"], 128)
        channels = set()
        for row in animations:
            _shape(row, {"id", "node_id", "property", "duration_ticks", "loop", "interpolation", "keyframes"})
            if (
                not isinstance(row["node_id"], str)
                or row["node_id"] not in by_node
                or not isinstance(row["property"], str)
                or row["property"] not in {"x", "y", "visible", "frame"}
            ):
                raise SceneGraphError("editor_graph_reference", "Animation target/property is absent")
            channel = (row["node_id"], row["property"])
            if channel in channels:
                raise SceneGraphError(
                    "editor_graph_channel", "A node property has multiple conflicting timelines"
                )
            channels.add(channel)
            duration = _int(row["duration_ticks"], 1, 216000)
            _bool(row["loop"])
            if (
                not isinstance(row["interpolation"], str)
                or row["interpolation"] not in {"step", "linear"}
                or row["property"] in {"visible", "frame"}
                and row["interpolation"] != "step"
            ):
                raise SceneGraphError(
                    "editor_graph_interpolation", "Discrete channels require step interpolation"
                )
            keys = row["keyframes"]
            if not isinstance(keys, list) or not 1 <= len(keys) <= 128:
                raise SceneGraphError("editor_graph_limit", "Animation requires1..128keyframes")
            previous = -1
            for key in keys:
                _shape(key, {"tick", "value"})
                tick = _int(key["tick"], 0, duration)
                if tick <= previous:
                    raise SceneGraphError(
                        "editor_graph_keyframe", "Timeline keys must have strictly increasing ticks"
                    )
                previous = tick
                if row["property"] == "visible":
                    _bool(key["value"])
                elif row["property"] == "frame":
                    _int(key["value"], 0, len(by_node[row["node_id"]]["frames"]) - 1)
                else:
                    _num(key["value"])
            if keys[0]["tick"] != 0:
                raise SceneGraphError("editor_graph_keyframe", "Timeline must declare its initial tick0value")
        rules = _rows(value["rules"], 64)
        for row in rules:
            _shape(row, {"id", "trigger", "conditions", "actions", "cooldown_ticks", "once", "enabled"})
            _int(row["cooldown_ticks"], 1, 216000)
            _bool(row["once"])
            _bool(row["enabled"])
            trigger = row["trigger"]
            kind = trigger.get("kind") if isinstance(trigger, Mapping) else None
            if kind == "input":
                _shape(trigger, {"kind", "action"})
                if not isinstance(trigger["action"], str) or trigger["action"] not in _ACTIONS:
                    raise SceneGraphError("editor_graph_trigger", "Input trigger names an absent action")
            elif kind == "tick_interval":
                _shape(trigger, {"kind", "interval"})
                _int(trigger["interval"], 1, 216000)
            elif kind == "region_enter":
                _shape(trigger, {"kind", "x", "y", "width", "height"})
                for key in ("x", "y"):
                    _num(trigger[key], 0, 65536)
                for key in ("width", "height"):
                    _num(trigger[key], 1, 65536)
            elif kind == "event":
                _shape(trigger, {"kind", "event"})
                _id(trigger["event"])
            else:
                raise SceneGraphError("editor_graph_trigger", "Unknown typed trigger")
            if not isinstance(row["conditions"], list) or len(row["conditions"]) > 8:
                raise SceneGraphError("editor_graph_limit", "Rule condition count exceeds8")
            for condition in row["conditions"]:
                _shape(condition, {"source", "key", "op", "value"})
                if (
                    not isinstance(condition["op"], str)
                    or condition["op"] not in _COMPARE
                    or not isinstance(condition["source"], str)
                    or condition["source"] not in {"variable", "metric"}
                ):
                    raise SceneGraphError("editor_graph_condition", "Unknown typed condition operator/source")
                if not isinstance(condition["key"], str) or condition["key"] not in (
                    by_var if condition["source"] == "variable" else _METRICS
                ):
                    raise SceneGraphError("editor_graph_reference", "Condition source is absent")
                _num(condition["value"], -1000000, 1000000)
            if not isinstance(row["actions"], list) or not 1 <= len(row["actions"]) <= 16:
                raise SceneGraphError("editor_graph_limit", "Rule requires1..16boundedactions")
            for action in row["actions"]:
                self._action(action, by_node, by_var, cues)
        self._encoded = _json(value)
        self._depths = depths

    @staticmethod
    def _action(action, nodes, variables, cues):
        kind = action.get("kind") if isinstance(action, Mapping) else None
        if not isinstance(kind, str):
            raise SceneGraphError("editor_graph_action", "Rule action requires a typed kind")
        if kind in {"set_variable", "add_variable"}:
            _shape(action, {"kind", "variable_id", "value"})
            if not isinstance(action["variable_id"], str) or action["variable_id"] not in variables:
                raise SceneGraphError("editor_graph_reference", "Rule variable is absent")
            row = variables[action["variable_id"]]
            _num(
                action["value"],
                row["min"] if kind == "set_variable" else -1000000,
                row["max"] if kind == "set_variable" else 1000000,
            )
        elif kind in {"set_metric", "add_metric"}:
            _shape(action, {"kind", "metric", "value"})
            if not isinstance(action["metric"], str) or action["metric"] not in _MUTABLE_METRICS:
                raise SceneGraphError("editor_graph_metric", "Rule cannot mutate that metric")
            _int(action["value"], 0 if kind == "set_metric" else -1000000, 1000000)
        elif kind == "trade":
            _shape(action, {"kind", "cost", "resource", "amount"})
            _int(action["cost"], 1, 1000000)
            _int(action["amount"], 1, 1000000)
            if not isinstance(action["resource"], str) or action["resource"] not in {
                "seeds",
                "crops",
                "fish",
            }:
                raise SceneGraphError("editor_graph_trade", "Trade resource is absent")
        elif kind == "set_node_visibility":
            _shape(action, {"kind", "node_id", "visible"})
            _bool(action["visible"])
            if not isinstance(action["node_id"], str) or action["node_id"] not in nodes:
                raise SceneGraphError("editor_graph_reference", "Rule node is absent")
        elif kind == "set_node_offset":
            _shape(action, {"kind", "node_id", "x", "y"})
            _num(action["x"])
            _num(action["y"])
            if not isinstance(action["node_id"], str) or action["node_id"] not in nodes:
                raise SceneGraphError("editor_graph_reference", "Rule node is absent")
        elif kind == "emit_event":
            _shape(action, {"kind", "event"})
            _id(action["event"])
        elif kind == "play_audio":
            _shape(action, {"kind", "cue_id"})
            if not isinstance(action["cue_id"], str) or action["cue_id"] not in cues:
                raise SceneGraphError("editor_graph_reference", "Audio cue is absent")
        elif kind == "dialogue":
            _shape(action, {"kind", "text"})
            if not isinstance(action["text"], str) or len(action["text"].encode()) > 2048:
                raise SceneGraphError("editor_graph_dialogue", "Dialogue exceeds2048UTF8bytes")
        elif kind == "teleport":
            _shape(action, {"kind", "x", "y"})
            _num(action["x"], 0, 65536)
            _num(action["y"], 0, 65536)
        elif kind == "win":
            _shape(action, {"kind"})
        elif kind == "reward":
            _shape(action, {"kind", "value"})
            _num(action["value"], -1, 1)
        else:
            raise SceneGraphError("editor_graph_action", "Unknown typed rule action")

    @property
    def digest(self):
        return hashlib.sha256(self._encoded).hexdigest()

    def as_dict(self):
        return json.loads(self._encoded)

    def inspect(self):
        value = self.as_dict()
        economy = [action for row in value["rules"] for action in row["actions"] if action["kind"] == "trade"]
        producers = {
            row["id"]: {action["event"] for action in row["actions"] if action["kind"] == "emit_event"}
            for row in value["rules"]
        }
        event_edges = [
            {"from_rule": source, "to_rule": row["id"], "event": row["trigger"]["event"]}
            for source, names in producers.items()
            for row in value["rules"]
            if row["trigger"]["kind"] == "event" and row["trigger"]["event"] in names
        ]
        successors = {row["id"]: set() for row in value["rules"]}
        indegrees = dict.fromkeys(successors, 0)
        for edge in event_edges:
            if edge["to_rule"] not in successors[edge["from_rule"]]:
                successors[edge["from_rule"]].add(edge["to_rule"])
                indegrees[edge["to_rule"]] += 1
        ready = [key for key, count in indegrees.items() if not count]
        visited = 0
        while ready:
            key = ready.pop()
            visited += 1
            for successor in successors[key]:
                indegrees[successor] -= 1
                if not indegrees[successor]:
                    ready.append(successor)
        return {
            "schema_version": "skeleton.console_scene_graph_review.v1",
            "graph_digest": self.digest,
            "nodes": len(value["nodes"]),
            "hierarchy_depth": max(self._depths.values(), default=0),
            "animations": len(value["animations"]),
            "keyframes": sum(len(row["keyframes"]) for row in value["animations"]),
            "variables": len(value["variables"]),
            "rules": len(value["rules"]),
            "maximum_rule_actions_per_tick": sum(len(row["actions"]) for row in value["rules"]),
            "economy_trades": len(economy),
            "event_edges": event_edges,
            "event_cycle_possible": visited < len(successors),
            "event_dispatch_scope": "Emitted named events are deduplicated and queued for the next fixedtick; cycles are bounded by cooldown,64rules/tick and episode step limit, not recursive code",
            "atomic_trade_scope": "positive fixed money cost for positive bounded original resources; no credit or recursive rule dispatch",
            "reference_and_cycle_validation": "pass",
            "execution_scope": "design_scene_simulation",
            "hardware_compatibility_verified": False,
            "game_quality_verified": False,
        }


class ConsoleGraphRuntime:
    """Per-episode mutable state, recreated by exact input-history replay."""

    def __init__(self, graph):
        self.graph = graph
        self.document = graph.as_dict()
        self.nodes = {row["id"]: row for row in self.document["nodes"]}
        self.entity_nodes = {
            row["entity_id"]: row["id"] for row in self.document["nodes"] if row["entity_id"] is not None
        }
        self.variable_specs = {row["id"]: row for row in self.document["variables"]}
        self.animations_by_node = {
            key: [row for row in self.document["animations"] if row["node_id"] == key] for key in self.nodes
        }
        self.reset()

    def reset(self):
        self.variables = {key: row["initial"] for key, row in self.variable_specs.items()}
        self.overrides, self.last_fired, self.fire_counts, self.regions = {}, {}, {}, {}
        self.executed_actions = self.skipped_actions = 0
        self.last_rule_ids, self.pending_events, self.last_trigger_events = [], [], []
        self._pose_tick, self._pose_cache = None, {}

    def _local(self, key, tick):
        row = self.nodes[key]
        state = {"x": row["x"], "y": row["y"], "visible": row["visible"], "frame": 0}
        for animation in self.animations_by_node[key]:
            at = (
                tick % animation["duration_ticks"]
                if animation["loop"]
                else min(tick, animation["duration_ticks"])
            )
            keys = animation["keyframes"]
            previous = keys[0]
            following = None
            for frame in keys[1:]:
                if frame["tick"] > at:
                    following = frame
                    break
                previous = frame
            value = previous["value"]
            if following and animation["interpolation"] == "linear":
                value += (
                    (following["value"] - value)
                    * (at - previous["tick"])
                    / (following["tick"] - previous["tick"])
                )
            state[animation["property"]] = value
        state.update(self.overrides.get(key, {}))
        return state

    def pose(self, entity_id, tick):
        if self._pose_tick != tick:
            self._pose_tick, self._pose_cache = tick, {}
        if entity_id in self._pose_cache:
            return dict(self._pose_cache[entity_id])
        key = self.entity_nodes.get(entity_id)
        if key is None:
            return {"x": 0, "y": 0, "visible": True, "frame": None}
        leaf = self._local(key, tick)
        frame = self.nodes[key]["frames"][leaf["frame"]] if self.nodes[key]["frames"] else None
        x, y, visible = leaf["x"], leaf["y"], leaf["visible"]
        key = self.nodes[key]["parent_id"]
        while key is not None:
            parent = self._local(key, tick)
            x += parent["x"]
            y += parent["y"]
            visible = visible and parent["visible"]
            key = self.nodes[key]["parent_id"]
        result = {"x": x, "y": y, "visible": visible, "frame": dict(frame) if frame else None}
        self._pose_cache[entity_id] = result
        return dict(result)

    def state(self):
        return {
            "variables": dict(self.variables),
            "overrides": {key: dict(row) for key, row in self.overrides.items()},
            "last_fired": dict(self.last_fired),
            "fire_counts": dict(self.fire_counts),
            "regions": dict(self.regions),
            "executed_actions": self.executed_actions,
            "skipped_actions": self.skipped_actions,
            "last_rule_ids": list(self.last_rule_ids),
            "pending_events": list(self.pending_events),
            "last_trigger_events": list(self.last_trigger_events),
        }

    def advance(
        self, *, tick, action, player_rect, events, metrics, mutate_metric, collision, teleport, win, dialogue
    ):
        """Return actual emitted events, explicit cue IDs and authored utility."""
        original_events = frozenset((*events, *self.pending_events))
        self.pending_events = []
        self.last_trigger_events = sorted(original_events)
        emitted, cues, reward = [], [], 0.0
        self.last_rule_ids = []
        for rule in self.document["rules"]:
            trigger = rule["trigger"]
            kind = trigger["kind"]
            trigger_hit = False
            if kind == "input":
                trigger_hit = action == trigger["action"]
            elif kind == "tick_interval":
                trigger_hit = tick % trigger["interval"] == 0
            elif kind == "event":
                trigger_hit = trigger["event"] in original_events
            elif kind == "region_enter":
                x, y, w, h = player_rect
                inside = (
                    x < trigger["x"] + trigger["width"]
                    and x + w > trigger["x"]
                    and y < trigger["y"] + trigger["height"]
                    and y + h > trigger["y"]
                )
                trigger_hit = inside and not self.regions.get(rule["id"], False)
                self.regions[rule["id"]] = inside
            if (
                not rule["enabled"]
                or not trigger_hit
                or rule["once"]
                and self.fire_counts.get(rule["id"], 0)
                or tick - self.last_fired.get(rule["id"], -216000) < rule["cooldown_ticks"]
            ):
                continue
            if not all(
                _COMPARE[c["op"]](
                    self.variables[c["key"]] if c["source"] == "variable" else metrics()[c["key"]], c["value"]
                )
                for c in rule["conditions"]
            ):
                continue
            self.last_fired[rule["id"]] = tick
            self.fire_counts[rule["id"]] = self.fire_counts.get(rule["id"], 0) + 1
            self.last_rule_ids.append(rule["id"])
            for effect in rule["actions"]:
                kind = effect["kind"]
                accepted = True
                if kind in {"set_variable", "add_variable"}:
                    key = effect["variable_id"]
                    spec = self.variable_specs[key]
                    value = (
                        effect["value"] if kind == "set_variable" else self.variables[key] + effect["value"]
                    )
                    accepted = spec["min"] <= value <= spec["max"]
                    if accepted:
                        self.variables[key] = value
                elif kind in {"set_metric", "add_metric"}:
                    value = (
                        effect["value"]
                        if kind == "set_metric"
                        else metrics()[effect["metric"]] + effect["value"]
                    )
                    accepted = mutate_metric(effect["metric"], value)
                elif kind == "trade":
                    current = metrics()
                    value = current[effect["resource"]] + effect["amount"]
                    accepted = current["money"] >= effect["cost"] and value <= 1000000
                    if accepted:
                        mutate_metric("money", current["money"] - effect["cost"])
                        mutate_metric(effect["resource"], value)
                elif kind == "set_node_visibility":
                    self.overrides.setdefault(effect["node_id"], {})["visible"] = effect["visible"]
                elif kind == "set_node_offset":
                    self.overrides.setdefault(effect["node_id"], {}).update(x=effect["x"], y=effect["y"])
                elif kind == "emit_event":
                    emitted.append(effect["event"])
                elif kind == "play_audio":
                    cues.append(effect["cue_id"])
                elif kind == "dialogue":
                    dialogue(effect["text"])
                elif kind == "teleport":
                    accepted = not collision(effect["x"], effect["y"])
                    if accepted:
                        teleport(effect["x"], effect["y"])
                elif kind == "win":
                    win()
                elif kind == "reward":
                    reward += effect["value"]
                if accepted:
                    self.executed_actions += 1
                else:
                    self.skipped_actions += 1
        self._pose_cache = {}
        self.pending_events = list(dict.fromkeys(emitted))
        return emitted, cues, reward
