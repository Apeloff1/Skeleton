"""Deterministic, bounded cinematic rehearsal and multi-variation evidence engine.

This simulates *shot/camera/continuity constraints*, not rendered pixels, cloth
physics, game-engine frames, or neural-network optimizer steps. Forward and
reverse audits inspect one trace; reversing is not a second independent sample.
Every output is a quarantined candidate for independent rights/quality review.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from hashlib import sha256
from itertools import product
from math import atan2, degrees, hypot, isfinite, sqrt
from multiprocessing import get_context
from pathlib import Path
from typing import Any
import argparse
import json
import os
import re
import sys
import tempfile

SCHEMA = "skeleton.jeeves.cinematic_sim.v1"
REPORT_SCHEMA = "skeleton.jeeves.cinematic_multisim_report.v1"
CAMERAS = frozenset(("establishing", "wide", "medium", "closeup", "extreme_closeup",
                     "tracking", "over_shoulder", "first_person", "fixed", "pan_to",
                     "tilt", "dolly", "crane", "orbit", "rack_focus", "handheld"))
TRANSITIONS = frozenset(("continuous", "straight", "match_cut", "cross_cut",
                         "dissolve", "fade", "player_control"))
AXES = frozenset(("axis_a", "axis_b", "neutral"))
ID = re.compile(r"[a-z][a-z0-9_]{1,47}\Z")
MAX_SHOTS = 48
MAX_FRAMES_PER_SIM = 2048
MAX_SIMULATIONS = 512
MAX_BATCH_FRAMES = 180000
ZERO = "0" * 64


class CinematicSimError(ValueError):
    """Unsafe, ambiguous or unreviewed cinematic source or experiment."""


def _require(value: bool, problem: str) -> None:
    if not value:
        raise CinematicSimError(problem)


def _json(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, OverflowError) as exc:
        raise CinematicSimError("finite JSON-only cinematic data required") from exc


def _hash(value: Any) -> str:
    return sha256(_json(value)).hexdigest()


def _bounded_int(value: Any, low: int, high: int, name: str) -> int:
    _require(type(value) is int and low <= value <= high, "invalid " + name)
    return value


def _name(value: Any) -> str:
    _require(type(value) is str and ID.fullmatch(value) is not None,
             "invalid source-owned identity")
    return value


def _vec(value: Any, name: str) -> tuple[int, int, int]:
    _require(type(value) is list and len(value) == 3, "invalid " + name)
    return tuple(_bounded_int(v, -1000000, 1000000, name) for v in value)


def _list(value: Any, low: int, high: int, name: str) -> list[Any]:
    _require(type(value) is list and low <= len(value) <= high,
             "invalid bounded " + name)
    return value


def _unique(rows: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    out = {}
    for row in rows:
        _require(type(row) is dict and "id" in row, "invalid " + label)
        key = _name(row["id"])
        _require(key not in out, "duplicate " + label + " identity")
        out[key] = row
    return out


def validate_scene(scene: dict[str, Any]) -> dict[str, Any]:
    """Check scene, cinematic timeline, persistent identities and source rights."""
    _require(type(scene) is dict and set(scene) == {
        "schema_version", "source_project_id", "scene_id", "rights_reviewed",
        "actors", "items", "apparel", "dialogue", "shots"}, "scene schema changed")
    _require(scene["schema_version"] == SCHEMA and scene["rights_reviewed"] is True,
             "original scene requires explicitly reviewed source rights")
    _name(scene["source_project_id"])
    _name(scene["scene_id"])
    actors = _unique(_list(scene["actors"], 1, 32, "cast"), "actor")
    items = _unique(_list(scene["items"], 0, 64, "items"), "item")
    apparel = _unique(_list(scene["apparel"], 1, 64, "apparel"), "apparel")
    dialogue = _unique(_list(scene["dialogue"], 0, 256, "dialogue"), "line")
    for actor in actors.values():
        _require(set(actor) == {"id", "voice_id", "appearance_id", "strength_g",
                                "allowed_apparel"}, "actor schema changed")
        _name(actor["voice_id"])
        _name(actor["appearance_id"])
        _bounded_int(actor["strength_g"], 0, 100000, "actor carry capacity")
        _require(len(set(_list(actor["allowed_apparel"], 1, 16, "wardrobe"))) ==
                 len(actor["allowed_apparel"]), "duplicate authored wardrobe")
        for choice in actor["allowed_apparel"]:
            _require(choice in apparel, "unapproved wardrobe identity")
    for item in items.values():
        _require(set(item) == {"id", "mass_g"}, "item schema changed")
        _bounded_int(item["mass_g"], 0, 50000, "item mass")
    for outfit in apparel.values():
        _require(set(outfit) == {"id", "drag_pct", "mobility_pct"},
                 "apparel schema changed")
        _bounded_int(outfit["drag_pct"], 0, 95, "apparel aerodynamic drag")
        _bounded_int(outfit["mobility_pct"], 5, 100, "apparel mobility")
    for line in dialogue.values():
        _require(set(line) == {"id", "actor_id"}, "dialogue schema changed")
        _require(line["actor_id"] in actors, "line lacks approved actor")
    shots = _list(scene["shots"], 1, MAX_SHOTS, "shots")
    seen, spoken, previous, tick = set(), [], None, 0
    for shot in shots:
        _require(type(shot) is dict and set(shot) == {
            "id", "start_ms", "duration_ms", "camera", "axis", "transition",
            "actor_id", "voice_id", "dialogue_ids", "item_id", "apparel_id",
            "lighting_id"}, "shot schema changed")
        _name(shot["id"])
        _require(shot["id"] not in seen, "duplicate shot")
        seen.add(shot["id"])
        _require(_bounded_int(shot["start_ms"], 0, 120000, "start_ms") == tick,
                 "cutscene timeline has gap or overlap")
        duration = _bounded_int(shot["duration_ms"], 200, 30000, "shot duration")
        tick += duration
        _require(tick <= 120000, "cutscene exceeds 120 seconds")
        _require(shot["axis"] in AXES and shot["transition"] in TRANSITIONS,
                 "invalid camera screen axis or transition")
        cam = shot["camera"]
        _require(type(cam) is dict and set(cam) == {
            "mode", "from_mm", "to_mm", "look_from_mm", "look_to_mm",
            "fov_start_deg", "fov_end_deg"}, "camera schema changed")
        _require(cam["mode"] in CAMERAS, "unknown cinematic camera angle")
        for key in ("from_mm", "to_mm", "look_from_mm", "look_to_mm"):
            _vec(cam[key], key)
        for key in ("fov_start_deg", "fov_end_deg"):
            _bounded_int(cam[key], 15, 120, key)
        _require(shot["actor_id"] in actors, "actor absent from cast")
        _require(shot["voice_id"] == actors[shot["actor_id"]]["voice_id"],
                 "cutscene permanently changed actor voice")
        _require(shot["apparel_id"] in actors[shot["actor_id"]]["allowed_apparel"],
                 "cutscene outfit violates approved character identity")
        _require(shot["item_id"] == "" or shot["item_id"] in items, "unapproved prop")
        _name(shot["lighting_id"])
        lines = _list(shot["dialogue_ids"], 0, 32, "shot dialogue")
        for line in lines:
            _require(line in dialogue and dialogue[line]["actor_id"] == shot["actor_id"],
                     "dialogue line assigned to wrong actor or absent source")
            spoken.append(line)
        if previous and previous["axis"] != shot["axis"]:
            _require(previous["camera"]["mode"] == "establishing" and
                     not previous["dialogue_ids"] and
                     shot["transition"] in ("straight", "match_cut"),
                     "unmotivated 180-degree screen-axis reversal")
        previous = shot
    _require(spoken == list(dialogue), "dialogue must occur exactly once in authored order")
    return {"source_digest": _hash(scene), "total_ms": tick, "shot_count": len(shots),
            "dialogue_count": len(dialogue), "project": scene["source_project_id"],
            "reviewed_source_rights": True, "rendered_video_verified": False}


def variation_controls(*, offsets: tuple[int, ...] = (0,), pan_rates: tuple[int, ...] = (100,),
                       lens_offsets: tuple[int, ...] = (0,), item_mass_deltas: tuple[int, ...] = (0,),
                       apparel_drag_deltas: tuple[int, ...] = (0,), seeds: tuple[int, ...] = (0,),
                       item_variants: tuple[str, ...] = ("",),
                       apparel_variants: tuple[str, ...] = ("",),
                       limit: int = MAX_SIMULATIONS) -> tuple[dict[str, int], ...]:
    """Product-space variations with deterministic order and strict admission."""
    _bounded_int(limit, 1, MAX_SIMULATIONS, "simulation cap")
    ranges = ((offsets, -60, 60, "camera yaw offset"),
              (pan_rates, 40, 160, "pan rate pct"),
              (lens_offsets, -15, 15, "lens shift"),
              (item_mass_deltas, -1000, 1000, "item mass adjustment"),
              (apparel_drag_deltas, -30, 30, "apparel drag adjustment"),
              (seeds, 0, 2**31 - 1, "seed"))
    for values, lo, hi, name in ranges:
        _require(type(values) is tuple and 1 <= len(values) <= 12 and
                 len(set(values)) == len(values), "invalid " + name + " choices")
        for value in values:
            _bounded_int(value, lo, hi, name)
    for values, title in ((item_variants, "item"), (apparel_variants, "apparel")):
        _require(type(values) is tuple and 1 <= len(values) <= 16 and
                 len(set(values)) == len(values), "invalid " + title + " variant set")
        for identity in values:
            _require(identity == "" or (type(identity) is str and ID.fullmatch(identity)),
                     "invalid " + title + " variant identity")
    combos = product(*(entry[0] for entry in ranges), item_variants, apparel_variants)
    names = ("yaw_offset_deg", "pan_rate_pct", "fov_offset_deg",
             "item_mass_delta_g", "apparel_drag_delta_pct", "seed",
             "item_variant_id", "apparel_variant_id")
    out = []
    for values in combos:
        if len(out) >= limit:
            break
        out.append(dict(zip(names, values)))
    return tuple(out)


def _point(a: tuple[int, int, int], b: tuple[int, int, int], fraction: float):
    return tuple(round(x + (y - x) * fraction, 3) for x, y in zip(a, b))


def _direction(origin: tuple[float, ...], target: tuple[float, ...]):
    dx, dy, dz = (b - a for a, b in zip(origin, target))
    horizontal = hypot(dx, dy)
    distance = sqrt(dx*dx + dy*dy + dz*dz)
    return (degrees(atan2(dy, dx)), degrees(atan2(dz, horizontal)), distance)


def _angle_difference(a: float, b: float) -> float:
    return (b - a + 180.0) % 360.0 - 180.0


class SimulationController:
    """Real incremental deterministic shot simulation, pause/resume/seek and audit."""
    def __init__(self, scene: dict[str, Any], controls: dict[str, int], *, frame_ms: int = 100):
        self.validation = validate_scene(scene)
        _bounded_int(frame_ms, 25, 250, "frame interval")
        expected = set(variation_controls()[0])
        _require(type(controls) is dict and set(controls) == expected,
                 "unknown simulation controls")
        variation_controls(
            offsets=(controls["yaw_offset_deg"],), pan_rates=(controls["pan_rate_pct"],),
            lens_offsets=(controls["fov_offset_deg"],),
            item_mass_deltas=(controls["item_mass_delta_g"],),
            apparel_drag_deltas=(controls["apparel_drag_delta_pct"],),
            seeds=(controls["seed"],), item_variants=(controls["item_variant_id"],),
            apparel_variants=(controls["apparel_variant_id"],))
        items = {x["id"] for x in scene["items"]}
        wardrobes = {x["id"]: set(x["allowed_apparel"]) for x in scene["actors"]}
        if controls["item_variant_id"]:
            _require(controls["item_variant_id"] in items,
                     "item+sim refers to unknown authored item")
        if controls["apparel_variant_id"]:
            _require(all(controls["apparel_variant_id"] in wardrobes[shot["actor_id"]]
                         for shot in scene["shots"]),
                     "apparel+sim cannot override an actor with unapproved outfit")
        self.scene, self.controls, self.frame_ms = scene, controls, frame_ms
        self.times = tuple(range(0, self.validation["total_ms"], frame_ms)) + (
            self.validation["total_ms"],)
        _require(len(self.times) <= MAX_FRAMES_PER_SIM, "simulation requires too many frames")
        self.cursor = 0
        self.paused = False
        self.trace: list[dict[str, Any]] = []
        self.previous_digest = ZERO

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def seek(self, position: int) -> None:
        """Seek only within audited observation history; no fabricated future."""
        _bounded_int(position, 0, len(self.trace), "seek cursor")
        self.trace = self.trace[:position]
        self.cursor = position
        self.previous_digest = self.trace[-1]["digest"] if self.trace else ZERO

    def checkpoint(self) -> dict[str, Any]:
        """Checkpoint an in-flight simulator, never the serving LLM weights."""
        value = {
            "schema_version": "skeleton.jeeves.cinematic_cursor.v1",
            "source_digest": self.validation["source_digest"],
            "controls": dict(self.controls), "frame_ms": self.frame_ms,
            "cursor": self.cursor, "paused": self.paused,
            "tail_digest": self.previous_digest,
            "observations": list(self.trace),
            "serving_model_state_included": False,
        }
        value["checkpoint_sha256"] = _hash(value)
        return value

    @classmethod
    def from_checkpoint(cls, scene: dict[str, Any], checkpoint: dict[str, Any]):
        """Resume an intact trace without replaying already executed frames."""
        _require(type(checkpoint) is dict and set(checkpoint) == {
            "schema_version", "source_digest", "controls", "frame_ms",
            "cursor", "paused", "tail_digest", "observations",
            "serving_model_state_included", "checkpoint_sha256",
        }, "unknown simulation checkpoint format")
        signature = checkpoint["checkpoint_sha256"]
        body = {key: value for key, value in checkpoint.items() if key != "checkpoint_sha256"}
        _require(signature == _hash(body) and
                 checkpoint["schema_version"] == "skeleton.jeeves.cinematic_cursor.v1",
                 "simulation checkpoint integrity failed")
        _require(checkpoint["serving_model_state_included"] is False,
                 "simulation checkpoints must not carry live model state")
        controller = cls(scene, checkpoint["controls"], frame_ms=checkpoint["frame_ms"])
        _require(checkpoint["source_digest"] == controller.validation["source_digest"],
                 "simulator source changed since checkpoint")
        entries = checkpoint["observations"]
        position = _bounded_int(checkpoint["cursor"], 0, len(controller.times), "sim cursor")
        _require(type(entries) is list and len(entries) == position,
                 "simulation checkpoint contains an invalid cursor")
        prior = ZERO
        for index, entry in enumerate(entries):
            _require(type(entry) is dict and entry.get("frame") == index and
                     entry.get("tick_ms") == controller.times[index],
                     "simulation checkpoint has reordered observations")
            frame = {k: v for k, v in entry.items() if k not in ("digest", "previous_digest")}
            _require(entry.get("previous_digest") == prior and
                     entry.get("digest") == _hash({
                         "frame": frame, "previous_digest": prior,
                     }), "simulation checkpoint chain integrity failed")
            prior = entry["digest"]
        _require(prior == checkpoint["tail_digest"],
                 "simulation checkpoint tail does not match observation chain")
        _require(type(checkpoint["paused"]) is bool,
                 "checkpoint pause state invalid")
        controller.cursor = position
        controller.trace = entries[:]
        controller.previous_digest = prior
        controller.paused = checkpoint["paused"]
        return controller

    def _frame(self, index: int) -> dict[str, Any]:
        tick = self.times[index]
        shot = next((s for s in self.scene["shots"]
                    if tick < s["start_ms"] + s["duration_ms"]), self.scene["shots"][-1])
        progress = min(1.0, max(0.0, (tick - shot["start_ms"]) / shot["duration_ms"]))
        rate = self.controls["pan_rate_pct"] / 100
        smooth = min(1.0, max(0.0, progress * rate))
        eased = smooth*smooth*(3.0-2.0*smooth)
        cam = shot["camera"]
        origin = _point(_vec(cam["from_mm"], "from_mm"), _vec(cam["to_mm"], "to_mm"), eased)
        look = _point(_vec(cam["look_from_mm"], "look_from_mm"),
                      _vec(cam["look_to_mm"], "look_to_mm"), eased)
        yaw, pitch, distance = _direction(origin, look)
        yaw = round(((yaw + self.controls["yaw_offset_deg"] + 180) % 360) - 180, 4)
        pitch = round(pitch, 4)
        fov = round(cam["fov_start_deg"] +
                    (cam["fov_end_deg"] - cam["fov_start_deg"]) * eased +
                    self.controls["fov_offset_deg"], 4)
        item_id = (self.controls["item_variant_id"] or shot["item_id"]) if shot["item_id"] else ""
        outfit_id = self.controls["apparel_variant_id"] or shot["apparel_id"]
        item = next((x for x in self.scene["items"] if x["id"] == item_id), None)
        actor = next(x for x in self.scene["actors"] if x["id"] == shot["actor_id"])
        apparel = next(x for x in self.scene["apparel"] if x["id"] == outfit_id)
        mass = max(0, (item["mass_g"] if item else 0) + self.controls["item_mass_delta_g"]) if item else 0
        drag = max(0, min(100, apparel["drag_pct"] + self.controls["apparel_drag_delta_pct"]))
        mobility = round(apparel["mobility_pct"] * (100 - drag) / 100, 2)
        issues = []
        if distance < 300:
            issues.append("camera_occlusion_or_invalid_focus_distance")
        if not -85 <= pitch <= 85:
            issues.append("unreadable_camera_pitch")
        if not 15 <= fov <= 120:
            issues.append("invalid_focal_length")
        if mass > actor["strength_g"]:
            issues.append("item_exceeds_actor_capacity")
        if mobility < 20:
            issues.append("apparel_prevents_required_motion")
        return {"frame": index, "tick_ms": tick, "shot": shot["id"],
                "camera": cam["mode"], "yaw_deg": yaw, "pitch_deg": pitch,
                "fov_deg": fov, "camera_mm": origin, "focus_mm": look,
                "focus_distance_mm": round(distance, 2),
                "actor": actor["id"], "voice": actor["voice_id"],
                "item": item_id, "item_mass_g": mass,
                "apparel": outfit_id, "mobility_pct": mobility,
                "lighting": shot["lighting_id"], "dialogue": shot["dialogue_ids"],
                "issues": issues}

    def step(self) -> dict[str, Any] | None:
        if self.paused or self.cursor >= len(self.times):
            return None
        frame = self._frame(self.cursor)
        if self.trace and frame["shot"] == self.trace[-1]["shot"]:
            difference = abs(_angle_difference(self.trace[-1]["yaw_deg"], frame["yaw_deg"]))
            elapsed = max(1, frame["tick_ms"] - self.trace[-1]["tick_ms"])
            if difference * 1000 / elapsed > 180:
                frame["issues"].append("abrupt_camera_pan_rate")
        body = {"frame": frame, "previous_digest": self.previous_digest}
        entry = {**frame, "previous_digest": self.previous_digest, "digest": _hash(body)}
        self.trace.append(entry)
        self.previous_digest = entry["digest"]
        self.cursor += 1
        return entry

    def run(self) -> tuple[dict[str, Any], ...]:
        self.resume()
        while self.cursor < len(self.times):
            self.step()
        return tuple(self.trace)

    def reverse_audit(self) -> dict[str, Any]:
        """Audit the same collected trace backwards WITHOUT executing the sim again."""
        _require(self.cursor == len(self.times) and not self.paused,
                 "cannot audit incomplete or paused simulation")
        failures = []
        successor = None
        for index in range(len(self.trace)-1, -1, -1):
            entry = self.trace[index]
            fields = {k: v for k, v in entry.items() if k not in ("digest", "previous_digest")}
            recomputed = _hash({"frame": fields, "previous_digest": entry["previous_digest"]})
            if (entry["frame"] != index or entry["digest"] != recomputed or
                    (successor is not None and successor["previous_digest"] != entry["digest"]) or
                    (index == 0 and entry["previous_digest"] != ZERO)):
                failures.append(index)
            successor = entry
        return {"audit_direction": "reverse", "observations_inspected": len(self.trace),
                "first_failure_indices": failures[:16], "failures": len(failures),
                "no_simulation_restart": True, "independent_training_examples_added": 0,
                "passed": not failures}


def simulate_once(scene: dict[str, Any], controls: dict[str, int], *,
                  frame_ms: int = 100) -> dict[str, Any]:
    controller = SimulationController(scene, controls, frame_ms=frame_ms)
    trace = controller.run()
    reverse = controller.reverse_audit()
    issues = {}
    for entry in trace:
        for issue in entry["issues"]:
            issues[issue] = issues.get(issue, 0) + 1
    sampled = [dict(trace[i]) for i in sorted({0, len(trace)//4, len(trace)//2,
                                               3*len(trace)//4, len(trace)-1})]
    # Capture per-shot pan ranges, actor props, costume and failure rates.
    # Data is recorded for each executed frame; metrics do not invent video.
    metrics = []
    for shot in controller.scene["shots"]:
        rows = [e for e in trace if e["shot"] == shot["id"]]
        metrics.append({
            "shot_id": shot["id"], "camera_mode": shot["camera"]["mode"],
            "frames": len(rows),
            "yaw_range_deg": [min(x["yaw_deg"] for x in rows),
                              max(x["yaw_deg"] for x in rows)],
            "pitch_range_deg": [min(x["pitch_deg"] for x in rows),
                                max(x["pitch_deg"] for x in rows)],
            "fov_range_deg": [min(x["fov_deg"] for x in rows),
                              max(x["fov_deg"] for x in rows)],
            "minimum_focus_distance_mm": min(x["focus_distance_mm"] for x in rows),
            "item_variants_seen": sorted({x["item"] for x in rows}),
            "apparel_variants_seen": sorted({x["apparel"] for x in rows}),
            "issue_frames": sum(bool(x["issues"]) for x in rows),
            "first_observation_digest": rows[0]["digest"],
            "last_observation_digest": rows[-1]["digest"],
        })
    summary = {
        "schema_version": "skeleton.jeeves.cinematic_sim_receipt.v1",
        "source_digest": controller.validation["source_digest"],
        "controls": controls, "frames_executed": len(trace),
        "shot_count": controller.validation["shot_count"],
        "dialogue_count": controller.validation["dialogue_count"],
        "forward_head_digest": trace[-1]["digest"],
        "audit": {"forward": {"observations": len(trace),
                              "issues": issues, "source_verified": True},
                  "reverse": reverse},
        "sampled_observations": sampled,
        "per_shot_metrics": metrics,
        "camera_motion_observed": True, "cinematic_quality_established": False,
        "cloth_physics_rendered": False, "audio_generated": False,
        "video_rendered": False, "training_steps": 0,
        "independently_reviewed": False,
    }
    summary["receipt_sha256"] = _hash(summary)
    return summary


def run_batch(scene: dict[str, Any], *, variations: tuple[dict[str, int], ...],
              workers: int = 1, frame_ms: int = 100) -> dict[str, Any]:
    """Run bounded independent parameterized rehearsals in deterministic order."""
    validated = validate_scene(scene)
    _bounded_int(workers, 1, 8, "sim workers")
    _bounded_int(frame_ms, 25, 250, "frame_ms")
    _require(type(variations) is tuple and 1 <= len(variations) <= MAX_SIMULATIONS,
             "multi-simulation run outside budget")
    frames_per_sim = (validated["total_ms"] + frame_ms - 1) // frame_ms + 1
    _require(frames_per_sim * len(variations) <= MAX_BATCH_FRAMES,
             "multi-simulation aggregate frame budget exceeded")
    _require(len({_hash(v) for v in variations}) == len(variations),
             "duplicate control choices inflate evidence")
    if workers == 1:
        results = [simulate_once(scene, v, frame_ms=frame_ms) for v in variations]
    else:
        with ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn")) as pool:
            futures = [pool.submit(simulate_once, scene, v, frame_ms=frame_ms)
                       for v in variations]
            results = [f.result() for f in futures]
    _require(all(r["source_digest"] == validated["source_digest"] for r in results),
             "cross-project evidence splice")
    forward_count = sum(r["frames_executed"] for r in results)
    reverse_count = sum(r["audit"]["reverse"]["observations_inspected"] for r in results)
    _require(forward_count == reverse_count, "missing reverse audit coverage")
    audit_failures = sum(r["audit"]["reverse"]["failures"] for r in results)
    results_by_identity: dict[str, dict[str, Any]] = {}
    for row in results:
        key = _hash({"source": row["source_digest"], "controls": row["controls"],
                     "head": row["forward_head_digest"]})
        _require(key not in results_by_identity, "duplicate simulation receipt")
        results_by_identity[key] = row
    # A different seed with exactly the same deterministic trace is still NOT
    # novel data. Report unique traces separately from executed variants.
    distinct_traces = len({r["forward_head_digest"] for r in results})
    aggregate_issues: dict[str, int] = {}
    for row in results:
        for issue, count in row["audit"]["forward"]["issues"].items():
            aggregate_issues[issue] = aggregate_issues.get(issue, 0) + count
    report = {
        "schema_version": REPORT_SCHEMA, "project": validated["project"],
        "scene_source_sha256": validated["source_digest"],
        "simulations_executed": len(results), "parallel_processes_requested": workers,
        "forward_observations": forward_count, "reverse_observations": reverse_count,
        "audit_passes_on_same_data": 2, "independent_sgd_exposures": 0,
        "unique_trace_digests": distinct_traces,
        "duplicates_not_counted_as_new_training": len(results) - distinct_traces,
        "aggregate_issue_counts": aggregate_issues,
        "camera_modes_observed": sorted({
            shot["camera"]["mode"] for shot in scene["shots"]}),
        "item_variants_observed": sorted({
            shot["item"] for result in results for shot in result["sampled_observations"]}),
        "apparel_variants_observed": sorted({
            shot["apparel"] for result in results for shot in result["sampled_observations"]}),
        "reverse_audit_failures": audit_failures,
        "simulators": results, "source_rights_reviewed": True,
        "candidate_status": "quarantined_pending_independent_review",
        "production_weights_modified": False, "training_executed": False,
        "rendered_cutscenes": False,
    }
    report["receipt_sha256"] = _hash(report)
    return report


def verify_batch_report(report: dict[str, Any]) -> dict[str, Any]:
    """Adversarial structural/tamper audit of an immutable batch report."""
    _require(type(report) is dict and report.get("schema_version") == REPORT_SCHEMA,
             "unknown cinematic report")
    claimed = report.get("receipt_sha256")
    _require(claimed == _hash({k: v for k, v in report.items() if k != "receipt_sha256"}),
             "cinematic batch receipt hash mismatch")
    rows = report.get("simulators")
    _require(type(rows) is list and len(rows) == report["simulations_executed"],
             "simulator batch count changed")
    _require(report["reverse_observations"] == report["forward_observations"] ==
             sum(row["frames_executed"] for row in rows), "forward/reverse counts differ")
    _require(report["unique_trace_digests"] == len({
        row["forward_head_digest"] for row in rows}), "duplicate lineage accounting changed")
    _require(report["duplicates_not_counted_as_new_training"] ==
             len(rows) - report["unique_trace_digests"], "duplicate accounting changed")
    for row in rows:
        _require(row.get("receipt_sha256") == _hash({
            k: v for k, v in row.items() if k != "receipt_sha256"
        }), "tampered simulation receipt")
        _require(row["audit"]["reverse"]["passed"] is True and
                 row["audit"]["reverse"]["observations_inspected"] == row["frames_executed"],
                 "reverse data audit was not complete")
    _require(report["training_executed"] is False and
             report["production_weights_modified"] is False, "unverifiable training claim")
    return {"status": "verified_quarantined_simulation_evidence",
            "source_digest": report["scene_source_sha256"],
            "simulations": len(rows), "reverse_audit_verified": True,
            "model_training_executed": False}


def quarantine_review_pairs(report: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """Forward and reverse teaching prompts from each *unique* trace.

    The two perspectives share one evidence group. Neither is training data
    until independent source-rights and answer-quality adjudication.
    """
    verify_batch_report(report)
    seen = set()
    cases = []
    for row in report["simulators"]:
        head = row["forward_head_digest"]
        if head in seen:
            continue
        seen.add(head)
        group = _hash({"scene": row["source_digest"], "head": head})
        for perspective in ("forward_causality", "reverse_forensic_audit"):
            instruction = (
                "Explain whether the authored camera angle, pan-to motion, item "
                "and apparel choices satisfy shot continuity using the evidence."
                if perspective == "forward_causality" else
                "Trace the recorded cutscene outcomes backward to their source "
                "camera, wardrobe, dialogue and item constraints; identify faults."
            )
            cases.append({
                "schema_version": "skeleton.jeeves.cinematic_review_candidate.v1",
                "source_project_id": report["project"],
                "source_scene_digest": row["source_digest"],
                "paired_evidence_group": group,
                "candidate_id": _hash({"group": group, "perspective": perspective}),
                "perspective": perspective, "instruction": instruction,
                "evidence_digest": head, "controls": row["controls"],
                "quality_issues": row["audit"]["forward"]["issues"],
                "reverse_audit_failures": row["audit"]["reverse"]["failures"],
                "example_independence_group": group,
                "approval": "quarantined", "human_reviewed": False,
                "rights_independently_cleared": False,
                "eligible_for_optimizer": False,
                "training_steps_performed": 0,
            })
    _require(len(cases) == 2 * report["unique_trace_digests"],
             "reverse candidate count drift")
    return tuple(cases)


def _read_json(path: Path, max_bytes: int) -> dict[str, Any]:
    _require(not path.is_symlink() and path.is_file() and
             16 <= path.stat().st_size <= max_bytes, "regular bounded JSON input required")
    def pairs(entries):
        value = {}
        for k, v in entries:
            _require(k not in value, "duplicate JSON property")
            value[k] = v
        return value
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs,
                       parse_constant=lambda v: (_ for _ in ()).throw(
                           CinematicSimError("non-finite JSON")))
    _require(type(value) is dict, "JSON object required")
    return value


def _write_new_bytes(path: Path, payload: bytes):
    _require(not path.exists() and not path.is_symlink() and
             path.parent.is_dir() and not path.parent.is_symlink(),
             "output must be a new file in an existing directory")
    staged = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, mode="wb",
                                         prefix=".cinema-", delete=False) as handle:
            staged = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(staged, 0o600)
        os.link(staged, path)  # exclusive publication; never replace a file
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


def _write_new(path: Path, content: dict[str, Any]):
    _write_new_bytes(path, _json(content) + b"\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", type=Path)
    parser.add_argument("--audit-report", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--candidate-output", type=Path,
                        help="new quarantined two-direction training review JSONL")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--limit", type=int, default=64)
    parser.add_argument("--frame-ms", type=int, default=100)
    parser.add_argument("--yaw-offsets", type=int, nargs="+", default=[-30, 0, 30])
    parser.add_argument("--pan-rates", type=int, nargs="+", default=[75, 100, 125])
    parser.add_argument("--fov-offsets", type=int, nargs="+", default=[-10, 0, 10])
    parser.add_argument("--item-mass-deltas", type=int, nargs="+", default=[0, 250])
    parser.add_argument("--apparel-drag-deltas", type=int, nargs="+", default=[0, 15])
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1])
    parser.add_argument("--item-variants", nargs="+", default=[""])
    parser.add_argument("--apparel-variants", nargs="+", default=[""])
    args = parser.parse_args(argv)
    try:
        if args.audit_report is not None:
            _require(args.scene is None and args.output is None,
                     "reverse-only audit cannot start another simulation")
            source_report = _read_json(args.audit_report, 32 * 1024 * 1024)
            output = verify_batch_report(source_report)
            if args.candidate_output is not None:
                cases = quarantine_review_pairs(source_report)
                _write_new_bytes(args.candidate_output, b"".join(
                    _json(case) + b"\n" for case in cases))
                output["quarantined_review_cases"] = len(cases)
        else:
            _require(args.scene is not None, "operator scene source required")
            scene = _read_json(args.scene, 128 * 1024)
            variations = variation_controls(
                offsets=tuple(args.yaw_offsets), pan_rates=tuple(args.pan_rates),
                lens_offsets=tuple(args.fov_offsets),
                item_mass_deltas=tuple(args.item_mass_deltas),
                apparel_drag_deltas=tuple(args.apparel_drag_deltas),
                seeds=tuple(args.seeds), item_variants=tuple(args.item_variants),
                apparel_variants=tuple(args.apparel_variants), limit=args.limit)
            output = run_batch(scene, variations=variations, workers=args.workers,
                               frame_ms=args.frame_ms)
            if args.output is not None:
                _write_new(args.output, output)
            if args.candidate_output is not None:
                cases = quarantine_review_pairs(output)
                _write_new_bytes(args.candidate_output, b"".join(
                    _json(case) + b"\n" for case in cases))
                output["quarantined_review_cases"] = len(cases)
        print(json.dumps({key: value for key, value in output.items()
                          if key != "simulators"}, sort_keys=True))
        return 0
    except (CinematicSimError, ValueError, TypeError, OSError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:400],
                          "model_training_executed": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
