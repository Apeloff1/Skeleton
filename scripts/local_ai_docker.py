#!/usr/bin/env python3
"""Operate a single canonical Skeleton Jeeves image with opt-in CPU/GPU overlays.

No shell commands, silent model downloads, destructive volume operations, remote
model fallback, credentials in logs or independent inference services.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import stat
import subprocess
import sys
from typing import Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
BASE = "docker-compose.yml"
LOCAL = "docker-compose.local-ai.yml"
GPU_OVERLAYS = {
    "cpu": None,
    "nvidia": "docker-compose.local-ai.nvidia.yml",
    "rocm": "docker-compose.local-ai.rocm.yml",
}
ENV_FENCE = {
    "AI_PROVIDER": "local",
    "AI_MODEL": "jeeves",
    "AI_LOCAL_DEPLOYMENT_PATH": "/app/local-ai/jeeves.json",
    "AI_LOCAL_MODEL_PATH": "",
    "AI_LOCAL_MODEL_CATALOG_PATH": "",
    "JEEVES_LOCAL_ONLY": "1",
    "JEEVES_PRIMARY_MODEL_ID": "jeeves",
    "AI_LOCAL_GUARD_REQUIRED": "1",
}
EMPTY_FENCE = (
    "OPENAI_API_KEY", "EMERGENT_LLM_KEY", "AI_SECONDARY_API_KEY",
    "AI_SECONDARY_BASE_URL", "AI_SECONDARY_MODEL", "AI_VERIFICATION_MODEL",
)


class LocalDockerError(ValueError):
    """Refuse a topology, command, or artifact that cannot be proven safe."""


def compose_command(mode: str, root: Path = ROOT) -> list[str]:
    if mode not in GPU_OVERLAYS:
        raise LocalDockerError("unsupported accelerator mode")
    files = [BASE, LOCAL]
    if GPU_OVERLAYS[mode]:
        files.append(GPU_OVERLAYS[mode])
    result = ["docker", "compose", "--project-directory", str(root)]
    envfile = root / ".env"
    if not envfile.is_file() or envfile.is_symlink():
        raise LocalDockerError("run canonical app setup to create private .env first")
    result += ["--env-file", str(envfile)]
    for file in files:
        if not (root / file).is_file():
            raise LocalDockerError("required local AI overlay is missing")
        result += ["-f", str(root / file)]
    return result


def _run(args: Sequence[str], *, root: Path = ROOT, capture: bool = False) -> str:
    try:
        completed = subprocess.run(
            list(args), cwd=root, check=False,
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=3600,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LocalDockerError("Docker operation unavailable or timed out") from exc
    if completed.returncode != 0:
        # Docker diagnostics can contain interpolated credentials, proxy URLs
        # and private paths. Never return raw stdout/stderr in operator output.
        raise LocalDockerError("Docker command failed; inspect Docker locally")
    if not capture and completed.stdout.strip():
        print(completed.stdout.rstrip())
    return completed.stdout if capture else ""


def _mount_from_compose(data: Mapping[str, object]) -> tuple[Path, str]:
    services = data.get("services")
    if not isinstance(services, dict) or set(services) != {
        "mongo", "skeleton", "backend", "frontend", "chroma",
    }:
        raise LocalDockerError("compose runtime service topology differs from canonical assembly")
    skeleton = services.get("skeleton")
    if not isinstance(skeleton, dict):
        raise LocalDockerError("canonical engine service is unavailable")
    environment = skeleton.get("environment")
    if not isinstance(environment, dict) or any(
        environment.get(key, "") != value for key, value in ENV_FENCE.items()
    ) or any(str(environment.get(key, "") or "").strip() for key in EMPTY_FENCE):
        raise LocalDockerError("engine Compose local-only provider fence differs")
    if skeleton.get("read_only") is not True:
        raise LocalDockerError("engine must preserve a read-only root filesystem")
    if "ALL" not in skeleton.get("cap_drop", []):
        raise LocalDockerError("engine capabilities were not dropped")
    if "no-new-privileges:true" not in skeleton.get("security_opt", []):
        raise LocalDockerError("engine privilege fence is missing")
    mounts = [
        volume for volume in skeleton.get("volumes", [])
        if isinstance(volume, dict) and volume.get("target") == "/app/local-ai"
    ]
    if len(mounts) != 1 or mounts[0].get("read_only") is not True:
        raise LocalDockerError("model directory must be mounted exactly once and read-only")
    volume = mounts[0]
    if volume.get("type") != "bind" or not isinstance(volume.get("source"), str):
        raise LocalDockerError("model artifact source must be an explicit host bind mount")
    host = Path(volume["source"])
    if (not host.is_absolute() or host.is_symlink()
            or "," in str(host) or any(ord(char) < 32 for char in str(host))):
        raise LocalDockerError("model artifact host path is not a safe absolute bind path")
    try:
        if not stat.S_ISDIR(host.lstat().st_mode):
            raise LocalDockerError("model directory does not yet exist")
    except OSError as exc:
        raise LocalDockerError("model directory missing: create it without changing existing data") from exc
    image = skeleton.get("image")
    if not isinstance(image, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9./_:@-]{0,239}", image):
        raise LocalDockerError("engine must have an explicit safe local image reference")
    ports = skeleton.get("ports")
    if not isinstance(ports, list) or not ports:
        raise LocalDockerError("missing host-local engine ingress")
    for port in ports:
        if not isinstance(port, dict) or port.get("host_ip") not in ("127.0.0.1", "::1"):
            raise LocalDockerError("engine cannot be published to a non-loopback interface")
    return host, image


def _bounded_limit(value: object, *, name: str) -> str:
    """Use the rendered Compose resource limit, never a different host default."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise LocalDockerError("local engine resource limit missing or invalid: " + name)
    text = str(value).strip()
    if not re.fullmatch(r"[1-9][0-9]{0,14}(?:\.[0-9]{1,3})?(?:[kKmMgGtT][bB]?)?", text):
        raise LocalDockerError("local engine resource limit invalid: " + name)
    if name in ("cpus", "pids_limit") and re.search(r"[kKmMgGtT]", text):
        raise LocalDockerError("local engine CPU/PID limit cannot have a size suffix")
    return text


