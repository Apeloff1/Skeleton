#!/usr/bin/env python3
"""Physical four-service Docker qualification with a tiny local static ELF.

NO downloaded base image, registry pull, GGUF, Mongo user state, external API
or production container. Builds an x86_64 syscall-only test process using
the Ubuntu runner's local GNU assembler/linker. Imports it into four random
single-purpose images, starts four containers on a random INTERNAL-only
Compose bridge, checks health/isolation and denies an outbound UDP route.
Deletes only artifacts carrying the freshly generated random test scope.

This is a synthetic *Docker deployment* qualification, NOT a physical
Skeleton/Jeeves app run, licensed GGUF test or database recovery proof.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import platform
import secrets
import subprocess
import sys
import tarfile
import tempfile
from typing import Any

from scripts import local_ai_docker as host
from scripts import local_ai_offline_launch as launch

SCHEMA = "skeleton.local-ai.docker.physical-synthetic-four-service.v1"
ROLES = ("mongo", "skeleton", "backend", "frontend")
MAX_OUTPUT = 1 << 20

# x86_64 Linux raw syscalls only. argv[1] beginning with h exits healthy;
# beginning with e attempts sendto(1.1.1.1:53 UDP), exits success ONLY if
# the kernel denies it. The default entry point idles via nanosleep.
ASM = r"""
.section .text
.global _start
_start:
    mov (%rsp), %rcx
    cmp $2, %rcx
    jb idle
    mov 16(%rsp), %rdi
    cmpb $104, (%rdi)
    je good
    cmpb $101, (%rdi)
    je test_egress
idle:
    mov $35, %rax
    lea delay(%rip), %rdi
    xor %rsi, %rsi
    syscall
    jmp idle
test_egress:
    mov $41, %rax
    mov $2, %rdi
    mov $2, %rsi
    xor %rdx, %rdx
    syscall
    cmp $0, %rax
    jl good
    mov %rax, %rdi
    mov $44, %rax
    lea packet(%rip), %rsi
    mov $4, %rdx
    xor %r10, %r10
    lea remote(%rip), %r8
    mov $16, %r9
    syscall
    cmp $0, %rax
    jl good
bad:
    mov $60, %rax
    mov $1, %rdi
    syscall
good:
    mov $60, %rax
    xor %rdi, %rdi
    syscall
.section .rodata
.balign 8
delay:
    .quad 1
    .quad 0
packet:
    .ascii "test"
.balign 4
remote:
    .word 2
    .word 0x3500
    .byte 1,1,1,1
    .quad 0
