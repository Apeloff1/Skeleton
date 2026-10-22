"""Host-authorized Godot 4 import and runtime scene probe for compiled 3D assets.

This script is emitted by trusted Python from bounded compiler receipts, NOT
from local-model instructions. It runs against the exact assembled candidate
after a real editor import and measures imported MeshInstance3D geometry,
instantiated scene placements, source-authored transforms and collision shapes.
It cannot certify pixels, dynamics, collision contact, or visual quality.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from .studio_interaction_contract import digest

SCHEMA = "skeleton.jeeves.mesh_engine_probe.v1"
PREFIX = "JEEVES_MESH_PROBE "
MAX_LOG = 2_000_000
SCRIPT_PATH = "_jeeves_authored_asset_probe.gd"


class MeshEngineProbeError(ValueError):
    """Native 3D asset import/instantiation was not independently observed."""


def _bounded_claim(candidate: Mapping[str, Any]) -> dict[str, Any]:
    receipt = candidate.get("receipt") if isinstance(candidate, Mapping) else None
    if not isinstance(receipt, Mapping):
        raise MeshEngineProbeError("runtime mesh probe requires signed candidate")
    data = dict(receipt)
    seal = data.pop("receipt_sha256", None)
    if seal != digest(data):
        raise MeshEngineProbeError("native candidate receipt was modified")
    meshes = receipt.get("packaged_original_meshes")
    physics = receipt.get("packaged_original_mesh_physics")
    lods = receipt.get("packaged_original_mesh_lods")
    placements = receipt.get("packaged_original_mesh_placements")
    if (type(meshes) is not list or len(meshes) > 64
            or type(physics) is not list or len(physics) > 64
            or type(lods) is not list or len(lods) > 64
            or not isinstance(placements, Mapping)
            or type(placements.get("instances")) is not list
            or len(placements["instances"]) > 128):
        raise MeshEngineProbeError("native project asset inventory unbounded")
    names: set[str] = set()
    expected_meshes: list[str] = []
    for entry in meshes:
        name = entry.get("asset_id") if isinstance(entry, Mapping) else None
        if (type(name) is not str or not 1 <= len(name) <= 64
                or not name[0].islower()
                or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-"
                       for c in name)
                or name in names):
            raise MeshEngineProbeError("invalid or duplicate original 3D model")
        names.add(name)
        expected_meshes.append(name)
    physics_names = set()
    expected_bodies = []
    for entry in physics:
        name = entry.get("asset_id") if isinstance(entry, Mapping) else None
        if type(name) is not str or name not in names or name in physics_names:
            raise MeshEngineProbeError("physics asset lacks unique imported model")
        physics_names.add(name)
        expected_bodies.append(name)
    lod_names = set()
    expected_lod_paths: list[str] = []
    for item in lods:
        name = item.get("asset_id") if isinstance(item, Mapping) else None
        if type(name) is not str or name not in names or name in lod_names:
            raise MeshEngineProbeError("native LOD asset lacks original imported GLB")
        lod_names.add(name)
        levels = item.get("levels")
        if type(levels) is not int or not 1 <= levels <= 4:
            raise MeshEngineProbeError("native LOD manifest has no finite levels")
        for index in range(1, levels + 1):
            expected_lod_paths.append(
                "game/frontier/meshes/" + name + ".lod" + str(index) + ".glb"
            )
    expected_placements = []
    instance_names = set()
    for entry in placements["instances"]:
        if not isinstance(entry, Mapping):
            raise MeshEngineProbeError("native scene placement is malformed")
        asset, ident = entry.get("asset_id"), entry.get("instance_id")
        category = entry.get("visual_or_physics")
        if (type(asset) is not str or asset not in names
                or type(ident) is not str or ident in instance_names
                or not ident or len(ident) > 64
                or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-"
                       for c in ident)
                or category not in ("visual", "lod", "physics")
                or (category == "physics" and asset not in physics_names)
                or (category == "lod" and asset not in lod_names)):
            raise MeshEngineProbeError("game placement targets unapproved 3D resource")
        instance_names.add(ident)
        expected_placements.append({
            "instance_id": ident,
            "asset_id": asset,
            "kind": category,
            "position_mm": entry.get("position_mm"),
            "scale_per_mille": entry.get("scale_per_mille"),
        })
    return {
        "candidate_sha256": seal,
        "mesh_ids": sorted(expected_meshes),
        "physics_ids": sorted(expected_bodies),
        "lod_ids": sorted(lod_names),
        "lod_paths": sorted(expected_lod_paths),
        "instances": sorted(expected_placements, key=lambda x: x["instance_id"]),
    }


def compile_native_mesh_probe(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Build a self-contained trusted Godot SceneTree source + expected results."""
    expected = _bounded_claim(candidate)
    if not expected["mesh_ids"]:
        raise MeshEngineProbeError("a 3D probe must have real mesh outputs")
    # JSON is quoted twice so no source-controlled model text is injected
    # into GDScript, even for future extension of expected receipt fields.
    expected_text = json.dumps(expected, sort_keys=True, separators=(",", ":"))
    literal = json.dumps(expected_text, ensure_ascii=True)
    script = "\n".join([
        "extends SceneTree",
        "",
        "const EXPECTED_SOURCE: String = " + literal,
        "",
        "func _initialize() -> void:",
        '    call_deferred("_probe")',
        "",
        "func _fail(reason: String) -> void:",
        '    printerr("JEEVES_MESH_PROBE_FAILURE " + reason)',
        "    quit(1)",
        "",
        "func _probe() -> void:",
        "    var expected = JSON.parse_string(EXPECTED_SOURCE)",
        "    if not (expected is Dictionary):",
        '        _fail("source contract")',
        "        return",
        "    var imported: Array[String] = []",
        "    for mesh_id in expected[\"mesh_ids\"]:",
        '        var resource_path = "res://game/frontier/meshes/" + str(mesh_id) + ".glb"',
        "        var model = load(resource_path)",
        "        if not (model is PackedScene):",
        '            _fail("GLB importer refused " + str(mesh_id))',
        "            return",
        "        var node = model.instantiate()",
        "        if not (node is Node3D):",
        '            _fail("GLB has no 3D root " + str(mesh_id))',
        "            return",
        "        get_root().add_child(node)",
        "        var surfaces := 0",
        '        for visual in node.find_children("*", "MeshInstance3D", true, false):',
        "            if visual.mesh == null:",
        '                _fail("GLB mesh instance has no mesh")',
        "                return",
        "            surfaces += visual.mesh.get_surface_count()",
        "        node.queue_free()",
        "        if surfaces < 1:",
        '            _fail("GLB has no imported geometry " + str(mesh_id))',
        "            return",
        "        imported.append(str(mesh_id))",
        "    var imported_lods: Array[String] = []",
        "    for lod_path in expected[\"lod_paths\"]:",
        '        var lod_scene = load("res://" + str(lod_path))',
        "        if not (lod_scene is PackedScene):",
        '            _fail("authored LOD GLB importer refused " + str(lod_path))',
        "            return",
        "        var lod_node = lod_scene.instantiate()",
        "        if not (lod_node is Node3D):",
        '            _fail("authored LOD has no 3D root")',
        "            return",
        "        get_root().add_child(lod_node)",
        "        var lod_surfaces := 0",
        '        for visual in lod_node.find_children("*", "MeshInstance3D", true, false):',
        "            if visual.mesh != null:",
        "                lod_surfaces += visual.mesh.get_surface_count()",
        "        lod_node.queue_free()",
        "        if lod_surfaces < 1:",
        '            _fail("authored LOD contains no imported mesh surfaces")',
        "            return",
        "        imported_lods.append(str(lod_path))",
        "    var inspected_bodies: Array[String] = []",
        "    for mesh_id in expected[\"physics_ids\"]:",
        '        var resource_path = "res://game/frontier/meshes/" + str(mesh_id) + ".physics.tscn"',
        "        var authored_body = load(resource_path)",
        "        if not (authored_body is PackedScene):",
        '            _fail("collision PackedScene missing")',
        "            return",
        "        var body = authored_body.instantiate()",
        "        if not (body is PhysicsBody3D or body is Area3D):",
        '            _fail("authored physics is not a Godot physics node")',
        "            return",
        "        get_root().add_child(body)",
        '        var collider = body.get_node_or_null("CollisionShape")',
        "        if not (collider is CollisionShape3D) or collider.shape == null:",
        '            _fail("authored body has no active CollisionShape3D")',
        "            return",
        "        inspected_bodies.append(str(mesh_id))",
        "        body.queue_free()",
        "    var placed: Array[String] = []",
        "    if expected[\"instances\"].size() > 0:",
        '        var root_scene = load("res://game/frontier/expedition.tscn")',
        "        if not (root_scene is PackedScene):",
        '            _fail("playable game scene lacks original meshes")',
        "            return",
        "        var world = root_scene.instantiate()",
        "        if not (world is Node3D):",
        '            _fail("playable game root is not Node3D")',
        "            return",
        "        get_root().add_child(world)",
        "        for entry in expected[\"instances\"]:",
        '            var instance_path = "OriginalMeshInstances/" + str(entry["instance_id"])',
        "            var instance = world.get_node_or_null(instance_path)",
        "            if not (instance is Node3D):",
        '                _fail("source-authored game instance omitted " + instance_path)',
        "                return",
        '            var desired_position = entry["position_mm"]',
        "            var expected_position = Vector3(",
        "                float(desired_position[0]) / 1000.0,",
        "                float(desired_position[1]) / 1000.0,",
        "                float(desired_position[2]) / 1000.0",
        "            )",
        "            if instance.position.distance_to(expected_position) > 0.002:",
        '                _fail("source-authored game transform diverges")',
        "                return",
        '            var desired_scale = float(entry["scale_per_mille"]) / 1000.0',
        "            if instance.scale.distance_to(Vector3.ONE * desired_scale) > 0.002:",
        '                _fail("source-authored game scale diverges")',
        "                return",
        '            if entry["kind"] == "physics":',
        "                if not (instance is PhysicsBody3D or instance is Area3D):",
        '                    _fail("placed physical mesh lacks active body")',
        "                    return",
        '                var collider = instance.get_node_or_null("CollisionShape")',
        "                if not (collider is CollisionShape3D) or collider.shape == null:",
        '                    _fail("placed body has no collision shape")',
        "                    return",
        "            placed.append(str(entry[\"instance_id\"]))",
        "        world.queue_free()",
        "    var observed = {",
        '        "candidate_sha256": expected["candidate_sha256"],',
        '        "mesh_ids": imported,',
        '        "physics_ids": inspected_bodies,',
        '        "lod_paths": imported_lods,',
        '        "instance_ids": placed,',
        '        "imported_mesh_count": imported.size(),',
        '        "imported_lod_mesh_count": imported_lods.size(),',
        '        "active_physics_bodies": inspected_bodies.size(),',
        '        "game_instances": placed.size(),',
        "    }",
        '    print("' + PREFIX + '" + JSON.stringify(observed))',
        "    quit(0)",
        "",
    ])
    result = {
        "schema_version": SCHEMA,
        "source_candidate_receipt_sha256": expected["candidate_sha256"],
        "probe_script_sha256": sha256(script.encode("utf-8")).hexdigest(),
        "expected": expected,
        "script": script,
        "native_engine_executed": False,
    }
    return result


