"""Reviewed original-world resource economy with bounded deterministic replay.

Source-only engine handoff; no payment, real currency, external assets or device
qualification. Every publication is operator-reviewed under a world-wide lease.
"""
from __future__ import annotations

from collections import deque
from hashlib import sha256
import base64
import html
import os
from typing import Any

from .bundle import _artifact_read
from .session import SessionStore, validate_session
from .world_canon import (
    CanonError, WorldStore, _id, _keys, _list, _text,
    canonical, digest, prove, strict_json,
)

SCHEMA = "jeeves.world.economy.v1"
RECEIPT_SCHEMA = "jeeves.world.economy_receipt.v1"
MAX_RESOURCES = 8
MAX_EFFECTS = 512
MAX_BALANCE = 100
MAX_ECONOMY_STATES = 4096


def _quantity(value: Any, label: str) -> int:
    if type(value) is not int or value < 0 or value > MAX_BALANCE:
        raise CanonError("economy_invalid_quantity", label)
    return value


def _amounts(value: Any, resource_ids: set[str], label: str) -> dict[str, int]:
    if type(value) is not dict or not set(value) <= resource_ids:
        raise CanonError("economy_invalid_resource_map", label)
    for key, amount in value.items():
        _id(key, label)
        _quantity(amount, label)
    return value


def validate_economy(source: Any, world: Any) -> dict[str, Any]:
    prove(world)
    data = _keys(source, {
        "schema", "world_id", "world_digest", "prompt", "resources",
        "effects", "approved", "review_note",
    })
    if data["schema"] != SCHEMA:
        raise CanonError("economy_schema_mismatch")
    if data["world_id"] != world["id"] or data["world_digest"] != digest(world):
        raise CanonError("economy_world_lease_mismatch")
    _text(data["prompt"], "prompt", 4096)
    if type(data["approved"]) is not bool:
        raise CanonError("economy_invalid_approval")
    if data["approved"]:
        _text(data["review_note"], "review_note", 400)
    elif data["review_note"] != "":
        raise CanonError("economy_unreviewed_note")
    resources = _list(data["resources"], "resources", MAX_RESOURCES)
    if not resources:
        raise CanonError("economy_empty_resources")
    ids: set[str] = set()
    for resource in resources:
        _keys(resource, {"id", "name", "initial", "capacity"})
        rid = _id(resource["id"], "resource.id")
        if rid in ids:
            raise CanonError("economy_duplicate_resource", rid)
        ids.add(rid)
        _text(resource["name"], "resource.name")
        initial = _quantity(resource["initial"], "initial")
        capacity = _quantity(resource["capacity"], "capacity")
        if capacity == 0 or initial > capacity:
            raise CanonError("economy_invalid_capacity", rid)
    if resources != sorted(resources, key=lambda r: r["id"]):
        raise CanonError("economy_resource_order")
    choice_ids = {choice["id"] for choice in world["choices"]}
    effects = _list(data["effects"], "effects", MAX_EFFECTS)
    seen: set[str] = set()
    for effect in effects:
        _keys(effect, {"choice", "costs", "gains"})
        cid = _id(effect["choice"], "effect.choice")
        if cid not in choice_ids or cid in seen:
            raise CanonError("economy_invalid_choice_effect", cid)
        seen.add(cid)
        _amounts(effect["costs"], ids, "costs")
        _amounts(effect["gains"], ids, "gains")
        if not effect["costs"] and not effect["gains"]:
            raise CanonError("economy_empty_effect", cid)
    if effects != sorted(effects, key=lambda e: e["choice"]):
        raise CanonError("economy_effect_order")
    if len(canonical(data)) > 524288:
        raise CanonError("economy_source_too_large")
    return data


