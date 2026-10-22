"""Real Godot 4 replay for the EXACT original sprite-bound Expedition ZIP candidate.

Unlike the baseline native runner, this loads the actual complete candidate
including the authored AnimatedSprite3D player binding and every original PNG,
TRES and TSCN asset. It compares its output to the same Python Expedition
simulation, checks the original source hash and verifies that Godot really
completed the requested route. A native gameplay receipt is NEVER a pixel/
screen recording or proof of visual quality; rendering remains unobserved.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any

from skeleton.jeeves.game_frontier_expedition import ExpeditionError, ExpeditionWorld, Traveler
from skeleton.jeeves.game_frontier_expedition_godot import make_expedition_autoplay
from skeleton.jeeves.game_frontier_expedition_native_verify import (
    NativeExpeditionError, inspect_native_expedition_trace,
)
from .studio_interaction_contract import digest

MAX_LOG_BYTES = 4_000_000
PREFIX = "EXPEDITION_COMPLETE "


class SpriteBoundNativeError(ValueError):
    """A real native source-bound sprite playthrough was not observed."""


def _sha(path: Path) -> str:
    h = sha256()
    with path.open("rb") as reader:
        for chunk in iter(lambda: reader.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_exact_original_candidate_native_expedition(
    candidate: Mapping[str, Any], world: ExpeditionWorld, player: Traveler,
    *, godot_executable: str, timeout_seconds: int = 90,
    require_sprite: bool = False,
) -> dict[str, Any]:
    """Run exact hashed Godot project, including authored meshes and 3D physics."""
    if not isinstance(world, ExpeditionWorld) or not isinstance(player, Traveler):
        raise SpriteBoundNativeError("original typed world/player required")
    if (type(godot_executable) is not str or not godot_executable
            or type(timeout_seconds) is not int
            or not 1 <= timeout_seconds <= 300):
        raise SpriteBoundNativeError("host must select bounded native Godot 4 execution")
    binary = Path(godot_executable)
    if (not binary.is_absolute() or binary.is_symlink() or not binary.is_file()):
        raise SpriteBoundNativeError("host-approved Godot binary is missing")
    files = candidate.get("files")
    binaries = candidate.get("binary_assets")
    proof = candidate.get("receipt")
    has_sprite = (
        proof.get("animated_sprite3d_player_script_compiled") is True
        or bool(proof.get("animated_npc_sprite3d_source_compiled"))
    ) if isinstance(proof, Mapping) else False
    meshes = proof.get("packaged_original_meshes") if isinstance(proof, Mapping) else None
    has_mesh = type(meshes) is list and bool(meshes)
    has_real_assets = (
        has_sprite or has_mesh or bool(proof.get("packaged_original_audio"))
    ) if isinstance(proof, Mapping) else False
    if (not isinstance(files, Mapping) or not isinstance(binaries, Mapping)
            or not isinstance(proof, Mapping)
            or type(require_sprite) is not bool
            or (require_sprite and not has_sprite)
            or not has_real_assets
            or proof.get("world_sha256") != world.digest):
        raise SpriteBoundNativeError(
            "native run requires the exact reviewed original asset candidate"
        )
    expected = proof.get("godot_file_hashes")
    if (not isinstance(expected, Mapping)
            or set(expected) != set(files) | set(binaries)
            or set(files) & set(binaries)):
        raise SpriteBoundNativeError("native candidate file proof is incomplete")
    contents: dict[str, bytes] = {}
    for name, value in files.items():
        if type(name) is not str or type(value) is not str:
            raise SpriteBoundNativeError("text-native game file cannot be recovered")
        contents[name] = value.encode("utf-8")
    for name, value in binaries.items():
        if type(name) is not str or type(value) is not bytes:
            raise SpriteBoundNativeError("native game image bytes not verified")
        contents[name] = value
    for name, value in contents.items():
        path = Path(name)
        if (path.is_absolute() or ".." in path.parts
                or path.as_posix() != name or "\\" in name
                or sha256(value).hexdigest() != expected[name]):
            raise SpriteBoundNativeError("native avatar project contains unverified file path or bytes")
    # The original Expedition autoplay helper plans from the typed world
    # and traveler under the exact same independent source route mechanics.
    recipe = make_expedition_autoplay(world, player)
    recipe_bytes = json.dumps(recipe, sort_keys=True, separators=(",", ":"),
                              allow_nan=False).encode("utf-8")
    if "game/frontier/autoplay.json" in contents:
        raise SpriteBoundNativeError("candidate attempted to override authorized autoplay")
    if "_jeeves_authored_asset_probe.gd" in contents:
        raise SpriteBoundNativeError("candidate cannot shadow trusted native probe")
    contents["game/frontier/autoplay.json"] = recipe_bytes
    baseline = _sha(binary)
    try:
        version = subprocess.run(
            [str(binary), "--version"], stdin=subprocess.DEVNULL,
            capture_output=True, timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SpriteBoundNativeError("real Godot version could not be verified") from exc
    if (version.returncode != 0 or len(version.stdout) > 1000
            or not version.stdout.decode("utf-8", "replace").strip().startswith("4.")):
        raise SpriteBoundNativeError("real installed Godot 4 executable required")
    with tempfile.TemporaryDirectory(prefix="jeeves-avatar-godot-") as scratch:
        root = Path(scratch)
        for name, raw in contents.items():
            destination = root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
        mesh_probe = None
        if has_mesh:
            from .studio_original_mesh_native_probe import (
                MeshEngineProbeError, run_host_mesh_probe,
            )
            try:
                mesh_probe = run_host_mesh_probe(
                    root, binary, candidate, timeout_seconds=timeout_seconds,
                )
            except MeshEngineProbeError as exc:
                raise SpriteBoundNativeError(
                    "actual authored GLBs, body or game instances did not import"
                ) from exc
        with tempfile.TemporaryFile() as logfile:
            try:
                result = subprocess.run(
                    [str(binary), "--headless", "--path", str(root),
                     "--quit-after", "20", "--", "--expedition-autoplay"],
                    cwd=root, stdin=subprocess.DEVNULL,
                    stdout=logfile, stderr=subprocess.STDOUT,
                    timeout=timeout_seconds, check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise SpriteBoundNativeError("native sprite-bound game failed to run") from exc
            if logfile.tell() > MAX_LOG_BYTES:
                raise SpriteBoundNativeError("native sprite game exceeded bounded replay log")
            logfile.seek(0)
            output = logfile.read().decode("utf-8", errors="replace")
    if _sha(binary) != baseline:
        raise SpriteBoundNativeError("native Godot executable was modified during replay")
    if any(marker in output for marker in (
        "SCRIPT ERROR:", "Parse Error:", "ERROR:", "Failed loading resource",
    )):
        raise SpriteBoundNativeError(
            "actual Godot asset project emitted engine script/import errors"
        )
    if result.returncode != 0:
        raise SpriteBoundNativeError(
            "sprite-bound native Godot process exited with error "
            + str(result.returncode)
        )
    completions = [
        line[len(PREFIX):] for line in output.splitlines() if line.startswith(PREFIX)
    ]
    if len(completions) != 1 or len(completions[0]) > 65536:
        raise SpriteBoundNativeError("actual sprite-bound game did not finish a unique run")
    try:
        observed = json.loads(completions[0])
    except (TypeError, ValueError) as exc:
        raise SpriteBoundNativeError("native sprite gameplay completion is invalid JSON") from exc
    if (type(observed) is not dict
            or set(observed) != {
                "world_digest", "route_digest", "completed", "steps",
                "candidate_receipt_head",
            }
            or observed["world_digest"] != world.digest
            or observed["route_digest"] != recipe["route_digest"]
            or observed["completed"] is not True
            or type(observed["steps"]) is not int
            or observed["steps"] != len(recipe["steps"])):
        raise SpriteBoundNativeError("native sprite game completed a different world or route")
    try:
        replay = inspect_native_expedition_trace(
            output, world, player, expected_complete=True,
        )
    except (ExpeditionError, NativeExpeditionError) as exc:
        raise SpriteBoundNativeError("Godot sprite game observations contradict Python replay") from exc
    if (replay["native_candidate_receipt_head"] != observed["candidate_receipt_head"]
            or replay["executed_actions"] != len(recipe["steps"])):
        raise SpriteBoundNativeError("sprite-bound game reports inconsistent native transitions")
    from .studio_sprite_compass_evidence import (
        PREFIX as COMPASS_PREFIX,
        SpriteCompassEvidenceError, inspect_native_compass_observations,
    )
    binding = proof.get("authored_player_avatar_binding")
    compass_receipt = None
    if isinstance(binding, Mapping) and binding.get("directional_animations"):
        try:
            compass_receipt = inspect_native_compass_observations(
                output, world, recipe, binding,
            )
        except SpriteCompassEvidenceError as exc:
            raise SpriteBoundNativeError(
                "real Godot player heading differs from original world movement"
            ) from exc
    elif any(line.startswith(COMPASS_PREFIX) for line in output.splitlines()):
        raise SpriteBoundNativeError(
            "unapproved native game source claimed player compass observations"
        )
    result_proof = {
        "schema_version": "skeleton.jeeves.sprite_bound_native_playthrough.v1",
        "project_id": world.project_id,
        "world_digest": world.digest,
        "source_head_sha256": proof["source_head_sha256"],
        "native_candidate_receipt_sha256": proof["receipt_sha256"],
        "player_binding_sha256": (
            binding["receipt_sha256"] if isinstance(binding, Mapping) else None
        ),
        "compass_replay_receipt_sha256": (
            compass_receipt["receipt_sha256"] if compass_receipt else None
        ),
        "observed_compass_transitions": (
            compass_receipt["waypoint_compass_events_verified"]
            if compass_receipt else 0
        ),
        "native_player_heading_observed": (
            compass_receipt["sprite_animation_observed"]
            if compass_receipt else False
        ),
        "bound_godot_script_sha256": proof["godot_file_hashes"]["game/frontier/expedition.gd"],
        "native_executable_sha256": baseline,
        "native_log_sha256": sha256(output.encode("utf-8")).hexdigest(),
        "observed_replay_receipt": replay["receipt_digest"],
        "native_process_executed": True,
        "native_gameplay_consistent": True,
        "completed": True,
        "real_avatar_script_loaded_for_gameplay": (
            proof.get("animated_sprite3d_player_script_compiled") is True
        ),
        "real_npc_sprite_script_loaded_for_gameplay": (
            proof.get("animated_npc_sprite3d_source_compiled") is True
        ),
        "native_mesh_probe_receipt_sha256": (
            mesh_probe["receipt_sha256"] if mesh_probe is not None else None
        ),
        "actual_godot_meshes_imported": (
            mesh_probe["imported_geometry_mesh_count"] if mesh_probe else 0
        ),
        "actual_godot_lod_meshes_imported": (
            mesh_probe["imported_lod_geometry_count"] if mesh_probe else 0
        ),
        "actual_godot_physics_bodies_instantiated": (
            mesh_probe["instanced_3d_physics_bodies"] if mesh_probe else 0
        ),
        "actual_godot_scene_mesh_instances": (
            mesh_probe["source_game_scene_instances"] if mesh_probe else 0
        ),
        "actual_physics_contacts_observed": False,
        "visual_output_independently_observed": False,
    }
    result_proof["receipt_digest"] = digest(result_proof)
    return result_proof


def run_sprite_bound_native_expedition(
    candidate: Mapping[str, Any], world: ExpeditionWorld, player: Traveler,
    *, godot_executable: str, timeout_seconds: int = 90,
) -> dict[str, Any]:
    """Backwards-compatible sprite-only entrypoint for its existing callers."""
    return run_exact_original_candidate_native_expedition(
        candidate, world, player,
        godot_executable=godot_executable, timeout_seconds=timeout_seconds,
        require_sprite=True,
    )


__all__ = [
    "SpriteBoundNativeError", "run_sprite_bound_native_expedition",
    "run_exact_original_candidate_native_expedition",
]