"""


class SyntheticDockerError(host.LocalDockerError):
    """One physical Docker synthetic deployment invariant did not hold."""


def _cmd(argv: list[str], *, root: Path, timeout: int = 120,
         may_fail: bool = False) -> str:
    if (not 2 <= len(argv) <= 26 or
            any(not isinstance(x, str) or not 0 < len(x) < 8192 for x in argv)):
        raise SyntheticDockerError("physical four-service argv invalid")
    try:
        output = subprocess.run(
            argv, cwd=root, text=True, capture_output=True,
            check=False, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise SyntheticDockerError("physical four-service Docker command unavailable") from None
    if (len(output.stdout) > MAX_OUTPUT or len(output.stderr) > MAX_OUTPUT):
        raise SyntheticDockerError("physical Docker output over bounded limit")
    if output.returncode != 0:
        if may_fail:
            return ""
        raise SyntheticDockerError("physical synthetic Docker stage failed")
    return output.stdout.strip()


def _probe_image(root: Path, nonce: str) -> Path:
    if platform.system() != "Linux" or platform.machine() not in ("x86_64", "amd64"):
        raise SyntheticDockerError("synthetic ELF is qualified only on Linux amd64")
    source = root / "probe.s"
    object_file = root / "probe.o"
    executable = root / "probe"
    source.write_text(ASM, encoding="ascii")
    _cmd(["as", "--64", "-o", str(object_file), str(source)], root=root, timeout=30)
    _cmd(["ld", "-static", "--build-id=none", "-o", str(executable),
          str(object_file)], root=root, timeout=30)
    body = executable.read_bytes()
    if not 100 <= len(body) <= 1048576 or body[:4] != b"\x7fELF":
        raise SyntheticDockerError("compiled private ELF identity unavailable")
    archive = root / "probe-rootfs.tar"
    with tarfile.open(archive, "w:") as tar:
        info = tarfile.TarInfo("probe")
        info.mode = 0o755
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        info.mtime = 0
        info.size = len(body)
        tar.addfile(info, io.BytesIO(body))
    archive.chmod(0o600)
    return archive


def _compose_spec(project: str, images: dict[str, str]) -> dict[str, Any]:
    if set(images) != set(ROLES) or any(
        not isinstance(value, str) or not value.startswith("sha256:")
        or len(value) != 71 or
        any(c not in "0123456789abcdef" for c in value[7:])
        for value in images.values()
    ):
        raise SyntheticDockerError("synthetic image ID inventory invalid")
    return {
        "name": project,
        "services": {
            role: {
                "image": images[role],
                "read_only": True,
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "mem_limit": "128m",
                "cpus": 0.5,
                "pids_limit": 64,
                "restart": "no",
                "networks": ["tutolage"],
                "volumes": [role + "_data:/data"],
                "healthcheck": {
                    "test": ["CMD", "/probe", "health"],
                    "interval": "1s", "timeout": "2s",
                    "retries": 6, "start_period": "1s",
                },
            }
            for role in ROLES
        },
        "networks": {
            "tutolage": {"name": project + "_tutolage",
                         "driver": "bridge", "internal": True},
        },
        "volumes": {role + "_data": {"driver": "local"} for role in ROLES},
    }


def _live_four(prefix: list[str], project: str, ids: dict[str, str],
               root: Path) -> list[dict[str, Any]]:
    name = project + "_tutolage"
    launch._attest_internal_bridge(name, project, root)
    result: list[dict[str, Any]] = []
    all_ids = set()
    for role in ROLES:
        cid = _cmd([*prefix, "ps", "-q", role], root=root)
        if (not launch.CID.fullmatch(cid) or cid in all_ids):
            raise SyntheticDockerError("synthetic Compose container identity invalid")
        all_ids.add(cid)
        raw = _cmd([
            "docker", "inspect", "--format", "{{json .}}", cid,
        ], root=root)
        record = json.loads(raw)
        config, state, docker = (
            record.get("Config"), record.get("State"), record.get("HostConfig")
        )
        nets = record.get("NetworkSettings", {}).get("Networks")
        if any(not isinstance(x, dict) for x in (config, state, docker, nets)):
            raise SyntheticDockerError("synthetic container inspect shape invalid")
        labels = config.get("Labels")
        if (record.get("Image") != ids[role]
                or not isinstance(labels, dict)
                or labels.get("com.docker.compose.project") != project
                or labels.get("com.docker.compose.service") != role
                or state.get("Running") is not True
                or state.get("Health", {}).get("Status") != "healthy"
                or docker.get("ReadonlyRootfs") is not True
                or docker.get("Privileged") is not False
                or docker.get("CapAdd")
                or "ALL" not in [str(x).upper() for x in docker.get("CapDrop", [])]
                or not any(v in ("no-new-privileges", "no-new-privileges:true")
                           for v in docker.get("SecurityOpt", []))
                or set(nets) != {name}
                or docker.get("PortBindings")):
            raise SyntheticDockerError("real Docker container violated offline isolation")
        # UDP sendto on the internal-only bridge must be denied by the kernel
        # instead of obtaining a default route. This tests a concrete packet
        # attempt, not a full host-firewall/network security proof.
        _cmd(["docker", "exec", cid, "/probe", "egress"], root=root,
             timeout=15)
        result.append({
            "role": role, "image_id": ids[role], "health": "healthy",
            "root_readonly": True, "capabilities_dropped": True,
            "network_internal": True, "external_udp_sendto_denied": True,
            "published_ports": 0,
        })
    return result


def physical_synthetic_four_service() -> dict[str, Any]:
    nonce = secrets.token_hex(12)
    project = "skl-physical-four-" + nonce
    tags = {role: "skl-physical-" + nonce + ":" + role for role in ROLES}
    created_tags: list[str] = []
    created_project = False
    with tempfile.TemporaryDirectory(prefix="skl-offline-four-") as directory:
        root = Path(directory)
        root.chmod(0o700)
        archive = _probe_image(root, nonce)
        prefix = ["docker", "compose", "--project-directory", str(root),
                  "-f", str(root / "compose.json")]
        ids: dict[str, str] = {}
        try:
            # Verify our random project does not refer to any existing user
            # container, running OR stopped. No stale project may be adopted.
            existing = _cmd([
                "docker", "ps", "-a", "--no-trunc",
                "--filter", "label=com.docker.compose.project=" + project,
                "--format", "{{.ID}}",
            ], root=root)
            if existing:
                raise SyntheticDockerError("random synthetic project already exists")
            for role in ROLES:
                image = _cmd([
                    "docker", "image", "import",
                    "--change", 'ENTRYPOINT ["/probe"]',
                    "--change", "ENV SKL_PROBE_ROLE=" + role,
                    str(archive), tags[role],
                ], root=root, timeout=120)
                if not image.startswith("sha256:") or len(image) != 71:
                    raise SyntheticDockerError("synthetic Docker import image ID invalid")
                created_tags.append(tags[role])
                actual = _cmd([
                    "docker", "image", "inspect", "--format", "{{.Id}}",
                    tags[role],
                ], root=root)
                if image != actual:
                    raise SyntheticDockerError("synthetic image ID differs from import")
                ids[role] = image
            if len(set(ids.values())) != len(ROLES):
                raise SyntheticDockerError("synthetic images did not receive distinct IDs")
            source = _compose_spec(project, ids)
            spec = root / "compose.json"
            spec.write_text(json.dumps(source, sort_keys=True), encoding="utf-8")
            spec.chmod(0o600)
            rendered = json.loads(_cmd([*prefix, "config", "--format", "json"],
                                       root=root))
            if (set(rendered["services"]) != set(ROLES)
                    or rendered["networks"]["tutolage"]["internal"] is not True
                    or any(rendered["services"][role]["image"] != ids[role]
                           for role in ROLES)):
                raise SyntheticDockerError("physical four-image Compose render changed")
            created_project = True
            _cmd([*prefix, "up", "-d", "--no-build", "--pull", "never",
                  "--wait", "--wait-timeout", "90", *ROLES],
                 root=root, timeout=150)
            results = _live_four(prefix, project, ids, root)
            return {
                "schema": SCHEMA,
                "status": "physical_four_synthetic_services_healthy_no_pull_internal",
                "real_docker_compose_run_executed": True,
                "synthetic_images_created_from_local_ELF": len(created_tags),
                "source_image_registry_pulls": 0,
                "containers_started": len(results),
                "all_exact_image_ids": True,
                "all_healthchecks_passed": True,
                "all_running_containers_readonly": True,
                "all_capabilities_dropped": True,
                "internal_only_network": True,
                "external_udp_sendto_denied": True,
                "host_firewall_policy_qualified": False,
                "production_app_images_executed": False,
                "licensed_gguf_executed": False,
                "production_data_volumes_touched": False,
                "backend_protected_chat_qualified": False,
                "database_recovery_qualified": False,
                "release_qualified": False,
                "services": results,
            }
        finally:
            if created_project:
                # The project name is a high-entropy test-only namespace,
                # verified to be absent before setup. Only its own newly
                # created Compose volume/network/container objects are
                # destroyed; do not use a global prune or remove-orphans.
                _cmd([*prefix, "down", "--volumes", "--timeout", "10"],
                     root=root, timeout=90, may_fail=False)
            for tag in created_tags:
                _cmd(["docker", "image", "rm", tag], root=root,
                     timeout=60, may_fail=True)


def main() -> int:
    try:
        print(json.dumps(physical_synthetic_four_service(), sort_keys=True))
        return 0
    except (SyntheticDockerError, host.LocalDockerError, ValueError,
            TypeError, OSError, KeyError, json.JSONDecodeError):
        print(json.dumps({
            "schema": SCHEMA, "ok": False,
            "error": "isolated physical four-container Docker qualification failed",
        }), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