def verify_native_mesh_probe_output(
    compiled: Mapping[str, Any], output: str, *, executable_sha256: str,
    import_log_sha256: str,
) -> dict[str, Any]:
    """No result based solely on exit code, claimed hashes or missing log lines."""
    if (not isinstance(compiled, Mapping)
            or type(output) is not str or len(output) > MAX_LOG
            or type(import_log_sha256) is not str
            or len(import_log_sha256) != 64):
        raise MeshEngineProbeError("native probe output or import log is unavailable")
    expected = compiled.get("expected")
    if not isinstance(expected, Mapping):
        raise MeshEngineProbeError("native expected source was lost")
    results = [
        line[len(PREFIX):]
        for line in output.splitlines() if line.startswith(PREFIX)
    ]
    if len(results) != 1 or len(results[0]) > 65536:
        raise MeshEngineProbeError("Godot did not produce a unique 3D asset observation")
    try:
        observed = json.loads(results[0])
    except (ValueError, UnicodeDecodeError) as exc:
        raise MeshEngineProbeError("Godot probe returned malformed evidence") from exc
    if not isinstance(observed, dict) or set(observed) != {
        "candidate_sha256", "mesh_ids", "physics_ids", "lod_paths",
        "instance_ids", "imported_mesh_count", "imported_lod_mesh_count",
        "active_physics_bodies", "game_instances",
    }:
        raise MeshEngineProbeError("runtime probe returned incomplete measurements")
    tests = (
        ("mesh_ids", expected["mesh_ids"]),
        ("physics_ids", expected["physics_ids"]),
        ("lod_paths", expected["lod_paths"]),
        ("instance_ids", [i["instance_id"] for i in expected["instances"]]),
    )
    for field, required in tests:
        if observed[field] != required:
            raise MeshEngineProbeError("native observed " + field + " differs from source")
    for count_field, labels in (
        ("imported_mesh_count", "mesh_ids"),
        ("imported_lod_mesh_count", "lod_paths"),
        ("active_physics_bodies", "physics_ids"),
        ("game_instances", "instance_ids"),
    ):
        if (type(observed[count_field]) is not int
                or observed[count_field] != len(observed[labels])):
            raise MeshEngineProbeError("claimed native asset counts are inconsistent")
    proof = {
        "schema_version": "skeleton.jeeves.mesh_engine_observation.v1",
        "candidate_receipt_sha256": expected["candidate_sha256"],
        "probe_script_sha256": compiled["probe_script_sha256"],
        "native_executable_sha256": executable_sha256,
        "editor_import_log_sha256": import_log_sha256,
        "probe_stdout_sha256": sha256(output.encode("utf-8")).hexdigest(),
        "imported_geometry_mesh_count": observed["imported_mesh_count"],
        "imported_lod_geometry_count": observed["imported_lod_mesh_count"],
        "instanced_3d_physics_bodies": observed["active_physics_bodies"],
        "source_game_scene_instances": observed["game_instances"],
        "source_meshes_imported_in_godot": True,
        "native_scene_instances_examined": True,
        "native_collision_shapes_present": (
            observed["active_physics_bodies"] > 0
        ),
        "native_physics_contacts_observed": False,
        "native_rendered_pixels_observed": False,
    }
    proof["receipt_sha256"] = digest(proof)
    return proof


