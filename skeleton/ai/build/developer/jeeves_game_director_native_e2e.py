"""Optional actual Godot 4 -> Python Director game protocol acceptance.

Runs against an isolated source copy and temporary game session, never a user
save. Starts an authenticated loopback service and a genuine Godot SceneTree
script that performs a quest input and reads the persisted result.

A pass establishes native Godot HTTP action interoperability only; it does
not qualify rendered assets, full graphical completion, physical controllers,
packaging, or a released native save.
"""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import subprocess
import tempfile
from typing import Any

from skeleton.developer.jeeves_game_director_atlas import export, verify
from skeleton.developer.jeeves_game_director_e2e import _mirror, _Service
from skeleton.developer.jeeves_game_director_session import begin, inspect
from skeleton.developer.jeeves_game_production_board import _load_world

SCHEMA = "skeleton.jeeves.director_godot_http_acceptance.v1"


def _run_godot(executable: str, argv: list[str], *,
               environ: dict[str, str], timeout: float) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [executable, *argv], capture_output=True, text=True, errors="replace",
            timeout=timeout, env=environ, check=False)
        return {
            "binary_launched": True, "passed": result.returncode == 0,
            "exit_code": result.returncode,
            "probe_success_marker": "JEEVES_NATIVE_DIRECTOR_PROBE_OK" in result.stdout,
            # Avoid exposing any subprocess log containing secrets or local
            # paths; the probe deliberately logs only a fixed success marker.
            "stderr_nonempty": bool(result.stderr.strip()),
        }
    except subprocess.TimeoutExpired:
        return {"binary_launched": True, "passed": False,
                "probe_success_marker": False, "reason": "native probe timed out"}
    except (OSError, ValueError):
        return {"binary_launched": False, "passed": False,
                "probe_success_marker": False, "reason": "Godot binary could not launch"}


def accept(root: Path, *, source: str, timeout: float = 90.0) -> dict[str, Any]:
    if type(timeout) not in (int, float) or not 10 <= timeout <= 300:
        raise ValueError("native Director E2E requires a per-process timeout of 10..300 seconds")
    world, original_sha = _load_world(root, source)
    from skeleton.forge.playtest import resolve_binary
    godot, origin, binary_trusted = resolve_binary()
    if not godot:
        return {
            "ok": False, "action": "director-native-http-e2e", "schema": SCHEMA,
            "reason": "No Godot 4 binary available; native interoperability not executed",
            "godot_binary_executed": False, "native_quest_input_verified": False,
        }
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="skeleton-godot-bridge-") as directory:
        scratch = Path(directory) / "game"
        mirrored = _mirror(root, source, scratch)
        session = "godot_native_probe"
        before = begin(scratch, source=mirrored, session=session)
        package = export(scratch, source=mirrored)
        checked = verify(scratch, source=mirrored)
        if not checked["source_manifest_verified"]:
            raise ValueError("generated source media failed exact native project verification")
        stage = str(Path(package["path"]))
        env = os.environ.copy()
        # The isolated local bridge and Godot child alone share this one-off
        # secret. No project or cached build file contains it.
        token = secrets.token_urlsafe(36)
        env["SKELETON_DIRECTOR_BRIDGE_TOKEN"] = token
        env["SKELETON_DIRECTOR_PROBE_WORLD"] = world.digest
        for phase, args in (
            ("godot_project_import", ["--headless", "--path", stage, "--import"]),
        ):
            observed = _run_godot(str(godot), args, environ=env, timeout=timeout)
            results.append({"phase": phase, **observed})
            if not observed["passed"]:
                return {
                    "ok": False, "schema": SCHEMA, "action": "director-native-http-e2e",
                    "source_sha256": original_sha,
                    "native_quest_input_verified": False, "stages": results,
                    "binary_origin": str(origin), "binary_artifact_verified": bool(binary_trusted),
                }
        service = _Service(scratch, session, token)
        try:
            service.start()
            if service.server is None:
                raise ValueError("isolated native gameplay transport not running")
            env["SKELETON_DIRECTOR_PROBE_PORT"] = str(service.server.server_port)
            observed = _run_godot(
                str(godot), ["--headless", "--path", stage,
                             "--script", "res://director_probe.gd"],
                environ=env, timeout=timeout)
            results.append({"phase": "godot_quest_action_and_recovery", **observed})
        finally:
            service.stop()
        after = inspect(scratch, session=session)
        after_import = verify(scratch, source=mirrored)
        action_verified = bool(
            after_import["source_manifest_verified"] and
            observed["passed"] and observed["probe_success_marker"]
            and after["sequence"] == before["sequence"] + 1
            and after["turn"] == before["turn"] + 1
            and after["world_sha256"] == world.digest
            and after["current_state_sha256"] != before["current_state_sha256"]
        )
    from skeleton.developer.jeeves_game_quality import _read
    if _read(root, source, 16 * 1024 * 1024)[1] != original_sha:
        raise ValueError("original Director source changed during native Godot verification")
    return {
        "ok": action_verified, "schema": SCHEMA,
        "action": "director-native-http-e2e",
        "world_sha256": world.digest, "source_sha256": original_sha,
        "actual_godot4_process_launched": any(x["binary_launched"] for x in results),
        "native_quest_input_verified": action_verified,
        "native_quest_recovery_verified": action_verified,
        "source_only_artifact": False,
        "isolated_game_save_cleaned_up": True,
        "binary_origin": str(origin), "binary_artifact_verified": bool(binary_trusted),
        "stages": results,
        "rendered_gameplay_quality_verified": False,
        "full_campaign_native_completion_verified": False,
        "physical_gamepad_tested": False,
    }
