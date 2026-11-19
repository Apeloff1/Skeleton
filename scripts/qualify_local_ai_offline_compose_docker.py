#!/usr/bin/env python3
"""Physical Docker Compose *parser* qualification for four immutable image IDs.

This test never starts/loads/pulls an image or mounts a state volume. It uses a
randomized temporary Compose project with synthetic image IDs, checks the
actual installed Docker Compose CLI's multi-file effective rendering, and
ensures unrelated privileged/security drift is detectable by deep comparison.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

SCHEMA = "skeleton.local-ai.docker.physical-offline-compose-parser.v1"
ID = "sha256:" + "d" * 64
ROLES = ("mongo", "skeleton", "backend", "frontend")


class PhysicalOfflineComposeError(RuntimeError):
    """Unable to verify local Docker Compose's digest-only render contract."""


def _call(files: list[Path], project: Path) -> dict[str, Any]:
    command = ["docker", "compose", "--project-directory", str(project)]
    for path in files:
        command += ["-f", str(path)]
    command += ["config", "--format", "json"]
    try:
        outcome = subprocess.run(
            command, cwd=project, text=True, capture_output=True,
            check=False, timeout=40,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PhysicalOfflineComposeError("Docker Compose CLI unavailable") from exc
    if outcome.returncode != 0:
        # Never print raw Compose diagnostics; application configurations
        # might contain interpolated local credentials.
        raise PhysicalOfflineComposeError("Docker Compose rejected offline image-ID overlay")
    if not 0 < len(outcome.stdout) <= 1024 * 1024:
        raise PhysicalOfflineComposeError("Compose parser response exceeds budget")
    try:
        parsed = json.loads(outcome.stdout)
    except (ValueError, TypeError) as exc:
        raise PhysicalOfflineComposeError("Compose parser returned non-JSON") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("services"), dict):
        raise PhysicalOfflineComposeError("Compose parser service map unavailable")
    return parsed


def qualify_physical_offline_compose() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="skl-offline-compose-parser-") as name:
        project = Path(name)
        project.chmod(0o700)
        base = project / "compose.yml"
        overlay = project / "compose.offline.yml"
        privileged = project / "compose.hostile.yml"
        # No build, image pull, Docker socket, daemon, network or persistent state.
        source = {
            "name": "skl-offline-compose-qualify",
            "services": {
                role: {
                    "image": "example.invalid/source-" + role + ":unavailable",
                    "read_only": True,
                    "cap_drop": ["ALL"],
                    "security_opt": ["no-new-privileges:true"],
                    "environment": {
                        "JEEVES_LOCAL_ONLY": "1",
                        "AI_PROVIDER": "local" if role == "skeleton" else "",
                    },
                    "networks": ["local-only"],
                }
                for role in ROLES
            },
            "networks": {
                "local-only": {"driver": "bridge"},
            },
        }
        # JSON is valid YAML for Docker Compose file parsing. Immutable refs
        # are synthetic, so no image exists or can be fetched in this test.
        base.write_text(json.dumps(source, sort_keys=True), encoding="utf-8")
        override = {"services": {
            role: {"image": ID} for role in ROLES
        }}
        overlay.write_text(json.dumps(override, sort_keys=True), encoding="utf-8")
        changed = {"services": {
            "mongo": {"privileged": True},
        }}
        privileged.write_text(json.dumps(changed, sort_keys=True), encoding="utf-8")
        canonical = _call([base], project)
        pinned = _call([base, overlay], project)
        expected = copy.deepcopy(canonical)
        if set(expected["services"]) != set(ROLES):
            raise PhysicalOfflineComposeError("canonical synthetic service roles differ")
        for role in ROLES:
            expected["services"][role]["image"] = ID
        if pinned != expected:
            raise PhysicalOfflineComposeError("offline Compose changed more than image identities")
        hostile = _call([base, overlay, privileged], project)
        if hostile == expected or hostile["services"]["mongo"].get("privileged") is not True:
            raise PhysicalOfflineComposeError("hostile Compose privileged drift was not exposed")
        return {
            "schema": SCHEMA,
            "status": "real_compose_parser_four_digest_only_image_merges_verified",
            "real_docker_compose_cli_executed": True,
            "images_selected_by_sha256": len(ROLES),
            "all_service_nonimage_fields_unchanged": True,
            "hostile_privilege_change_detected": True,
            "images_pulled": False,
            "images_loaded": False,
            "containers_started": False,
            "application_state_accessed": False,
            "model_inference_executed": False,
            "guarded_chat_qualified": False,
            "production_compose_render_qualified": False,
            "release_qualified": False,
        }


def main() -> int:
    try:
        print(json.dumps(qualify_physical_offline_compose(), sort_keys=True))
        return 0
    except (PhysicalOfflineComposeError, OSError, ValueError):
        print(json.dumps({
            "schema": SCHEMA, "ok": False,
            "error": "physical Docker Compose image-ID parser qualification unavailable",
        }), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
