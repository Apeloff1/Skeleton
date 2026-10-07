"""Text-to-animation pipeline: rigs, keyframes, state machines, blend trees.

Materialises an animation set for a character description: a standard
humanoid rig, procedurally keyframed clips for the requested actions, a state
machine wiring the clips, and a 1-D blend tree for locomotion.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

from skeleton.kernel.errors import ValidationError
from skeleton.kernel.events import EventBus
from skeleton.kernel.ids import PipelineRunId

HUMANOID_BONES: tuple[str, ...] = (
    "root", "spine", "chest", "neck", "head",
    "shoulder_l", "upper_arm_l", "forearm_l", "hand_l",
    "shoulder_r", "upper_arm_r", "forearm_r", "hand_r",
    "upper_leg_l", "lower_leg_l", "foot_l",
    "upper_leg_r", "lower_leg_r", "foot_r",
)


@dataclass(frozen=True)
class Keyframe:
    t: float
    bone: str
    rotation: tuple[float, float, float]


@dataclass(frozen=True)
class Clip:
    name: str
    duration_s: float
    loop: bool
    frames: tuple[Keyframe, ...]


@dataclass(frozen=True)
class AnimState:
    name: str
    clip: str
    transitions: tuple[tuple[str, str], ...] = ()


@dataclass
class AnimationSpec:
    run_id: str
    rig: tuple[str, ...]
    clips: list[Clip]
    state_machine: list[AnimState]
    blend_tree: dict[str, Any]
    generated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "rig": list(self.rig),
            "clips": [{"name": c.name, "duration_s": c.duration_s, "loop": c.loop,
                        "frames": len(c.frames)} for c in self.clips],
            "state_machine": [{"name": s.name, "clip": s.clip,
                                "transitions": [[t, tgt] for t, tgt in s.transitions]}
                               for s in self.state_machine],
            "blend_tree": self.blend_tree,
            "generated_at": self.generated_at,
        }


def _procedural_clip(name: str, duration: float, *, loop: bool, amplitude: float) -> Clip:
    frames: list[Keyframe] = []
    steps = max(2, int(duration * 10))
    for i in range(steps + 1):
        t = duration * i / steps
        phase = 2.0 * math.pi * i / steps
        frames.append(Keyframe(t=round(t, 3), bone="root",
                               rotation=(0.0, amplitude * math.sin(phase), 0.0)))
    return Clip(name=name, duration_s=duration, loop=loop, frames=tuple(frames))


class AnimationPipeline:
    """Orchestrates animation-set generation."""

    def __init__(self, bus: EventBus | None = None) -> None:
        self._bus = bus or EventBus()

    def run(self, description: str, *,
            actions: tuple[str, ...] = ("idle", "walk", "run", "attack")) -> AnimationSpec:
        if not description or not description.strip():
            raise ValidationError("description must be non-empty")
        if not actions:
            raise ValidationError("at least one action is required")

        run_id = str(PipelineRunId.new())
        start = self._bus.emit("pipeline.animation.started", {"run_id": run_id})
        clips = [
            _procedural_clip(a, duration={"idle": 2.0, "walk": 1.0, "run": 0.6}.get(a, 0.8),
                             loop=a in {"idle", "walk", "run"},
                             amplitude={"idle": 3.0, "walk": 12.0, "run": 22.0}.get(a, 18.0))
            for a in actions
        ]
        states: list[AnimState] = []
        for a in actions:
            if a == "idle":
                states.append(AnimState("idle", "idle", (("move", "walk"), ("combat", "attack"))))
            elif a == "walk":
                states.append(AnimState("walk", "walk", (("stop", "idle"), ("sprint", "run"))))
            elif a == "run":
                states.append(AnimState("run", "run", (("slow", "walk"),)))
            else:
                states.append(AnimState(a, a, (("done", "idle"),)))
        blend_tree = {
            "type": "blend_1d",
            "parameter": "speed",
            "points": [
                {"threshold": 0.0, "clip": "idle"},
                {"threshold": 2.0, "clip": "walk"},
                {"threshold": 5.5, "clip": "run"},
            ],
        }
        spec = AnimationSpec(run_id=run_id, rig=HUMANOID_BONES, clips=clips,
                             state_machine=states, blend_tree=blend_tree)
        self._bus.emit("pipeline.animation.completed",
                       {"run_id": run_id, "clips": len(clips)},
                       correlation_id=start.correlation_id, causation_id=start.event_id)
        return spec