def _graph(source: Any, world: Any):
    data = validate_economy(source, world)
    resources = data["resources"]
    resource_ids = [r["id"] for r in resources]
    capacities = tuple(r["capacity"] for r in resources)
    effects = {effect["choice"]: effect for effect in data["effects"]}
    edges: dict[str, list[Any]] = {}
    for edge in world["choices"]:
        edges.setdefault(edge["from"], []).append(edge)
    for values in edges.values():
        values.sort(key=lambda e: e["id"])
    return data, resource_ids, capacities, effects, edges


def _advance(edge: Any, balances: tuple[int, ...], resource_ids: list[str],
             capacities: tuple[int, ...], effects: dict[str, Any]) -> tuple[int, ...] | None:
    effect = effects.get(edge["id"], {"costs": {}, "gains": {}})
    result = []
    for index, rid in enumerate(resource_ids):
        cost = effect["costs"].get(rid, 0)
        gain = effect["gains"].get(rid, 0)
        if cost > balances[index]:
            return None
        amount = balances[index] - cost + gain
        if amount > capacities[index]:
            return None
        result.append(amount)
    return tuple(result)


def prove_economy(source: Any, world: Any) -> dict[str, Any]:
    data, resource_ids, capacities, effects, edges = _graph(source, world)
    initial = tuple(r["initial"] for r in data["resources"])
    start = (world["start"], frozenset(), initial)
    queue = deque([(start, ())])
    seen = {start}
    ending_ids = {item["scene"] for item in world["endings"]}
    witnesses: dict[str, list[str]] = {}
    exercised: set[str] = set()
    while queue:
        (scene, flags, balances), path = queue.popleft()
        if scene in ending_ids:
            witnesses.setdefault(scene, list(path))
            continue
        enabled = 0
        for edge in edges.get(scene, []):
            if not set(edge["requires"]) <= flags:
                continue
            updated = _advance(edge, balances, resource_ids, capacities, effects)
            if updated is None:
                continue
            enabled += 1
            exercised.add(edge["id"])
            state = (edge["to"], flags | frozenset(edge["grants"]), updated)
            if state not in seen:
                seen.add(state)
                if len(seen) > MAX_ECONOMY_STATES:
                    raise CanonError("economy_state_budget_exhausted")
                queue.append((state, path + (edge["id"],)))
        if not enabled:
            raise CanonError("economy_reachable_dead_end", scene)
    if set(witnesses) != ending_ids:
        raise CanonError("economy_unreachable_endings")
    if set(effects) - exercised:
        raise CanonError("economy_unreachable_effect")
    return {
        "schema": "jeeves.world.economy_proof.v1",
        "world_digest": digest(world), "economy_digest": digest(data),
        "states_explored": len(seen),
        "ending_witnesses": {key: witnesses[key] for key in sorted(witnesses)},
        "exercised_effects": sorted(set(effects) & exercised),
    }


def replay_economy(source: Any, world: Any, choices: Any) -> dict[str, Any]:
    data, resource_ids, capacities, effects, edges = _graph(source, world)
    if type(choices) is not list or len(choices) > 512:
        raise CanonError("economy_invalid_trace")
    scene = world["start"]
    flags: frozenset[str] = frozenset()
    balances = tuple(r["initial"] for r in data["resources"])
    trace = []
    for choice_id in choices:
        _id(choice_id, "choice")
        matches = [edge for edge in edges.get(scene, [])
                   if edge["id"] == choice_id and set(edge["requires"]) <= flags]
        if len(matches) != 1:
            raise CanonError("economy_invalid_transition")
        edge = matches[0]
        next_balances = _advance(edge, balances, resource_ids, capacities, effects)
        if next_balances is None:
            raise CanonError("economy_unaffordable_transition")
        scene = edge["to"]
        flags = flags | frozenset(edge["grants"])
        balances = next_balances
        trace.append({"choice": choice_id, "scene": scene,
                      "balances": dict(zip(resource_ids, balances))})
    return {
        "schema": "jeeves.world.economy_replay.v1",
        "world_id": world["id"], "world_digest": digest(world),
        "economy_digest": digest(data), "scene": scene,
        "ending": scene in {item["scene"] for item in world["endings"]},
        "balances": dict(zip(resource_ids, balances)),
        "flags": sorted(flags), "trace": trace,
    }


