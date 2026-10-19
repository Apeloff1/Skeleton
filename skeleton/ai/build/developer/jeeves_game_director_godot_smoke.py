"""Optional real Godot 4 smoke runner for generated Director scene/player UI.

Unlike source manifest checks this invokes an available local Godot binary.
It qualifies only scene startup, not game completion, input latency, audio
playback, professional visual quality, a release installer or model training.
No CI workflow, email alert, provider call or remote installation is created.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
from typing import Any

from skeleton.developer.jeeves_game_director_atlas import verify

SCHEMA = "skeleton.jeeves.director_godot_smoke.v1"


def _safe_env() -> dict[str, str]:
    environ = os.environ.copy()
    # Never allow an external process to accidentally inherit a live Director
    # HTTP bearer credential from the build terminal.
    environ.pop("SKELETON_DIRECTOR_BRIDGE_TOKEN", None)
    return environ


def _execute(argv: list[str], *, timeout: float, env: dict[str, str]) -> dict[str, Any]:
    try:
        result = subprocess.run(argv, capture_output=True, text=True,
                                timeout=timeout, check=False, env=env)
        return {
            "executed": True, "exit_code": result.returncode,
            "passed": result.returncode == 0,
            "stdout_tail": result.stdout[-2000:],
            "stderr_tail": result.stderr[-2000:],
        }
    except subprocess.TimeoutExpired:
        return {"executed": True, "passed": False,
                "error": "Godot process exceeded specialized smoke timeout"}
    except (OSError, ValueError) as exc:
        return {"executed": False, "passed": False, "error": str(exc)}


def smoke(root: Path, *, source: str, timeout: float = 90.0) -> dict[str, Any]:
    if (type(timeout) not in (int, float) or not 10 <= timeout <= 300):
        raise ValueError("Godot per-stage smoke timeout must be 10..300 seconds")
    atlas = verify(root, source=source)
    from skeleton.forge.playtest import resolve_binary
    binary, origin, trusted = resolve_binary()
    if not binary:
        return {"ok": False, "schema": SCHEMA, "action": "director-godot-smoke",
                "error": "No Godot binary resolved; no engine execution attempted",
                "atlas_source_verified": True, "native_gameplay_verified": False}
    executable = str(binary)
    output = {
        "ok": False, "schema": SCHEMA, "action": "director-godot-smoke",
        "atlas_source_verified": atlas["source_manifest_verified"],
        "binary_origin": str(origin), "binary_artifact_verified": bool(trusted),
        "native_gameplay_verified": False,
        "full_game_or_first_install_verified": False,
        "stages": [],
    }
    env = _safe_env()
    version = _execute([executable, "--version"], timeout=timeout, env=env)
    output["stages"].append({"name": "godot_binary_version", **version})
    if not version.get("passed") or not version.get("stdout_tail", "").strip().startswith("4."):
        output["error"] = "Godot 4 executable/version not verified"
        return output
    directory = str(Path(atlas["path"]))
    for name, argv in (
        ("godot_source_import", [executable, "--headless", "--path", directory, "--import"]),
        ("godot_scene_atlas_start", [executable, "--headless", "--path", directory,
                                    "res://main.tscn", "--quit-after", "8"]),
        ("godot_live_quest_ui_start", [executable, "--headless", "--path", directory,
                                     "res://director_player.tscn", "--quit-after", "8"]),
    ):
        stage = _execute(argv, timeout=timeout, env=env)
        output["stages"].append({"name": name, **stage})
        if not stage["passed"]:
            output["error"] = name + " did not qualify"
            return output
    output["ok"] = True
    output["actual_godot4_binary_invoked"] = True
    output["source_import_and_two_scenes_started"] = True
    output["native_gameplay_verified"] = False
    return output
