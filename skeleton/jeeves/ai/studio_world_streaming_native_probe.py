"""Trusted Godot 4 camera-transition observations for source-owned streaming.

The probe operates on the exact hash-checked game, never on a regenerated
baseline, and separates observed scene node lifecycle from unobserved GPU
memory, visual quality, or collision contact. Scripts are host-generated and
cannot be substituted by a user-authored .gd file.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any

from .studio_interaction_contract import digest
from .studio_world_chunks import compile_world_chunk_catalog
from .studio_world_streaming_activation import (
    WorldStreamingActivationError, verify_streaming_policy_archive,
)

SCHEMA = "skeleton.jeeves.world_streaming_native_probe.v1"
SCRIPT_PATH = "_jeeves_world_stream_probe.gd"
PREFIX = "JEEVES_WORLD_STREAM_OBSERVED "
MAX_LOG_BYTES = 2_000_000
MAX_SOURCE_BYTES = 256_000


class NativeWorldStreamError(ValueError):
    """A real native camera-driven streaming lifecycle was not observed."""


def _source(candidate: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(candidate, Mapping):
        raise NativeWorldStreamError("streaming probe needs an actual Godot candidate")
    receipt = candidate.get("receipt")
    files, binaries = candidate.get("files"), candidate.get("binary_assets")
    if (not isinstance(receipt, Mapping) or not isinstance(files, Mapping)
            or not isinstance(binaries, Mapping)):
        raise NativeWorldStreamError("native streaming requires real source files")
    unsealed = dict(receipt)
    proof = unsealed.pop("receipt_sha256", None)
    if proof != digest(unsealed):
        raise NativeWorldStreamError("original game manifest signature is invalid")
    policy = receipt.get("world_streaming_policy")
    if (not isinstance(policy, Mapping) or policy.get("enabled") is not True
            or policy.get("mode") != "replace_static"
            or policy.get("godot_streaming_observed") is not False):
        raise NativeWorldStreamError("native candidate has no approved live streaming")
    scene = files.get("game/frontier/expedition.tscn")
    raw_world = binaries.get("game/frontier/assets/world-index.json")
    raw_chunks = binaries.get("game/frontier/assets/world-chunks.json")
    raw_policy = binaries.get("game/frontier/assets/world_streaming.source.json")
    if (type(scene) is not str or type(raw_world) is not bytes
            or type(raw_chunks) is not bytes or type(raw_policy) is not bytes
            or len(raw_world) > MAX_SOURCE_BYTES
            or len(raw_chunks) > MAX_SOURCE_BYTES):
        raise NativeWorldStreamError("streaming source files omitted or oversized")
    hashes = receipt.get("godot_file_hashes")
    if (not isinstance(hashes, Mapping)
            or any(sha256(content).hexdigest() != hashes.get(path)
                   for path, content in (
                       ("game/frontier/expedition.tscn", scene.encode("utf-8")),
                       ("game/frontier/assets/world-index.json", raw_world),
                       ("game/frontier/assets/world-chunks.json", raw_chunks),
                       ("game/frontier/assets/world_streaming.source.json", raw_policy),
                   ))):
        raise NativeWorldStreamError("actual authored streaming bytes do not match receipt")
    try:
        world = json.loads(raw_world)
        chunks = json.loads(raw_chunks)
        canonical = lambda x: json.dumps(
            x, sort_keys=True, ensure_ascii=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if (canonical(world) != raw_world or canonical(chunks) != raw_chunks
                or type(world) is not dict or type(chunks) is not dict):
            raise NativeWorldStreamError("world catalogs are not canonical")
        if (digest({k: v for k, v in world.items()
                    if k != "receipt_sha256"}) != world.get("receipt_sha256")
                or compile_world_chunk_catalog(world) != chunks):
            raise NativeWorldStreamError("world and chunk catalogs disagree")
        if (sha256(raw_world).hexdigest() != receipt.get("world_spatial_index_sha256")
                or sha256(raw_chunks).hexdigest() != receipt.get("world_chunk_catalog_sha256")
                or policy.get("placement_source_receipt_sha256")
                != receipt["packaged_original_mesh_placements"]["receipt_sha256"]):
            raise NativeWorldStreamError("original chunk/world receipt ancestry changed")
        verified = verify_streaming_policy_archive(
            raw_policy, policy, receipt["packaged_original_mesh_placements"], scene,
        )
        if not verified.get("enabled"):
            raise NativeWorldStreamError("actual game root is not streaming enabled")
    except (WorldStreamingActivationError, KeyError, ValueError,
            TypeError, UnicodeDecodeError) as exc:
        raise NativeWorldStreamError("streaming source cannot independently replay") from exc
    instances = world.get("instances")
    if (type(instances) is not list or not 1 <= len(instances) <= 128):
        raise NativeWorldStreamError("active streaming requires bounded placed assets")
    pinned = sorted(
        item["instance_id"] for item in instances
        if item.get("kind") == "physics"
        and item.get("physics_body_type") in ("rigid", "area")
    )
    temporary = sorted(
        (item for item in instances if item["instance_id"] not in pinned),
        key=lambda item: item["instance_id"],
    )
    if not temporary:
        raise NativeWorldStreamError(
            "native unload certification needs a non-stateful original mesh instance"
        )
    target = temporary[0]
    expected = {
        "schema_version": SCHEMA,
        "candidate_receipt_sha256": proof,
        "world_receipt_sha256": world["receipt_sha256"],
        "chunk_receipt_sha256": chunks["receipt_sha256"],
        "activation_receipt_sha256": policy["receipt_sha256"],
        "source_instance_ids": sorted(item["instance_id"] for item in instances),
        "pinned_instance_ids": pinned,
        "target_id": target["instance_id"],
        "near_position_mm": target["position_mm"],
        "far_position_mm": [1_000_000_000, 1_000_000_000, 1_000_000_000],
        "max_steps": len(instances) + 4,
    }
    return expected


_GODOT_PROBE = r'''extends SceneTree
const EXPECTED_JSON: String = @@EXPECTED@@

func _initialize() -> void:
    call_deferred("_probe")

func _fail(reason: String) -> void:
    printerr("JEEVES_WORLD_STREAM_FAILURE " + reason)
    quit(1)

func _sorted_ids(instance_map: Dictionary) -> Array:
    var keys := instance_map.keys()
    keys.sort()
    return keys

func _probe() -> void:
    var expected = JSON.parse_string(EXPECTED_JSON)
    if not (expected is Dictionary):
        _fail("source contract")
        return
    var scene = load("res://game/frontier/expedition.tscn")
    if not (scene is PackedScene):
        _fail("missing actual playable Godot scene")
        return
    var world = scene.instantiate()
    if not (world is Node3D):
        _fail("actual game is not a Godot 3D root")
        return
    get_root().add_child(world)
    var streamer = world.get_node_or_null("OriginalMeshInstances")
    if streamer == null or not (streamer is Node3D):
        _fail("actual game lacks streamed mesh node")
        return
    if not streamer.has_method("_process"):
        _fail("streamer has no live frame implementation")
        return
    streamer.set_process(false)
    var camera := Camera3D.new()
    camera.name = "JeevesIndependentStreamingProbeCamera"
    world.add_child(camera)
    camera.current = true
    await process_frame
    var xyz: Array = expected["near_position_mm"]
    camera.global_position = Vector3(
        float(xyz[0]) / 1000.0, float(xyz[1]) / 1000.0,
        float(xyz[2]) / 1000.0
    )
    for step in range(int(expected["max_steps"])):
        streamer.call("_process", 0.016)
    var near = streamer.get("_loaded")
    if not (near is Dictionary):
        _fail("actual streamer has no instance state")
        return
    var near_ids: Array = _sorted_ids(near)
    if not near.has(expected["target_id"]):
        _fail("near camera did not instantiate reviewed scenery")
        return
    for ident in expected["pinned_instance_ids"]:
        if not near.has(ident):
            _fail("pinned physics body was never instantiated")
            return
    for ident in near_ids:
        if not expected["source_instance_ids"].has(ident):
            _fail("streamer generated a foreign instance")
            return
        var node = near[ident]
        if not (node is Node3D) or node.get_parent() != streamer:
            _fail("spawned node is not an attached scene instance")
            return
    var far_xyz: Array = expected["far_position_mm"]
    camera.global_position = Vector3(
        float(far_xyz[0]) / 1000.0, float(far_xyz[1]) / 1000.0,
        float(far_xyz[2]) / 1000.0
    )
    for step in range(int(expected["max_steps"])):
        streamer.call("_process", 0.016)
    var far = streamer.get("_loaded")
    if not (far is Dictionary):
        _fail("streamer lost its loaded map")
        return
    var far_ids: Array = _sorted_ids(far)
    if far.has(expected["target_id"]):
        _fail("offscreen static mesh was not unloaded")
        return
    for ident in expected["pinned_instance_ids"]:
        if not far.has(ident) or far[ident] != near[ident]:
            _fail("stateful body was evicted or rebuilt")
            return
    if far_ids != expected["pinned_instance_ids"]:
        _fail("distant source scene retained unintended objects")
        return
    var result = {
        "candidate_receipt_sha256": expected["candidate_receipt_sha256"],
        "world_receipt_sha256": expected["world_receipt_sha256"],
        "chunk_receipt_sha256": expected["chunk_receipt_sha256"],
        "activation_receipt_sha256": expected["activation_receipt_sha256"],
        "near_instance_ids": near_ids,
        "far_instance_ids": far_ids,
        "target_id": expected["target_id"],
        "target_spawned": true,
        "target_unloaded": true,
        "stateful_instances_retained": true
    }
    print("JEEVES_WORLD_STREAM_OBSERVED " + JSON.stringify(result))
    world.queue_free()
    quit(0)
'''


def compile_native_world_stream_probe(candidate: Mapping[str, Any]) -> dict[str, Any]:
    expected = _source(candidate)
    encoded = json.dumps(
        json.dumps(expected, sort_keys=True, ensure_ascii=True,
                   separators=(",", ":")),
        ensure_ascii=True,
    )
    script = _GODOT_PROBE.replace("@@EXPECTED@@", encoded)
    return {
        "schema_version": SCHEMA,
        "expected": expected,
        "script": script,
        "script_sha256": sha256(script.encode("utf-8")).hexdigest(),
        "native_executed": False,
    }


def verify_native_world_stream_output(
    compiled: Mapping[str, Any], output: str,
    *, executable_sha256: str,
) -> dict[str, Any]:
    if (not isinstance(compiled, Mapping) or type(output) is not str
            or len(output.encode("utf-8")) > MAX_LOG_BYTES
            or any(tag in output for tag in (
                "SCRIPT ERROR:", "Parse Error:", "ERROR:", "Failed loading resource",
                "JEEVES_WORLD_STREAM_FAILURE",
            ))):
        raise NativeWorldStreamError("Godot streaming failed or emitted engine errors")
    lines = [
        line[len(PREFIX):] for line in output.splitlines()
        if line.startswith(PREFIX)
    ]
    if len(lines) != 1 or len(lines[0]) > 65536:
        raise NativeWorldStreamError("no unique real native streaming observation")
    try:
        actual = json.loads(lines[0])
    except (ValueError, TypeError) as exc:
        raise NativeWorldStreamError("native streaming observation is not JSON") from exc
    expected = compiled.get("expected")
    required = {
        "candidate_receipt_sha256", "world_receipt_sha256",
        "chunk_receipt_sha256", "activation_receipt_sha256",
        "near_instance_ids", "far_instance_ids", "target_id",
        "target_spawned", "target_unloaded", "stateful_instances_retained",
    }
    if not isinstance(expected, Mapping) or type(actual) is not dict or set(actual) != required:
        raise NativeWorldStreamError("native streaming receipt missing observations")
    for field in (
        "candidate_receipt_sha256", "world_receipt_sha256",
        "chunk_receipt_sha256", "activation_receipt_sha256", "target_id",
    ):
        if actual[field] != expected[field]:
            raise NativeWorldStreamError("streaming runtime source identity mismatch")
    near, far = actual["near_instance_ids"], actual["far_instance_ids"]
    if (type(near) is not list or type(far) is not list
            or len(set(near)) != len(near) or len(set(far)) != len(far)
            or any(type(v) is not str for v in near + far)
            or not set(near) <= set(expected["source_instance_ids"])
            or far != expected["pinned_instance_ids"]
            or expected["target_id"] not in near
            or expected["target_id"] in far
            or not all(actual[key] is True for key in (
                "target_spawned", "target_unloaded", "stateful_instances_retained",
            ))):
        raise NativeWorldStreamError("camera-driven scene lifecycle contradicts source")
    receipt = {
        "schema_version": "skeleton.jeeves.world_streaming_native_observation.v1",
        "candidate_receipt_sha256": expected["candidate_receipt_sha256"],
        "source_world_receipt_sha256": expected["world_receipt_sha256"],
        "source_chunk_receipt_sha256": expected["chunk_receipt_sha256"],
        "source_activation_receipt_sha256": expected["activation_receipt_sha256"],
        "probe_script_sha256": compiled["script_sha256"],
        "godot_executable_sha256": executable_sha256,
        "native_log_sha256": sha256(output.encode("utf-8")).hexdigest(),
        "near_instantiated_count": len(near),
        "far_instantiated_count": len(far),
        "pinned_physics_instances_retained": len(far),
        "observed_camera_driven_instantiation": True,
        "observed_camera_driven_unloading": True,
        "observed_physics_instance_identity_retention": True,
        "observed_collision_contacts": False,
        "observed_gpu_residency": False,
        "observed_rendered_pixels": False,
    }
    receipt["receipt_sha256"] = digest(receipt)
    return receipt


def run_host_world_stream_probe(
    root: Path, binary: Path, candidate: Mapping[str, Any],
    *, timeout_seconds: int, executable_sha256: str,
) -> dict[str, Any]:
    compiled = compile_native_world_stream_probe(candidate)
    path = root / SCRIPT_PATH
    if path.exists():
        raise NativeWorldStreamError("project attempted to shadow trusted Godot probe")
    path.write_text(compiled["script"], encoding="utf-8")
    try:
        with tempfile.TemporaryFile() as log:
            run = subprocess.run(
                [str(binary), "--headless", "--path", str(root),
                 "--script", "res://" + SCRIPT_PATH],
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                timeout=timeout_seconds, check=False,
            )
            if run.returncode or log.tell() > MAX_LOG_BYTES:
                raise NativeWorldStreamError("Godot did not complete camera transition")
            log.seek(0)
            output = log.read().decode("utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise NativeWorldStreamError("host Godot process unavailable for streaming") from exc
    return verify_native_world_stream_output(
        compiled, output, executable_sha256=executable_sha256,
    )


__all__ = [
    "NativeWorldStreamError", "compile_native_world_stream_probe",
    "verify_native_world_stream_output", "run_host_world_stream_probe",
]
