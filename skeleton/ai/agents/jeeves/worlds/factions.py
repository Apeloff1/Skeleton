"""Reviewed faction reputation derived exclusively from canonical world choices.

Faction reputation is not a free-form model claim. The author creates rules
bound to known choice IDs, explicitly reviews them, and a player earns effects
only by replaying legal source-leased decisions. All custody is descriptor-
anchored through WorldStore, with an exclusive per-world mutation lease.
"""
from __future__ import annotations

from hashlib import sha256
import os
from typing import Any

from .session import replay_choices, validate_session
from .world_canon import (
    CanonError, WorldStore, _id, _keys, _list, _text, canonical,
    compile_html, digest, prove, strict_json,
)

SCHEMA = "jeeves.world.factions.v1"
HANDOFF_SCHEMA = "jeeves.world.factions_handoff.v1"
RECEIPT_SCHEMA = "jeeves.world.factions_receipt.v1"
MAX_FACTIONS = 48
MAX_RULES = 256
MAX_REPUTATION = 100


def _validate_faction(item: Any) -> dict[str, Any]:
    obj = _keys(item, {"id", "name", "description"})
    _id(obj["id"], "faction.id")
    _text(obj["name"], "faction.name", 160)
    _text(obj["description"], "faction.description", 1024)
    return obj


def _validate_rule(item: Any, faction_ids: set[str],
                   choice_ids: set[str]) -> dict[str, Any]:
    obj = _keys(item, {"id", "choice_id", "faction_id", "delta", "reason"})
    _id(obj["id"], "rule.id")
    if _id(obj["choice_id"], "rule.choice_id") not in choice_ids:
        raise CanonError("unknown_faction_choice", obj["id"])
    if _id(obj["faction_id"], "rule.faction_id") not in faction_ids:
        raise CanonError("unknown_faction", obj["id"])
    if type(obj["delta"]) is not int or not -20 <= obj["delta"] <= 20 or obj["delta"] == 0:
        raise CanonError("invalid_reputation_delta", obj["id"])
    _text(obj["reason"], "rule.reason", 512)
    return obj


def validate_factions(data: Any, world: Any) -> dict[str, Any]:
    proof = prove(world)
    obj = _keys(data, {
        "schema", "world_id", "world_digest", "prompt", "factions", "rules",
        "approved", "review_note",
    })
    if obj["schema"] != SCHEMA:
        raise CanonError("faction_schema_mismatch")
    if obj["world_id"] != world["id"] or obj["world_digest"] != proof.source_digest:
        raise CanonError("faction_world_lease_mismatch")
    _text(obj["prompt"], "prompt", 4096)
    if type(obj["approved"]) is not bool:
        raise CanonError("invalid_faction_approval")
    if type(obj["review_note"]) is not str or len(obj["review_note"]) > 512:
        raise CanonError("invalid_faction_review_note")
    if obj["approved"]:
        _text(obj["review_note"], "review_note", 512)
    factions = _list(obj["factions"], "factions", MAX_FACTIONS)
    rules = _list(obj["rules"], "rules", MAX_RULES)
    if not factions or not rules:
        raise CanonError("empty_faction_rules")
    faction_ids = [_validate_faction(f)["id"] for f in factions]
    if faction_ids != sorted(set(faction_ids)):
        raise CanonError("noncanonical_factions")
    choice_ids = {c["id"] for c in world["choices"]}
    rule_ids = [_validate_rule(rule, set(faction_ids), choice_ids)["id"]
                for rule in rules]
    if rule_ids != sorted(set(rule_ids)):
        raise CanonError("noncanonical_faction_rules")
    if len(canonical(obj)) > 524288:
        raise CanonError("factions_too_large")
    return obj


