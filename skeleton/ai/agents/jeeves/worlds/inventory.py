"""Reviewed, source-leased inventory and item consequences for original worlds.

A choice can award or spend authored items. Every transition is replayable and
the bounded state graph proves no reachable non-ending becomes inventory-locked.
No model proposal is allowed to approve itself or write source implicitly.
"""
from __future__ import annotations

from collections import deque
from hashlib import sha256
import base64
import html
import os
from typing import Any

from .bundle import _artifact_read
from .world_canon import (
    CanonError, WorldStore, _id, _keys, _list, _text,
    canonical, digest, prove, strict_json,
)

SCHEMA = "jeeves.world.inventory.v1"
PROOF_SCHEMA = "jeeves.world.inventory_proof.v1"
RECEIPT_SCHEMA = "jeeves.world.inventory_receipt.v1"
MAX_ITEMS = 16
MAX_STATES = 8192
MAX_QTY = 9
MAX_HTML_BYTES = 1048576


def _quantity(value: Any, field: str) -> int:
    if type(value) is not int or not 0 <= value <= MAX_QTY:
        raise CanonError("inventory_invalid_quantity", field)
    return value


def validate_inventory(data: Any, world: Any) -> dict[str, Any]:
    prove(world)
    obj = _keys(data, {
        "schema", "world_id", "world_digest", "prompt", "items", "effects",
        "approved", "review_note",
    })
    if obj["schema"] != SCHEMA:
        raise CanonError("inventory_schema_mismatch")
    if obj["world_id"] != world["id"] or obj["world_digest"] != digest(world):
        raise CanonError("inventory_source_lease_mismatch")
    _text(obj["prompt"], "prompt", 4096)
    _text(obj["review_note"], "review_note", 512)
    if type(obj["approved"]) is not bool:
        raise CanonError("inventory_invalid_approval")
    items = _list(obj["items"], "items", MAX_ITEMS)
    if not items:
        raise CanonError("inventory_empty")
    item_ids = set()
    for item in items:
        _keys(item, {"id", "name", "description", "initial", "capacity"})
        iid = _id(item["id"], "item.id")
        if iid in item_ids:
            raise CanonError("inventory_duplicate_item", iid)
        item_ids.add(iid)
        _text(item["name"], "item.name", 200)
        _text(item["description"], "item.description", 2048)
        capacity = _quantity(item["capacity"], "item.capacity")
        initial = _quantity(item["initial"], "item.initial")
        if capacity == 0 or initial > capacity:
            raise CanonError("inventory_invalid_capacity", iid)
    if [item["id"] for item in items] != sorted(item_ids):
        raise CanonError("inventory_unsorted_items")
    choice_ids = {choice["id"] for choice in world["choices"]}
    effect_ids = set()
    for effect in _list(obj["effects"], "effects", len(choice_ids) + 1):
        _keys(effect, {"choice", "spend", "gain"})
        choice = _id(effect["choice"], "effect.choice")
        if choice not in choice_ids or choice in effect_ids:
            raise CanonError("inventory_invalid_choice", choice)
        effect_ids.add(choice)
        for field in ("spend", "gain"):
            changes = _list(effect[field], field, MAX_ITEMS)
            ids = []
            for change in changes:
                _keys(change, {"item", "quantity"})
                iid = _id(change["item"], "change.item")
                if iid not in item_ids:
                    raise CanonError("inventory_unknown_item", iid)
                amount = _quantity(change["quantity"], "change.quantity")
                if amount == 0:
                    raise CanonError("inventory_zero_effect", iid)
                ids.append(iid)
            if ids != sorted(set(ids)):
                raise CanonError("inventory_unsorted_effects", field)
        if set(x["item"] for x in effect["spend"]) & set(x["item"] for x in effect["gain"]):
            raise CanonError("inventory_conflicting_effect", choice)
    if [effect["choice"] for effect in obj["effects"]] != sorted(effect_ids):
        raise CanonError("inventory_unsorted_choices")
    if len(canonical(obj)) > 524288:
        raise CanonError("inventory_source_too_large")
    return obj


def _transitions(world: Any, data: Any) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    edges: dict[str, list[dict[str, Any]]] = {}
    for choice in world["choices"]:
        edges.setdefault(choice["from"], []).append(choice)
    for choices in edges.values():
        choices.sort(key=lambda value: value["id"])
    return edges, {effect["choice"]: effect for effect in data["effects"]}


