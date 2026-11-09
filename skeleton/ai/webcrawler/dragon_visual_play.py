"""Engine-neutral, bounded visual play through explicitly trusted adapters.

The controller never launches a game or obtains desktop control by itself.
An operator supplies a target-scoped adapter and revocable session grant.
Frames are genuine adapter outputs; traces do not claim enjoyment or victory.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from time import monotonic
from typing import Callable, Protocol

from ..game_builder.contracts import canonical_digest


def _id(value: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > 192:
        raise ValueError("bounded session/adapter identity required")


@dataclass(frozen=True, slots=True)
class PlayGrant:
    owner: str
    session_id: str
    adapter_id: str
    artifact_digest: str
    allowed_buttons: frozenset[str]
    expires_at: float
    max_steps: int = 600
    max_wall_seconds: float = 60.0

    def __post_init__(self) -> None:
        from math import isfinite
        for value in (self.owner, self.session_id, self.adapter_id):
            _id(value)
        if not isinstance(self.artifact_digest, str) or len(self.artifact_digest) != 64 or any(c not in "0123456789abcdef" for c in self.artifact_digest):
            raise ValueError("exact authorized game artifact required")
        if not isinstance(self.allowed_buttons, frozenset) or not 1 <= len(self.allowed_buttons) <= 32:
            raise ValueError("bounded button allowlist required")
        for button in self.allowed_buttons:
            _id(button)
        if type(self.max_steps) is not int or not 1 <= self.max_steps <= 10000:
            raise ValueError("bounded play steps required")
        for value in (self.expires_at, self.max_wall_seconds):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
                raise ValueError("finite session expiry and time budget required")
        if self.max_wall_seconds > 300:
            raise ValueError("play budget exceeds five minutes")


@dataclass(frozen=True, slots=True)
class VisualFrame:
    sequence: int
    width: int
    height: int
    rgb: bytes
    terminal: bool = False

    def __post_init__(self) -> None:
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("nonnegative frame sequence required")
        if type(self.width) is not int or type(self.height) is not int or not 1 <= self.width <= 1920 or not 1 <= self.height <= 1080:
            raise ValueError("bounded visual frame geometry required")
        if not isinstance(self.rgb, bytes) or len(self.rgb) != self.width*self.height*3:
            raise ValueError("exact RGB frame payload required")
        if type(self.terminal) is not bool:
            raise ValueError("explicit terminal frame state required")

    @property
    def digest(self) -> str:
        return canonical_digest({"sequence": self.sequence, "width": self.width,
            "height": self.height, "rgb_sha256": sha256(self.rgb).hexdigest(), "terminal": self.terminal})


@dataclass(frozen=True, slots=True)
class PlayAction:
    buttons: frozenset[str]
    frames: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.buttons, frozenset) or len(self.buttons) > 32:
            raise ValueError("bounded button set required")
        for value in self.buttons:
            _id(value)
        if type(self.frames) is not int or not 1 <= self.frames <= 4:
            raise ValueError("each action is bounded to four frames")


class GameVisualAdapter(Protocol):
    adapter_id: str
    artifact_digest: str

    def capture(self) -> VisualFrame: ...
    def advance(self, action: PlayAction) -> None: ...
    def release_inputs(self) -> None: ...


@dataclass(frozen=True, slots=True)
class PlayTrace:
    owner: str
    session_id: str
    adapter_id: str
    artifact_digest: str
    stop_reason: str
    steps: tuple[dict, ...]

    def to_payload(self) -> dict:
        body = {"schema": "skeleton.dragon.visual_play_trace.v1", "owner": self.owner,
            "session_id": self.session_id, "adapter_id": self.adapter_id,
            "artifact_digest": self.artifact_digest, "stop_reason": self.stop_reason,
            "steps": list(self.steps), "release_authority": False,
            "claim_boundary": "adapter-observed bounded visual control; no player certification or legal clearance"}
        return {**body, "trace_digest": canonical_digest(body)}


class DragonVisualPlayer:
    def __init__(self, adapter: GameVisualAdapter, grant: PlayGrant, *,
                 consent_current: Callable[[PlayGrant], bool], clock: Callable[[], float] = monotonic):
        if adapter.adapter_id != grant.adapter_id or adapter.artifact_digest != grant.artifact_digest:
            raise PermissionError("adapter does not match consented target artifact")
        self.adapter = adapter
        self.grant = grant
        self.consent_current = consent_current
        self.clock = clock
        self._used = False

    def _admitted(self, start: float) -> str | None:
        from math import isfinite
        now = self.clock()
        if isinstance(now, bool) or not isinstance(now, (int, float)) or not isfinite(now) or now < start:
            raise ValueError("play clock must be finite and monotonic")
        if now >= self.grant.expires_at:
            return "expired"
        if now-start >= self.grant.max_wall_seconds:
            return "time_budget"
        if self.consent_current(self.grant) is not True:
            return "revoked"
        if self.adapter.adapter_id != self.grant.adapter_id or self.adapter.artifact_digest != self.grant.artifact_digest:
            return "target_changed"
        return None

    def run(self, policy: Callable[[VisualFrame], PlayAction]) -> PlayTrace:
        """Single-use finite visual loop; always releases held controls.

        Adapter capture/advance and policy calls must themselves be bounded by
        their trusted worker. A synchronous Python callback cannot be forcibly
        interrupted here; this controller checks admission around each call.
        """
        if self._used:
            raise PermissionError("play session grant already consumed")
        self._used = True
        steps = []
        previous_sequence = -1
        previous_digest = canonical_digest({"session": self.grant.session_id,
            "artifact": self.grant.artifact_digest, "adapter": self.grant.adapter_id})
        reason = "step_budget"
        try:
            from math import isfinite
            start = self.clock()
            if isinstance(start, bool) or not isinstance(start, (int, float)) or not isfinite(start) or start < 0:
                raise ValueError("play clock must be finite and monotonic")
            for _ in range(self.grant.max_steps):
                denied = self._admitted(start)
                if denied:
                    reason = denied
                    break
                frame = self.adapter.capture()
                if not isinstance(frame, VisualFrame) or frame.sequence <= previous_sequence:
                    raise ValueError("adapter frame sequence replay or malformed capture")
                previous_sequence = frame.sequence
                denied = self._admitted(start)
                if denied:
                    reason = denied
                    break
                if frame.terminal:
                    body = {"frame_digest": frame.digest, "sequence": frame.sequence,
                            "action": None, "previous_digest": previous_digest}
                    steps.append({**body, "step_digest": canonical_digest(body)})
                    reason = "terminal_observed"
                    break
                action = policy(frame)
                if not isinstance(action, PlayAction) or not action.buttons <= self.grant.allowed_buttons:
                    raise PermissionError("policy action exceeds game-control allowlist")
                denied = self._admitted(start)
                if denied:
                    reason = denied
                    break
                self.adapter.advance(action)
                body = {"frame_digest": frame.digest, "sequence": frame.sequence,
                    "action": {"buttons": sorted(action.buttons), "frames": action.frames},
                    "previous_digest": previous_digest}
                previous_digest = canonical_digest(body)
                steps.append({**body, "step_digest": previous_digest})
        finally:
            self.adapter.release_inputs()
        return PlayTrace(self.grant.owner, self.grant.session_id, self.grant.adapter_id,
            self.grant.artifact_digest, reason, tuple(steps))


def frame_change(previous: VisualFrame, current: VisualFrame) -> dict:
    """Compute observable visual change without pretending to infer mechanics."""
    if (previous.width, previous.height) != (current.width, current.height) or current.sequence <= previous.sequence:
        raise ValueError("visual comparison requires ordered equal-geometry frames")
    changed = sum(previous.rgb[i:i+3] != current.rgb[i:i+3] for i in range(0, len(current.rgb), 3))
    return {"changed_pixels": changed, "pixel_count": current.width*current.height,
        "fraction": changed/(current.width*current.height), "mechanic_classification": "unclassified",
        "previous_frame": previous.digest, "current_frame": current.digest}
