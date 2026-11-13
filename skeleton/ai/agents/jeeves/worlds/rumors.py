"""Original rumor transmission through real choices, NPC encounters and branch proof."""
from __future__ import annotations

import base64
from collections import deque
from hashlib import sha256
import html
import os
from typing import Any

from .bundle import _artifact_read
from .cast import CastStore, validate_cast
from .session import SessionStore, replay_choices, validate_session
from .world_canon import CanonError, _id, _keys, _list, _text, canonical, digest, prove, strict_json

SCHEMA = "jeeves.world.rumors.v1"
PROOF_SCHEMA = "jeeves.world.rumors_proof.v1"
RECEIPT_SCHEMA = "jeeves.world.rumors_receipt.v1"


def validate_rumors(source: Any, world: Any, cast: Any) -> dict[str, Any]:
    prove(world)
    validate_cast(cast, world)
    obj = _keys(source, {"schema", "world_id", "world_digest", "cast_digest",
                         "prompt", "approved", "review_note", "rumors", "routes"})
    if obj["schema"] != SCHEMA:
        raise CanonError("rumors_schema_mismatch")
    if (obj["world_id"] != world["id"] or obj["world_digest"] != digest(world)
            or obj["cast_digest"] != digest(cast)):
        raise CanonError("rumors_source_lease_mismatch")
    _text(obj["prompt"], "prompt", 4096)
    _text(obj["review_note"], "review_note", 512)
    if type(obj["approved"]) is not bool:
        raise CanonError("rumors_invalid_approval")
    actors = {actor["id"]: actor for actor in cast["characters"]}
    choices = {choice["id"]: choice for choice in world["choices"]}
    rumors = _list(obj["rumors"], "rumors", 12)
    routes = _list(obj["routes"], "routes", 48)
    if not rumors:
        raise CanonError("rumors_empty")
    ids = []
    for rumor in rumors:
        _keys(rumor, {"id", "claim", "stance", "origin", "seed_choice", "text"})
        ids.append(_id(rumor["id"], "rumor.id"))
        _id(rumor["claim"], "rumor.claim")
        if type(rumor["stance"]) is not str or rumor["stance"] not in ("supports", "denies"):
            raise CanonError("rumors_invalid_stance")
        origin = _id(rumor["origin"], "rumor.origin")
        choice_id = _id(rumor["seed_choice"], "rumor.seed_choice")
        if origin not in actors:
            raise CanonError("rumors_unknown_origin")
        if choice_id not in choices or choices[choice_id]["to"] not in actors[origin]["scenes"]:
            raise CanonError("rumors_origin_not_present")
        _text(rumor["text"], "rumor.text", 2048)
    if ids != sorted(set(ids)):
        raise CanonError("rumors_noncanonical_rumors")
    route_ids = []
    for route in routes:
        _keys(route, {"id", "rumor", "from_actor", "to_actor", "choice", "scene"})
        route_ids.append(_id(route["id"], "route.id"))
        if _id(route["rumor"], "route.rumor") not in ids:
            raise CanonError("rumors_unknown_route_rumor")
        sender = _id(route["from_actor"], "route.from_actor")
        recipient = _id(route["to_actor"], "route.to_actor")
        scene = _id(route["scene"], "route.scene")
        choice_id = _id(route["choice"], "route.choice")
        if sender == recipient or sender not in actors or recipient not in actors:
            raise CanonError("rumors_invalid_transfer")
        if (scene not in actors[sender]["scenes"]
                or scene not in actors[recipient]["scenes"]):
            raise CanonError("rumors_absent_participant")
        if choice_id not in choices or choices[choice_id]["to"] != scene:
            raise CanonError("rumors_transfer_not_arrival")
    if route_ids != sorted(set(route_ids)):
        raise CanonError("rumors_noncanonical_routes")
    if len(canonical(obj)) > 524288:
        raise CanonError("rumors_too_large")
    return obj


def _advance(source: Any, known: tuple[frozenset[str], ...],
             choice: str) -> tuple[tuple[frozenset[str], ...], list[str]]:
    updated = [set(actors) for actors in known]
    deliveries = []
    for index, rumor in enumerate(source["rumors"]):
        if rumor["seed_choice"] == choice:
            updated[index].add(rumor["origin"])
            deliveries.append("seed:" + rumor["id"])
    # Transfer is one causal hop per choice; a recipient cannot immediately
    # retransmit on that same transition unless already informed beforehand.
    for route in source["routes"]:
        index = next(i for i, r in enumerate(source["rumors"]) if r["id"] == route["rumor"])
        if route["choice"] == choice and route["from_actor"] in known[index]:
            updated[index].add(route["to_actor"])
            deliveries.append("route:" + route["id"])
    return tuple(frozenset(actors) for actors in updated), sorted(deliveries)


