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
from itertools import pairwise
from pathlib import Path
from statistics import median
from typing import Any

from .game_console_assets import decode_png, png_rgba
from .game_learning import (
    GameLearningCancelled,
    GameLearningError,
    GamePolicyLearner,
    _copy_json,
)
from .game_learning_parallel import GameEnvironmentRequest
from .game_studio_learning import StudioLearningCampaign

SCHEMA = "skeleton.game.studio_review.v1"
MAX_FRAMES = 25
MAX_STEPS = 512
MAX_RESULT = 2 * 1024 * 1024


def _copy(value: Any, limit: int = MAX_RESULT) -> Any:
    return _copy_json(value, limit=limit)


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
        here / "game_console_editor.py",
        here / "game_console_graph.py",
        here / "game_console_simulation.py",
        here / "game_successor.py",
        here / "game_emulator_host.py",
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
        descriptor = _copy(getattr(environment, "descriptor", {}), 262144)
        native_binding = descriptor.get("native_observation")
        geometry_snapshot = None
        if request.kind == "console_editor":
            geometry = environment.review_geometry(max_cells=32768)
            geometry_snapshot = {
                key: geometry[key]
                for key in (
                    "schema_version",
                    "available",
                    "reason",
                    "project_digest",
                    "manifest_digest",
                    "source_manifest_digest",
                    "graph_digest",
                    "environment_digest",
                    "state_digest",
                    "tick",
                    "world_size",
                    "player_spawn_rect",
                    "player_current_rect",
                    "movement_mode",
                    "dynamic_geometry",
                    "geometry_digest",
                    "scope",
                )
                if key in geometry
            }
        semantic_trace_bytes = 0
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
            info = _semantic_info(outcome.info)
            semantic_trace_bytes += len(json.dumps(info, separators=(",", ":")).encode())
            if semantic_trace_bytes > 524288:
                raise GameLearningError("executed semantic evidence exceeds its byte budget")
            trace.append(
                {
                    "step": index + 1,
                    "action": action,
                    "reward": outcome.reward,
                    "transition_digest": outcome.transition_digest,
                    "observation_digest": _digest(dict(observation)),
                    "terminated": terminal,
                    "truncated": truncated,
                    "info": info,
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
        semantics = analyze_executed_semantics(
            request,
            trace,
            source_identity=identity,
            native_binding=native_binding,
            geometry_snapshot=geometry_snapshot,
            guard=guard,
        )
        result["semantic_review"] = semantics
        result["remedial_actions"] = semantics["remedial_actions"]
        result["findings"] = [*result["findings"], *semantics["findings"]][:128]
        result["metrics"]["semantic_scope"] = semantics["scope"]
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
            "semantic_trace_bytes": 524288,
            "initial_geometry_cells": 32768,
            "remedial_actions": 16,
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


def _semantic_info(info):
    """Retain measured state/events without copying native raw-frame evidence."""
    if not isinstance(info, Mapping):
        raise GameLearningError("executed runtime semantic metadata must be a mapping")
    keys = (
        "runtime_kind",
        "events",
        "won",
        "goal_reached",
        "dead",
        "player_x",
        "player_y",
        "vx",
        "vy",
        "contact_entity_ids",
        "movement_observation",
        "native_measurement",
        "attempted_controls",
        "collision_semantics_available",
        "state_digest",
        "rules_fired",
    )
    return _copy({key: info[key] for key in keys if key in info}, 16384)


def _approved_native_binding(request, value):
    if request.kind != "libretro" or value is None:
        return None
    from .game_emulator_host import validate_native_observation

    approved = validate_native_observation(value, core_id=request.core_id, target_id=request.target_id)
    if approved is None:
        raise GameLearningError("native review descriptor did not yield approved observation authority")
    return _copy(approved, 65536)


def _native_values(binding, measured):
    if not isinstance(measured, dict) or (
        measured.get("layout_digest") != binding["layout"]["layout_digest"]
        or measured.get("artifact_digest") != binding["artifact_digest"]
        or measured.get("producer_job_id") != binding["producer_job_id"]
        or not isinstance(measured.get("memory_digest"), str)
        or len(measured["memory_digest"]) != 64
        or any(char not in "0123456789abcdef" for char in measured["memory_digest"])
    ):
        raise GameLearningError("measured native values differ from their exact approved artifact/layout")
    values = measured.get("values")
    fields = binding["layout"]["fields"]
    if not isinstance(values, dict) or set(values) != set(fields):
        raise GameLearningError("native measured field coverage differs from the approved layout")
    for name, field in fields.items():
        if type(values[name]) is not int or not field["minimum"] <= values[name] <= field["maximum"]:
            raise GameLearningError("native measured value is outside its declared integer encoding")
    return values


def _overlaps(a, b):
    return a[0] < b[0] + b[2] and a[0] + a[2] > b[0] and a[1] < b[1] + b[3] and a[1] + a[3] > b[1]


def _editor_layout(request, guard):
    """Initial authored geometry; independent of task/combat/timeline success."""
    from collections import deque

    from .game_console_editor import ConsoleProject, file_manifest_digest
    from .game_console_graph import ConsoleGraphRuntime

    project = ConsoleProject.from_files(request.tree, target_id=request.target_id)
    document = project.as_dict()
    graph = project.scene_graph.as_dict()
    poses = ConsoleGraphRuntime(project.scene_graph)
    player = next(row for row in document["entities"] if row["kind"] == "player")
    layers = document["layers"]
    width = max(row["offset"][0] + row["width"] * 8 for row in layers)
    height = max(row["offset"][1] + row["height"] * 8 for row in layers)
    pw, ph = player["width"], player["height"]
    dynamic = bool(graph["animations"]) or any(
        effect["kind"] in {"set_node_visibility", "set_node_offset", "teleport", "win"}
        for rule in graph["rules"]
        for effect in rule["actions"]
    )
    one_way = any(cell["collision"] == "one_way" for layer in layers for cell in layer["cells"]) or any(
        row["kind"] == "platform" and row["properties"]["one_way"] for row in document["entities"]
    )
    platforms, goals = [], []
    for row in document["entities"]:
        pose = poses.pose(row["id"], 0)
        rect = [row["x"] + pose["x"], row["y"] + pose["y"], row["width"], row["height"]]
        if not pose["visible"]:
            continue
        if row["kind"] == "platform" and not row["properties"]["one_way"]:
            platforms.append((row["id"], rect))
        if row["kind"] == "goal":
            goals.append(
                {
                    "target_id": row["id"],
                    "kind": "entity",
                    "rect": rect,
                    "source_ref": "source:game/editor/console.json#entities/" + row["id"],
                }
            )
    for layer in layers:
        for index, cell in enumerate(layer["cells"]):
            if cell["collision"] == "goal" and len(goals) < 64:
                x, y = index % layer["width"], index // layer["width"]
                goals.append(
                    {
                        "target_id": layer["id"] + ":" + str(x) + ":" + str(y),
                        "kind": "tile",
                        "rect": [layer["offset"][0] + x * 8, layer["offset"][1] + y * 8, 8, 8],
                        "source_ref": "source:game/editor/console.json#layers/"
                        + layer["id"]
                        + "/cells/"
                        + str(index),
                    }
                )
    facts = {
        "available": True,
        "classification": "initial_authored_geometry_not_full_game_solver",
        "document_digest": project.digest,
        "manifest_digest": file_manifest_digest(request.tree),
        "normalized_manifest_digest": project.manifest_digest,
        "graph_digest": project.scene_graph.digest,
        "world_size": [width, height],
        "player_id": player["id"],
        "spawn_rect": [player["x"], player["y"], pw, ph],
        "movement_mode": document["config"]["movement_mode"],
        "dynamic_geometry": dynamic,
        "one_way_geometry": one_way,
        "targets": [],
        "limitations": [
            "Initial geometry only; combat, resource gates, portals, timeline changes and authored rules can change reachable outcomes."
        ],
    }

    collision_queries = 0

    def collision(x, y):
        nonlocal collision_queries
        collision_queries += 1
        if collision_queries % 128 == 0:
            guard()
        body = [x, y, pw, ph]
        refs = []
        if x < 0 or y < 0 or x + pw > width or y + ph > height:
            refs.append({"kind": "world_boundary", "source_ref": "source:game/editor/console.json#layers"})
        for identity, rect in platforms:
            if _overlaps(body, rect):
                refs.append(
                    {
                        "kind": "entity",
                        "entity_id": identity,
                        "rect": rect,
                        "source_ref": "source:game/editor/console.json#entities/" + identity,
                    }
                )
        for layer in layers:
            ox, oy = layer["offset"]
            for ty in range(
                max(0, math.floor((y - oy) / 8)),
                min(layer["height"] - 1, math.floor((y + ph - 1e-8 - oy) / 8)) + 1,
            ):
                for tx in range(
                    max(0, math.floor((x - ox) / 8)),
                    min(layer["width"] - 1, math.floor((x + pw - 1e-8 - ox) / 8)) + 1,
                ):
                    cell = layer["cells"][ty * layer["width"] + tx]
                    if cell["collision"] == "solid":
                        refs.append(
                            {
                                "kind": "tile",
                                "layer_id": layer["id"],
                                "x": tx,
                                "y": ty,
                                "cell": cell,
                                "source_ref": "source:game/editor/console.json#layers/"
                                + layer["id"]
                                + "/cells/"
                                + str(ty * layer["width"] + tx),
                            }
                        )
        return refs[:64]

    footprint = (math.ceil(pw / 8) + 1) * (math.ceil(ph / 8) + 1)
    if footprint > 64:
        facts.update(available=False, reason="player_collision_footprint_exceeds64tiles")
        return facts, project, document, graph
    spawn_contacts = collision(player["x"], player["y"])
    facts["spawn_contacts"] = spawn_contacts
    total_cells = sum(len(layer["cells"]) for layer in layers)
    facts["source_cells"] = total_cells
    if document["config"]["movement_mode"] != "top_down":
        facts.update(
            route_available=False,
            route_reason="Platformer reachability requires actual jump/one_way dynamics; no top_down grid claim.",
        )
        return facts, project, document, graph
    ox, oy = player["x"] % 8, player["y"] % 8
    columns = max(0, math.floor((width - pw - ox) / 8) + 1)
    rows = max(0, math.floor((height - ph - oy) / 8) + 1)
    if columns * rows > 32768 or total_cells > 65536:
        facts.update(
            route_available=False,
            route_reason="Authored geometry exceeds bounded exact grid budget.",
            grid_cells=columns * rows,
        )
        return facts, project, document, graph
    start = (int((player["x"] - ox) / 8), int((player["y"] - oy) / 8))
    parents = {start: None} if not spawn_contacts else {}
    queue = deque(parents)
    blocked_frontier = []
    visited_iterations = 0
    while queue:
        visited_iterations += 1
        if visited_iterations % 64 == 0:
            guard()
        col, row = queue.popleft()
        for adjacent in ((col - 1, row), (col + 1, row), (col, row - 1), (col, row + 1)):
            if adjacent in parents or not 0 <= adjacent[0] < columns or not 0 <= adjacent[1] < rows:
                continue
            dx, dy = adjacent[0] - col, adjacent[1] - row
            contacts = []
            for fraction in (2, 4, 6, 8):
                contacts = collision(ox + col * 8 + dx * fraction, oy + row * 8 + dy * fraction)
                if contacts:
                    break
            if contacts:
                if len(blocked_frontier) < 64:
                    blocked_frontier.append(
                        {
                            "from": [ox + col * 8, oy + row * 8],
                            "toward": [ox + adjacent[0] * 8, oy + adjacent[1] * 8],
                            "contacts": contacts[:4],
                        }
                    )
                continue
            parents[adjacent] = (col, row)
            queue.append(adjacent)
    facts.update(
        route_available=True,
        method="body_rect_four_neighbor8px_with2px_segment_contacts",
        grid_cells=columns * rows,
        visited_cells=len(parents),
        blocked_frontier=blocked_frontier,
    )
    facts["collision_queries"] = collision_queries
    for goal in goals[:64]:
        guard()
        destination = next(
            (
                cell
                for cell in parents
                if _overlaps([ox + cell[0] * 8, oy + cell[1] * 8, pw, ph], goal["rect"])
            ),
            None,
        )
        route = []
        cursor = destination
        while cursor is not None:
            route.append([ox + cursor[0] * 8, oy + cursor[1] * 8])
            cursor = parents[cursor]
        route.reverse()
        facts["targets"].append(
            {
                **goal,
                "grid_route_found": destination is not None,
                "route_length_cells": len(route),
                "route_sample": route[:64],
                "classification": "initial_geometry_candidate_not_task_completion_proof",
            }
        )
    return facts, project, document, graph


def analyze_executed_semantics(
    request, trace, *, source_identity=None, native_binding=None, geometry_snapshot=None, guard=lambda: None
):
    """Source facts plus measured responses; no opaque-ROM semantic guessing."""
    if (
        not isinstance(request, GameEnvironmentRequest)
        or not isinstance(trace, list)
        or len(trace) > MAX_STEPS
    ):
        raise GameLearningError("semantic review requires one registered request and bounded executed trace")
    identity = dict(source_identity or {})
    findings, proposals = [], []
    opaque_rom = request.kind == "libretro" or (request.kind == "builtin" and request.rom_source is not None)
    scope = (
        "opaque_rom_pixel_advisory"
        if opaque_rom
        else "declared_reference_runtime" if request.kind == "builtin" else "authored_simulation"
    )
    layout, project, document, graph = (
        {"available": False, "reason": "No typed authored scene geometry for this adapter."},
        None,
        None,
        None,
    )
    if request.kind == "console_editor":
        layout, project, document, graph = _editor_layout(request, guard)
        if geometry_snapshot is not None:
            layout["runtime_initial_snapshot"] = _copy(geometry_snapshot, 16384)
    elif request.kind == "successor":
        from .game_successor import GameSuccessorError, validate_successor_routes

        spec = json.loads(request.tree["game/successor/spec.json"])
        if spec.get("gameplay_mode") == "top_down":
            try:
                layout = {
                    "available": True,
                    "source_ref": "source:game/successor/spec.json#world",
                    **validate_successor_routes(spec),
                }
            except GameSuccessorError as exc:
                layout = {
                    "available": True,
                    "source_ref": "source:game/successor/spec.json#world",
                    "classification": "analytical_authored_geometry_not_measured_task_success",
                    "initial_route_valid": False,
                    "reason": str(exc),
                }
        else:
            layout = {
                "available": False,
                "reason": "No full continuous platformer reachability solver is claimed.",
            }

    def add(code, message, refs, measurement, severity="warning"):
        finding = {
            "code": code,
            "severity": severity,
            "message": message,
            "evidence_refs": refs,
            "measurement": measurement,
            "classification": (
                "source_bound_semantic_candidate"
                if refs and refs[0].startswith("source:")
                else "actual_bounded_run_observation"
            ),
            "candidate_constraint": {
                "requires": "Inspect this exact source and executed counterexample before accepting a change.",
                "automatic_mutation": False,
            },
        }
        finding["finding_id"] = _digest(finding)
        findings.append(finding)
        return finding

    def command(finding, operation, payload, reason):
        if len(proposals) >= 16:
            return
        value = {
            "operation": operation,
            "payload": payload,
            "finding_id": finding["finding_id"],
            "reason": reason,
            "source_request_digest": request.digest,
            "source_identity": {key: value for key, value in identity.items() if key != "environment"},
            "requires_explicit_execution": True,
            "automatic_execution": False,
        }
        value["proposal_digest"] = _digest(value)
        proposals.append(value)

    if project is not None:
        if layout.get("spawn_contacts"):
            refs = [row["source_ref"] for row in layout["spawn_contacts"]]
            finding = add(
                "authored_spawn_collision",
                "The declared player spawn overlaps initial solid geometry. Inspect the colliding source cells/entities.",
                refs,
                {
                    "player_id": layout["player_id"],
                    "spawn_rect": layout["spawn_rect"],
                    "contacts": layout["spawn_contacts"],
                },
            )
            command(
                finding,
                "console.inspect",
                {"section": "entities", "record_id": layout["player_id"]},
                "Inspect the actual player spawn source record.",
            )
            if (
                type(identity.get("project_version")) is int
                and identity.get("project_id") == document["project_id"]
            ):
                from .game_console_editor import apply_console_edits

                for contact in layout["spawn_contacts"]:
                    if contact["kind"] != "tile":
                        continue
                    edit = {
                        "op": "set_map_cell",
                        "layer_id": contact["layer_id"],
                        "x": contact["x"],
                        "y": contact["y"],
                        "cell": {**contact["cell"], "collision": "none"},
                    }
                    try:
                        apply_console_edits(
                            request.tree,
                            target_id=request.target_id,
                            edits=[edit],
                            expected_manifest_digest=layout["manifest_digest"],
                        )
                    except ValueError:
                        continue
                    command(
                        finding,
                        "console.edit",
                        {
                            "expected_version": identity["project_version"],
                            "expected_manifest_digest": layout["manifest_digest"],
                            "idempotency_key": "review-remedy:"
                            + request.digest
                            + ":"
                            + finding["finding_id"],
                            "edits": [edit],
                        },
                        "Optional validated one-cell draft removes this measured source spawn blocker; inspect before execution.",
                    )
                    break
        for target in layout.get("targets", []):
            if not target["grid_route_found"]:
                finding = add(
                    "no_initial_grid_route",
                    "No body-sized route to this goal was found in the bounded initial collision snapshot. Dynamic rules or abilities may provide another route.",
                    [target["source_ref"]],
                    {
                        "target_id": target["target_id"],
                        "rect": target["rect"],
                        "visited_cells": layout["visited_cells"],
                        "dynamic_geometry": layout["dynamic_geometry"],
                        "one_way_geometry": layout["one_way_geometry"],
                    },
                    severity=(
                        "info" if layout["dynamic_geometry"] or layout["one_way_geometry"] else "warning"
                    ),
                )
                if target["kind"] == "entity":
                    command(
                        finding,
                        "console.inspect",
                        {"section": "entities", "record_id": target["target_id"]},
                        "Inspect this exact goal and its initial transform before editing geometry.",
                    )
        resource_rules = {
            effect.get("metric")
            for rule in graph["rules"]
            for effect in rule["actions"]
            if effect["kind"] in {"set_metric", "add_metric"}
        } | {
            effect.get("resource")
            for rule in graph["rules"]
            for effect in rule["actions"]
            if effect["kind"] == "trade"
        }
        for npc in document["entities"]:
            if npc["kind"] != "npc":
                continue
            quest = npc["properties"]["quest_type"]
            resource = "crops" if quest == "deliver_crop" else "fish" if quest == "catch_fish" else None
            natural = (
                resource == "crops"
                and any(row["kind"] == "crop" for row in document["entities"])
                or resource == "fish"
                and (
                    any(row["kind"] == "water" for row in document["entities"])
                    or any(
                        cell["collision"] == "water"
                        for layer in document["layers"]
                        for cell in layer["cells"]
                    )
                )
            )
            if resource and not natural and resource not in resource_rules:
                finding = add(
                    "quest_resource_has_no_producer",
                    "This authored quest requires a resource with no producing entity/tile or typed resource rule in this scene.",
                    ["source:game/editor/console.json#entities/" + npc["id"]],
                    {
                        "npc_id": npc["id"],
                        "quest_type": quest,
                        "required_count": npc["properties"]["required_count"],
                        "resource": resource,
                        "producing_entities_or_tiles": 0,
                        "producing_rules": 0,
                    },
                )
                command(
                    finding,
                    "console.inspect",
                    {"section": "entities", "record_id": npc["id"]},
                    "Inspect the exact quest requirement and add an appropriate original producer through the editor.",
                )
    if layout.get("initial_route_valid") is False:
        add(
            "authored_route_validation_failed",
            "The authored geometry validator rejected a spawn/goal/relic route; this is analytical evidence, not a claim about combat or task mastery.",
            [layout["source_ref"]],
            {"reason": layout["reason"]},
        )

    events, positions, contacts = {}, [], []
    successful, dead, native_rows = [], [], []
    native = _approved_native_binding(request, native_binding)
    for row in trace:
        guard()
        info = row.get("info", {})
        for event in info.get("events", []):
            if isinstance(event, str) and len(event) <= 128:
                events[event] = events.get(event, 0) + 1
        response = info.get("movement_observation")
        if isinstance(response, dict):
            point = response.get("end")
        else:
            point = [info.get("player_x"), info.get("player_y")]
        if opaque_rom:
            measured = info.get("native_measurement")
            if native is not None and measured is not None:
                values = _native_values(native, measured)
                point = [values["player_x"], values["player_y"]]
                native_rows.append({"step": row["step"], **measured})
                if values["won"] == 1:
                    successful.append(row["step"])
                if values["health"] == 0:
                    dead.append(row["step"])
            else:
                point = None
        else:
            if info.get("won") is True or info.get("goal_reached") is True:
                successful.append(row["step"])
            if info.get("dead") is True:
                dead.append(row["step"])
        if (
            isinstance(point, (list, tuple))
            and len(point) == 2
            and all(type(value) in (int, float) and math.isfinite(value) for value in point)
        ):
            positions.append((row["step"], row["action"], tuple(point)))
        if isinstance(info.get("contact_entity_ids"), list):
            contacts.extend(
                {"step": row["step"], "entity_id": entity}
                for entity in info["contact_entity_ids"][:16]
                if isinstance(entity, str)
            )
    if native_rows:
        scope = "approved_native_observation"
        layout = {
            "available": True,
            "classification": "source_bound_native_ram_not_collision_or_route_proof",
            "descriptor_digest": native["descriptor_digest"],
            "layout_digest": native["layout"]["layout_digest"],
            "document_digest": native["layout"]["document_digest"],
            "graph_digest": native["layout"]["graph_digest"],
            "artifact_digest": native["artifact_digest"],
            "producer_job_id": native["producer_job_id"],
            "fields": native["layout"]["fields"],
            "measurement_scope": native["layout"]["measurement_scope"],
            "collision_semantics_available": False,
            "route_available": False,
            "measured_steps": len(native_rows),
            "measurement_digest": _digest(native_rows),
        }
    zero_runs = []
    run = []
    directions = {
        "left",
        "right",
        "up",
        "down",
        "left_jump",
        "right_jump",
        "up_left",
        "up_right",
        "down_left",
        "down_right",
    }
    for previous, current in pairwise(positions):
        if (
            current[0] == previous[0] + 1
            and current[1] == previous[1]
            and current[1] in directions
            and math.hypot(current[2][0] - previous[2][0], current[2][1] - previous[2][1]) < 0.01
        ):
            if not run:
                run.append(previous)
            run.append(current)
        else:
            if len(run) >= 8:
                zero_runs.append(run)
            run = []
    if len(run) >= 8:
        zero_runs.append(run)
    for run in zero_runs[:16]:
        matching_contacts = [row for row in contacts if run[0][0] <= row["step"] <= run[-1][0]]
        add(
            "held_control_without_displacement",
            "A directional action was held for at least eight executed steps without measurable physical displacement. Collision or authored locking may explain it; inspect the counterexample.",
            ["step:" + str(run[0][0]), "step:" + str(run[-1][0])],
            {
                "action": run[0][1],
                "first_step": run[0][0],
                "last_step": run[-1][0],
                "position_pixels": list(run[-1][2]),
                "contacts": matching_contacts[:16],
            },
        )
    result = {
        "schema_version": "skeleton.game.studio_semantic_review.v1",
        "scope": scope,
        "layout": layout,
        "control_response": {
            "physical_positions_available": bool(positions),
            "observed_position_steps": len(positions),
            "unchanged_directional_holds": len(zero_runs),
            "contact_samples": contacts[:64],
            "blocked_collision_queries": sum(
                row.get("info", {}).get("movement_observation", {}).get("blocked_collision_queries", 0)
                for row in trace
            ),
            "collision_semantics_available": request.kind == "console_editor",
            "native_collision_or_body_inference": False,
        },
        "actual_events": events,
        "native_measurement_samples": native_rows[:16],
        "observed_success_steps": successful[:16] if scope != "opaque_rom_pixel_advisory" else [],
        "observed_death_steps": dead[:16] if scope != "opaque_rom_pixel_advisory" else [],
        "findings": findings[:128],
        "remedial_actions": proposals,
        "source_request_digest": request.digest,
        "limitations": [
            "A goal not reached in this bounded run is not proven unreachable.",
            "Opaque ROM pixels cannot establish player identity, task success, control response or semantic defects.",
            "Static grid routes do not solve jumping, combat, gates, timeline rules or full progression.",
        ],
    }
    result["semantic_digest"] = _digest(result)
    return _copy(result)
