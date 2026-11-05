"""Reviewed narrative promises: source-leased setup, payoff, proof and player replay.

Promises describe authored dramatic obligations, not generated facts. The model may
preview a proposal, but only an operator can publish and approve it. A required
promise must be discharged on every reachable ending path after it is triggered.
"""
from __future__ import annotations

from collections import deque
from hashlib import sha256
import os
from typing import Any

from .session import SessionStore, replay_choices
from .world_canon import (
    CanonError, WorldStore, _id, _keys, _list, _text, canonical, compile_html,
    digest, prove, strict_json,
)

SCHEMA = "jeeves.world.promises.v1"
HANDOFF_SCHEMA = "jeeves.world.promises_handoff.v1"
RECEIPT_SCHEMA = "jeeves.world.promises_receipt.v1"
MAX_PROMISES = 16
MAX_PROOF_STATES = 4096
MAX_PROOF_STEPS = 512


def validate_promises(data: Any, world: Any) -> dict[str, Any]:
    proof = prove(world)
    obj = _keys(data, {
        "schema", "world_id", "world_digest", "prompt", "promises",
        "approved", "review_note",
    })
    if obj["schema"] != SCHEMA:
        raise CanonError("promises_schema_mismatch")
    if obj["world_id"] != world["id"] or obj["world_digest"] != proof.source_digest:
        raise CanonError("promises_world_lease_mismatch")
    _text(obj["prompt"], "promises.prompt", 4096)
    if type(obj["approved"]) is not bool:
        raise CanonError("promises_approval_invalid")
    if type(obj["review_note"]) is not str or len(obj["review_note"]) > 512:
        raise CanonError("promises_review_note_invalid")
    if obj["approved"]:
        _text(obj["review_note"], "promises.review_note", 512)
    items = _list(obj["promises"], "promises", MAX_PROMISES)
    if not items:
        raise CanonError("promises_empty")
    choices = {c["id"] for c in world["choices"]}
    seen: set[str] = set()
    for item in items:
        _keys(item, {
            "id", "title", "setup", "payoff", "trigger_choice",
            "resolve_choice", "required",
        })
        pid = _id(item["id"], "promise.id")
        if pid in seen:
            raise CanonError("promise_duplicate", pid)
        seen.add(pid)
        _text(item["title"], "promise.title", 160)
        _text(item["setup"], "promise.setup", 1024)
        _text(item["payoff"], "promise.payoff", 1024)
        trigger = _id(item["trigger_choice"], "promise.trigger_choice")
        resolve = _id(item["resolve_choice"], "promise.resolve_choice")
        if trigger not in choices or resolve not in choices:
            raise CanonError("promise_unknown_choice", pid)
        if trigger == resolve:
            raise CanonError("promise_same_trigger_and_resolution", pid)
        if type(item["required"]) is not bool:
            raise CanonError("promise_required_invalid", pid)
    if [item["id"] for item in items] != sorted(seen):
        raise CanonError("promises_not_canonical")
    if len(canonical(obj)) > 524288:
        raise CanonError("promises_too_large")
    return obj


def propose_promises(
    world: Any, *, prompt: str, promise_id: str, title: str, setup: str,
    payoff: str, trigger_choice: str, resolve_choice: str, required: bool = True,
) -> dict[str, Any]:
    """Build an original, review-required proposal from explicit author inputs."""
    data = {
        "schema": SCHEMA, "world_id": world["id"], "world_digest": digest(world),
        "prompt": prompt, "promises": [{
            "id": promise_id, "title": title, "setup": setup, "payoff": payoff,
            "trigger_choice": trigger_choice, "resolve_choice": resolve_choice,
            "required": required,
        }], "approved": False, "review_note": "",
    }
    return validate_promises(data, world)


def edit_promises(data: Any, world: Any, operation: Any) -> dict[str, Any]:
    validate_promises(data, world)
    top = _keys(operation, {"action", "value"})
    ops = (_list(top["value"], "promise_batch", 32)
           if top["action"] == "batch" else [top])
    if not ops:
        raise CanonError("empty_promise_edit")
    candidate = strict_json(canonical(data))
    for op in ops:
        entry = _keys(op, {"action", "value"})
        action, value = entry["action"], entry["value"]
        if action in ("add", "replace"):
            _keys(value, {
                "id", "title", "setup", "payoff", "trigger_choice",
                "resolve_choice", "required",
            })
            found = [i for i, item in enumerate(candidate["promises"])
                     if item["id"] == value["id"]]
            if action == "add":
                if found:
                    raise CanonError("promise_duplicate")
                candidate["promises"].append(value)
            else:
                if len(found) != 1:
                    raise CanonError("promise_unknown_edit_target")
                candidate["promises"][found[0]] = value
        elif action == "remove":
            _keys(value, {"id"})
            before = len(candidate["promises"])
            candidate["promises"] = [
                item for item in candidate["promises"] if item["id"] != value["id"]
            ]
            if len(candidate["promises"]) != before - 1:
                raise CanonError("promise_unknown_edit_target")
        else:
            raise CanonError("promise_unsupported_edit")
    candidate["promises"].sort(key=lambda item: item["id"])
    candidate["approved"] = False
    candidate["review_note"] = ""
    return validate_promises(candidate, world)