def _apply(items: list[dict[str, Any]], amounts: tuple[int, ...], effect: Any) -> tuple[int, ...] | None:
    if effect is None:
        return amounts
    positions = {item["id"]: i for i, item in enumerate(items)}
    updated = list(amounts)
    for change in effect["spend"]:
        index = positions[change["item"]]
        if updated[index] < change["quantity"]:
            return None
        updated[index] -= change["quantity"]
    for change in effect["gain"]:
        index = positions[change["item"]]
        updated[index] += change["quantity"]
        if updated[index] > items[index]["capacity"]:
            return None
    return tuple(updated)


def prove_inventory(data: Any, world: Any) -> dict[str, Any]:
    obj = validate_inventory(data, world)
    items = obj["items"]
    edges, effects = _transitions(world, obj)
    endings = {entry["scene"] for entry in world["endings"]}
    initial = (world["start"], frozenset(), tuple(item["initial"] for item in items))
    queue = deque([(initial, ())])
    visited = {initial}
    ending_witnesses: dict[str, Any] = {}
    item_witnesses: dict[str, Any] = {}
    effect_witnesses: dict[str, Any] = {}
    while queue:
        (scene, flags, quantities), trace = queue.popleft()
        for index, item in enumerate(items):
            if quantities[index] and item["id"] not in item_witnesses:
                item_witnesses[item["id"]] = list(trace)
        if scene in endings:
            ending_witnesses.setdefault(scene, {
                "choices": list(trace),
                "inventory": {item["id"]: quantities[i] for i, item in enumerate(items)},
                "flags": sorted(flags),
            })
            continue
        enabled = 0
        for choice in edges.get(scene, ()):
            if not set(choice["requires"]) <= flags:
                continue
            next_quantities = _apply(items, quantities, effects.get(choice["id"]))
            if next_quantities is None:
                continue
            enabled += 1
            next_trace = trace + (choice["id"],)
            if choice["id"] in effects:
                effect_witnesses.setdefault(choice["id"], list(next_trace))
            state = (
                choice["to"],
                flags | frozenset(choice["grants"]),
                next_quantities,
            )
            if state not in visited:
                visited.add(state)
                if len(visited) > MAX_STATES:
                    raise CanonError("inventory_state_budget")
                queue.append((state, next_trace))
        if enabled == 0:
            raise CanonError("inventory_reachable_dead_end", scene)
    missing = endings - set(ending_witnesses)
    if missing:
        raise CanonError("inventory_unreachable_endings", ",".join(sorted(missing)))
    missing_effects = set(effects) - set(effect_witnesses)
    if missing_effects:
        raise CanonError("inventory_unreachable_effects", ",".join(sorted(missing_effects)))
    return {
        "schema": PROOF_SCHEMA,
        "world_id": world["id"],
        "world_digest": digest(world),
        "inventory_digest": digest(obj),
        "states_explored": len(visited),
        "ending_witnesses": {k: ending_witnesses[k] for k in sorted(ending_witnesses)},
        "item_witnesses": {k: item_witnesses[k] for k in sorted(item_witnesses)},
        "effect_witnesses": {k: effect_witnesses[k] for k in sorted(effect_witnesses)},
        "qualification": "bounded_item_consequences_and_no_softlocks",
    }


def propose_inventory(world: Any, *, prompt: str, item_id: str, name: str,
                      description: str, pickup_choice: str) -> dict[str, Any]:
    _text(prompt, "prompt", 4096)
    _id(item_id, "item_id")
    _text(name, "name", 200)
    _text(description, "description", 2048)
    obj = {
        "schema": SCHEMA, "world_id": world["id"], "world_digest": digest(world),
        "prompt": prompt,
        "items": [{
            "id": item_id, "name": name, "description": description,
            "initial": 0, "capacity": 9,
        }],
        "effects": [{
            "choice": pickup_choice, "spend": [],
            "gain": [{"item": item_id, "quantity": 1}],
        }],
        "approved": False,
        "review_note": "Awaiting original-author item review",
    }
    prove_inventory(obj, world)
    return obj


