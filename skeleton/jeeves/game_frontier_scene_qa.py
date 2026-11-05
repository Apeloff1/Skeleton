"""Qualified physics/event evidence -> authorised playable scene QA (GF-P0-185).

A playable scene is admitted only when three things agree:

* a ``RuntimeBinding`` (from ``game_frontier_runtime_binding``) proving the
  candidate was authorised and routed into the runtime;
* a chain of native multi-actor physics tick receipts whose hash chain
  re-verifies and whose semantic events are reported in full;
* a rendered-world report captured from a real Godot run of the bound
  files: frame count, frame pacing, non-blank frame coverage, and the digest
  of the binding JSON the running scene loaded.

Without a Godot report the verdict is ``pending_native_render`` and the
scene is never marked playable. There is no fallback that simulates a render.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Mapping, Sequence

from .game_frontier_runtime_binding import RuntimeBinding

BINDING_FILE = "frontier/data/runtime_binding.json"


class SceneQAError(ValueError):
    pass


@dataclass(frozen=True)
class RenderedWorldReport:
    """Facts measured by a headless/native Godot run of the bound scene."""

    godot_version: str
    loaded_binding_sha256: str
    frames_rendered: int
    frame_times_ms: tuple[float, ...]
    nonblank_fraction: float
    node_paths_seen: frozenset[str]
    script_errors: int

    def __post_init__(self) -> None:
        if not self.godot_version.startswith("4."):
            raise SceneQAError("Godot 4.x run required")
        if type(self.frames_rendered) is not int or self.frames_rendered < 0:
            raise SceneQAError("frames_rendered invalid")
        if len(self.frame_times_ms) != self.frames_rendered:
            raise SceneQAError("one frame time per rendered frame required")
        if any(type(t) not in (int, float) or not math.isfinite(t) or t <= 0
               for t in self.frame_times_ms):
            raise SceneQAError("frame times must be positive finite")
        if not 0.0 <= self.nonblank_fraction <= 1.0:
            raise SceneQAError("nonblank_fraction outside 0..1")
        if type(self.script_errors) is not int or self.script_errors < 0:
            raise SceneQAError("script_errors invalid")


@dataclass(frozen=True)
class SceneQAThresholds:
    min_frames: int = 120
    max_p95_frame_ms_factor: float = 1.5
    min_nonblank_fraction: float = 0.9


@dataclass(frozen=True)
class SceneQAVerdict:
    binding_id: str
    verdict: str
    playable: bool
    failures: tuple[str, ...]
    physics_ticks: int
    physics_events: Mapping[str, int]
    p95_frame_ms: float | None
    qa_digest: str


def _p95(values: Sequence[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)]


def _verify_chain(receipts: Sequence) -> dict[str, int]:
    prev = "0" * 64
    counts: dict[str, int] = {}
    for expected_tick, r in enumerate(receipts):
        if r.tick != expected_tick or r.prev_digest != prev:
            raise SceneQAError(f"physics receipt chain broken at tick {expected_tick}")
        prev = r.state_digest
        for event in r.events:
            counts[event.kind] = counts.get(event.kind, 0) + 1
    return dict(sorted(counts.items()))


def qualify_playable_scene(binding: RuntimeBinding, physics_receipts: Sequence,
                           report: RenderedWorldReport | None, *,
                           thresholds: SceneQAThresholds = SceneQAThresholds()) -> SceneQAVerdict:
    if not isinstance(binding, RuntimeBinding):
        raise SceneQAError("RuntimeBinding required")
    if not physics_receipts:
        raise SceneQAError("qualified native physics evidence required")
    events = _verify_chain(physics_receipts)
    failures: list[str] = []
    p95 = None
    if report is None:
        verdict = "pending_native_render"
    else:
        binding_json = binding.godot_files.get(BINDING_FILE)
        if binding_json is None:
            raise SceneQAError("binding has no runtime_binding.json")
        if report.loaded_binding_sha256 != sha256(binding_json.encode()).hexdigest():
            failures.append("godot_loaded_different_binding")
        if report.frames_rendered < thresholds.min_frames:
            failures.append("too_few_frames")
        if report.frame_times_ms:
            p95 = _p95(report.frame_times_ms)
            budget = 1000.0 / binding.fps * thresholds.max_p95_frame_ms_factor
            if p95 > budget:
                failures.append("frame_pacing_over_budget")
        if report.nonblank_fraction < thresholds.min_nonblank_fraction:
            failures.append("blank_frames")
        missing = {o.node_path for o in binding.outputs} - report.node_paths_seen
        if missing:
            failures.append("runtime_nodes_missing:" + ",".join(sorted(missing)))
        if report.script_errors:
            failures.append("script_errors")
        verdict = "failed" if failures else "playable"
    digest = sha256(json.dumps({
        "binding": binding.binding_id, "verdict": verdict,
        "failures": failures, "ticks": len(physics_receipts),
        "last_state": physics_receipts[-1].state_digest,
        "events": events, "p95": p95,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return SceneQAVerdict(binding.binding_id, verdict, verdict == "playable",
                          tuple(failures), len(physics_receipts), events, p95, digest)
