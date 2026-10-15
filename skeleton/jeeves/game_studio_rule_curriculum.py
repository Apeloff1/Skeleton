"""AI-proposed, source-bound game-rule variation and multi-condition policy learning.

The model may propose *data*, never executable Python or unrestricted source
patches. Every edit is normalized by the canonical editor/scene validators,
bound to its ancestor source and the real runtime implementation, and run
through the same replay-authoritative Jeeves game-learning environment.

A single Q policy learns across baseline and changed circumstances because
all variants share one pinned environment spec and include their circumstance
in the observed state. Native rendering and production neural-weight updates
are not claimed. No training/promotion authority is supplied by this module.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from hashlib import sha256
import json
import re

from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.system_editors import editor_spec, make_editor_document
from .game_learning_runtime import EpisodeStep, GameEnvironmentSpec
from .game_studio_environment import StudioGameEnvironment, make_studio_source, parse_studio_source

PROPOSAL_SCHEMA = "skeleton.game_builder.ai_rule_proposal.v1"
PLAN_SCHEMA = "skeleton.game_builder.rule_curriculum.v1"
SNAPSHOT_SCHEMA = "skeleton.game_builder.rule_environment_snapshot.v1"
MAX_PROPOSALS = 7
MAX_OPERATIONS = 12
MAX_PLAN_BYTES = 192_000
_ID = re.compile(r"[a-z][a-z0-9_-]{2,47}\Z")
_PATH = re.compile(r"[a-z][a-z0-9_]{0,47}\Z")
_LOCKED = frozenset({
    "id", "seed", "schema", "schema_version", "digest", "source",
    "source_code", "executable", "script", "title", "filename",
    "url", "uri", "signature", "owner", "homebrew_only",
})


class RuleCurriculumError(ValueError):
    """AI-requested mechanics variation is untrusted, unsafe or unreplayable."""


def _bytes(value: object, maximum: int = MAX_PLAN_BYTES) -> bytes:
    try:
        data = json.dumps(value, sort_keys=True, separators=(",", ":"),
                          allow_nan=False, ensure_ascii=True).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise RuleCurriculumError("rule proposals require finite JSON") from exc
    if len(data) > maximum:
        raise RuleCurriculumError("rule proposal exceeds the fixed source budget")
    return data


def _plain(value: object) -> object:
    return json.loads(_bytes(value))


def _sha(value: object) -> str:
    return sha256(_bytes(value)).hexdigest()


def _id(value: object, title: str) -> str:
    if type(value) is not str or not _ID.fullmatch(value):
        raise RuleCurriculumError(title + " requires a stable safe identifier")
    return value


def _scalar(value: object) -> bool:
    return value is None or type(value) in (str, bool, int)


def _alter(current: object, op: str, value: object) -> object:
    if op == "set":
        if not _scalar(value) or current is None or type(current) is not type(value):
            raise RuleCurriculumError("a rule may only replace an existing typed scalar")
        if type(value) is str and (len(value) > 160 or
                                    any(ord(char) < 32 for char in value)):
            raise RuleCurriculumError("rule replacement text exceeds safe limits")
        return value
    if op == "toggle":
        if type(current) is not bool or value is not None:
            raise RuleCurriculumError("toggle requires a boolean source and null argument")
        return not current
    if op in ("add", "multiply"):
        if type(current) is not int or type(value) is not int:
            raise RuleCurriculumError("numeric rule operators require exact integers")
        if abs(value) > 100000 or abs(current) > 100000000:
            raise RuleCurriculumError("rule numeric magnitude exceeds admission")
        return current + value if op == "add" else current * value
    raise RuleCurriculumError("rule operator must be set, toggle, add or multiply")


def _setting_op(settings: dict, metadata: Mapping[str, object],
                op: Mapping[str, object]) -> None:
    key = op["path"]
    if not isinstance(key, str) or not _PATH.fullmatch(key) or key in _LOCKED:
        raise RuleCurriculumError("setting path is protected or undeclared")
    fields = {row["key"]: row for row in metadata["fields"]}
    if key not in fields or key not in settings:
        raise RuleCurriculumError("AI cannot invent game-rule configuration keys")
    field = fields[key]
    operator = op["op"]
    if field["kind"] in ("enum", "text") and operator != "set":
        raise RuleCurriculumError("non-numeric authored rules require exact set")
    if field["kind"] == "bool" and operator not in ("set", "toggle"):
        raise RuleCurriculumError("boolean authored rules cannot be numerically manipulated")
    settings[key] = _alter(settings[key], operator, op["value"])


def _layout_op(layout: dict, op: Mapping[str, object]) -> None:
    path = op["path"]
    if type(path) is not str or not 1 <= len(path) <= 128:
        raise RuleCurriculumError("layout patch path is not admitted")
    parts = path.split("/")
    if not 1 <= len(parts) <= 6:
        raise RuleCurriculumError("source layout path exceeds bounded depth")
    node = layout
    for token in parts[:-1]:
        if token in _LOCKED:
            raise RuleCurriculumError("cannot replace source identity or provenance")
        if type(node) is dict:
            if not _PATH.fullmatch(token) or token not in node:
                raise RuleCurriculumError("AI cannot create authored layout objects")
            node = node[token]
        elif type(node) is list:
            if not token.isdecimal() or (len(token) > 1 and token[0] == "0"):
                raise RuleCurriculumError("layout list indices must be canonical")
            index = int(token)
            if index >= len(node):
                raise RuleCurriculumError("layout patch cannot extend finite arrays")
            node = node[index]
        else:
            raise RuleCurriculumError("layout path traverses a source scalar")
    terminal = parts[-1]
    if terminal in _LOCKED:
        raise RuleCurriculumError("game source identity and provenance cannot be edited")
    if type(node) is dict:
        if not _PATH.fullmatch(terminal) or terminal not in node:
            raise RuleCurriculumError("layout rule is not an existing authored key")
        previous = node[terminal]
        node[terminal] = _alter(previous, op["op"], op["value"])
    elif type(node) is list:
        if not terminal.isdecimal() or (len(terminal) > 1 and terminal[0] == "0"):
            raise RuleCurriculumError("layout list index is not canonical")
        index = int(terminal)
        if index >= len(node):
            raise RuleCurriculumError("layout patch exceeds authored array length")
        previous = node[index]
        node[index] = _alter(previous, op["op"], op["value"])
    else:
        raise RuleCurriculumError("layout rule must address an existing leaf")


def apply_rule_proposal(base_source: Mapping[str, object],
                        proposal: Mapping[str, object]) -> dict[str, object]:
    """Accept untrusted AI-suggested rule changes only as validated game data."""
    source = parse_studio_source(_plain(base_source))
    if type(proposal) is not dict or set(proposal) != {
        "schema_version", "proposal_id", "base_digest", "reason",
        "scene_seed", "operations",
    } or proposal["schema_version"] != PROPOSAL_SCHEMA:
        raise RuleCurriculumError("exact declarative AI rule proposal required")
    _bytes(proposal, 8192)
    _id(proposal["proposal_id"], "AI rule proposal")
    if proposal["base_digest"] != _sha(source):
        raise RuleCurriculumError("stale proposal cannot mutate another game's rules")
    reason = proposal["reason"]
    if (type(reason) is not str or not 8 <= len(reason) <= 160
            or any(ord(ch) < 32 for ch in reason)):
        raise RuleCurriculumError("AI must state a bounded scenario hypothesis")
    seed = proposal["scene_seed"]
    if seed is not None and (type(seed) is not int or not 0 <= seed <= 2**31 - 1):
        raise RuleCurriculumError("scene seed outside canonical original-game bounds")
    operations = proposal["operations"]
    if type(operations) is not list or not 1 <= len(operations) <= MAX_OPERATIONS:
        raise RuleCurriculumError("bounded nonempty typed rule changes required")
    settings = deepcopy(source["settings"])
    metadata = editor_spec(source["editor"])
    seen = set()
    scene_ops = []
    for edit in operations:
        if type(edit) is not dict or set(edit) != {"scope", "path", "op", "value"}:
            raise RuleCurriculumError("AI change requires exact typed operation envelope")
        if edit["scope"] not in ("settings", "layout"):
            raise RuleCurriculumError("rules cannot patch executable source or model policy")
        if type(edit["path"]) is not str:
            raise RuleCurriculumError("rule path is not a string")
        key = (edit["scope"], edit["path"])
        if key in seen:
            raise RuleCurriculumError("duplicate edits to the same mechanic are not deterministic")
        seen.add(key)
        if edit["scope"] == "settings":
            _setting_op(settings, metadata, edit)
        else:
            scene_ops.append(edit)
    try:
        normalized = make_editor_document(source["editor"], settings)["settings"]
        if source["editor"] == "platform_profile" and normalized["homebrew_only"] is not True:
            raise RuleCurriculumError("AI cannot disable the original-game rights boundary")
        scene = None
        if scene_ops or seed is not None:
            if source["editor"] in ("maze", "rpg"):
                raise RuleCurriculumError("these engines do not admit authored scenes")
            if seed is None:
                raise RuleCurriculumError("layout edits require exact source-bound scene seed")
            if (source["scene"] is not None and
                    source["scene"]["seed"] == seed and normalized == source["settings"]):
                layout = deepcopy(source["scene"]["layout"])
            else:
                layout = make_advanced_scene(source["editor"], normalized, seed=seed)["layout"]
            for edit in scene_ops:
                _layout_op(layout, edit)
            scene = make_advanced_scene(source["editor"], normalized, seed=seed,
                                        layout=layout)
        elif source["scene"] is not None:
            if normalized != source["settings"]:
                # A different ruleset requires the scene to be explicitly
                # regenerated and checked, never reuse a stale scene checksum.
                raise RuleCurriculumError("changed rules require a regenerated scene_seed")
            scene = source["scene"]
        variant = make_studio_source(source["editor"], normalized,
                                     scene=scene, actions=source["actions"])
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise RuleCurriculumError("AI mechanics exceeded canonical game-rule bounds") from exc
    if _sha(variant) == _sha(source):
        raise RuleCurriculumError("rule proposal must actually change gameplay circumstances")
    return variant


def make_rule_curriculum(base_source: Mapping[str, object],
                         proposals: Sequence[Mapping[str, object]],
                         *, max_steps: int = 32) -> dict[str, object]:
    base = parse_studio_source(_plain(base_source))
    if (type(proposals) not in (tuple, list) or not 1 <= len(proposals) <= MAX_PROPOSALS
            or type(max_steps) is not int or not 1 <= max_steps <= 128):
        raise RuleCurriculumError("rule scenario/episode budget exceeded")
    entries = [{"scenario_id": "baseline", "proposal": None, "source": base}]
    ids, hashes = {"baseline"}, {_sha(base)}
    for raw in proposals:
        proposal = _plain(raw)
        scenario_id = _id(proposal.get("proposal_id"), "scenario")
        if scenario_id in ids:
            raise RuleCurriculumError("duplicate AI rule proposal identity")
        source = apply_rule_proposal(base, proposal)
        source_hash = _sha(source)
        if source_hash in hashes:
            raise RuleCurriculumError("duplicate scenarios must not inflate curriculum coverage")
        ids.add(scenario_id)
        hashes.add(source_hash)
        entries.append({"scenario_id": scenario_id, "proposal": proposal,
                        "source": source})
    result = {
        "schema_version": PLAN_SCHEMA,
        "max_steps": max_steps,
        "base_source": base,
        "scenarios": entries,
        "production_weights_modified": False,
        "automatic_rule_promotion": False,
    }
    _bytes(result)
    return {**result, "digest": _sha(result)}


def verify_rule_curriculum(value: object) -> dict[str, object]:
    if type(value) is not dict or set(value) != {
        "schema_version", "max_steps", "base_source", "scenarios",
        "production_weights_modified", "automatic_rule_promotion", "digest",
    } or value["schema_version"] != PLAN_SCHEMA:
        raise RuleCurriculumError("exact rule curriculum envelope required")
    _bytes(value)
    scenarios = value["scenarios"]
    if type(scenarios) is not list or not 2 <= len(scenarios) <= MAX_PROPOSALS + 1:
        raise RuleCurriculumError("rule scenarios must include baseline and bounded candidates")
    if (value["production_weights_modified"] is not False or
            value["automatic_rule_promotion"] is not False):
        raise RuleCurriculumError("source proposal cannot claim model/rule promotion")
    proposals = []
    for index, entry in enumerate(scenarios):
        if (type(entry) is not dict or set(entry) != {
            "scenario_id", "proposal", "source"
        }):
            raise RuleCurriculumError("scenario entry contains extraneous authority fields")
        if index == 0:
            if entry["scenario_id"] != "baseline" or entry["proposal"] is not None:
                raise RuleCurriculumError("original-game baseline may not be rewritten")
        else:
            proposals.append(entry["proposal"])
    rebuilt = make_rule_curriculum(value["base_source"], proposals,
                                   max_steps=value["max_steps"])
    if rebuilt != _plain(value):
        raise RuleCurriculumError("rule source, scenario or digest failed independent regeneration")
    return rebuilt


class RuleCurriculumEnvironment:
    """Shared-policy game environment with deterministic circumstance scheduling."""

    def __init__(self, plan: Mapping[str, object]) -> None:
        self.plan = verify_rule_curriculum(_plain(plan))
        self.sources = tuple(row["source"] for row in self.plan["scenarios"])
        self.names = tuple(row["scenario_id"] for row in self.plan["scenarios"])
        seed_env = StudioGameEnvironment(self.sources[0], max_steps=self.plan["max_steps"])
        try:
            child = seed_env.spec
            child_digests = []
            for source in self.sources:
                probe = StudioGameEnvironment(source, max_steps=self.plan["max_steps"])
                try:
                    if probe.spec.actions != child.actions or (
                            probe.spec.observation_bins != child.observation_bins
                            or probe.spec.reward_components != child.reward_components):
                        raise RuleCurriculumError(
                            "a policy must not mix incompatible runtime feature or action contracts"
                        )
                    child_digests.append(probe.spec.environment_digest)
                finally:
                    probe.close()
        finally:
            seed_env.close()
        bins = {name: tuple(values) for name,values in child.observation_bins.items()}
        bins["circumstance"] = (-0.1, 0.1, 0.4, 0.65, 0.9)
        self.spec = GameEnvironmentSpec(
            "studio-rules:" + self.sources[0]["editor"],
            _sha({"rule_plan_digest": self.plan["digest"],
                  "runtime_digests": child_digests,
                  "environment_schema": PLAN_SCHEMA}),
            child.actions, bins, child.reward_components, self.plan["max_steps"],
        )
        self._active: StudioGameEnvironment | None = None
        self._seed: int | None = None
        self._index: int | None = None
        self._chain = ""

    @property
    def done(self) -> bool:
        return False if self._active is None else self._active.done

    @property
    def descriptor(self) -> dict[str, object]:
        return {
            "spec": self.spec.as_dict(),
            "rule_plan_digest": self.plan["digest"],
            "source_digests": [_sha(source) for source in self.sources],
            "schedule": "episode_seed_modulo_scenario_count",
            "training_weights": "local_q_policy_only",
            "production_weights_modified": False,
        }

    def _observation(self, observation: Mapping[str, float]) -> dict[str, float]:
        if self._index is None:
            raise RuleCurriculumError("reset before observing rule scenario")
        # Encodes the scenario as real policy state to prevent learning a
        # false single-context action value across unlike mechanics.
        result = dict(observation)
        result["circumstance"] = self._index / (len(self.sources) - 1)
        return result

    def reset(self, seed: int) -> Mapping[str, float]:
        if type(seed) is not int or not 0 <= seed <= 2**63 - 1:
            raise RuleCurriculumError("bounded source-specific episode seed required")
        self.close()
        self._seed = seed
        self._index = seed % len(self.sources)
        self._active = StudioGameEnvironment(self.sources[self._index],
                                             max_steps=self.plan["max_steps"])
        observed = self._active.reset(seed)
        self._chain = _sha({
            "environment_digest": self.spec.environment_digest,
            "rule_plan_digest": self.plan["digest"],
            "scenario": self.names[self._index], "seed": seed,
            "child_initial": self._active.snapshot()["source_session_digest"],
        })
        return self._observation(observed)

    def step(self, action: str) -> EpisodeStep:
        if self._active is None or self._index is None or self._seed is None:
            raise RuleCurriculumError("reset before game-rule learning")
        result = self._active.step(action)
        current = _sha({
            "environment": self.spec.environment_digest,
            "scenario_id": self.names[self._index],
            "scenario_source_digest": _sha(self.sources[self._index]),
            "seed": self._seed, "action": action,
            "child_transition_digest": result.transition_digest,
            "previous": self._chain,
        })
        self._chain = current
        return EpisodeStep(
            self._observation(result.observation), dict(result.reward_components),
            result.terminated, result.truncated,
            {**dict(result.info), "rule_curriculum_digest": self.plan["digest"],
             "scenario_id": self.names[self._index],
             "scenario_index": self._index,
             "scenario_source_digest": _sha(self.sources[self._index]),
             "source_bound_settings": True},
            current,
        )

    def preview(self) -> dict[str, object] | None:
        if self._active is None or self._index is None:
            return None
        return {
            "schema_version": "skeleton.game_builder.rule_preview.v1",
            "scenario_id": self.names[self._index],
            "source_digest": _sha(self.sources[self._index]),
            "game": self._active.preview(),
            "real_hardware_certified": False,
        }

    def snapshot(self) -> dict[str, object]:
        if self._active is None or self._index is None or self._seed is None:
            raise RuleCurriculumError("reset before rule snapshot")
        payload = {
            "schema_version": SNAPSHOT_SCHEMA,
            "environment_digest": self.spec.environment_digest,
            "rule_plan_digest": self.plan["digest"],
            "scenario_index": self._index, "scenario_id": self.names[self._index],
            "seed": self._seed, "child": self._active.snapshot(),
            "transition_digest": self._chain,
        }
        return {**payload, "digest": _sha(payload)}

    def restore(self, snapshot: Mapping[str, object]) -> Mapping[str, float]:
        if type(snapshot) is not dict or set(snapshot) != {
            "schema_version", "environment_digest", "rule_plan_digest",
            "scenario_index", "scenario_id", "seed", "child",
            "transition_digest", "digest"
        } or snapshot["schema_version"] != SNAPSHOT_SCHEMA:
            raise RuleCurriculumError("exact source-bound rule snapshot required")
        _bytes(snapshot)
        raw = {key: value for key,value in snapshot.items() if key != "digest"}
        if (_sha(raw) != snapshot["digest"]
                or snapshot["environment_digest"] != self.spec.environment_digest
                or snapshot["rule_plan_digest"] != self.plan["digest"]):
            raise RuleCurriculumError("rule snapshot identity or checksum differs")
        child = snapshot["child"]
        if type(child) is not dict or type(child.get("actions")) is not list:
            raise RuleCurriculumError("rule snapshot must contain replayable game commands")
        candidate = type(self)(self.plan)
        candidate.reset(snapshot["seed"])
        if snapshot["scenario_index"] != candidate._index or (
                snapshot["scenario_id"] != candidate.names[candidate._index]):
            raise RuleCurriculumError("seed-modulo scenario schedule cannot be forged")
        for command in child["actions"]:
            if candidate.done:
                raise RuleCurriculumError("replayed scenario advanced past terminal state")
            candidate.step(command)
        if candidate.snapshot() != _plain(snapshot):
            raise RuleCurriculumError("snapshot differs from independent original-game replay")
        self.close()
        self._active, self._seed, self._index, self._chain = (
            candidate._active, candidate._seed, candidate._index, candidate._chain,
        )
        return self._observation(self._active.snapshot()["observation"])

    def close(self) -> None:
        if self._active is not None:
            self._active.close()
        self._active = None
        self._seed = None
        self._index = None
        self._chain = ""


__all__ = [
    "PROPOSAL_SCHEMA", "PLAN_SCHEMA", "SNAPSHOT_SCHEMA", "MAX_PROPOSALS",
    "RuleCurriculumError", "apply_rule_proposal", "make_rule_curriculum",
    "verify_rule_curriculum", "RuleCurriculumEnvironment",
]
