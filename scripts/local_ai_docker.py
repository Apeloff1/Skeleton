#!/usr/bin/env python3
"""Operate a single canonical Skeleton Jeeves image with opt-in CPU/GPU overlays.

No shell commands, silent model downloads, destructive volume operations, remote
model fallback, credentials in logs or independent inference services.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
import stat
import subprocess
import sys
from typing import Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
# Direct invocation must be able to import the repository's explicit
# model custody utility even without editable installation or PYTHONPATH.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BASE = "docker-compose.yml"
LOCAL = "docker-compose.local-ai.yml"
from scripts.local_ai_compose_boundary import (
    ComposeBoundaryError, validate_compose_boundary,
)

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
    # Docker stdout may contain private env, transient proxy URLs or image
    # build output from plugins. Return only explicitly requested private data
    # to the internal validator; never echo untrusted daemon text by default.
    return completed.stdout if capture else ""


def _mount_from_compose(data: Mapping[str, object]) -> tuple[Path, str]:
    services = data.get("services")
    required_services = {"mongo", "skeleton", "backend", "frontend"}
    actual_services = set(services) if isinstance(services, dict) else set()
    if actual_services not in (required_services, required_services | {"chroma"}):
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
    build = skeleton.get("build")
    args = build.get("args") if isinstance(build, dict) else None
    if not isinstance(args, dict) or str(args.get("SKL_LOCAL_ONLY_IMAGE")) != "1":
        raise LocalDockerError("local Jeeves image must exclude hosted inference extras")
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


def _validate_config(mode: str, topology: dict[str, object]) -> dict[str, object]:
    """Check normalized Compose output, including optional Chroma profile."""
    if mode not in GPU_OVERLAYS or not isinstance(topology, dict):
        raise LocalDockerError("invalid Docker local-AI profile or topology")
    mount, image = _mount_from_compose(topology)
    try:
        boundary = validate_compose_boundary(topology)
    except ComposeBoundaryError as exc:
        raise LocalDockerError("full local-only Compose boundary admission failed") from exc
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
        "services": len(topology["services"]),
        "optional_chroma_present": "chroma" in topology["services"],
        "limits": limits,
        "render_gid": render_gid,
        "downloaded_models": False,
        "compose_boundary": boundary,
        "inference_executed": False,
    }


def inspect_config(mode: str, root: Path = ROOT) -> dict[str, object]:
    command = compose_command(mode, root)
    raw = _run([*command, "config", "--format", "json"], root=root, capture=True)
    try:
        topology = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LocalDockerError("Docker Compose returned invalid topology JSON") from exc
    return _validate_config(mode, topology)


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
    providers = data.get("providers")
    local_rows = (
        [row for row in providers if isinstance(row, dict) and row.get("id") == "local"]
        if isinstance(providers, list) else []
    )
    # The real backend's sanitized /api/ai/providers contract exposes a list
    # of dictionaries, not a list of provider-name strings. Verify the engine
    # owner and configured Jeeves identity; do not infer live chat readiness
    # from a remote provider, missing row, or response shape alone.
    local = local_rows[0] if len(local_rows) == 1 else None
    observed = (
        data.get("engine") == "skeleton-engine"
        and data.get("active") == "local"
        and data.get("availability_observed") is True
        and type(data.get("llm_available")) is bool
        and local is not None
        and local.get("ownership") == "engine-process"
        and local.get("model") == "jeeves"
        and type(local.get("available")) is bool
    )
    return {
        "schema": "skeleton.local-ai.docker.readiness.v1",
        "observed": observed,
        "provider": "local",
        "ready": observed and data.get("llm_available") is True and local["available"] is True,
        "readiness_code": data.get("active_readiness_code")
        if observed and isinstance(data.get("active_readiness_code"), str) else None,
        "inference_qualified": False,  # Backend availability is not a live chat receipt.
    }



_RECEIPT_SCHEMAS = {
    "pin": ("skeleton.local-ai.docker.preflight.v1", "pinned_not_inference_qualified"),
    "preflight": ("skeleton.local-ai.docker.preflight.v1", "artifact_verified_not_inference_qualified"),
    "qualify": ("skeleton.local_model.qualification.v1", "qualified"),
}


def _decode_receipt(payload: str, phase: str) -> dict[str, object]:
    """Do not admit a process merely because it exited zero.

    Model execution is external to the host supervisor. Its bounded,
    digest-bound machine receipt is mandatory, distinct from stdout text.
    """
    if phase not in _RECEIPT_SCHEMAS or not isinstance(payload, str) or len(payload) > 32768:
        raise LocalDockerError("local model qualification receipt unavailable")
    try:
        receipt = json.loads(payload)
    except (ValueError, TypeError) as exc:
        raise LocalDockerError("local model qualification did not return a valid receipt") from exc
    schema, status = _RECEIPT_SCHEMAS[phase]
    schema_field = "schema_version" if phase == "qualify" else "schema"
    if (
        not isinstance(receipt, dict)
        or receipt.get("ok") is not True
        or receipt.get(schema_field) != schema
        or receipt.get("status") != status
        or receipt.get("model_id") != "jeeves"
        or receipt.get("provider") != "local"
        or receipt.get("network_required") is not False
    ):
        raise LocalDockerError("local model qualification identity or status is invalid")
    for key in ("manifest_sha256", "model_sha256", "executable_sha256"):
        digest = receipt.get(key)
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise LocalDockerError("local model qualification digest is invalid")
    if phase == "qualify":
        response_id = receipt.get("response_id")
        if (
            receipt.get("runtime_kind") != "llama.cpp-cli"
            or not isinstance(response_id, str)
            or receipt["model_sha256"] not in response_id
            or receipt["executable_sha256"] not in response_id
            or not isinstance(receipt.get("receipt_digest"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", receipt["receipt_digest"])
        ):
            raise LocalDockerError("local model generation has no independent digest-bound receipt")
        # Recompute the canonical local runtime's exact receipt digest. A
        # well-formed but altered response must never authorize service boot.
        signed = dict(receipt)
        expected_digest = signed.pop("receipt_digest")
        # The in-container CLI adds 'ok' around the canonical deployment
        # receipt; it is NOT a member of the engine's signed payload.
        signed.pop("ok", None)
        observed_digest = hashlib.sha256(json.dumps(
            signed, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")).hexdigest()
        if observed_digest != expected_digest:
            raise LocalDockerError("local model generation receipt content changed")
    elif (
        receipt.get("inference_executed") is not False
        or not isinstance(receipt.get("model_bytes"), int)
        or receipt["model_bytes"] <= 0
    ):
        raise LocalDockerError("artifact preflight must not be represented as inference")
    return receipt


def _run_model_step(
    mode: str, action: str, *, root: Path = ROOT,
    extra: Sequence[str] = (),
) -> dict[str, object]:
    argv = _isolated_container(mode, action, root=root, extra=extra)
    return _decode_receipt(_run(argv, root=root, capture=True), action)


def _validate_model_mode(mode: str, receipt: Mapping[str, object]) -> None:
    """A device choice must match the immutable GGUF pin BEFORE generation.

    This is configuration admission, not a proof of actual GPU offload. GPU
    physical qualification is an independent device evidence gate.
    """
    if mode not in GPU_OVERLAYS:
        raise LocalDockerError("unsupported local AI accelerator mode")
    layers = receipt.get("gpu_layers_requested")
    if type(layers) is not int or not 0 <= layers <= 1024:
        raise LocalDockerError("pinned GGUF GPU layer declaration is unavailable")
    if (mode == "cpu" and layers != 0) or (mode != "cpu" and layers == 0):
        raise LocalDockerError("pinned GGUF GPU layers do not match selected Docker mode")
    context = receipt.get("context_size")
    if type(context) is not int or not 256 <= context <= 131072:
        raise LocalDockerError("pinned GGUF context is outside qualified operator range")


def _require_same_model(
    preflight: Mapping[str, object], qualification: Mapping[str, object],
) -> None:
    if any(preflight[k] != qualification[k] for k in (
        "model_id", "model_sha256", "executable_sha256", "manifest_sha256",
    )):
        raise LocalDockerError(
            "local GGUF changed between preflight and inference; service startup denied"
        )

def _epoch_capability_receipt(payload: str, role: str) -> dict[str, object]:
    """Reject contradictory or fabricated-looking process capability results."""
    if role not in ("backend", "engine") or not isinstance(payload, str) or len(payload) > 4096:
        raise LocalDockerError("Mongo epoch capability receipt unavailable")
    try:
        record = json.loads(payload)
    except (ValueError, TypeError) as exc:
        raise LocalDockerError("Mongo epoch capability receipt malformed") from exc
    if (not isinstance(record, dict) or record.get("ok") is not True
            or record.get("role") != role
            or record.get("schema") != "skeleton.local-ai.mongo-epoch-capability.v1"
            or record.get("status") != "replica_primary_linearizable_read_verified_not_writer_fenced"
            or record.get("replica_primary_observed") is not True
            or record.get("linearizable_read_executed") is not True
            or record.get("epoch_records_created") is not False
            or record.get("shared_epoch_writers_bound") is not False
            or record.get("actor_migration_complete") is not False
            or record.get("guarded_chat_qualified") is not False
            or not isinstance(record.get("replica_set"), str)
            or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", record["replica_set"])
            or not isinstance(record.get("primary_fingerprint_sha256"), str)
            or not re.fullmatch(r"[a-f0-9]{64}", record["primary_fingerprint_sha256"])):
        raise LocalDockerError("Mongo epoch capability identity or evidence is invalid")
    return record


def attest_shared_epoch_capability(mode: str, root: Path = ROOT) -> dict[str, object]:
    """Prove both canonical service containers observe the same Mongo primary.

    A read-only prerequisite only: this does NOT initialize or bind writers,
    grant guarded inference, migrate data, or establish actor quiescence.
    """
    inspect_config(mode, root)
    prefix = compose_command(mode, root)
    evidence: dict[str, dict[str, object]] = {}
    for role, service in (("engine", "skeleton"), ("backend", "backend")):
        result = _run([
            *prefix, "exec", "-T", service, "python", "-m",
            "skeleton.persistence.docker_epoch_preflight", "--role", role,
        ], root=root, capture=True)
        evidence[role] = _epoch_capability_receipt(result, role)
    first, second = evidence["engine"], evidence["backend"]
    if (first["replica_set"] != second["replica_set"]
            or first["primary_fingerprint_sha256"] != second["primary_fingerprint_sha256"]):
        raise LocalDockerError("engine/backend do not share one admitted Mongo primary")
    return {
        "schema": "skeleton.local-ai.mongo-epoch-dual-service.v1",
        "status": "shared_replica_primary_capability_verified_not_writer_fenced",
        "replica_set": first["replica_set"],
        "primary_fingerprint_sha256": first["primary_fingerprint_sha256"],
        "engine_read": True,
        "backend_read": True,
        "writer_epoch_bound": False,
        "actor_migration_complete": False,
        "guarded_chat_qualified": False,
        "application_recovery_qualified": False,
    }


def inventory_source_epochs(
    mode: str, *, max_records: int = 1024, root: Path = ROOT,
) -> dict[str, object]:
    """Read-only bounded backend+engine actor inventory, no migration."""
    if type(max_records) is not int or not 1 <= max_records <= 4096:
        raise LocalDockerError("source epoch inventory record budget is invalid")
    # Require actual running daemon and same replica primary first.
    from scripts.local_ai_runtime_attestation import attest_runtime
    attest_runtime(mode, root)
    attest_shared_epoch_capability(mode, root)
    prefix = compose_command(mode, root)
    raw = _run([*prefix, "config", "--format", "json"], root=root, capture=True)
    try:
        topology = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise LocalDockerError("epoch inventory Compose configuration unavailable") from exc
    _validate_config(mode, topology)
    try:
        env = topology["services"]["skeleton"]["environment"]
        engine_database = env["SKL_MONGO_DATABASE"]
    except (TypeError, KeyError):
        raise LocalDockerError("canonical engine memory database identity missing") from None
    if (not isinstance(engine_database, str)
            or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", engine_database)
            or engine_database == "skeleton_guarded_source"):
        raise LocalDockerError("canonical engine memory database identity invalid")
    output = _run([
        *prefix, "exec", "-T", "backend", "python", "-m",
        "skeleton.persistence.docker_epoch_inventory",
        "--engine-database", engine_database,
        "--max-records", str(max_records),
    ], root=root, capture=True)
    if not isinstance(output, str) or len(output) > 8192:
        raise LocalDockerError("source epoch inventory receipt exceeds budget")
    try:
        receipt = json.loads(output)
    except (ValueError, TypeError) as exc:
        raise LocalDockerError("source epoch inventory receipt malformed") from exc
    expected_keys = {
        "ok", "schema", "status", "conversation_records_scanned",
        "memory_records_scanned", "unique_actor_count",
        "conversation_scan_truncated", "memory_scan_truncated",
        "actors_without_epoch", "actors_unstable_or_quarantined",
        "all_sampled_actor_epochs_stable",
        "bounded_complete_for_selected_collections",
        "writer_quiescence_verified", "external_writers_excluded",
        "actor_migration_complete", "guarded_chat_qualified",
        "collections_modified",
    }
    # Explicit schema whitelist: never reflect unexpected backend fields
    # containing actor IDs, Mongo credentials or document content.
    if not isinstance(receipt, dict) or set(receipt) != expected_keys:
        raise LocalDockerError("epoch inventory receipt includes undeclared fields")
    if (receipt.get("ok") is not True
            or receipt.get("schema") != "skeleton.local-ai.mongo-epoch-inventory.v1"
            or receipt.get("status") != "read_only_inventory_not_quiescence_or_migration_qualified"
            or receipt.get("collections_modified") is not False
            or receipt.get("writer_quiescence_verified") is not False
            or receipt.get("external_writers_excluded") is not False
            or receipt.get("actor_migration_complete") is not False
            or receipt.get("guarded_chat_qualified") is not False):
        raise LocalDockerError("epoch inventory cannot grant source migration authority")
    for key in ("conversation_records_scanned", "memory_records_scanned", "unique_actor_count"):
        value = receipt.get(key)
        if type(value) is not int or not 0 <= value <= 2 * max_records:
            raise LocalDockerError("source epoch inventory counts are invalid")
    for key in ("conversation_scan_truncated", "memory_scan_truncated",
                "all_sampled_actor_epochs_stable",
                "bounded_complete_for_selected_collections"):
        if type(receipt.get(key)) is not bool:
            raise LocalDockerError("source epoch inventory completeness evidence invalid")
    incomplete = (receipt["conversation_scan_truncated"]
                  or receipt["memory_scan_truncated"])
    if receipt["bounded_complete_for_selected_collections"] is not (not incomplete):
        raise LocalDockerError("source epoch inventory completeness contradicts bounds")
    if incomplete:
        if (receipt["actors_without_epoch"] is not None
                or receipt["actors_unstable_or_quarantined"] is not None
                or receipt["all_sampled_actor_epochs_stable"] is not False):
            raise LocalDockerError("truncated inventory cannot assert actor epoch coverage")
    else:
        for key in ("actors_without_epoch", "actors_unstable_or_quarantined"):
            value = receipt[key]
            if type(value) is not int or not 0 <= value <= receipt["unique_actor_count"]:
                raise LocalDockerError("inventory actor epoch evidence invalid")
        if receipt["all_sampled_actor_epochs_stable"] is not (
            receipt["actors_without_epoch"] == 0
            and receipt["actors_unstable_or_quarantined"] == 0
        ):
            raise LocalDockerError("inventory actor epoch state is inconsistent")
    return receipt


def up(mode: str, root: Path = ROOT) -> None:
    # Both exact-byte admission and REAL one-shot inference must succeed
    # BEFORE service startup. This does NOT qualify the canonical chat guard.
    first = _run_model_step(mode, "preflight", root=root)
    _validate_model_mode(mode, first)
    qualified = _run_model_step(mode, "qualify", root=root)
    _require_same_model(first, qualified)
    # Docker Compose -d alone returns before backend readiness; bound startup
    # health checks instead of declaring a false unavailable provider on race.
    _run([*compose_command(mode, root), "up", "-d", "--no-build",
          "--pull", "never", "--wait", "--wait-timeout", "180",
          "mongo", "skeleton", "backend", "frontend"], root=root)
    # Independently verify the actual Docker container/image state after --wait;
    # source-valid Compose cannot certify stale or privileged live containers.
    from scripts.local_ai_runtime_attestation import attest_runtime
    print(json.dumps(attest_runtime(mode, root), sort_keys=True))
    print(json.dumps(attest_shared_epoch_capability(mode, root), sort_keys=True))
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
    sub.add_parser("status", help="Inspect actual running service security and readiness")
    sub.add_parser("attest-runtime", help="Read-only attestation of running containers and image IDs")
    sub.add_parser("epoch-preflight", help="Read-only dual-service Mongo primary/linearizable capability")
    sub.add_parser("recovery-preflight", help="Read-only physical Mongo/SQLite/Chroma volume custody and active-writer inventory")
    cold = sub.add_parser("cold-backup-app", help="Opt-in isolated cold byte copy of Mongo, SQLite and optional Chroma volumes")
    cold.add_argument("--destination", type=Path, required=True,
                      help="NEW archive directory under a private operator-owned parent")
    cold.add_argument("--acknowledge-non-atomic", action="store_true",
                      help="Accept that a physical copy is NOT proof of database consistency")
    check = sub.add_parser("verify-cold-app-backup", help="Independently rehash the complete offline application volume archive")
    check.add_argument("--directory", type=Path, required=True)
    inventory = sub.add_parser("epoch-inventory", help="Read-only bounded canonical actor/epoch migration inventory")
    inventory.add_argument("--max-records", type=int, default=1024)
    sub.add_parser("stop", help="Stop services without deleting containers or volumes")
    sub.add_parser("image-inventory", help="Read-only inventory of the four existing locally built images")
    bind_plan = sub.add_parser("plan-offline-compose", help="Read-only no-pull Compose image-ID binding admission")
    bind_plan.add_argument("--directory", type=Path, required=True)
    bind_plan.add_argument("--expected-receipt-sha256", required=True)
    bind_prepare = sub.add_parser("prepare-offline-compose", help="Create a private, attested four-ID Compose override")
    bind_prepare.add_argument("--directory", type=Path, required=True)
    bind_prepare.add_argument("--expected-receipt-sha256", required=True)
    bind_prepare.add_argument("--destination", type=Path, required=True)
    bind_check = sub.add_parser("verify-offline-compose", help="Read-only re-attestation of pinned Compose overlay and daemon")
    bind_check.add_argument("--directory", type=Path, required=True)
    bind_check.add_argument("--expected-receipt-sha256", required=True)
    bind_check.add_argument("--overlay-directory", type=Path, required=True)
    offline_model = sub.add_parser("qualify-offline-model", help="One exact-ID native local GGUF turn with canonical no-network Jeeves")
    offline_model.add_argument("--directory", type=Path, required=True)
    offline_model.add_argument("--expected-receipt-sha256", required=True)
    offline_model.add_argument("--overlay-directory", type=Path, required=True)
    offline_model.add_argument("--max-output-tokens", type=int, default=32)
    fresh_plan = sub.add_parser("plan-fresh-offline-launch", help="Read-only admission for new, empty offline application state")
    fresh_plan.add_argument("--directory", type=Path, required=True)
    fresh_plan.add_argument("--expected-receipt-sha256", required=True)
    fresh_plan.add_argument("--overlay-directory", type=Path, required=True)
    running = sub.add_parser("attest-running-offline", help="Inspect four actual running exact-ID containers and resource boundaries")
    running.add_argument("--directory", type=Path, required=True)
    running.add_argument("--expected-receipt-sha256", required=True)
    running.add_argument("--overlay-directory", type=Path, required=True)
    fresh = sub.add_parser("launch-fresh-offline", help="Opt-in first-install no-pull launch: WRITES NEW application volumes")
    fresh.add_argument("--directory", type=Path, required=True)
    fresh.add_argument("--expected-receipt-sha256", required=True)
    fresh.add_argument("--overlay-directory", type=Path, required=True)
    fresh.add_argument("--allow-new-app-volumes", action="store_true")
    transfer_verify = sub.add_parser("verify-image-transfer", help="Daemon-free tagless and full-layer image archive verification")
    transfer_verify.add_argument("--directory", type=Path, required=True)
    import_plan = sub.add_parser("plan-image-import", help="Validate archived images against destination Docker platform without importing")
    import_plan.add_argument("--directory", type=Path, required=True)
    import_plan.add_argument("--expected-receipt-sha256", required=True)
    load_images = sub.add_parser("import-images", help="Stage verified images by ID; never start containers")
    load_images.add_argument("--directory", type=Path, required=True)
    load_images.add_argument("--expected-receipt-sha256", required=True)
    load_images.add_argument("--allow-image-store-mutation", action="store_true")
    bundle_export = sub.add_parser("export-images", help="Export pinned local Docker images to NEW offline private byte archive")
    bundle_export.add_argument("--destination", type=Path, required=True)
    bundle_verify = sub.add_parser("verify-image-bundle", help="Daemon-free independent rehash of offline Docker image bundle")
    bundle_verify.add_argument("--directory", type=Path, required=True)
    backup = sub.add_parser("backup-model", help="Copy all exact-pinned Jeeves model bytes offline")
    backup.add_argument("--source", type=Path, required=True, help="existing host local AI mount")
    backup.add_argument("--destination", type=Path, required=True, help="new private backup directory")
    verify = sub.add_parser("verify-model-backup", help="Independently rehash a local AI backup")
    verify.add_argument("--directory", type=Path, required=True, help="existing backup directory")
    restore = sub.add_parser(
        "restore-model-backup",
        help="Rehydrate a pinned model backup into a NEW private root (never the live mount)",
    )
    restore.add_argument("--source", type=Path, required=True, help="verified offline model backup root")
    restore.add_argument("--destination", type=Path, required=True, help="new, nonexisting local mount root")
    verify_restore = sub.add_parser(
        "verify-model-restore", help="Read-only rehash of separately restored model bytes"
    )
    verify_restore.add_argument("--directory", type=Path, required=True, help="existing restored model root")
    args = parser.parse_args(argv)
    try:
        if args.action == "plan-fresh-offline-launch":
            from scripts.local_ai_offline_launch import plan_fresh_offline_launch
            print(json.dumps(plan_fresh_offline_launch(
                args.mode, args.directory, args.overlay_directory,
                expected_receipt_sha256=args.expected_receipt_sha256,
            ), sort_keys=True))
        elif args.action == "attest-running-offline":
            from scripts.local_ai_offline_launch import attest_running_offline
            print(json.dumps(attest_running_offline(
                args.mode, args.directory, args.overlay_directory,
                expected_receipt_sha256=args.expected_receipt_sha256,
            ), sort_keys=True))
        elif args.action == "launch-fresh-offline":
            from scripts.local_ai_offline_launch import launch_fresh_offline
            print(json.dumps(launch_fresh_offline(
                args.mode, args.directory, args.overlay_directory,
                expected_receipt_sha256=args.expected_receipt_sha256,
                allow_new_app_volumes=args.allow_new_app_volumes,
            ), sort_keys=True))
        elif args.action == "qualify-offline-model":
            from scripts.local_ai_offline_compose import qualify_offline_model
            print(json.dumps(qualify_offline_model(
                args.mode, args.directory, args.overlay_directory,
                expected_receipt_sha256=args.expected_receipt_sha256,
                max_output_tokens=args.max_output_tokens,
            ), sort_keys=True))
        elif args.action == "plan-offline-compose":
            from scripts.local_ai_offline_compose import plan_binding
            print(json.dumps(plan_binding(
                args.mode, args.directory,
                expected_receipt_sha256=args.expected_receipt_sha256,
            ), sort_keys=True))
        elif args.action == "prepare-offline-compose":
            from scripts.local_ai_offline_compose import prepare_binding
            print(json.dumps(prepare_binding(
                args.mode, args.directory, args.destination,
                expected_receipt_sha256=args.expected_receipt_sha256,
            ), sort_keys=True))
        elif args.action == "verify-offline-compose":
            from scripts.local_ai_offline_compose import verify_binding
            print(json.dumps(verify_binding(
                args.mode, args.directory, args.overlay_directory,
                expected_receipt_sha256=args.expected_receipt_sha256,
            ), sort_keys=True))
        elif args.action == "verify-image-transfer":
            from scripts.local_ai_image_transfer import verify_transfer
            print(json.dumps(verify_transfer(args.directory), sort_keys=True))
        elif args.action == "plan-image-import":
            from scripts.local_ai_image_transfer import plan_import
            print(json.dumps(plan_import(
                args.directory, mode=args.mode,
                expected_receipt_sha256=args.expected_receipt_sha256,
            ), sort_keys=True))
        elif args.action == "import-images":
            from scripts.local_ai_image_transfer import import_untagged_images
            print(json.dumps(import_untagged_images(
                args.directory, mode=args.mode,
                expected_receipt_sha256=args.expected_receipt_sha256,
                allow_image_store_mutation=args.allow_image_store_mutation,
            ), sort_keys=True))
        elif args.action == "image-inventory":
            from scripts.local_ai_image_bundle import image_inventory
            print(json.dumps(image_inventory(args.mode), sort_keys=True))
        elif args.action == "export-images":
            from scripts.local_ai_image_bundle import export_image_bundle
            print(json.dumps(export_image_bundle(args.mode, args.destination), sort_keys=True))
        elif args.action == "verify-image-bundle":
            from scripts.local_ai_image_bundle import verify_image_bundle
            print(json.dumps(verify_image_bundle(args.directory), sort_keys=True))
        elif args.action == "backup-model":
            from scripts.local_ai_model_backup import backup_model
            print(json.dumps(backup_model(args.source, args.destination), sort_keys=True))
        elif args.action == "verify-model-backup":
            from scripts.local_ai_model_backup import verify_backup
            print(json.dumps(verify_backup(args.directory), sort_keys=True))
        elif args.action == "restore-model-backup":
            from scripts.local_ai_model_restore import restore_model_backup
            print(json.dumps(restore_model_backup(args.source, args.destination), sort_keys=True))
        elif args.action == "verify-model-restore":
            from scripts.local_ai_model_restore import verify_restore
            print(json.dumps(verify_restore(args.directory), sort_keys=True))
        elif args.action == "doctor":
            print(json.dumps(inspect_config(args.mode), sort_keys=True))
        elif args.action == "build":
            build(args.mode)
        elif args.action in {"pin", "preflight", "qualify"}:
            extra: list[str] = []
            if args.action == "pin":
                _validate_model_mode(args.mode, {
                    "gpu_layers_requested": args.gpu_layers, "context_size": args.context,
                })
                extra = [
                    "--model", args.model, "--executable", args.executable,
                    "--profile", args.profile, "--context", str(args.context),
                    "--gpu-layers", str(args.gpu_layers),
                ]
                if args.threads is not None:
                    extra += ["--threads", str(args.threads)]
            if args.action == "qualify":
                extra = ["--max-output-tokens", str(args.max_output_tokens)]
            if args.action == "qualify":
                initial = _run_model_step(args.mode, "preflight")
                _validate_model_mode(args.mode, initial)
                completed = _run_model_step(args.mode, "qualify", extra=extra)
                _require_same_model(initial, completed)
            else:
                completed = _run_model_step(args.mode, args.action, extra=extra)
                if args.action == "preflight":
                    _validate_model_mode(args.mode, completed)
            print(json.dumps(completed, sort_keys=True))
        elif args.action == "up":
            up(args.mode)
        elif args.action == "stop":
            stop(args.mode)
        elif args.action == "cold-backup-app":
            from scripts.local_ai_cold_backup import cold_backup_application
            print(json.dumps(cold_backup_application(
                args.mode, args.destination,
                acknowledged_non_atomic=args.acknowledge_non_atomic,
            ), sort_keys=True))
        elif args.action == "verify-cold-app-backup":
            from scripts.local_ai_cold_backup import verify_application_cold_backup
            print(json.dumps(verify_application_cold_backup(args.directory), sort_keys=True))
        elif args.action == "recovery-preflight":
            from scripts.local_ai_recovery import preflight_application_recovery
            print(json.dumps(preflight_application_recovery(args.mode), sort_keys=True))
        elif args.action == "epoch-preflight":
            from scripts.local_ai_runtime_attestation import attest_runtime
            print(json.dumps(attest_runtime(args.mode), sort_keys=True))
            print(json.dumps(attest_shared_epoch_capability(args.mode), sort_keys=True))
        elif args.action == "epoch-inventory":
            print(json.dumps(inventory_source_epochs(
                args.mode, max_records=args.max_records,
            ), sort_keys=True))
        else:
            from scripts.local_ai_runtime_attestation import attest_runtime
            print(json.dumps(attest_runtime(args.mode), sort_keys=True))
            if args.action == "status":
                _run([*compose_command(args.mode), "exec", "-T", "skeleton",
                      "python", "-m", "skeleton.app.docker_local_ai",
                      "preflight", "--require-env"], root=ROOT)
                print(json.dumps(live_ai_status(args.mode), sort_keys=True))
    except (LocalDockerError, ValueError, TypeError, OSError, RuntimeError) as exc:
        # Model custody errors can contain host paths: redact all inner details.
        print(json.dumps({"ok": False, "error": "local AI operation rejected"}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
