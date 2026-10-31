"""B049 world-state persistence/replay with compact event+checkpoint log.

Store-agnostic: callers persist ``WorldLog.to_dict`` via any save port
(e.g. the GF-B game save plane).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from ._digest import digest

Reducer = Callable[[dict[str, Any], Mapping[str, Any]], dict[str, Any]]


class WorldReplayError(ValueError):
    pass


@dataclass
class WorldLog:
    initial: dict[str, Any]
    checkpoint_every: int = 64
    events: list[dict[str, Any]] = field(default_factory=list)
    checkpoints: dict[int, dict[str, Any]] = field(default_factory=dict)  # index -> {state, digest}

    def append(self, event: Mapping[str, Any], reducer: Reducer, state: dict[str, Any]) -> dict[str, Any]:
        new = reducer(copy.deepcopy(state), event)
        self.events.append(dict(event))
        n = len(self.events)
        if n % self.checkpoint_every == 0:
            self.checkpoints[n] = {"state": copy.deepcopy(new), "digest": digest(new)}
        return new

    def replay(self, reducer: Reducer, upto: int | None = None) -> dict[str, Any]:
        upto = len(self.events) if upto is None else upto
        if not 0 <= upto <= len(self.events):
            raise WorldReplayError("upto out of range")
        base = max((i for i in self.checkpoints if i <= upto), default=0)
        state = copy.deepcopy(self.checkpoints[base]["state"]) if base else copy.deepcopy(self.initial)
        if base and digest(state) != self.checkpoints[base]["digest"]:
            raise WorldReplayError(f"checkpoint {base} corrupted")
        for ev in self.events[base:upto]:
            state = reducer(state, ev)
        return state

    def verify(self, reducer: Reducer) -> bool:
        state = copy.deepcopy(self.initial)
        for i, ev in enumerate(self.events, 1):
            state = reducer(state, ev)
            cp = self.checkpoints.get(i)
            if cp and cp["digest"] != digest(state):
                return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {"schema": "skeleton.worldsim.log/v1", "initial": self.initial,
                "checkpoint_every": self.checkpoint_every, "events": self.events,
                "checkpoints": {str(k): v for k, v in sorted(self.checkpoints.items())}}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "WorldLog":
        if d.get("schema") != "skeleton.worldsim.log/v1":
            raise WorldReplayError("schema mismatch")
        return cls(dict(d["initial"]), int(d["checkpoint_every"]), list(d["events"]),
                   {int(k): v for k, v in d["checkpoints"].items()})