def _check_contradictions(source: Any, known: tuple[frozenset[str], ...]) -> None:
    beliefs: dict[tuple[str, str], str] = {}
    for rumor, informed in zip(source["rumors"], known):
        for actor in informed:
            key = (actor, rumor["claim"])
            if key in beliefs and beliefs[key] != rumor["stance"]:
                raise CanonError("rumors_coexisting_contradiction")
            beliefs[key] = rumor["stance"]


def prove_rumors(source: Any, world: Any, cast: Any) -> dict[str, Any]:
    obj = validate_rumors(source, world, cast)
    edges: dict[str, list[dict[str, Any]]] = {}
    for choice in world["choices"]:
        edges.setdefault(choice["from"], []).append(choice)
    for group in edges.values():
        group.sort(key=lambda item: item["id"])
    endings = {ending["scene"] for ending in world["endings"]}
    initial = (world["start"], frozenset(),
               tuple(frozenset() for _ in obj["rumors"]))
    queue = deque([(initial, ())])
    visited = {initial}
    witnesses: dict[str, list[str]] = {}
    endings_seen: dict[str, list[str]] = {}
    while queue:
        (scene, flags, known), trace = queue.popleft()
        if scene in endings:
            endings_seen.setdefault(scene, list(trace))
            continue
        enabled = [choice for choice in edges.get(scene, ())
                   if set(choice["requires"]) <= flags]
        if not enabled:
            raise CanonError("rumors_reachable_dead_end")
        if len(trace) >= 128:
            raise CanonError("rumors_step_budget")
        for choice in enabled:
            informed, deliveries = _advance(obj, known, choice["id"])
            _check_contradictions(obj, informed)
            path = trace + (choice["id"],)
            for delivery in deliveries:
                witnesses.setdefault(delivery, list(path))
            state = (choice["to"], flags | frozenset(choice["grants"]), informed)
            if state in visited:
                continue
            if len(visited) >= 4096:
                raise CanonError("rumors_state_budget")
            visited.add(state)
            queue.append((state, path))
    required = {"seed:" + rumor["id"] for rumor in obj["rumors"]}
    required |= {"route:" + route["id"] for route in obj["routes"]}
    if required - set(witnesses):
        raise CanonError("rumors_unreachable_delivery")
    if endings - set(endings_seen):
        raise CanonError("rumors_unreachable_ending")
    return {"schema": PROOF_SCHEMA, "world_digest": digest(world),
            "cast_digest": digest(cast), "rumors_digest": digest(obj),
            "states_explored": len(visited),
            "delivery_witnesses": {k: witnesses[k] for k in sorted(witnesses)},
            "ending_witnesses": {k: endings_seen[k] for k in sorted(endings_seen)}}


def propose_rumors(world: Any, cast: Any, *, prompt: str, rumor_id: str,
                   claim: str, stance: str, origin: str, seed_choice: str,
                   text: str) -> dict[str, Any]:
    obj = {"schema": SCHEMA, "world_id": world["id"],
           "world_digest": digest(world), "cast_digest": digest(cast),
           "prompt": prompt, "approved": False,
           "review_note": "Original rumor needs author review",
           "rumors": [{"id": rumor_id, "claim": claim, "stance": stance,
                       "origin": origin, "seed_choice": seed_choice, "text": text}],
           "routes": []}
    prove_rumors(obj, world, cast)
    return obj


def edit_rumors(source: Any, world: Any, cast: Any, operation: Any) -> dict[str, Any]:
    validate_rumors(source, world, cast)
    op = _keys(operation, {"action", "value"})
    candidate = strict_json(canonical(source))
    action, value = op["action"], op["value"]
    if action in ("add_rumor", "replace_rumor", "add_route", "replace_route"):
        collection = "rumors" if action.endswith("rumor") else "routes"
        required = ({"id", "claim", "stance", "origin", "seed_choice", "text"}
                    if collection == "rumors"
                    else {"id", "rumor", "from_actor", "to_actor", "choice", "scene"})
        _keys(value, required)
        if action.startswith("add_"):
            candidate[collection].append(value)
        else:
            matches = [i for i, item in enumerate(candidate[collection])
                       if item["id"] == value["id"]]
            if len(matches) != 1:
                raise CanonError("rumors_unknown_edit")
            candidate[collection][matches[0]] = value
        candidate[collection].sort(key=lambda item: item["id"])
    elif action in ("remove_rumor", "remove_route"):
        _keys(value, {"id"})
        collection = "rumors" if action == "remove_rumor" else "routes"
        old = len(candidate[collection])
        candidate[collection] = [item for item in candidate[collection]
                                 if item["id"] != value["id"]]
        if len(candidate[collection]) != old - 1:
            raise CanonError("rumors_unknown_edit")
    else:
        raise CanonError("rumors_unsupported_edit")
    candidate["approved"] = False
    candidate["review_note"] = "Edited rumor network requires renewed review"
    prove_rumors(candidate, world, cast)
    return candidate