def propose_economy(world: Any, *, prompt: str, resource_id: str,
                    name: str, initial: int, capacity: int,
                    choice_id: str, cost: int, gain: int) -> dict[str, Any]:
    _text(prompt, "prompt", 4096)
    _id(resource_id, "resource_id")
    _text(name, "name")
    _id(choice_id, "choice_id")
    if cost == 0 and gain == 0:
        raise CanonError("economy_empty_effect")
    source = {
        "schema": SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "prompt": prompt,
        "resources": [{"id": resource_id, "name": name,
                       "initial": initial, "capacity": capacity}],
        "effects": [{"choice": choice_id,
                     "costs": {resource_id: cost} if cost else {},
                     "gains": {resource_id: gain} if gain else {}}],
        "approved": False, "review_note": "",
    }
    prove_economy(source, world)
    return source


def edit_economy(source: Any, world: Any, operation: Any) -> dict[str, Any]:
    validate_economy(source, world)
    candidate = strict_json(canonical(source))
    op = _keys(operation, {"action", "value"})
    action, value = op["action"], op["value"]
    if action in {"add_resource", "replace_resource"}:
        _keys(value, {"id", "name", "initial", "capacity"})
        existing = [r for r in candidate["resources"] if r["id"] == value["id"]]
        if (action == "add_resource" and existing) or (
            action == "replace_resource" and len(existing) != 1
        ):
            raise CanonError("economy_invalid_resource_edit")
        candidate["resources"] = [r for r in candidate["resources"]
                                  if r["id"] != value["id"]] + [value]
    elif action == "remove_resource":
        _keys(value, {"id"})
        if not any(r["id"] == value["id"] for r in candidate["resources"]):
            raise CanonError("economy_unknown_resource")
        candidate["resources"] = [r for r in candidate["resources"]
                                  if r["id"] != value["id"]]
    elif action == "upsert_effect":
        _keys(value, {"choice", "costs", "gains"})
        candidate["effects"] = [e for e in candidate["effects"]
                                if e["choice"] != value["choice"]] + [value]
    elif action == "remove_effect":
        _keys(value, {"choice"})
        if not any(e["choice"] == value["choice"] for e in candidate["effects"]):
            raise CanonError("economy_unknown_effect")
        candidate["effects"] = [e for e in candidate["effects"]
                                if e["choice"] != value["choice"]]
    else:
        raise CanonError("economy_invalid_edit")
    candidate["resources"].sort(key=lambda r: r["id"])
    candidate["effects"].sort(key=lambda e: e["choice"])
    candidate["approved"] = False
    candidate["review_note"] = ""
    prove_economy(candidate, world)
    return candidate


def approve_economy(source: Any, world: Any, review_note: str) -> dict[str, Any]:
    _text(review_note, "review_note")
    prove_economy(source, world)
    candidate = strict_json(canonical(source))
    candidate["approved"] = True
    candidate["review_note"] = review_note
    prove_economy(candidate, world)
    return candidate


