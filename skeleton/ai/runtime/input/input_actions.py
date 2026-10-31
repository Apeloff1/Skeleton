"""B024: device-agnostic input actions with remappable semantic bindings.

Keyboard, mouse, touch and gamepad controls all resolve to the same semantic
:class:`Action` objects (``"jump"``, ``"move"`` ...).  Gameplay reads actions,
never devices.

* :class:`Control` - a validated ``device`` + ``path`` (``keyboard`` /
  ``key.space``, ``gamepad`` / ``stick.left.x``, ``touch`` / ``tap`` ...).
* :class:`Binding` - control -> action, with optional modifier chord, scale
  (for composite axes such as WASD) and dead-zone.
* :class:`ActionMap` - default bindings plus user overrides; ``rebind`` /
  ``unbind`` / ``reset`` with conflict detection inside a context, and
  JSON-safe export/import of overrides only.
* :class:`InputState` - feed raw ``(control, value)`` samples, then read
  per-frame action values plus pressed/released edges.

Pure data and deterministic: no OS/device IO happens here.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

DEVICES = ("keyboard", "mouse", "touch", "gamepad")
ACTION_KINDS = ("button", "axis1d", "axis2d")
_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_PATH_RE = {
    "keyboard": re.compile(r"^key\.[a-z0-9_]+$"),
    "mouse": re.compile(r"^(button\.(left|right|middle|back|forward)|delta\.(x|y)|wheel\.(x|y))$"),
    "touch": re.compile(r"^(tap|double_tap|long_press|swipe\.(x|y)|pinch|drag\.(x|y))$"),
    "gamepad": re.compile(r"^(button\.(south|east|west|north|start|select|l1|r1|l3|r3|dpad_(up|down|left|right))|trigger\.(left|right)|stick\.(left|right)\.(x|y))$"),
}
MODIFIERS = ("alt", "ctrl", "meta", "shift")
MAX_BINDINGS = 4096
MAX_OVERRIDES = 1024
PRESS_THRESHOLD = 0.5


class InputContractError(ValueError):
    """Invalid input action/binding definition or remap."""


def _id(value: Any, what: str) -> str:
    if not isinstance(value, str) or not _ID_RE.match(value) or len(value) > 64:
        raise InputContractError(f"invalid {what}: {value!r}")
    return value


@dataclass(frozen=True, order=True)
class Control:
    device: str
    path: str

    def __post_init__(self) -> None:
        if self.device not in DEVICES:
            raise InputContractError(f"unknown device: {self.device!r}")
        if not isinstance(self.path, str) or not _PATH_RE[self.device].match(self.path):
            raise InputContractError(f"invalid {self.device} control: {self.path!r}")

    @classmethod
    def parse(cls, text: str) -> "Control":
        if not isinstance(text, str) or ":" not in text:
            raise InputContractError(f"control must be 'device:path': {text!r}")
        device, path = text.split(":", 1)
        return cls(device, path)

    def __str__(self) -> str:
        return f"{self.device}:{self.path}"


@dataclass(frozen=True)
class Action:
    action_id: str
    kind: str = "button"
    context: str = "gameplay"

    def __post_init__(self) -> None:
        _id(self.action_id, "action_id")
        _id(self.context, "context")
        if self.kind not in ACTION_KINDS:
            raise InputContractError(f"invalid action kind: {self.kind!r}")


@dataclass(frozen=True)
class Binding:
    action_id: str
    control: Control
    modifiers: tuple[str, ...] = ()
    scale: float = 1.0
    axis: str = "x"  # which component of an axis2d this feeds
    deadzone: float = 0.0

    def __post_init__(self) -> None:
        _id(self.action_id, "action_id")
        if not isinstance(self.control, Control):
            raise InputContractError("binding control must be a Control")
        mods = tuple(sorted(set(self.modifiers)))
        if len(mods) != len(self.modifiers) or any(m not in MODIFIERS for m in mods):
            raise InputContractError(f"invalid modifiers: {self.modifiers!r}")
        if mods and self.control.device != "keyboard":
            raise InputContractError("modifiers only apply to keyboard controls")
        object.__setattr__(self, "modifiers", mods)
        if not isinstance(self.scale, (int, float)) or isinstance(self.scale, bool) or not -16.0 <= self.scale <= 16.0 or self.scale == 0:
            raise InputContractError("scale must be a non-zero number in [-16, 16]")
        if self.axis not in ("x", "y"):
            raise InputContractError("axis must be 'x' or 'y'")
        if not isinstance(self.deadzone, (int, float)) or not 0.0 <= self.deadzone < 1.0:
            raise InputContractError("deadzone must be in [0, 1)")

    @property
    def chord(self) -> tuple[str, tuple[str, ...]]:
        return (str(self.control), self.modifiers)


class ActionMap:
    """Actions + default bindings + user overrides (remapping)."""

    def __init__(self, actions: Iterable[Action], defaults: Iterable[Binding]) -> None:
        self.actions: dict[str, Action] = {}
        for a in actions:
            if a.action_id in self.actions:
                raise InputContractError(f"duplicate action: {a.action_id}")
            self.actions[a.action_id] = a
        self._defaults = tuple(defaults)
        if len(self._defaults) > MAX_BINDINGS:
            raise InputContractError("binding budget exceeded")
        self._overrides: dict[str, tuple[Binding, ...]] = {}
        self._validate(self._defaults)

    def _validate(self, bindings: Iterable[Binding]) -> None:
        seen: dict[tuple[str, tuple[str, tuple[str, ...]]], str] = {}
        for b in bindings:
            if b.action_id not in self.actions:
                raise InputContractError(f"binding for unknown action: {b.action_id}")
            key = (self.actions[b.action_id].context, b.chord)
            if key in seen and seen[key] != b.action_id:
                raise InputContractError(f"conflict: {b.control} already bound to {seen[key]!r} in context {key[0]!r}")
            seen[key] = b.action_id

    def bindings(self, action_id: str | None = None) -> tuple[Binding, ...]:
        out: list[Binding] = []
        for aid in sorted(self.actions):
            if action_id is not None and aid != action_id:
                continue
            if aid in self._overrides:
                out.extend(self._overrides[aid])
            else:
                out.extend(b for b in self._defaults if b.action_id == aid)
        return tuple(out)

    def devices_for(self, action_id: str) -> tuple[str, ...]:
        return tuple(sorted({b.control.device for b in self.bindings(action_id)}))

    def _set(self, action_id: str, bindings: tuple[Binding, ...]) -> None:
        if action_id not in self.actions:
            raise InputContractError(f"unknown action: {action_id}")
        trial = dict(self._overrides)
        trial[action_id] = bindings
        if len(trial) > MAX_OVERRIDES:
            raise InputContractError("override budget exceeded")
        old, self._overrides = self._overrides, trial
        try:
            self._validate(self.bindings())
        except InputContractError:
            self._overrides = old
            raise

    def rebind(self, action_id: str, old: Control, new: Control, *, modifiers: Iterable[str] = ()) -> None:
        """Replace ``old`` with ``new`` for one action; atomic on conflict."""
        current = self.bindings(action_id)
        hits = [b for b in current if b.control == old]
        if not hits:
            raise InputContractError(f"{old} is not bound to {action_id}")
        rest = tuple(b for b in current if b.control != old)
        moved = tuple(replace(b, control=new, modifiers=tuple(modifiers)) for b in hits)
        self._set(action_id, rest + moved)

    def bind(self, binding: Binding) -> None:
        self._set(binding.action_id, self.bindings(binding.action_id) + (binding,))

    def unbind(self, action_id: str, control: Control) -> None:
        self._set(action_id, tuple(b for b in self.bindings(action_id) if b.control != control))

    def reset(self, action_id: str | None = None) -> None:
        if action_id is None:
            self._overrides.clear()
        else:
            self._overrides.pop(action_id, None)

    def export_overrides(self) -> dict[str, list[dict[str, Any]]]:
        return {
            aid: [{"control": str(b.control), "modifiers": list(b.modifiers), "scale": b.scale, "axis": b.axis, "deadzone": b.deadzone} for b in bs]
            for aid, bs in sorted(self._overrides.items())
        }

    def import_overrides(self, data: Mapping[str, Any]) -> None:
        """Load exported overrides; all-or-nothing."""
        if not isinstance(data, Mapping) or len(data) > MAX_OVERRIDES:
            raise InputContractError("overrides must be a mapping within budget")
        staged: dict[str, tuple[Binding, ...]] = {}
        for aid, rows in data.items():
            if aid not in self.actions or not isinstance(rows, list):
                raise InputContractError(f"bad override entry: {aid!r}")
            staged[aid] = tuple(
                Binding(aid, Control.parse(r["control"]), tuple(r.get("modifiers", ())), float(r.get("scale", 1.0)), r.get("axis", "x"), float(r.get("deadzone", 0.0)))
                for r in rows
                if isinstance(r, Mapping)
            )
        old, self._overrides = self._overrides, staged
        try:
            self._validate(self.bindings())
        except InputContractError:
            self._overrides = old
            raise


@dataclass
class InputState:
    """Per-frame resolution of raw control samples into action values."""

    action_map: ActionMap
    active_contexts: frozenset[str] = frozenset({"gameplay"})
    _raw: dict[str, float] = field(default_factory=dict)
    _held_mods: set[str] = field(default_factory=set)
    _prev: dict[str, Any] = field(default_factory=dict)
    _cur: dict[str, Any] = field(default_factory=dict)

    def feed(self, control: Control | str, value: float) -> None:
        c = Control.parse(control) if isinstance(control, str) else control
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value != value:
            raise InputContractError("sample value must be a finite number")
        v = max(-1.0, min(1.0, float(value)))
        if c.device == "keyboard" and c.path[4:] in MODIFIERS:
            (self._held_mods.add if v else self._held_mods.discard)(c.path[4:])
        self._raw[str(c)] = v

    def update(self) -> None:
        self._prev = self._cur
        cur: dict[str, Any] = {}
        for aid, action in self.action_map.actions.items():
            if action.context not in self.active_contexts:
                continue
            x = y = 0.0
            for b in self.action_map.bindings(aid):
                if b.modifiers and not set(b.modifiers) <= self._held_mods:
                    continue
                raw = self._raw.get(str(b.control), 0.0)
                if abs(raw) <= b.deadzone:
                    continue
                if b.axis == "y":
                    y += raw * b.scale
                else:
                    x += raw * b.scale
            clamp = lambda n: max(-1.0, min(1.0, n))  # noqa: E731
            if action.kind == "button":
                cur[aid] = max(abs(x), abs(y)) >= PRESS_THRESHOLD
            elif action.kind == "axis1d":
                cur[aid] = clamp(x + y)
            else:
                cur[aid] = (clamp(x), clamp(y))
        self._cur = cur
        # transient controls (taps, wheel, deltas) reset each frame
        for k in [k for k in self._raw if k.startswith(("touch:tap", "touch:double_tap", "mouse:wheel", "mouse:delta"))]:
            del self._raw[k]

    def value(self, action_id: str) -> Any:
        return self._cur.get(action_id, False if self._kind(action_id) == "button" else 0.0 if self._kind(action_id) == "axis1d" else (0.0, 0.0))

    def pressed(self, action_id: str) -> bool:
        return self._cur.get(action_id) is True and self._prev.get(action_id) is not True

    def released(self, action_id: str) -> bool:
        return self._prev.get(action_id) is True and self._cur.get(action_id) is not True

    def _kind(self, action_id: str) -> str:
        if action_id not in self.action_map.actions:
            raise InputContractError(f"unknown action: {action_id}")
        return self.action_map.actions[action_id].kind


__all__ = ["Action", "ActionMap", "Binding", "Control", "InputContractError", "InputState", "DEVICES"]