def inspect_config(mode: str, root: Path = ROOT) -> dict[str, object]:
    command = compose_command(mode, root)
    raw = _run([*command, "config", "--format", "json"], root=root, capture=True)
    try:
        topology = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LocalDockerError("Docker Compose returned invalid topology JSON") from exc
    if not isinstance(topology, dict):
        raise LocalDockerError("Docker Compose returned invalid topology")
    mount, image = _mount_from_compose(topology)
    skeleton = topology["services"]["skeleton"]
    limits = {
        "memory": _bounded_limit(skeleton.get("mem_limit"), name="memory"),
        "cpus": _bounded_limit(skeleton.get("cpus"), name="cpus"),
        "pids_limit": _bounded_limit(skeleton.get("pids_limit"), name="pids_limit"),
        "shm_size": _bounded_limit(skeleton.get("shm_size"), name="shm_size"),
    }
    render_gid = None
    if mode == "rocm":
        groups = skeleton.get("group_add")
        if not isinstance(groups, list) or len(groups) != 1:
            raise LocalDockerError("AMD render group must be exactly one authorized GID")
        render_gid = str(groups[0])
        if not render_gid.isdecimal() or not 1 <= int(render_gid) <= 65535:
            raise LocalDockerError("AMD render group GID is invalid")
        devices = skeleton.get("devices", [])
        if not isinstance(devices, list):
            raise LocalDockerError("AMD device mapping is invalid")
        device_sources = {
            item.get("source") for item in devices if isinstance(item, dict)
        }
        if not {"/dev/kfd", "/dev/dri"}.issubset(device_sources):
            raise LocalDockerError("AMD device access is missing")
    elif mode == "nvidia":
        deploy = skeleton.get("deploy", {})
        resources = deploy.get("resources", {}) if isinstance(deploy, dict) else {}
        reservations = resources.get("reservations", {}) if isinstance(resources, dict) else {}
        devices = reservations.get("devices", []) if isinstance(reservations, dict) else []
        if not isinstance(devices, list) or not any(
            isinstance(dev, dict) and dev.get("driver") == "nvidia"
            and dev.get("count") == 1
            and "gpu" in dev.get("capabilities", [])
            for dev in devices
        ):
            raise LocalDockerError("NVIDIA device reservation is absent or not one GPU")
    return {
        "schema": "skeleton.local-ai.docker.host.v1",
        "status": "compose_verified_not_inference_qualified",
        "mode": mode,
        "model_directory": str(mount),
        "image": image,
        "runtime_service": "skeleton",
        "provider": "local",
        "services": 5,
        "limits": limits,
        "render_gid": render_gid,
        "downloaded_models": False,
        "inference_executed": False,
    }


