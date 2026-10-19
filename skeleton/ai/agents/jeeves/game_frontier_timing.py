"""Opt-in 30/50/60/120 presentation-rate bridge for existing Jeeves era engines.

Uses canonical DeterministicGameClock physics authority without replacing
EngineEraProfile.tick_hz. Call advance_one_frame once per presentation interval.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from .game_engine_timing import (
    DeterministicGameClock, TimingFrame, TimingMode,
)
from .game_frontier_dynamics import (
    FPS_MODES, FrontierDynamicsError, PresentationClock,
)


@dataclass(frozen=True)
class FrontierTimedFrame:
    presentation_index: int
    presentation_deadline_ns: int
    simulation_frame: TimingFrame


class FrontierEraTiming:
    """A real adapter, not a competing physics clock."""

    def __init__(self, era: str, *, fps: int):
        if type(fps) is not int or fps not in FPS_MODES:
            raise FrontierDynamicsError("presentation mode must be 30, 50, 60 or 120")
        self.presentation = PresentationClock(fps)
        self.simulation = DeterministicGameClock(era)
        policy = self.simulation.policy
        # Presentation is decoupled from physics, even for historical frame-
        # locked eras. Preserve authoritative simulation rate and domains.
        self.simulation.policy = replace(
            policy, presentation_hz=fps,
            mode=TimingMode.FIXED_INTERPOLATED
                 if policy.mode is TimingMode.FRAME_LOCKED else policy.mode,
            interpolation=True,
        )
        self.index = 0

    @property
    def simulation_hz(self) -> int:
        return self.simulation.policy.simulation_hz

    @property
    def presentation_fps(self) -> int:
        return self.presentation.fps

    def advance_one_frame(self) -> FrontierTimedFrame:
        start = self.presentation.deadline(self.index)
        end = self.presentation.deadline(self.index + 1)
        self.index += 1
        frame = self.simulation.advance(end - start)
        return FrontierTimedFrame(self.index - 1, end, frame)


def compare_presentation_modes(era: str, *, seconds: int = 1) -> dict:
    """Executable cross-FPS simulation clock equality audit.

    Bounded to 120 seconds; this proves only deterministic clock consistency,
    not native engine/gameplay scene equality or GPU render performance.
    """
    if type(seconds) is not int or not 1 <= seconds <= 120:
        raise FrontierDynamicsError("seconds must be integer in 1..120")
    ticks: dict[int, int] = {}
    results = {}
    for fps in sorted(FPS_MODES):
        bridge = FrontierEraTiming(era, fps=fps)
        last: FrontierTimedFrame | None = None
        for _ in range(fps * seconds):
            last = bridge.advance_one_frame()
        assert last is not None
        ticks[fps] = bridge.simulation.simulation_tick
        results[fps] = {
            "frames": fps * seconds,
            "simulation_ticks": ticks[fps],
            "presentation_deadline_ns": last.presentation_deadline_ns,
            "simulation_hz": bridge.simulation_hz,
        }
    return {
        "era": str(era), "seconds": seconds,
        "simulation_rate_identical": len(set(ticks.values())) == 1,
        "modes": results,
        "source": "canonical_game_engine_timing_clock_not_gameplay_e2e",
    }