PLAYER_JS = r"""
"use strict";
const data = JSON.parse(document.getElementById("economy-data").textContent);
const world = data.world, economy = data.economy;
const root = document.getElementById("play");
const effects = new Map(economy.effects.map(e => [e.choice, e]));
const scenes = new Map(world.scenes.map(s => [s.id, s]));
const endings = new Map(world.endings.map(e => [e.scene, e.label]));
let scene, flags, balances, trace;
function node(tag, value) {
  const element = document.createElement(tag);
  element.textContent = value;
  return element;
}
function reset() {
  scene = world.start; flags = new Set(); trace = [];
  balances = new Map(economy.resources.map(r => [r.id, r.initial]));
  render();
}
function available(choice) {
  if (!choice.requires.every(flag => flags.has(flag))) return false;
  const effect = effects.get(choice.id) || {costs: {}, gains: {}};
  return economy.resources.every(r => {
    const next = balances.get(r.id) - (effect.costs[r.id] || 0) +
      (effect.gains[r.id] || 0);
    return next >= 0 && next <= r.capacity;
  });
}
function advance(choice) {
  const effect = effects.get(choice.id) || {costs: {}, gains: {}};
  for (const r of economy.resources)
    balances.set(r.id, balances.get(r.id) - (effect.costs[r.id] || 0) +
      (effect.gains[r.id] || 0));
  choice.grants.forEach(flag => flags.add(flag));
  trace.push(choice.id); scene = choice.to; render();
}
function render() {
  root.replaceChildren();
  const here = scenes.get(scene);
  root.append(node("h1", here.title), node("p", here.narrative));
  for (const resource of economy.resources)
    root.append(node("p", resource.name + ": " + balances.get(resource.id) +
      "/" + resource.capacity));
  root.append(node("p", "Choices: " + trace.join(", ")));
  if (endings.has(scene)) {
    root.append(node("h2", "Ending: " + endings.get(scene)));
  } else {
    for (const choice of world.choices.filter(c => c.from === scene && available(c))) {
      const button = node("button", choice.label);
      button.type = "button";
      button.addEventListener("click", () => advance(choice));
      root.append(button);
    }
  }
  const restart = node("button", "Restart");
  restart.type = "button";
  restart.addEventListener("click", reset);
  root.append(restart);
}
reset();
""".strip()


def compile_economy(source: Any, world: Any) -> tuple[dict[str, Any], bytes]:
    if source["approved"] is not True:
        raise CanonError("economy_review_required")
    proof = prove_economy(source, world)
    recipe = {
        "schema": "jeeves.world.economy_engine_recipe.v1",
        "world_id": world["id"], "world_digest": digest(world),
        "economy_digest": digest(source), "resources": source["resources"],
        "effects": source["effects"], "proof": proof,
        "qualification": "original_source_recipe_not_device_certified",
    }
    embedded = canonical({"world": world, "economy": source}).decode(
        "utf-8").replace("<", "\\u003c")
    script_hash = base64.b64encode(sha256(PLAYER_JS.encode()).digest()).decode()
    markup = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'sha256-" + script_hash +
        "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
        "base-uri 'none'; form-action 'none'" + '">'
        "<title>Original economy: " + html.escape(world["id"]) +
        "</title></head><body><main id=\"play\" aria-live=\"polite\"></main>"
        '<script id="economy-data" type="application/json">' + embedded +
        "</script><script>" + PLAYER_JS + "</script></body></html>\n"
    ).encode("utf-8")
    if len(markup) > 1572864:
        raise CanonError("economy_playable_too_large")
    return recipe, markup