def replay_promises(data: Any, world: Any, choices: Any) -> dict[str, Any]:
    """Derive open and resolved obligations only from canonical player choices."""
    validate_promises(data, world)
    trace = replay_choices(world, choices)
    active: set[str] = set()
    ever: set[str] = set()
    resolved: set[str] = set()
    events: list[dict[str, Any]] = []
    for step_index, step in enumerate(trace["steps"][1:], 1):
        choice_id = step["choice"]
        for item in data["promises"]:
            pid = item["id"]
            if item["trigger_choice"] == choice_id and pid not in active:
                active.add(pid)
                ever.add(pid)
                resolved.discard(pid)
                events.append({"step": step_index, "id": pid, "event": "triggered"})
            if item["resolve_choice"] == choice_id and pid in active:
                active.remove(pid)
                resolved.add(pid)
                events.append({"step": step_index, "id": pid, "event": "resolved"})
    required = {item["id"] for item in data["promises"] if item["required"]}
    return {
        "schema": "jeeves.world.promise_replay.v1",
        "world_digest": digest(world), "promises_digest": digest(data),
        "choices_digest": digest(list(choices)), "scene": trace["scene"],
        "ending": trace["ending"], "triggered": sorted(ever),
        "resolved": sorted(resolved), "open": sorted(active),
        "open_required": sorted(active & required), "events": events,
        "ending_continuity_satisfied": (
            trace["ending"] is not None and not (active & required)
        ),
    }


def prove_promises(data: Any, world: Any) -> dict[str, Any]:
    """Exhaustively inspect reachable world states; never trust one happy path."""
    validate_promises(data, world)
    edges: dict[str, list[dict[str, Any]]] = {}
    for choice in world["choices"]:
        edges.setdefault(choice["from"], []).append(choice)
    for values in edges.values():
        values.sort(key=lambda c: c["id"])
    endings = {e["scene"] for e in world["endings"]}
    required = {p["id"] for p in data["promises"] if p["required"]}
    by_trigger: dict[str, set[str]] = {}
    by_resolve: dict[str, set[str]] = {}
    for promise in data["promises"]:
        by_trigger.setdefault(promise["trigger_choice"], set()).add(promise["id"])
        by_resolve.setdefault(promise["resolve_choice"], set()).add(promise["id"])
    initial = (world["start"], frozenset(), frozenset(), frozenset())
    queue = deque([(initial, ())])
    visited = {initial}
    triggered: set[str] = set()
    discharged: set[str] = set()
    ending_witnesses: dict[str, list[str]] = {}
    while queue:
        (scene, flags, open_ids, resolved_ids), path = queue.popleft()
        if scene in endings:
            if required & open_ids:
                raise CanonError("unresolved_required_promise",
                                 ",".join(sorted(required & open_ids)))
            ending_witnesses.setdefault(scene, list(path))
            continue
        enabled = [c for c in edges.get(scene, ())
                   if set(c["requires"]) <= flags]
        if not enabled:
            raise CanonError("promise_reachable_dead_end", scene)
        if len(path) >= MAX_PROOF_STEPS:
            raise CanonError("promise_step_budget")
        for choice in enabled:
            pid = choice["id"]
            opening = by_trigger.get(pid, set())
            closing = by_resolve.get(pid, set())
            new_open = (open_ids | opening) - closing
            new_resolved = (resolved_ids - opening) | (open_ids & closing)
            triggered.update(opening)
            discharged.update(open_ids & closing)
            state = (
                choice["to"], flags | frozenset(choice["grants"]),
                frozenset(new_open), frozenset(new_resolved),
            )
            if state not in visited:
                if len(visited) >= MAX_PROOF_STATES:
                    raise CanonError("promise_state_budget")
                visited.add(state)
                queue.append((state, path + (pid,)))
    if not required <= triggered:
        raise CanonError("required_promise_never_triggered",
                         ",".join(sorted(required - triggered)))
    if not required <= discharged:
        raise CanonError("required_promise_never_resolved",
                         ",".join(sorted(required - discharged)))
    if set(ending_witnesses) != endings:
        raise CanonError("promise_unreachable_ending")
    return {
        "schema": "jeeves.world.promise_proof.v1",
        "world_digest": digest(world), "promises_digest": digest(data),
        "states_explored": len(visited),
        "triggered": sorted(triggered), "discharged": sorted(discharged),
        "ending_witnesses": {k: ending_witnesses[k] for k in sorted(ending_witnesses)},
        "required_all_endings_closed": True,
    }


