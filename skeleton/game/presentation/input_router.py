"""Deterministic semantic input routing on the canonical presentation owner.

This maps already-captured keyboard/controller/touch events to game commands.
It does not claim native device drivers, haptics, or OS input capture.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from skeleton.game.presentation.flgb_presentation_runtime import (
    InputBinding, InputMap, PresentationContractError, digest_json, require_id,
)

MAX_BINDINGS = 128
MAX_EVENTS = 4096
ACTIONS = {
    "move-north": ("move", "north"),
    "move-south": ("move", "south"),
    "move-west": ("move", "west"),
    "move-east": ("move", "east"),
    "interact": ("interact", ""),
    "inventory": ("inventory", ""),
    "confirm": ("confirm", ""),
    "cancel": ("cancel", ""),
}
DEVICES = ("keyboard", "controller", "touch")


def _fields(value: Any, required: set[str]) -> dict:
    if not isinstance(value, dict) or set(value) != required:
        raise PresentationContractError("invalid input record fields")
    return value


def _revision(value: Any) -> int:
    if type(value) is not int or not 0 <= value <= 1_000_000:
        raise PresentationContractError("invalid input revision")
    return value


@dataclass(frozen=True)
class InputProfile:
    """Source-bound, revisioned input profile; rebind is an immutable operation."""

    profile_id: str
    revision: int
    bindings: tuple[InputBinding, ...]

    @classmethod
    def load(cls, source: Any) -> "InputProfile":
        _fields(source, {"version", "profile_id", "revision", "bindings"})
        if type(source["version"]) is not int or source["version"] != 1:
            raise PresentationContractError("unsupported input profile version")
        identifier = require_id(source["profile_id"], "profile_id")
        revision = _revision(source["revision"])
        records = source["bindings"]
        if not isinstance(records, list) or not 1 <= len(records) <= MAX_BINDINGS:
            raise PresentationContractError("invalid binding count")
        bindings = []
        for item in records:
            _fields(item, {"binding_id", "action_id", "device_class", "control_path", "modifiers"})
            if item["action_id"] not in ACTIONS or item["device_class"] not in DEVICES:
                raise PresentationContractError("unsupported action or device")
            if not isinstance(item["modifiers"], list) or len(item["modifiers"]) > 8:
                raise PresentationContractError("invalid modifiers")
            control = require_id(item["control_path"], "control_path")
            if len(control) > 64 or any(ord(c) < 33 for c in control):
                raise PresentationContractError("unsafe control path")
            bindings.append(InputBinding(
                item["binding_id"], item["action_id"], item["device_class"],
                control, tuple(item["modifiers"]),
            ))
        InputMap(bindings)
        return cls(identifier, revision, tuple(sorted(bindings, key=lambda b: b.binding_id)))

    def manifest(self) -> dict:
        return {
            "version": 1, "profile_id": self.profile_id, "revision": self.revision,
            "bindings": [
                {
                    "binding_id": b.binding_id, "action_id": b.action_id,
                    "device_class": b.device_class, "control_path": b.control_path,
                    "modifiers": list(b.modifiers),
                }
                for b in self.bindings
            ],
        }

    @property
    def digest(self) -> str:
        return digest_json(self.manifest())

    def rebind(self, binding_id: str, control_path: str, expected_revision: int) -> "InputProfile":
        require_id(binding_id, "binding_id")
        if _revision(expected_revision) != self.revision:
            raise PresentationContractError("stale profile revision")
        if self.revision >= 1_000_000:
            raise PresentationContractError("profile revision exhausted")
        if not any(binding.binding_id == binding_id for binding in self.bindings):
            raise PresentationContractError("unknown binding")
        manifest = self.manifest()
        manifest["revision"] += 1
        for binding in manifest["bindings"]:
            if binding["binding_id"] == binding_id:
                binding["control_path"] = control_path
        return InputProfile.load(manifest)


@dataclass(frozen=True)
class InputEvent:
    event_id: str
    sequence: int
    device_class: str
    control_path: str
    modifiers: tuple[str, ...]
    pressed: bool

    @classmethod
    def load(cls, raw: Any) -> "InputEvent":
        _fields(raw, {"event_id", "sequence", "device_class", "control_path", "modifiers", "pressed"})
        identifier = require_id(raw["event_id"], "event_id")
        if type(raw["sequence"]) is not int or not 0 <= raw["sequence"] < MAX_EVENTS:
            raise PresentationContractError("invalid event sequence")
        if raw["device_class"] not in DEVICES:
            raise PresentationContractError("unsupported input device")
        control = require_id(raw["control_path"], "control_path")
        if len(control) > 64 or any(ord(c) < 33 for c in control):
            raise PresentationContractError("unsafe input control")
        if not isinstance(raw["modifiers"], list) or len(raw["modifiers"]) > 8:
            raise PresentationContractError("invalid input modifiers")
        modifiers = tuple(sorted(require_id(value, "modifier") for value in raw["modifiers"]))
        if len(set(modifiers)) != len(modifiers):
            raise PresentationContractError("duplicate input modifier")
        if type(raw["pressed"]) is not bool:
            raise PresentationContractError("pressed must be boolean")
        return cls(identifier, raw["sequence"], raw["device_class"], control, modifiers, raw["pressed"])

    def manifest(self) -> dict:
        return {
            "event_id": self.event_id, "sequence": self.sequence,
            "device_class": self.device_class, "control_path": self.control_path,
            "modifiers": list(self.modifiers), "pressed": self.pressed,
        }


@dataclass(frozen=True)
class InputSession:
    """Replayable session with immutable canonical event storage."""

    profile: InputProfile
    _events: tuple[str, ...] = ()

    @property
    def events(self) -> tuple[dict, ...]:
        # Return detached copies; callers cannot mutate the authoritative ledger.
        return tuple(json.loads(record) for record in self._events)

    def step(self, event: InputEvent) -> "InputSession":
        event = InputEvent.load(event.manifest())
        if len(self._events) >= MAX_EVENTS or event.sequence != len(self._events):
            raise PresentationContractError("input sequence or budget violation")
        if any(json.loads(record)["event"]["event_id"] == event.event_id for record in self._events):
            raise PresentationContractError("duplicate input event identity")
        chord = (event.device_class, event.control_path, event.modifiers)
        binding = next(
            (b for b in self.profile.bindings
             if (b.device_class, b.control_path, b.modifiers) == chord), None
        )
        if binding is None:
            raise PresentationContractError("unbound input chord")
        kind, target = ACTIONS[binding.action_id]
        receipt = {
            "event": event.manifest(), "binding_id": binding.binding_id,
            "action_id": binding.action_id,
            "command": {"kind": kind, "target": target} if event.pressed else None,
            "previous_digest": json.loads(self._events[-1])["digest"]
                               if self._events else self.profile.digest,
        }
        receipt["digest"] = digest_json({"profile": self.profile.digest, "receipt": receipt})
        encoded = json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return InputSession(self.profile, (*self._events, encoded))

    def snapshot(self) -> dict:
        return {
            "schema_version": 1, "profile_digest": self.profile.digest,
            "events": list(self.events),
            "session_digest": digest_json(self.events),
        }

    @classmethod
    def restore(cls, profile: InputProfile, raw: Any) -> "InputSession":
        _fields(raw, {"schema_version", "profile_digest", "events", "session_digest"})
        if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
            raise PresentationContractError("unsupported input session version")
        if raw["profile_digest"] != profile.digest:
            raise PresentationContractError("input profile changed")
        events = raw["events"]
        if not isinstance(events, list) or len(events) > MAX_EVENTS:
            raise PresentationContractError("invalid input event ledger")
        session = cls(profile)
        for receipt in events:
            _fields(receipt, {"event", "binding_id", "action_id", "command", "previous_digest", "digest"})
            session = session.step(InputEvent.load(receipt["event"]))
            if json.dumps(session.events[-1], sort_keys=True, separators=(",", ":")) != json.dumps(
                receipt, sort_keys=True, separators=(",", ":")
            ):
                raise PresentationContractError("input replay receipt mismatch")
        if raw["session_digest"] != session.snapshot()["session_digest"]:
            raise PresentationContractError("input session digest mismatch")
        return session
