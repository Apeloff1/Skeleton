"""Deterministic multiscale temporal segmentation for gameplay analysis.

Segments bounded feature traces into candidate events using robust baseline
statistics and hysteresis. Outputs *candidate* transitions, not semantic
claims about mechanics. A later inference layer must test explanations.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import median


@dataclass(frozen=True)
class FeatureFrame:
    timestamp_ms: int
    features: tuple[float, ...]
    source_frame_id: str


@dataclass(frozen=True)
class TemporalEvent:
    start_ms: int
    peak_ms: int
    end_ms: int
    peak_change: float
    baseline_change: float
    feature_indices: tuple[int, ...]
    source_frame_ids: tuple[str, ...]
    interpretation: str = "unclassified_visual_transition"


@dataclass(frozen=True)
class SegmentationConfig:
    baseline_window: int = 9
    onset_multiplier: float = 3.0
    release_multiplier: float = 1.2
    noise_floor: float = 0.02
    min_event_frames: int = 1
    max_frames: int = 20000
    max_features: int = 256
    max_event_frames: int = 1000


def segment_feature_trace(
    frames: tuple[FeatureFrame, ...], *,
    authorized: bool, config: SegmentationConfig = SegmentationConfig(),
) -> tuple[TemporalEvent, ...]:
    if not authorized:
        raise PermissionError("temporal analysis requires authorization")
    if not 3 <= config.baseline_window <= 1001:
        raise ValueError("invalid baseline window")
    if not 1 < config.onset_multiplier <= 100 or not 0 < config.release_multiplier < config.onset_multiplier:
        raise ValueError("invalid hysteresis thresholds")
    if not isfinite(config.noise_floor) or not 0 < config.noise_floor <= 100:
        raise ValueError("invalid noise floor")
    if not 1 <= config.min_event_frames <= config.max_event_frames <= 100000:
        raise ValueError("invalid event frame bounds")
    if not 2 <= config.max_frames <= 1000000 or not 1 <= config.max_features <= 4096:
        raise ValueError("invalid feature budget")
    if len(frames) > config.max_frames:
        raise ValueError("frame budget exceeded")
    if len(frames) < 2:
        return ()
    dimension = len(frames[0].features)
    if not 1 <= dimension <= config.max_features:
        raise ValueError("invalid feature dimension")
    seen_frame_ids = set()
    for i, frame in enumerate(frames):
        if not isinstance(frame.timestamp_ms, int) or frame.timestamp_ms < 0:
            raise ValueError("invalid timestamp")
        if i and frame.timestamp_ms <= frames[i - 1].timestamp_ms:
            raise ValueError("timestamps must increase strictly")
        if not isinstance(frame.source_frame_id, str) or not 1 <= len(frame.source_frame_id) <= 256:
            raise ValueError("invalid source frame id")
        if frame.source_frame_id in seen_frame_ids:
            raise ValueError("duplicate source frame id")
        seen_frame_ids.add(frame.source_frame_id)
        if len(frame.features) != dimension or any(
            not isfinite(x) or not 0 <= x <= 1 for x in frame.features
        ):
            raise ValueError("invalid normalized feature vector")
    changes = [max(abs(a - b) for a, b in zip(
        frames[i - 1].features, frames[i].features,
    )) for i in range(1, len(frames))]
    events = []
    active_start = None
    peak_index = None
    peak_change = 0.0
    for index, change in enumerate(changes):
        history = changes[max(0, index - config.baseline_window):index]
        baseline = median(history) if history else config.noise_floor
        threshold = max(config.noise_floor, baseline) * config.onset_multiplier
        release = max(config.noise_floor, baseline) * config.release_multiplier
        if active_start is None:
            if change >= threshold:
                active_start = index
                peak_index = index
                peak_change = change
        else:
            if change > peak_change:
                peak_index = index
                peak_change = change
            length = index - active_start + 1
            if change <= release or length >= config.max_event_frames or index == len(changes) - 1:
                if length >= config.min_event_frames:
                    start_frame = active_start
                    end_frame = index + 1
                    peak = peak_index + 1
                    indices = tuple(
                        j for j, (a, b) in enumerate(zip(
                            frames[peak - 1].features, frames[peak].features,
                        )) if abs(a - b) >= config.noise_floor
                    )
                    events.append(TemporalEvent(
                        frames[start_frame].timestamp_ms,
                        frames[peak].timestamp_ms,
                        frames[end_frame].timestamp_ms,
                        round(peak_change, 6), round(baseline, 6),
                        indices,
                        tuple(f.source_frame_id for f in frames[start_frame:end_frame + 1]),
                    ))
                active_start = None
                peak_index = None
                peak_change = 0.0
    if active_start is None and changes:
        # A transition on the final sample has no following iteration to
        # close the event. Preserve the terminal observation explicitly.
        final_index = len(changes) - 1
        history = changes[max(0, final_index - config.baseline_window):final_index]
        baseline = median(history) if history else config.noise_floor
        if changes[final_index] >= max(config.noise_floor, baseline) * config.onset_multiplier:
            active_start = final_index
            peak_index = final_index
            peak_change = changes[final_index]
    if active_start is not None:
        start_frame = active_start
        peak = peak_index + 1
        end_frame = len(frames) - 1
        if end_frame - start_frame >= config.min_event_frames:
            indices = tuple(j for j, (a, b) in enumerate(zip(
                frames[peak - 1].features, frames[peak].features,
            )) if abs(a - b) >= config.noise_floor)
            events.append(TemporalEvent(
                frames[start_frame].timestamp_ms,
                frames[peak].timestamp_ms,
                frames[end_frame].timestamp_ms,
                round(peak_change, 6), round(config.noise_floor, 6),
                indices,
                tuple(f.source_frame_id for f in frames[start_frame:end_frame + 1]),
            ))
    return tuple(events)