def approve_promises(data: Any, world: Any, note: str) -> dict[str, Any]:
    validate_promises(data, world)
    _text(note, "promises.review_note", 512)
    candidate = strict_json(canonical(data))
    candidate["approved"] = True
    candidate["review_note"] = note
    prove_promises(candidate, world)
    return candidate


def compile_promises(data: Any, world: Any) -> dict[str, Any]:
    validate_promises(data, world)
    if not data["approved"]:
        raise CanonError("promise_review_required")
    proof = prove_promises(data, world)
    return {
        "schema": HANDOFF_SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "promises_digest": digest(data),
        "promises": data["promises"], "proof": proof,
        "review_note": data["review_note"],
        "runtime_contract": "all_required_promises_close_on_every_reachable_ending",
        "qualification": "source_proven_not_device_certified",
    }


class PromiseStore:
    """CAS-persisted authored promises with deterministic playable handoff."""
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _name(world_id: str) -> str:
        return _id(world_id, "world_id") + ".promises.json"

    @staticmethod
    def _artifacts(world_id: str) -> tuple[str, str, str]:
        _id(world_id, "world_id")
        return (
            world_id + ".promises.playable.html",
            world_id + ".promises.handoff.json",
            world_id + ".promises.receipt.json",
        )

    def _world(self, fd: int, world_id: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        world = strict_json(self.worlds._read(fd, world_id + ".json"))
        prove(world)
        if world["id"] != world_id:
            raise CanonError("identity_mismatch")
        return world

    def _data(self, fd: int, world_id: str, world: Any) -> dict[str, Any]:
        return validate_promises(
            strict_json(self.worlds._read(fd, self._name(world_id))), world)

    @staticmethod
    def _lock(fd: int, world_id: str) -> int:
        try:
            return os.open(world_id + ".lock",
                           os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                           0o600, dir_fd=fd)
        except FileExistsError:
            raise CanonError("lease_busy") from None

    def read(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            return self._data(fd, world_id, self._world(fd, world_id))
        finally:
            os.close(fd)

    def publish(self, world_id: str, data: Any, *,
                expected_digest: str | None = None, create: bool = False) -> str:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                world = self._world(fd, world_id)
                validate_promises(data, world)
                try:
                    old = digest(self._data(fd, world_id, world))
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    old = None
                if create:
                    if old is not None or expected_digest is not None:
                        raise CanonError("already_exists")
                elif old is None or expected_digest != old:
                    raise CanonError("stale_promises")
                self.worlds._write(fd, self._name(world_id), canonical(data))
                return digest(data)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def _outputs(self, world: Any, data: Any):
        handoff = compile_promises(data, world)
        html = compile_html(world).encode("utf-8")
        manifest = canonical(handoff)
        if max(len(html), len(manifest)) > 524288:
            raise CanonError("promise_artifact_too_large")
        names = self._artifacts(world["id"])
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world["id"],
            "world_digest": digest(world), "promises_digest": digest(data),
            "artifacts": {
                name: sha256(content).hexdigest()
                for name, content in zip(names[:2], (html, manifest))
            },
            "qualification": "source_proven_not_release_certified",
        }
        return receipt, (html, manifest)

    def compile(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                world = self._world(fd, world_id)
                data = self._data(fd, world_id, world)
                if digest(data) != expected_digest:
                    raise CanonError("stale_promises")
                receipt, contents = self._outputs(world, data)
                names = self._artifacts(world_id)
                for name, content in zip(names[:2], contents):
                    self.worlds._write(fd, name, content)
                self.worlds._write(fd, names[2], canonical(receipt))
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def verify(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                world = self._world(fd, world_id)
                data = self._data(fd, world_id, world)
                expected, contents = self._outputs(world, data)
                names = self._artifacts(world_id)
                if strict_json(self.worlds._read(fd, names[2])) != expected:
                    raise CanonError("promise_receipt_mismatch")
                for name, content in zip(names[:2], contents):
                    if self.worlds._read(fd, name) != content:
                        raise CanonError("promise_artifact_mismatch", name)
                return expected
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def player(self, world_id: str, slot: str) -> dict[str, Any]:
        world = self.worlds.read(world_id)
        data = self.read(world_id)
        if not data["approved"]:
            raise CanonError("promise_review_required")
        session = SessionStore(self.worlds.root).read(world_id, slot)
        return replay_promises(data, world, session["choices"])
