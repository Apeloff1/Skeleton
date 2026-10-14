"""Evidence-linked numerical studio reviews of actual canonical runtime frames.

This is a deterministic observer, not a language model or subjective art judge.
Offline operation timing does not measure display FPS or hardware performance.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from statistics import median
from typing import Any

from .game_console_assets import decode_png, png_rgba
from .game_learning import GameLearningCancelled, GameLearningError, GamePolicyLearner
from .game_learning_parallel import GameEnvironmentRequest
from .game_studio_learning import StudioLearningCampaign

SCHEMA = "skeleton.game.studio_review.v1"
MAX_FRAMES = 25
MAX_STEPS = 512
MAX_RESULT = 2 * 1024 * 1024


def _copy(value: Any, limit: int = MAX_RESULT) -> Any:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(data) > limit:
        raise GameLearningError("studio review evidence exceeds its byte budget")
    return json.loads(data)


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise GameLearningError(f"{name} must be an integer within [{low}, {high}]")
    return value


def review_implementation_digest() -> str:
    here = Path(__file__).parent
    from skeleton.ai.webcrawler import dragon_temporal_segmentation

    names = [
        here / "game_studio_review.py",
        here / "game_studio_learning.py",
        here / "game_console_assets.py",
        Path(dragon_temporal_segmentation.__file__),
    ]
    return _digest({path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in names})


def _decode(frame):
    if frame is None:
        return None
    if not isinstance(frame, Mapping):
        raise GameLearningError("runtime frame must be an actual frame projection")
    uri = frame.get("data_uri")
    if not isinstance(uri, str) or not uri.startswith("data:image/png;base64,"):
        return None
    if len(uri) > 700000:
        raise GameLearningError("runtime frame encoding exceeds its budget")
    raw = base64.b64decode(uri.split(",", 1)[1], validate=True)
    if not 33 <= len(raw) <= 524288:
        raise GameLearningError("runtime frame PNG exceeds its budget")
    width, height, pixels = decode_png(raw)
    if width * height > 1048576:
        raise GameLearningError("runtime frame pixels exceed their budget")
    measured = StudioLearningCampaign._frame(frame)
    step = max(1, math.ceil(width * height / 4096))
    samples = [tuple(pixels[index * 4 : index * 4 + 3]) for index in range(0, width * height, step)]
    ratio = min(1, 128 / width, 72 / height)
    tw, th = max(1, int(width * ratio)), max(1, int(height * ratio))
    thumbnail = bytearray(tw * th * 4)
    for y in range(th):
        for x in range(tw):
            source = (min(height - 1, int(y / ratio)) * width + min(width - 1, int(x / ratio))) * 4
            thumbnail[(y * tw + x) * 4 : (y * tw + x) * 4 + 4] = pixels[source : source + 4]
    encoded = png_rgba(bytes(thumbnail), tw, th)
    return (
        measured,
        samples,
        {
            "decoded_rgba_digest": hashlib.sha256(pixels).hexdigest(),
            "thumbnail": {
                "width": tw,
                "height": th,
                "png_digest": hashlib.sha256(encoded).hexdigest(),
                "data_uri": "data:image/png;base64," + base64.b64encode(encoded).decode(),
            },
        },
    )


def analyze_frame_sequence(
    frames: Sequence[Mapping[str, Any]], *, source_identity: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Observe supplied actual frames; caller supplies their scoped provenance.

    Each row has step, frame, optional observation, step_wall_ms/render_wall_ms.
    This pure observer grants no authority to caller-supplied evidence.
    """
    if not isinstance(frames, (list, tuple)) or not 1 <= len(frames) <= MAX_FRAMES:
        raise GameLearningError("studio review needs 1..25 bounded actual frame rows")
    identity = _copy(dict(source_identity or {}), 32768)
    records, findings, vectors = [], [], []
    prior_samples = prior_observation = None
    prior_size = None
    total_bytes = last_step = duplicate_moving = 0

    def finding(code, severity, message, refs, measurement, constraint):
        value = {
            "code": code,
            "severity": severity,
            "message": message,
            "evidence_refs": refs,
            "measurement": measurement,
            "candidate_constraint": constraint,
            "classification": "numeric_observation_requires_inspection",
        }
        value["finding_id"] = _digest(value)
        if len(findings) < 128:
            findings.append(value)

    for index, row in enumerate(frames):
        if not isinstance(row, Mapping):
            raise GameLearningError("studio frame row must be an object")
        step = _integer(row.get("step"), "frame step", 0, 4096)
        if index and step <= last_step:
            raise GameLearningError("actual frame steps must increase strictly")
        last_step = step
        timings = {}
        for key in ("step_wall_ms", "render_wall_ms"):
            value = row.get(key)
            if value is not None:
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (float, int))
                    or not math.isfinite(value)
                    or not 0 <= value <= 60000
                ):
                    raise GameLearningError("actual operation timing must be finite and bounded")
                timings[key] = float(value)
        decoded = _decode(row.get("frame"))
        ref = "frame:" + str(step)
        observation = _copy(dict(row.get("observation") or {}), 8192)
        if decoded is None:
            records.append({"evidence_ref": ref, "step": step, "available": False, "timings": timings})
            continue
        measured, samples, thumbnail = decoded
        total_bytes += measured["png_bytes"]
        if total_bytes > MAX_FRAMES * 524288:
            raise GameLearningError("studio frame sequence exceeds input byte budget")
        size = (measured["width"], measured["height"])
        motion = None
        moving = False
        if prior_samples is not None and size == prior_size and len(samples) == len(prior_samples):
            motion = sum(
                sum(abs(a - b) for a, b in zip(now, old)) for now, old in zip(samples, prior_samples)
            ) / max(1, len(samples) * 3 * 255)
            if isinstance(observation, dict) and isinstance(prior_observation, dict):
                movement = []
                for key in ("x", "y", "z"):
                    a, b = observation.get(key), prior_observation.get(key)
                    if (
                        type(a) in (int, float)
                        and type(b) in (int, float)
                        and math.isfinite(a)
                        and math.isfinite(b)
                    ):
                        movement.append(abs(a - b))
                moving = bool(movement and max(movement) >= 0.005)
            duplicate_moving += motion == 0 and moving
            if motion == 0 and moving:
                finding(
                    "unchanged_raster_during_motion",
                    "warning",
                    "The sampled image stayed identical while position observations changed. Inspect the paired frames; camera or sampling can also explain this.",
                    [records[-1]["evidence_ref"], ref],
                    {"sampled_rgb_delta": 0, "position_delta_threshold": 0.005},
                    {
                        "requires": "inspect renderer updates before accepting motion changes",
                        "automatic_mutation": False,
                    },
                )
        visual = measured["visual_metrics"]
        if visual["flat_raster"]:
            finding(
                "flat_raster",
                "warning",
                "The decoded frame has very little color or luminance variation.",
                [ref],
                {
                    "luminance_range": visual["luminance_range"],
                    "palette_bins": visual["occupied_quantized_palette_bins"],
                },
                {"requires": "inspect scene visibility and palette", "automatic_mutation": False},
            )
        if visual["opaque_fraction"] < 0.02:
            finding(
                "mostly_transparent_raster",
                "warning",
                "Less than two percent of sampled pixels are visible.",
                [ref],
                {"opaque_fraction": visual["opaque_fraction"]},
                {"requires": "verify intended background and visible layers", "automatic_mutation": False},
            )
        if prior_size is not None and prior_size != size:
            finding(
                "raster_geometry_changed",
                "info",
                "The runtime changed preview dimensions within this sequence.",
                [records[-1]["evidence_ref"], ref],
                {"before": list(prior_size), "after": list(size)},
                {"requires": "confirm viewport transition is intentional", "automatic_mutation": False},
            )
        record = {
            "evidence_ref": ref,
            "step": step,
            "available": True,
            **measured,
            **thumbnail,
            "timings": timings,
            "sampled_rgb_delta": motion,
            "observed_position_changed": moving,
            "runtime_projection": _copy(
                {
                    key: row["frame"][key]
                    for key in (
                        "runtime_kind",
                        "render_kind",
                        "state_digest",
                        "source_pixel_digest",
                        "native_runs",
                        "video_callbacks",
                        "tick",
                    )
                    if key in row["frame"]
                },
                4096,
            ),
        }
        records.append(record)
        luminance = visual["luminance_range"] / 255
        vectors.append(
            (
                step,
                (luminance, visual["edge_density"], visual["dominant_color_fraction"], min(1, motion or 0)),
                ref,
            )
        )
        prior_samples, prior_size, prior_observation = samples, size, observation

    if not vectors:
        finding(
            "raster_unavailable",
            "warning",
            "This actual runtime did not return supported PNG frames; visual sequence review is unavailable.",
            [record["evidence_ref"] for record in records],
            {"available_frames": 0, "attempted_frames": len(records)},
            {
                "requires": "obtain an actual supported renderer preview before accepting visual changes",
                "automatic_mutation": False,
            },
        )

    from skeleton.ai.webcrawler.dragon_temporal_segmentation import (
        FeatureFrame,
        SegmentationConfig,
        segment_feature_trace,
    )

    events = segment_feature_trace(
        tuple(FeatureFrame(step, values, ref) for step, values, ref in vectors),
        authorized=True,
        config=SegmentationConfig(max_frames=MAX_FRAMES),
    )
    temporal = [
        {
            "start_step": item.start_ms,
            "peak_step": item.peak_ms,
            "end_step": item.end_ms,
            "peak_change": item.peak_change,
            "feature_indices": list(item.feature_indices),
            "evidence_refs": list(item.source_frame_ids),
            "classification": "unclassified_visual_transition",
        }
        for item in events
    ]
    for event in temporal:
        finding(
            "abrupt_visual_transition",
            "info",
            "Dragon temporal segmentation detected a visual feature transition. Inspect it for an intentional scene change or disruptive flicker.",
            event["evidence_refs"],
            {"peak_feature_change": event["peak_change"]},
            {"requires": "inspect temporal transition", "automatic_mutation": False},
        )
    timing_metrics = {}
    for key in ("step_wall_ms", "render_wall_ms"):
        values = [record["timings"][key] for record in records if key in record["timings"]]
        if values:
            ordered = sorted(values)
            timing_metrics[key] = {
                "count": len(values),
                "median": median(values),
                "p95": ordered[min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1)],
                "maximum": max(values),
                "classification": "offline_operation_wall_time_not_display_fps",
            }
            slow = [record["evidence_ref"] for record in records if record["timings"].get(key, 0) > 16.667]
            if slow:
                finding(
                    "operation_exceeds_60hz_budget",
                    "info",
                    "An observed offline operation exceeded 16.667 milliseconds; this is a workload cost candidate, not measured display stutter.",
                    slow,
                    {"operation": key, "count": len(slow), "budget_ms": 16.667},
                    {
                        "requires": "measure target renderer in its actual presentation workload",
                        "automatic_mutation": False,
                    },
                )
    result = {
        "schema_version": SCHEMA,
        "reviewer": "dragon_numeric_sequence",
        "status": "observed" if len(vectors) == len(records) else "partial" if vectors else "unavailable",
        "quality_certified": False,
        "model_critic_executed": False,
        "source_identity": identity,
        "frames": records,
        "findings": findings,
        "temporal_events": temporal,
        "metrics": {
            "ui_readability": {
                "available": False,
                "reason": "No semantic text or declared HUD glyph bounds; raster visibility is measured separately.",
            },
            "captured_frames": len(records),
            "available_frames": len(vectors),
            "actual_input_png_bytes": total_bytes,
            "unchanged_moving_frame_pairs": duplicate_moving,
            "visual_transitions": len(temporal),
            **timing_metrics,
        },
        "limitations": [
            "Numeric raster statistics are not subjective aesthetics or semantic text readability.",
            "Offline preview timing is not display FPS, browser performance or isolated memory usage.",
            "Repeated images and abrupt transitions are inspection candidates, not proven defects.",
            "This review grants no asset rights, production promotion or hardware authority.",
        ],
        "candidate_constraints": {
            "automatic_project_edits": False,
            "review_required": True,
            "source_identity_must_match": identity,
        },
    }
    result["review_digest"] = _digest(result)
    return _copy(result)