def propose_factions(world: Any, *, prompt: str, faction_id: str, name: str,
                     description: str, choice_id: str, delta: int,
                     reason: str) -> dict[str, Any]:
    """Typed proposal from original author input; never silently approves."""
    proof = prove(world)
    data = {
        "schema": SCHEMA, "world_id": world["id"],
        "world_digest": proof.source_digest, "prompt": prompt,
        "factions": [{"id": faction_id, "name": name, "description": description}],
        "rules": [{"id": "first_effect", "choice_id": choice_id,
                   "faction_id": faction_id, "delta": delta, "reason": reason}],
        "approved": False, "review_note": "",
    }
    return validate_factions(data, world)


def edit_factions(data: Any, world: Any, operation: Any) -> dict[str, Any]:
    validate_factions(data, world)
    top = _keys(operation, {"action", "value"})
    actions = (_list(top["value"], "batch", 64)
               if top["action"] == "batch" else [top])
    if not actions:
        raise CanonError("empty_faction_edit")
    candidate = strict_json(canonical(data))
    for entry in actions:
        item = _keys(entry, {"action", "value"})
        action, value = item["action"], item["value"]
        if action in {"add_faction", "replace_faction", "add_rule", "replace_rule"}:
            field = "factions" if action.endswith("faction") else "rules"
            _keys(value, {"id", "name", "description"} if field == "factions"
                  else {"id", "choice_id", "faction_id", "delta", "reason"})
            if action.startswith("add_"):
                candidate[field].append(value)
            else:
                found = [i for i, old in enumerate(candidate[field])
                         if old["id"] == value["id"]]
                if len(found) != 1:
                    raise CanonError("unknown_faction_edit_target")
                candidate[field][found[0]] = value
        elif action in {"remove_faction", "remove_rule"}:
            _keys(value, {"id"})
            field = "factions" if action == "remove_faction" else "rules"
            before = len(candidate[field])
            candidate[field] = [x for x in candidate[field] if x["id"] != value["id"]]
            if len(candidate[field]) != before - 1:
                raise CanonError("unknown_faction_edit_target")
        else:
            raise CanonError("unsupported_faction_edit")
    candidate["factions"].sort(key=lambda x: x["id"])
    candidate["rules"].sort(key=lambda x: x["id"])
    candidate["approved"] = False
    candidate["review_note"] = ""
    return validate_factions(candidate, world)


def approve_factions(data: Any, world: Any, note: str) -> dict[str, Any]:
    validate_factions(data, world)
    _text(note, "review_note", 512)
    candidate = strict_json(canonical(data))
    candidate["approved"] = True
    candidate["review_note"] = note
    return validate_factions(candidate, world)


def replay_reputation(data: Any, world: Any, choices: Any) -> dict[str, Any]:
    validate_factions(data, world)
    replay = replay_choices(world, choices)
    reputation = {f["id"]: 0 for f in data["factions"]}
    events: list[dict[str, Any]] = []
    by_choice: dict[str, list[dict[str, Any]]] = {}
    for rule in data["rules"]:
        by_choice.setdefault(rule["choice_id"], []).append(rule)
    for index, step in enumerate(replay["steps"][1:], 1):
        for rule in by_choice.get(step["choice"], []):
            faction_id = rule["faction_id"]
            before = reputation[faction_id]
            after = max(-MAX_REPUTATION, min(MAX_REPUTATION, before + rule["delta"]))
            reputation[faction_id] = after
            events.append({
                "step": index, "choice_id": step["choice"], "rule_id": rule["id"],
                "faction_id": faction_id, "before": before, "after": after,
                "reason": rule["reason"],
            })
    return {
        "world_digest": digest(world), "factions_digest": digest(data),
        "scene": replay["scene"], "ending": replay["ending"],
        "reputation": reputation, "events": events,
        "choices_digest": digest(list(choices)),
    }