def run_host_mesh_probe(
    root: Path, godot_binary: Path, candidate: Mapping[str, Any], *,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Run actual Godot editor import then an independent 3D scene-tree probe.

    Requires the caller already verified the binary and wrote precisely the
    candidate project files into an isolated directory. No model-supplied
    Python code, command line switches, paths or scripts are executed.
    """
    compiled = compile_native_mesh_probe(candidate)
    if (root / SCRIPT_PATH).exists():
        raise MeshEngineProbeError("native input attempted to shadow trusted probe")
    script_path = root / SCRIPT_PATH
    script_path.write_text(compiled["script"], encoding="utf-8")
    import_log: bytes
    try:
        result = subprocess.run(
            [str(godot_binary), "--headless", "--path", str(root), "--import"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=timeout_seconds, check=False,
        )
        import_log = result.stdout
        if result.returncode or len(import_log) > MAX_LOG:
            raise MeshEngineProbeError("Godot 4 editor could not import authored GLBs")
        checked = subprocess.run(
            [str(godot_binary), "--headless", "--path", str(root),
             "--script", "res://" + SCRIPT_PATH],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=timeout_seconds, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MeshEngineProbeError(
            "host Godot 4 executable did not complete its 3D asset verification"
        ) from exc
    if checked.returncode != 0 or len(checked.stdout) > MAX_LOG:
        raise MeshEngineProbeError("Godot mesh probe failed engine scene validation")
    # Hash the installed executable without loading a potentially large
    # release/editor binary into the process address space.
    native_hash = sha256()
    with godot_binary.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            native_hash.update(block)
    return verify_native_mesh_probe_output(
        compiled, checked.stdout.decode("utf-8", "replace"),
        executable_sha256=native_hash.hexdigest(),
        import_log_sha256=sha256(import_log).hexdigest(),
    )


__all__ = [
    "MeshEngineProbeError", "compile_native_mesh_probe",
    "verify_native_mesh_probe_output", "run_host_mesh_probe",
]