def review_project_sequence(
    environment_request: Mapping[str, Any],
    *,
    actions: Sequence[str] | None = None,
    seed: int = 0,
    capture_every: int = 4,
    policy_snapshot: Mapping[str, Any] | None = None,
    cancel: Callable[[], bool] | None = None,
    on_event: Callable[[dict[str, Any]], None] | None = None,
    source_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute an initial-state review, without changing saved play/training state."""
    request = GameEnvironmentRequest.from_dict(environment_request)
    if request.emulator_timeout_seconds > 5:
        raise GameLearningError("studio review emulator operations are bounded to five seconds")
    if request.max_steps > MAX_STEPS:
        raise GameLearningError("studio review is bounded to 512 runtime steps")
    _integer(seed, "review seed", 0, 2**32 - 1)
    _integer(capture_every, "capture interval", 1, 32)
    if actions is not None and (
        not isinstance(actions, (tuple, list))
        or not 1 <= len(actions) <= request.max_steps
        or any(not isinstance(a, str) or not 1 <= len(a) <= 64 for a in actions)
    ):
        raise GameLearningError("review actions are outside their bounded episode")
    if actions is not None and policy_snapshot is not None:
        raise GameLearningError("choose explicit actions or one frozen policy")
    started, implementation = time.monotonic(), review_implementation_digest()

    def guard():
        if cancel and cancel():
            raise GameLearningCancelled("studio review cancelled")
        if time.monotonic() - started >= 60:
            raise GameLearningCancelled("studio review execution deadline exceeded")

    environment = None
    try:
        guard()
        environment = request.build(cancel=cancel)
        policy = (
            None
            if policy_snapshot is None
            else GamePolicyLearner.from_snapshot(dict(policy_snapshot), expected_spec=environment.spec)
        )
        allowed = environment.spec.actions
        if actions is not None and any(action not in allowed for action in actions):
            raise GameLearningError("review action is not registered for the actual environment")
        observation = environment.reset(seed)
        rows, trace, operation_times = [], [], []
        steps = len(actions) if actions is not None else request.max_steps
        interval = max(capture_every, math.ceil(steps / (MAX_FRAMES - 1)))

        def capture(sequence, step_ms=None):
            guard()
            before = time.perf_counter()
            frame = environment.preview()
            render_ms = (time.perf_counter() - before) * 1000
            rows.append(
                {
                    "step": sequence,
                    "frame": frame,
                    "observation": _copy(dict(observation), 8192),
                    "step_wall_ms": step_ms,
                    "render_wall_ms": render_ms,
                }
            )
            if on_event:
                on_event(
                    {
                        "kind": "studio_review_progress",
                        "steps": sequence,
                        "planned_steps": steps,
                        "captured_frames": len(rows),
                    }
                )

        capture(0)
        terminal = truncated = False
        total = 0.0
        for index in range(steps):
            guard()
            action = (
                actions[index]
                if actions is not None
                else (policy.predict(observation)["action"] if policy else allowed[index % len(allowed)])
            )
            before = time.perf_counter()
            outcome = environment.step(action)
            step_ms = (time.perf_counter() - before) * 1000
            operation_times.append(step_ms)
            observation = outcome.observation
            total += outcome.reward
            terminal, truncated = outcome.terminated, outcome.truncated
            trace.append(
                {
                    "step": index + 1,
                    "action": action,
                    "reward": outcome.reward,
                    "transition_digest": outcome.transition_digest,
                    "observation_digest": _digest(dict(observation)),
                    "terminated": terminal,
                    "truncated": truncated,
                }
            )
            if (index + 1) % interval == 0 or terminal or truncated or index + 1 == steps:
                capture(index + 1, step_ms)
            if terminal or truncated:
                break
        guard()
        if review_implementation_digest() != implementation:
            raise GameLearningError("numeric reviewer implementation changed during execution")
        identity = {
            **dict(source_identity or {}),
            "environment_request_digest": request.digest,
            "environment": environment.spec.as_dict(),
            "reviewer_implementation_digest": implementation,
            "policy_digest": None if policy is None else policy.snapshot_digest,
            "seed": seed,
            "controller": (
                "explicit_actions"
                if actions is not None
                else "frozen_q_policy" if policy else "registered_action_cycle"
            ),
        }
        result = analyze_frame_sequence(rows, source_identity=identity)
        guard()
        if review_implementation_digest() != implementation:
            raise GameLearningError("numeric reviewer implementation changed during analysis")
        result["metrics"]["project_source_bytes"] = sum(
            len(value.encode()) for value in (request.tree or {}).values()
        )
        result["metrics"]["project_file_count"] = len(request.tree or {})
        result["metrics"]["isolated_memory"] = {
            "available": False,
            "reason": "Shared observer process memory cannot be attributed to this project.",
        }
        result["resource_bounds"] = {
            "episode_steps": MAX_STEPS,
            "capture_frames": MAX_FRAMES,
            "decoded_frame_pixels": 1048576,
            "result_bytes": MAX_RESULT,
            "deadline_seconds": 60,
        }
        result["execution"] = {
            "steps": len(trace),
            "planned_steps": steps,
            "return": total,
            "terminated": terminal,
            "truncated": truncated,
            "capture_every": interval,
            "trace": trace,
            "trace_digest": _digest(trace),
            "step_wall_ms": {
                "count": len(operation_times),
                "median": median(operation_times) if operation_times else 0,
                "maximum": max(operation_times, default=0),
            },
            "elapsed_wall_ms": (time.monotonic() - started) * 1000,
        }
        result.pop("review_digest")
        result["review_digest"] = _digest(result)
        return _copy(result)
    finally:
        if environment is not None:
            close = getattr(environment, "close", None)
            if callable(close):
                close()