def _isolated_container(
    mode: str, operation: str, *, root: Path = ROOT, extra: Sequence[str] = (),
) -> list[str]:
    status = inspect_config(mode, root)
    mount = status["model_directory"]
    image = status["image"]
    limits = status.get("limits")
    if not isinstance(limits, dict):
        raise LocalDockerError("effective Compose resource limits were not observed")
    for name in ("memory", "cpus", "pids_limit", "shm_size"):
        limits[name] = _bounded_limit(limits.get(name), name=name)
    if operation not in ("pin", "preflight", "qualify"):
        raise LocalDockerError("unsupported model operation")
    writable = operation == "pin"
    options = [
        "docker", "run", "--rm", "--pull=never",
        "--network", "none", "--read-only",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--user", "10001:10001",
        "--init",
        "--memory", limits["memory"],
        "--cpus", limits["cpus"],
        "--pids-limit", limits["pids_limit"],
        "--shm-size", limits["shm_size"],
        "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777",
        "--mount", "type=bind,source=" + str(mount) +
        ",target=/app/local-ai" + ("" if writable else ",readonly"),
    ]
    if mode == "nvidia":
        options += ["--gpus", "1"]
    elif mode == "rocm":
        gid = status.get("render_gid")
        if not isinstance(gid, str) or not gid.isdecimal() or not 1 <= int(gid) <= 65535:
            raise LocalDockerError("set an authorized numeric SKL_LOCAL_AI_RENDER_GID in .env")
        options += [
            "--device", "/dev/kfd:/dev/kfd",
            "--device", "/dev/dri:/dev/dri",
            "--group-add", gid,
        ]
    return [
        *options, str(image),
        "python", "-m", "skeleton.app.docker_local_ai", operation, *extra,
    ]


def build(mode: str, root: Path = ROOT) -> None:
    inspect_config(mode, root)
    _run([*compose_command(mode, root), "build", "skeleton"], root=root)


def live_ai_status(mode: str, root: Path = ROOT) -> dict[str, object]:
    """Inspect canonical backend provider readiness; not a synthetic model probe.

    The existing application observes guard state at /api/ai/providers.
    This is separate from container liveness and standalone GGUF generation.
    """
    command = [
        *compose_command(mode, root), "exec", "-T", "backend", "python", "-c",
        "import json,urllib.request; print(urllib.request.urlopen("
        "'http://127.0.0.1:8001/api/ai/providers',timeout=5).read(65536).decode())",
    ]
    try:
        data = json.loads(_run(command, root=root, capture=True))
    except (LocalDockerError, json.JSONDecodeError) as exc:
        raise LocalDockerError("canonical backend AI readiness unavailable; preserve fail-closed status") from exc
    if not isinstance(data, dict):
        raise LocalDockerError("backend readiness response is not an object")
    # Do not accept a healthy other provider or a simulated/ancestor response.
    observed = (
        data.get("engine") == "skeleton-engine"
        and data.get("active") == "local"
        and data.get("availability_observed") is True
        and type(data.get("llm_available")) is bool
        and isinstance(data.get("providers"), list)
        and "local" in data["providers"]
    )
    return {
        "schema": "skeleton.local-ai.docker.readiness.v1",
        "observed": observed,
        "provider": "local",
        "ready": observed and data.get("llm_available") is True,
        "readiness_code": data.get("active_readiness_code")
        if observed and isinstance(data.get("active_readiness_code"), str) else None,
        "inference_qualified": False,  # Backend availability is not a live chat receipt.
    }