def edit_inventory(data: Any, world: Any, operation: Any) -> dict[str, Any]:
    obj = validate_inventory(data, world)
    op = _keys(operation, {"action", "value"})
    candidate = strict_json(canonical(obj))
    action, value = op["action"], op["value"]
    if action == "replace_item":
        _keys(value, {"id", "name", "description", "initial", "capacity"})
        matches = [i for i, item in enumerate(candidate["items"]) if item["id"] == value["id"]]
        if len(matches) != 1:
            raise CanonError("inventory_unknown_edit_item")
        candidate["items"][matches[0]] = value
    elif action == "add_item":
        _keys(value, {"id", "name", "description", "initial", "capacity"})
        candidate["items"].append(value)
        candidate["items"].sort(key=lambda item: item["id"])
    elif action == "upsert_effect":
        _keys(value, {"choice", "spend", "gain"})
        candidate["effects"] = [item for item in candidate["effects"] if item["choice"] != value["choice"]]
        candidate["effects"].append(value)
        candidate["effects"].sort(key=lambda item: item["choice"])
    elif action == "remove_effect":
        _keys(value, {"choice"})
        before = len(candidate["effects"])
        candidate["effects"] = [item for item in candidate["effects"] if item["choice"] != value["choice"]]
        if len(candidate["effects"]) == before:
            raise CanonError("inventory_unknown_edit_effect")
    else:
        raise CanonError("inventory_unsupported_edit")
    candidate["approved"] = False
    candidate["review_note"] = "Review required after inventory edit"
    prove_inventory(candidate, world)
    return candidate


_PLAYER_JS = r"""
"use strict";
const model = JSON.parse(document.getElementById("inventory-data").textContent);
const world = model.world;
const source = model.inventory;
const scenes = new Map(world.scenes.map(s => [s.id, s]));
const endings = new Map(world.endings.map(e => [e.scene, e.label]));
const effects = new Map(source.effects.map(e => [e.choice, e]));
const capacities = new Map(source.items.map(i => [i.id, i.capacity]));
let current = world.start;
let flags = new Set();
let stock = new Map(source.items.map(i => [i.id, i.initial]));
let trace = [];
const root = document.getElementById("play");
function element(tag, label) {
  const node = document.createElement(tag);
  node.textContent = label;
  return node;
}
function nextStock(choice) {
  if (!choice.requires.every(flag => flags.has(flag))) return null;
  const effect = effects.get(choice.id);
  const next = new Map(stock);
  if (effect) {
    for (const change of effect.spend) {
      if (next.get(change.item) < change.quantity) return null;
      next.set(change.item, next.get(change.item) - change.quantity);
    }
    for (const change of effect.gain) {
      const quantity = next.get(change.item) + change.quantity;
      if (quantity > capacities.get(change.item)) return null;
      next.set(change.item, quantity);
    }
  }
  return next;
}
function render() {
  root.replaceChildren();
  const scene = scenes.get(current);
  root.append(element("h1", scene.title), element("p", scene.narrative));
  const inventory = element("section", "");
  inventory.setAttribute("aria-label", "Inventory");
  inventory.append(element("h2", "Inventory"));
  for (const item of source.items) {
    inventory.append(element("p", item.name + ": " + stock.get(item.id)));
  }
  root.append(inventory);
  root.append(element("p", "Choices: " + trace.join(", ")));
  if (endings.has(current)) {
    root.append(element("h2", "Ending: " + endings.get(current)));
    const restart = element("button", "Restart");
    restart.addEventListener("click", () => {
      current = world.start; flags = new Set();
      stock = new Map(source.items.map(i => [i.id, i.initial]));
      trace = []; render();
    });
    root.append(restart);
    return;
  }
  for (const choice of world.choices.filter(c => c.from === current)) {
    if (nextStock(choice) === null) continue;
    const button = element("button", choice.label);
    button.addEventListener("click", () => {
      const updated = nextStock(choice);
      if (updated === null) return;
      stock = updated;
      for (const flag of choice.grants) flags.add(flag);
      current = choice.to; trace.push(choice.id); render();
    });
    root.append(button);
  }
}
render();
""".strip()


def compile_inventory_html(data: Any, world: Any) -> bytes:
    prove_inventory(data, world)
    if not data["approved"]:
        raise CanonError("inventory_review_required")
    payload = canonical({"world": world, "inventory": data}).decode("utf-8").replace("<", "\\u003c")
    script_hash = base64.b64encode(sha256(_PLAYER_JS.encode()).digest()).decode("ascii")
    title = html.escape(world["id"], quote=True)
    markup = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "script-src 'sha256-" + script_hash + "'; connect-src 'none'; "
        'style-src \'none\'; img-src \'none\'; base-uri \'none\'; form-action \'none\'">'
        '<title>' + title + ' inventory</title></head><body>'
        '<main id="play" aria-live="polite"></main>'
        '<script id="inventory-data" type="application/json">' + payload + '</script>'
        '<script>' + _PLAYER_JS + '</script></body></html>\n'
    ).encode("utf-8")
    if len(markup) > MAX_HTML_BYTES:
        raise CanonError("inventory_playable_too_large")
    return markup