def compile_factions(data: Any, world: Any) -> dict[str, Any]:
    validate_factions(data, world)
    if not data["approved"]:
        raise CanonError("faction_review_required")
    proof = prove(world)
    endings = {}
    for scene, witness in sorted(proof.ending_witnesses.items()):
        result = replay_reputation(data, world, list(witness))
        endings[scene] = {
            "choice_witness": list(witness),
            "reputation": result["reputation"],
            "events": result["events"],
        }
    return {
        "schema": HANDOFF_SCHEMA, "world_id": world["id"],
        "world_digest": proof.source_digest, "factions_digest": digest(data),
        "factions": data["factions"], "rules": data["rules"],
        "ending_outcomes": endings,
        "review_note": data["review_note"],
        "qualification": "author_reviewed_source_replay_not_device_certified",
    }


class FactionStore:
    """CAS-persisted faction rules and replay-verified playable handoff."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _name(world_id: str) -> str:
        return _id(world_id, "world_id") + ".factions.json"

    @staticmethod
    def _artifacts(world_id: str) -> tuple[str, str, str]:
        _id(world_id, "world_id")
        return (world_id + ".factions.playable.html",
                world_id + ".factions.handoff.json",
                world_id + ".factions.receipt.json")

    def _world(self, fd: int, world_id: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        world = strict_json(self.worlds._read(fd, world_id + ".json"))
        prove(world)
        if world["id"] != world_id:
            raise CanonError("identity_mismatch")
        return world

    def _data(self, fd: int, world_id: str, world: Any) -> dict[str, Any]:
        return validate_factions(
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
            world = self._world(fd, world_id)
            return self._data(fd, world_id, world)
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
                validate_factions(data, world)
                candidate = strict_json(canonical(data))
                candidate["approved"] = False
                candidate["review_note"] = ""
                validate_factions(candidate, world)
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
                    raise CanonError("stale_factions")
                self.worlds._write(fd, self._name(world_id), canonical(candidate))
                return digest(candidate)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def approve(self, world_id: str, *, expected_digest: str, note: str) -> str:
        """The sole durable approval transition; checked under the world lease."""
        _id(world_id, "world_id")
        _text(note, "review_note", 512)
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                world = self._world(fd, world_id)
                current = self._data(fd, world_id, world)
                if digest(current) != expected_digest:
                    raise CanonError("stale_factions")
                approved = approve_factions(current, world, note)
                self.worlds._write(fd, self._name(world_id), canonical(approved))
                return digest(approved)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def _outputs(self, world: Any, data: Any):
        handoff = compile_factions(data, world)
        names = self._artifacts(world["id"])
        from .overlay import compile_overlay_html
        contents = [compile_overlay_html(
            world, factions=data).encode("utf-8"),
            canonical(handoff)]
        if any(len(content) > 524288 for content in contents):
            raise CanonError("factions_output_too_large")
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world["id"],
            "world_digest": digest(world), "factions_digest": digest(data),
            "artifacts": {
                name: sha256(content).hexdigest()
                for name, content in zip(names[:2], contents)
            },
            "qualification": "source_replay_not_release_certified",
        }
        return receipt, contents

    def compile(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                world = self._world(fd, world_id)
                data = self._data(fd, world_id, world)
                if digest(data) != expected_digest:
                    raise CanonError("stale_factions")
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
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                world = self._world(fd, world_id)
                data = self._data(fd, world_id, world)
                expected, contents = self._outputs(world, data)
                names = self._artifacts(world_id)
                actual = strict_json(self.worlds._read(fd, names[2]))
                if actual != expected:
                    raise CanonError("faction_receipt_mismatch")
                for name, content in zip(names[:2], contents):
                    if self.worlds._read(fd, name) != content:
                        raise CanonError("faction_artifact_mismatch", name)
                return expected
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def player(self, world_id: str, slot: str) -> dict[str, Any]:
        from .session import SessionStore
        world = self.worlds.read(world_id)
        data = self.read(world_id)
        if not data["approved"]:
            raise CanonError("faction_review_required")
        session = SessionStore(self.worlds.root).read(world_id, slot)
        validate_session(session, world)
        return replay_reputation(data, world, session["choices"])