def up(mode: str, root: Path = ROOT) -> None:
    # Both exact-byte admission and REAL one-shot inference must succeed
    # BEFORE service startup. This does NOT qualify the canonical chat guard.
    _run(_isolated_container(mode, "preflight", root=root), root=root, capture=True)
    _run(_isolated_container(mode, "qualify", root=root), root=root, capture=True)
    _run([*compose_command(mode, root), "up", "-d", "--no-build",
          "mongo", "skeleton", "backend", "frontend"], root=root)
    live = live_ai_status(mode, root)
    print(json.dumps(live, sort_keys=True))
    if not live["ready"]:
        raise LocalDockerError(
            "services started but canonical guarded Jeeves chat is unavailable; "
            "trusted bootstrap/tokenizer authority must be qualified before app readiness"
        )


def stop(mode: str, root: Path = ROOT) -> None:
    # Stop only: never 'down', prune, volume delete, migrate Chroma or recreate
    # the existing writable-layer data recovery hold.
    _run([*compose_command(mode, root), "stop", "frontend", "backend", "skeleton", "mongo"], root=root)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=tuple(GPU_OVERLAYS), default="cpu")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("doctor", help="Check effective Compose topology and local provider fences")
    sub.add_parser("build", help="Build canonical engine image, without model acquisition")
    p = sub.add_parser("pin", help="Pin an existing GGUF and llama runtime in the model mount")
    p.add_argument("--model", required=True, help="mount-relative GGUF path")
    p.add_argument("--executable", required=True, help="mount-relative executable path")
    p.add_argument("--profile", default="qwen3-completion-chat",
                   choices=("raw", "llama-completion-chat", "qwen3-completion-chat"))
    p.add_argument("--context", type=int, default=4096)
    p.add_argument("--threads", type=int)
    p.add_argument("--gpu-layers", type=int, default=0)
    sub.add_parser("preflight", help="Offline hash-based artifact validation")
    q = sub.add_parser("qualify", help="Offline REAL GGUF generation, with receipt")
    q.add_argument("--max-output-tokens", type=int, default=32)
    sub.add_parser("up", help="Qualify first, then start the app with local AI")
    sub.add_parser("status", help="Inspect engine and service status; no model activation")
    sub.add_parser("stop", help="Stop services without deleting containers or volumes")
    args = parser.parse_args(argv)
    try:
        if args.action == "doctor":
            print(json.dumps(inspect_config(args.mode), sort_keys=True))
        elif args.action == "build":
            build(args.mode)
        elif args.action in {"pin", "preflight", "qualify"}:
            extra: list[str] = []
            if args.action == "pin":
                extra = [
                    "--model", args.model, "--executable", args.executable,
                    "--profile", args.profile, "--context", str(args.context),
                    "--gpu-layers", str(args.gpu_layers),
                ]
                if args.threads is not None:
                    extra += ["--threads", str(args.threads)]
            if args.action == "qualify":
                extra = ["--max-output-tokens", str(args.max_output_tokens)]
            _run(_isolated_container(args.mode, args.action, extra=extra),
                 capture=False)
        elif args.action == "up":
            up(args.mode)
        elif args.action == "stop":
            stop(args.mode)
        else:
            inspect_config(args.mode)
            _run([*compose_command(args.mode), "ps"], root=ROOT)
            _run([*compose_command(args.mode), "exec", "-T", "skeleton",
                  "python", "-m", "skeleton.app.docker_local_ai",
                  "preflight", "--require-env"], root=ROOT)
            print(json.dumps(live_ai_status(args.mode), sort_keys=True))
    except (LocalDockerError, ValueError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