class EconomyStore:
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str, str]:
        _id(world_id, "world_id")
        return (world_id + ".economy.json",
                world_id + ".economy.playable.html",
                world_id + ".economy.engine.json",
                world_id + ".economy.receipt.json")

    @staticmethod
    def _lock(fd: int, world_id: str) -> None:
        _id(world_id, "world_id")
        try:
            handle = os.open(world_id + ".lock", os.O_WRONLY | os.O_CREAT |
                             os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        except FileExistsError:
            raise CanonError("lease_busy") from None
        os.close(handle)

    def _world(self, fd: int, world_id: str) -> Any:
        _id(world_id, "world_id")
        world = strict_json(self.worlds._read(fd, world_id + ".json"))
        prove(world)
        if world["id"] != world_id:
            raise CanonError("economy_world_identity_mismatch")
        return world

    def _source(self, fd: int, world_id: str, world: Any) -> Any:
        source = strict_json(self.worlds._read(fd, self._names(world_id)[0]))
        return validate_economy(source, world)

    def inspect(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                source = self._source(fd, world_id, world)
                return {"economy": source, "proof": prove_economy(source, world)}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def propose(self, world_id: str, **kwargs: Any) -> dict[str, Any]:
        world = self.worlds.read(world_id)
        return propose_economy(world, **kwargs)

    def publish(self, world_id: str, source: Any, *,
                expected_digest: str | None = None, create: bool = False) -> str:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                prove_economy(source, world)
                if source["approved"]:
                    raise CanonError("economy_approval_requires_review")
                try:
                    previous = self._source(fd, world_id, world)
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    previous = None
                if create:
                    if previous is not None or expected_digest is not None:
                        raise CanonError("economy_already_exists")
                elif previous is None or digest(previous) != expected_digest:
                    raise CanonError("economy_stale_edit")
                self.worlds._write(fd, self._names(world_id)[0], canonical(source))
                return digest(source)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def edit(self, world_id: str, expected_digest: str, operation: Any) -> str:
        inspected = self.inspect(world_id)
        if digest(inspected["economy"]) != expected_digest:
            raise CanonError("economy_stale_edit")
        updated = edit_economy(
            inspected["economy"], self.worlds.read(world_id), operation)
        return self.publish(world_id, updated, expected_digest=expected_digest)

    def approve(self, world_id: str, expected_digest: str, review_note: str) -> str:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                source = self._source(fd, world_id, world)
                if digest(source) != expected_digest:
                    raise CanonError("economy_stale_edit")
                approved = approve_economy(source, world, review_note)
                self.worlds._write(fd, self._names(world_id)[0], canonical(approved))
                return digest(approved)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def _outputs(self, source: Any, world: Any):
        recipe, markup = compile_economy(source, world)
        manifest = canonical(recipe)
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world["id"],
            "world_digest": digest(world), "economy_digest": digest(source),
            "proof_digest": digest(recipe["proof"]),
            "artifacts": {
                self._names(world["id"])[1]: sha256(markup).hexdigest(),
                self._names(world["id"])[2]: sha256(manifest).hexdigest(),
            },
            "qualification": "reviewed_source_only_not_release_certified",
        }
        return receipt, markup, manifest

    def compile(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                source = self._source(fd, world_id, world)
                if digest(source) != expected_digest:
                    raise CanonError("economy_stale_edit")
                receipt, markup, manifest = self._outputs(source, world)
                names = self._names(world_id)
                self.worlds._write(fd, names[1], markup)
                self.worlds._write(fd, names[2], manifest)
                self.worlds._write(fd, names[3], canonical(receipt))
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def verify(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                source = self._source(fd, world_id, world)
                receipt, markup, manifest = self._outputs(source, world)
                names = self._names(world_id)
                if strict_json(self.worlds._read(fd, names[3])) != receipt:
                    raise CanonError("economy_receipt_mismatch")
                if _artifact_read(fd, names[1]) != markup:
                    raise CanonError("economy_playable_mismatch")
                if _artifact_read(fd, names[2]) != manifest:
                    raise CanonError("economy_recipe_mismatch")
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def player(self, world_id: str, slot: str) -> dict[str, Any]:
        _id(slot, "slot")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                source = self._source(fd, world_id, world)
                if source["approved"] is not True:
                    raise CanonError("economy_review_required")
                session = validate_session(strict_json(self.worlds._read(
                    fd, SessionStore._name(world_id, slot))), world)
                from .economy_session import economy_player_view
                return {"slot": slot, **economy_player_view(source, world, session)}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def editor(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        from .economy_editor import render_editor
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                source = self._source(fd, world_id, world)
                if digest(source) != expected_digest:
                    raise CanonError("economy_stale_edit")
                content = render_editor(source, world)
                name = world_id + ".economy.editor.html"
                self.worlds._write(fd, name, content)
                return {"html_file": name, "html_sha256": sha256(content).hexdigest(),
                        "economy_digest": digest(source)}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