def replay_rumors(source: Any, world: Any, cast: Any, choices: Any) -> dict[str, Any]:
    validate_rumors(source, world, cast)
    replay = replay_choices(world, choices)
    known = tuple(frozenset() for _ in source["rumors"])
    steps = []
    for step in replay["steps"]:
        deliveries = []
        if step["choice"] is not None:
            known, deliveries = _advance(source, known, step["choice"])
            _check_contradictions(source, known)
        heard = [{"rumor": rumor["id"], "actor": actor, "claim": rumor["claim"],
                  "stance": rumor["stance"], "text": rumor["text"]}
                 for rumor, actors in zip(source["rumors"], known)
                 for actor in sorted(actors)]
        steps.append({"scene": step["scene"], "choice": step["choice"],
                      "deliveries": deliveries, "heard": heard})
    return {"world_digest": digest(world), "cast_digest": digest(cast),
            "rumors_digest": digest(source), "scene": replay["scene"],
            "ending": replay["ending"], "steps": steps}


_PLAYER_JS = r"""
"use strict";
const data = JSON.parse(document.getElementById("rumor-data").textContent);
const world = data.world, network = data.rumors;
const scenes = new Map(world.scenes.map(s => [s.id, s]));
const endings = new Map(world.endings.map(e => [e.scene, e.label]));
const actors = new Map(data.cast.characters.map(a => [a.id, a.name]));
const root = document.getElementById("play");
let scene = world.start, flags = new Set(), trace = [];
let known = new Map(network.rumors.map(r => [r.id, new Set()]));
function node(tag, text) { const el = document.createElement(tag); el.textContent = text; return el; }
function render() {
  root.replaceChildren();
  const current = scenes.get(scene);
  root.append(node("h1", current.title), node("p", current.narrative));
  for (const rumor of network.rumors) for (const actor of known.get(rumor.id))
    if (data.cast.characters.find(a => a.id === actor).scenes.includes(scene))
      root.append(node("p", actors.get(actor) + " knows [" + rumor.stance + "]: " + rumor.text));
  root.append(node("p", "Choices: " + trace.join(", ")));
  if (endings.has(scene)) {
    root.append(node("h2", "Ending: " + endings.get(scene)));
    const restart = node("button", "Restart");
    restart.addEventListener("click", () => {
      scene = world.start; flags = new Set(); trace = [];
      known = new Map(network.rumors.map(r => [r.id, new Set()])); render();
    });
    root.append(restart); return;
  }
  for (const choice of world.choices.filter(c => c.from === scene)) {
    if (!choice.requires.every(flag => flags.has(flag))) continue;
    const button = node("button", choice.label);
    button.addEventListener("click", () => {
      const before = new Map(Array.from(known, ([id, actors]) => [id, new Set(actors)]));
      for (const rumor of network.rumors)
        if (rumor.seed_choice === choice.id) known.get(rumor.id).add(rumor.origin);
      for (const route of network.routes)
        if (route.choice === choice.id && before.get(route.rumor).has(route.from_actor))
          known.get(route.rumor).add(route.to_actor);
      for (const flag of choice.grants) flags.add(flag);
      trace.push(choice.id); scene = choice.to; render();
    });
    root.append(button);
  }
}
render();
""".strip()


def render_rumors_html(source: Any, world: Any, cast: Any) -> bytes:
    prove_rumors(source, world, cast)
    if not source["approved"] or not cast["approved"]:
        raise CanonError("rumors_review_required")
    payload = canonical({"world": world, "cast": cast, "rumors": source}).decode("utf-8").replace("<", "\\u003c")
    policy = base64.b64encode(sha256(_PLAYER_JS.encode()).digest()).decode("ascii")
    title = html.escape(world["id"], quote=True)
    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            "script-src 'sha256-" + policy + "'; connect-src 'none'; "
            'style-src \'none\'; img-src \'none\'; base-uri \'none\'; form-action \'none\'">'
            '<title>' + title + ' rumors</title></head><body>'
            '<main id="play" aria-live="polite"></main>'
            '<script id="rumor-data" type="application/json">' + payload + '</script>'
            '<script>' + _PLAYER_JS + '</script></body></html>\n').encode("utf-8")
    if len(page) > 1572864:
        raise CanonError("rumors_playable_too_large")
    return page