class InventoryStore:
    def __init__(self, root: str) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str]:
        _id(world_id, "world_id")
        return (
            world_id + ".inventory.json",
            world_id + ".inventory.playable.html",
            world_id + ".inventory.receipt.json",
        )

    def _read(self, fd: int, world_id: str, world: Any) -> dict[str, Any]:
        source = strict_json(self.worlds._read(fd, self._names(world_id)[0]))
        validate_inventory(source, world)
        return source

    def _world(self, fd: int, world_id: str) -> dict[str, Any]:
        source = strict_json(self.worlds._read(fd, world_id + ".json"))
        prove(source)
        if source["id"] != world_id:
            raise CanonError("identity_mismatch")
        return source

    @staticmethod
    def _lock(fd: int, world_id: str) -> None:
        try:
            handle = os.open(world_id + ".lock",
                             os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=fd)
        except FileExistsError:
            raise CanonError("lease_busy") from None
        os.close(handle)

    def propose(self, world_id: str, **kwargs: Any) -> dict[str, Any]:
        return propose_inventory(self.worlds.read(world_id), **kwargs)

    def inspect(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world = self._world(fd, world_id)
            data = self._read(fd, world_id, world)
            return {"inventory": data, "proof": prove_inventory(data, world)}
        finally:
            os.close(fd)

    def publish(self, world_id: str, data: Any, *,
                expected_digest: str | None = None, create: bool = False) -> str:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                candidate = strict_json(canonical(data))
                if type(candidate) is not dict:
                    raise CanonError("expected_object")
                candidate["approved"] = False
                candidate["review_note"] = "Review required after source publication"
                prove_inventory(candidate, world)
                name = self._names(world_id)[0]
                try:
                    current = self._read(fd, world_id, world)
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    current = None
                if create:
                    if current is not None or expected_digest is not None:
                        raise CanonError("inventory_already_exists")
                elif current is None or expected_digest != digest(current):
                    raise CanonError("inventory_stale_edit")
                self.worlds._write(fd, name, canonical(candidate))
                return digest(candidate)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def approve(self, world_id: str, *, expected_digest: str, review_note: str) -> str:
        _text(review_note, "review_note", 512)
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                data = self._read(fd, world_id, world)
                if digest(data) != expected_digest:
                    raise CanonError("inventory_stale_edit")
                data["approved"] = True
                data["review_note"] = review_note
                prove_inventory(data, world)
                self.worlds._write(fd, self._names(world_id)[0], canonical(data))
                return digest(data)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def _outputs(self, data: Any, world: Any) -> tuple[dict[str, Any], bytes]:
        proof = prove_inventory(data, world)
        playable = compile_inventory_html(data, world)
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world["id"],
            "world_digest": digest(world), "inventory_digest": digest(data),
            "proof_digest": digest(proof), "html_sha256": sha256(playable).hexdigest(),
            "html_file": self._names(world["id"])[1],
            "qualification": "offline_reviewed_source_leased_item_playable",
        }
        return receipt, playable

    def editor(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        """Publish an offline unapproved authoring UI under the world lease."""
        from .inventory_editor import render_editor
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                data = self._read(fd, world_id, world)
                if digest(data) != expected_digest:
                    raise CanonError("inventory_stale_edit")
                content = render_editor(data, world)
                name = world_id + ".inventory.editor.html"
                self.worlds._write(fd, name, content)
                return {
                    "html_file": name, "html_sha256": sha256(content).hexdigest(),
                    "inventory_digest": digest(data),
                }
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def compile(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                data = self._read(fd, world_id, world)
                if digest(data) != expected_digest:
                    raise CanonError("inventory_stale_edit")
                receipt, playable = self._outputs(data, world)
                _, html_name, receipt_name = self._names(world_id)
                self.worlds._write(fd, html_name, playable)
                self.worlds._write(fd, receipt_name, canonical(receipt))
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
                data = self._read(fd, world_id, world)
                receipt, playable = self._outputs(data, world)
                _, html_name, receipt_name = self._names(world_id)
                if strict_json(self.worlds._read(fd, receipt_name)) != receipt:
                    raise CanonError("inventory_receipt_mismatch")
                if _artifact_read(fd, html_name) != playable:
                    raise CanonError("inventory_playable_mismatch")
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
