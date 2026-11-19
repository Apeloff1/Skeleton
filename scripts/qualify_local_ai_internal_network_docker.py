#!/usr/bin/env python3
"""Physical disposable Docker bridge admission: internal-only, no app state.

Creates exactly one random, CI-owned internal bridge with canonical Compose
labels. Independently invokes the same runtime guard that the real offline
launcher uses; checks a hostile simulated noninternal response is rejected.
This does NOT assert measured host firewall policy or packet-level egress.
"""
from __future__ import annotations

import json
import secrets
import sys

from scripts import local_ai_docker as host
from scripts import local_ai_offline_launch as launch

SCHEMA = "skeleton.local-ai.docker.physical-internal-network.v1"


def qualify_internal_network() -> dict[str, object]:
    nonce = secrets.token_hex(12)
    project = "skl-offline-net-" + nonce
    name = project + "_tutolage"
    created = False
    original = host._run
    try:
        identity = original([
            "docker", "network", "create", "--driver", "bridge", "--internal",
            "--label", "com.docker.compose.project=" + project,
            "--label", "com.docker.compose.network=tutolage",
            name,
        ], root=host.ROOT, capture=True).strip()
        # Docker may have created the bridge even when its returned ID is
        # malformed. Keep cleanup armed for every successful create call.
        created = True
        if len(identity) != 64 or any(c not in "0123456789abcdef" for c in identity):
            raise launch.OfflineLaunchError("synthetic private network identity invalid")
        launch._attest_internal_bridge(name, project, host.ROOT)
        source = original([
            "docker", "network", "inspect", "--format", "{{json .}}", name
        ], root=host.ROOT, capture=True)
        parsed = json.loads(source)
        if (parsed.get("Internal") is not True or parsed.get("Driver") != "bridge"
                or parsed.get("Name") != name):
            raise launch.OfflineLaunchError("physical internal bridge not recognized")
        attempted = False

        def malicious(args, *, root=host.ROOT, capture=False):
            nonlocal attempted
            if args[:3] == ["docker", "network", "inspect"]:
                attempted = True
                corrupted = dict(parsed)
                corrupted["Internal"] = False
                return json.dumps(corrupted)
            return original(args, root=root, capture=capture)

        host._run = malicious
        try:
            try:
                launch._attest_internal_bridge(name, project, host.ROOT)
            except launch.OfflineLaunchError:
                denied = attempted
            else:
                denied = False
        finally:
            host._run = original
        if not denied:
            raise launch.OfflineLaunchError("noninternal network attack admitted")
        return {
            "schema": SCHEMA,
            "status": "real_docker_internal_network_metadata_verified",
            "real_docker_daemon_executed": True,
            "disposable_private_bridge_created": True,
            "internal_only_metadata_observed": True,
            "noninternal_drift_rejected": True,
            "application_containers_started": False,
            "application_volumes_touched": False,
            "model_inference_executed": False,
            "packet_level_egress_measured": False,
            "host_firewall_qualified": False,
            "protected_chat_qualified": False,
            "release_qualified": False,
        }
    finally:
        if created:
            # Only the freshly created random synthetic bridge can be removed.
            try:
                original(["docker", "network", "rm", name],
                         root=host.ROOT)
            except host.LocalDockerError:
                raise launch.OfflineLaunchError(
                    "disposable Docker network cleanup was incomplete"
                ) from None


def main() -> int:
    try:
        print(json.dumps(qualify_internal_network(), sort_keys=True))
        return 0
    except (host.LocalDockerError, ValueError, TypeError, OSError):
        print(json.dumps({"schema": SCHEMA, "ok": False,
                          "error": "isolated physical Docker network qualification failed"}),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
