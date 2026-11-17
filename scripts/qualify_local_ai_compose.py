#!/usr/bin/env python3
"""Source-only Docker Compose profile qualification, without real model artifacts.

Renders the actual canonical Compose files with ephemeral synthetic credentials
without printing the resolved secret-bearing configuration. No daemon build,
network model download, containers, GPU execution or inference is attempted.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

from scripts.local_ai_docker import GPU_OVERLAYS, BASE, LOCAL, LocalDockerError, _validate_config

ROOT = Path(__file__).resolve().parents[1]


def qualify(root: Path = ROOT) -> dict[str, object]:
    modes: list[str] = []
    with tempfile.TemporaryDirectory(prefix="skeleton-compose-source-") as temporary:
        private_env = dict(os.environ)
        one_use_password = secrets.token_urlsafe(42)
        uri = "mongodb://" + "admin:" + one_use_password + "@mongo:27017/skeleton?authSource=admin"
        private_env.update({
            "MONGO_INITDB_ROOT_USERNAME": "admin",
            "MONGO_INITDB_ROOT_PASSWORD": one_use_password,
            "MONGO_URL": uri,
            "SKL_MONGO_URI": uri,
            "JWT_SECRET": secrets.token_urlsafe(48),
            "GAMEFORGE_JWT_SECRET": secrets.token_urlsafe(48),
            "GF_SEAL_SECRET": secrets.token_urlsafe(48),
            "GF_KEYHOLDER_SEED": secrets.token_urlsafe(48),
            "SKELETON_MASTER_SECRET": secrets.token_urlsafe(48),
            "SKL_ENGINE_SERVICE_TOKEN": secrets.token_urlsafe(48),
            "SKELETON_LOCAL_MODEL_DIR": temporary,
            "SKL_LOCAL_AI_RENDER_GID": "109",  # Syntax-only CI, not an actual host group.
            "AI_PROVIDER": "local",
            "AI_MODEL": "jeeves",
            "JEEVES_LOCAL_ONLY": "1",
            "AI_LOCAL_GUARD_REQUIRED": "1",
            "OPENAI_API_KEY": "",
            "EMERGENT_LLM_KEY": "",
            "AI_SECONDARY_API_KEY": "",
            "AI_SECONDARY_BASE_URL": "",
            "AI_SECONDARY_MODEL": "",
            "AI_VERIFICATION_MODEL": "",
        })
        for mode, overlay in GPU_OVERLAYS.items():
            files = [BASE, LOCAL] + ([overlay] if overlay else [])
            command = ["docker", "compose", "--project-directory", str(root)]
            for filename in files:
                command += ["-f", str(root / filename)]
            command += ["config", "--format", "json"]
            try:
                process = subprocess.run(
                    command, cwd=root, env=private_env, text=True,
                    capture_output=True, timeout=90, check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise LocalDockerError("Docker Compose profile renderer is unavailable") from exc
            # Never leak the resolved env or Docker diagnostics: both may
            # contain ephemeral credentials, bind paths and proxy addresses.
            if process.returncode or not 0 < len(process.stdout) <= 2 * 1024 * 1024:
                raise LocalDockerError("Docker Compose profile configuration failed")
            try:
                config = json.loads(process.stdout)
            except (ValueError, TypeError) as exc:
                raise LocalDockerError("Docker Compose returned malformed profile JSON") from exc
            info = _validate_config(mode, config)
            if info["provider"] != "local" or info["mode"] != mode:
                raise LocalDockerError("Docker Compose profile identity differs")
            modes.append(mode)
    return {
        "schema": "skeleton.local-ai.docker.source-qualification.v1",
        "status": "config_verified_not_runtime_qualified",
        "profiles": modes,
        "service_owner": "skeleton",
        "model_downloaded": False,
        "docker_daemon_contacted": False,
        "inference_executed": False,
        "device_qualified": False,
    }


def main() -> int:
    try:
        print(json.dumps(qualify(), sort_keys=True))
        return 0
    except LocalDockerError:
        print(json.dumps({"ok": False, "error": "Docker profile source qualification failed"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