class RumorStore:
    """Private source leases, explicit review, atomic compile and byte verification."""
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.cast = CastStore(root)
        self.worlds = self.cast.worlds

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str]:
        _id(world_id, "world_id")
        return (world_id + ".rumors.json",
                world_id + ".rumors.playable.html",
                world_id + ".rumors.receipt.json")

    def _sources(self, fd: int, world_id: str) -> tuple[Any, Any]:
        world = self.cast._world(fd, world_id)
        return world, self.cast._cast(fd, world_id, world)

    def _read(self, fd: int, world_id: str, world: Any, cast: Any) -> Any:
        return validate_rumors(
            strict_json(self.worlds._read(fd, self._names(world_id)[0])), world, cast)

    def _locked(self, fd: int, world_id: str) -> None:
        handle = self.cast._lock(fd, world_id)
        os.close(handle)

    def propose(self, world_id: str, **kwargs: Any) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            return propose_rumors(*self._sources(fd, world_id), **kwargs)
        finally:
            os.close(fd)

    def inspect(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world, cast = self._sources(fd, world_id)
            source = self._read(fd, world_id, world, cast)
            return {"rumors": source, "proof": prove_rumors(source, world, cast)}
        finally:
            os.close(fd)

    def publish(self, world_id: str, source: Any, *,
                expected_digest: str | None = None, create: bool = False) -> str:
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                candidate = strict_json(canonical(source))
                if type(candidate) is not dict:
                    raise CanonError("expected_object")
                candidate["approved"] = False
                candidate["review_note"] = "Published rumor network needs author review"
                prove_rumors(candidate, world, cast)
                try:
                    old = self._read(fd, world_id, world, cast)
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    old = None
                if create:
                    if old is not None or expected_digest is not None:
                        raise CanonError("rumors_already_exists")
                elif old is None or digest(old) != expected_digest:
                    raise CanonError("rumors_stale_edit")
                self.worlds._write(fd, self._names(world_id)[0], canonical(candidate))
                return digest(candidate)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def approve(self, world_id: str, *, expected_digest: str, review_note: str) -> str:
        _text(review_note, "review_note", 512)
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                if not cast["approved"]:
                    raise CanonError("rumors_cast_review_required")
                source = self._read(fd, world_id, world, cast)
                if digest(source) != expected_digest:
                    raise CanonError("rumors_stale_edit")
                source["approved"] = True
                source["review_note"] = review_note
                prove_rumors(source, world, cast)
                self.worlds._write(fd, self._names(world_id)[0], canonical(source))
                return digest(source)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def player(self, world_id: str, slot: str) -> dict[str, Any]:
        _id(slot, "slot")
        fd = self.worlds._directory()
        try:
            world, cast = self._sources(fd, world_id)
            source = self._read(fd, world_id, world, cast)
            if not source["approved"] or not cast["approved"]:
                raise CanonError("rumors_review_required")
            session = validate_session(
                strict_json(self.worlds._read(fd, SessionStore._name(world_id, slot))), world)
            return {"slot": slot, "session_digest": digest(session),
                    "revision": session["revision"],
                    "player": replay_rumors(source, world, cast, session["choices"])}
        finally:
            os.close(fd)

    def _outputs(self, source: Any, world: Any, cast: Any) -> tuple[dict[str, Any], bytes]:
        proof = prove_rumors(source, world, cast)
        playable = render_rumors_html(source, world, cast)
        receipt = {"schema": RECEIPT_SCHEMA, "world_id": world["id"],
                   "world_digest": digest(world), "cast_digest": digest(cast),
                   "rumors_digest": digest(source), "proof_digest": digest(proof),
                   "html_file": self._names(world["id"])[1],
                   "html_sha256": sha256(playable).hexdigest(),
                   "qualification": "reviewed_original_rumors_not_release_certified"}
        return receipt, playable

    def compile(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                source = self._read(fd, world_id, world, cast)
                if digest(source) != expected_digest:
                    raise CanonError("rumors_stale_edit")
                receipt, playable = self._outputs(source, world, cast)
                names = self._names(world_id)
                self.worlds._write(fd, names[1], playable)
                self.worlds._write(fd, names[2], canonical(receipt))
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def verify(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                source = self._read(fd, world_id, world, cast)
                receipt, playable = self._outputs(source, world, cast)
                names = self._names(world_id)
                if strict_json(self.worlds._read(fd, names[2])) != receipt:
                    raise CanonError("rumors_receipt_mismatch")
                if _artifact_read(fd, names[1]) != playable:
                    raise CanonError("rumors_playable_mismatch")
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def editor(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        from .rumors_editor import render_editor
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                source = self._read(fd, world_id, world, cast)
                if digest(source) != expected_digest:
                    raise CanonError("rumors_stale_edit")
                page = render_editor(source, world, cast)
                name = world_id + ".rumors.editor.html"
                self.worlds._write(fd, name, page)
                return {"html_file": name, "html_sha256": sha256(page).hexdigest(),
                        "rumors_digest": digest(source)}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
