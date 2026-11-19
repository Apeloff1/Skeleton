#!/usr/bin/env python3
"""Bind verified, tagless offline Docker image IDs to canonical local-AI Compose.

This is an opt-in, read-only deployment *planning and qualification* surface:
it neither imports, retags, builds, pulls, starts, stops nor deletes containers.
An owner-private, create-only overlay never embeds application secrets. The
source Compose configuration is independently admitted before and after
Docker's actual multi-file merge; only four image references may differ.
Protected Jeeves inference and application recovery remain separately gated.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping

from scripts import local_ai_docker as host
from scripts import local_ai_image_bundle as bundle
from scripts import local_ai_image_transfer as transfer

SCHEMA = "skeleton.local-ai.docker.offline-compose-binding.v1"
FILE = "docker-compose.offline-image-ids.yml"
RECEIPT = "offline-compose-binding.receipt.json"
MAX_COMPOSE_BYTES = 4 * 1024 * 1024
MAX_RECEIPT_BYTES = 32 * 1024
MAX_OVERLAY_BYTES = 4096
_SERVICE_SET = frozenset(bundle.ROLES)
_PROJECT = re.compile(r"[a-z0-9][a-z0-9_-]{0,127}\Z")


class OfflineComposeError(host.LocalDockerError):
    """A local-only image-to-Compose boundary cannot be established."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (ValueError, TypeError, OverflowError) as exc:
        raise OfflineComposeError("offline Compose binding metadata malformed") from exc


def _decode(raw: object, *, ceiling: int, label: str) -> Any:
    if not isinstance(raw, str) or not 0 < len(raw.encode("utf-8")) <= ceiling:
        raise OfflineComposeError(label + " exceeds bounded size")
    try:
        return json.loads(raw, object_pairs_hook=bundle._pairs,
                          parse_constant=bundle._reject_constant)
    except (ValueError, UnicodeError, RecursionError, TypeError,
            bundle.ImageBundleError) as exc:
        raise OfflineComposeError(label + " is invalid JSON") from exc


def _original(mode: str, root: Path) -> dict[str, Any]:
    """Render and qualify the canonical source without exposing interpolated env."""
    admission = host.inspect_config(mode, root)
    if admission.get("provider") != "local" or admission.get("mode") != mode:
        raise OfflineComposeError("canonical local-only Compose provider changed")
    output = host._run([
        *host.compose_command(mode, root), "config", "--format", "json",
    ], root=root, capture=True)
    topology = _decode(output, ceiling=MAX_COMPOSE_BYTES,
                       label="canonical effective Compose")
    if not isinstance(topology, dict):
        raise OfflineComposeError("canonical Compose must render as object")
    # Leave all canonical ingress/security/resource/credential fences intact.
    host._validate_config(mode, topology)
    project = topology.get("name")
    services = topology.get("services")
    if (not isinstance(project, str) or not _PROJECT.fullmatch(project)
            or not isinstance(services, dict)
            or not _SERVICE_SET.issubset(services)
            or set(services) not in (_SERVICE_SET, _SERVICE_SET | {"chroma"})):
        raise OfflineComposeError("canonical local-only services or project changed")
    for service in _SERVICE_SET:
        if not isinstance(services[service], dict):
            raise OfflineComposeError("canonical service metadata malformed")
    return topology


def _ids(receipt: Mapping[str, Any]) -> dict[str, str]:
    records = receipt.get("images")
    if not isinstance(records, list) or len(records) != len(bundle.ROLES):
        raise OfflineComposeError("offline image receipt role inventory invalid")
    result: dict[str, str] = {}
    for role, row in zip(bundle.ROLES, records):
        if (not isinstance(row, dict) or row.get("service") != role
                or not isinstance(row.get("image_id"), str)
                or not bundle.IMAGE_ID.fullmatch(row["image_id"])):
            raise OfflineComposeError("offline image receipt identity invalid")
        result[role] = row["image_id"]
    return result


def _installed(ids: Mapping[str, str], root: Path) -> None:
    """Every pinned ID must exist locally. Tags are never consulted or changed."""
    if set(ids) != _SERVICE_SET:
        raise OfflineComposeError("offline image ID role inventory differs")
    for role in bundle.ROLES:
        digest = ids[role]
        if not isinstance(digest, str) or not bundle.IMAGE_ID.fullmatch(digest):
            raise OfflineComposeError("offline image reference is not digest-bound")
        found = host._run([
            "docker", "image", "inspect", "--format", "{{.Id}}", digest,
        ], root=root, capture=True).strip()
        if found != digest:
            raise OfflineComposeError("pinned offline Docker image not in destination store")


def _overlay_bytes(ids: Mapping[str, str]) -> bytes:
    """Deterministic YAML subset (JSON is valid YAML), exactly four image keys."""
    if set(ids) != _SERVICE_SET or any(
        not isinstance(ids[role], str) or not bundle.IMAGE_ID.fullmatch(ids[role])
        for role in bundle.ROLES
    ):
        raise OfflineComposeError("offline overlay image identity invalid")
    return _canonical({
        "services": {
            role: {"image": ids[role]} for role in bundle.ROLES
        },
    }) + b"\n"


def _expected(original: Mapping[str, Any],
              ids: Mapping[str, str]) -> dict[str, Any]:
    result = copy.deepcopy(original)
    for role in bundle.ROLES:
        result["services"][role]["image"] = ids[role]
    return result


def _render(mode: str, overlay: Path,
            original: Mapping[str, Any], ids: Mapping[str, str],
            root: Path) -> dict[str, Any]:
    if overlay.name != FILE:
        raise OfflineComposeError("offline Compose overlay filename differs")
    raw = host._run([
        *host.compose_command(mode, root), "-f", str(overlay),
        "config", "--format", "json",
    ], root=root, capture=True)
    actual = _decode(raw, ceiling=MAX_COMPOSE_BYTES,
                     label="rendered offline Compose")
    if actual != _expected(original, ids):
        # A config render can produce unrecognized redirects, credentials,
        # external profiles or mounts. Never accept them as a minor diff.
        raise OfflineComposeError("offline Compose changed more than four image identities")
    return actual


def _private_file(root: Path, filename: str, *, maximum: int) -> bytes:
    file = root / filename
    try:
        info = file.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or info.st_mode & 0o077
                or not 0 < info.st_size <= maximum):
            raise OfflineComposeError("offline Compose custody file not owner-private")
        fd = os.open(file, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                     | getattr(os, "O_CLOEXEC", 0))
        try:
            before = os.fstat(fd)
            if (before.st_dev, before.st_ino, before.st_size) != (
                info.st_dev, info.st_ino, info.st_size):
                raise OfflineComposeError("offline Compose file changed before read")
            data = bytearray()
            while len(data) <= maximum:
                chunk = os.read(fd, min(65536, maximum + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
            after = os.fstat(fd)
            now = file.lstat()
            attributes = lambda x: (
                x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns, x.st_ctime_ns
            )
            if (len(data) != info.st_size or len(data) > maximum
                    or attributes(info) != attributes(before)
                    or attributes(info) != attributes(after)
                    or attributes(after) != attributes(now)):
                raise OfflineComposeError("offline Compose custody file changed")
            return bytes(data)
        finally:
            os.close(fd)
    except OSError as exc:
        raise OfflineComposeError("offline Compose custody file unavailable") from exc


def _create_file(root: Path, name: str, data: bytes) -> None:
    """Exclusive-create, no-follow, owner-only metadata; seal receipt last."""
    path = root / name
    descriptor = os.open(
        path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
        getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as output:
            count = output.write(data)
            if count != len(data):
                raise OfflineComposeError("offline Compose custody short write")
            output.flush()
            os.fsync(output.fileno())
    except Exception:
        # Preserve failed private candidate without a finished receipt.
        raise


def _receipt(mode: str, project: str, source_sha256: str,
             ids: Mapping[str, str], overlay_sha256: str,
             platform: str) -> dict[str, Any]:
    if (mode not in host.GPU_OVERLAYS or not _PROJECT.fullmatch(project)
            or not bundle.HEX.fullmatch(source_sha256)
            or not bundle.HEX.fullmatch(overlay_sha256)
            or platform not in transfer.PLATFORMS):
        raise OfflineComposeError("offline binding receipt inputs invalid")
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "four_image_id_compose_render_qualified_not_app_started",
        "mode": mode,
        "project": project,
        "platform": platform,
        "source_receipt_file_sha256": source_sha256,
        "overlay_file": FILE,
        "overlay_sha256": overlay_sha256,
        "images": [{"service": role, "image_id": ids[role]}
                   for role in bundle.ROLES],
        "registry_pull_required": False,
        "compose_no_pull_argument": "--pull never",
        "compose_no_build_argument": "--no-build",
        "images_retagged": False,
        "containers_started": False,
        "model_inference_qualified": False,
        "guarded_chat_qualified": False,
        "writer_epoch_qualified": False,
        "recovery_qualified": False,
        "release_qualified": False,
    }
    result["receipt_sha256"] = hashlib.sha256(_canonical(result)).hexdigest()
    return result


def plan_binding(mode: str, archive: Path, *,
                 expected_receipt_sha256: str,
                 root: Path = host.ROOT) -> dict[str, Any]:
    """No writes, pulls or model execution. Require actual local images."""
    original = _original(mode, root)
    trusted = transfer.plan_import(
        archive, mode=mode, expected_receipt_sha256=expected_receipt_sha256,
        root=root,
    )
    ids = _ids(bundle.verify_image_bundle(archive))
    _installed(ids, root)
    content = _overlay_bytes(ids)
    project = original["name"]
    return {
        **_receipt(
            mode, project, trusted["receipt_file_sha256"], ids,
            hashlib.sha256(content).hexdigest(), trusted["platform"],
        ),
        "source_effective_compose_admitted": True,
        "all_four_image_ids_installed": True,
        "overlay_written": False,
        "actual_overlay_render_verified": False,
    }


def prepare_binding(mode: str, archive: Path, destination: Path, *,
                    expected_receipt_sha256: str,
                    root: Path = host.ROOT) -> dict[str, Any]:
    """Write and qualify a new private overlay; no startup side effects."""
    plan = plan_binding(
        mode, archive, expected_receipt_sha256=expected_receipt_sha256,
        root=root,
    )
    dest = bundle._private_path(destination, existing=False)
    # Repeat effective Compose admission just before any private artifact
    # creation. The original repository files are never written.
    original = _original(mode, root)
    if original["name"] != plan["project"]:
        raise OfflineComposeError("Compose project changed during plan")
    ids = _ids(bundle.verify_image_bundle(archive))
    if [{"service": role, "image_id": ids[role]}
            for role in bundle.ROLES] != plan["images"]:
        raise OfflineComposeError("offline source image identity changed")
    _installed(ids, root)
    dest.mkdir(mode=0o700)
    try:
        data = _overlay_bytes(ids)
        _create_file(dest, FILE, data)
        _render(mode, dest / FILE, original, ids, root)
        _installed(ids, root)
        if hashlib.sha256(_private_file(
            dest, FILE, maximum=MAX_OVERLAY_BYTES
        )).hexdigest() != plan["overlay_sha256"]:
            raise OfflineComposeError("offline overlay changed during rendering")
        # Receipt is always published last; a partial directory is unqualified.
        receipt = _receipt(
            mode, original["name"], expected_receipt_sha256, ids,
            plan["overlay_sha256"], plan["platform"],
        )
        _create_file(dest, RECEIPT, _canonical(receipt) + b"\n")
        result = verify_binding(
            mode, archive, dest, expected_receipt_sha256=expected_receipt_sha256,
            root=root,
        )
        return result
    except Exception as exc:
        raise OfflineComposeError(
            "offline Compose binding incomplete; private partial artifact preserved"
        ) from None


def verify_binding(mode: str, archive: Path, overlay_directory: Path, *,
                   expected_receipt_sha256: str,
                   root: Path = host.ROOT) -> dict[str, Any]:
    """Independently rehash, re-render and re-admit the exact overlay."""
    dest = bundle._private_path(overlay_directory, existing=True)
    if {x.name for x in dest.iterdir()} != {FILE, RECEIPT}:
        raise OfflineComposeError("offline Compose artifact has undeclared members")
    raw = _private_file(dest, RECEIPT, maximum=MAX_RECEIPT_BYTES)
    observed = _decode(raw.decode("utf-8"), ceiling=MAX_RECEIPT_BYTES,
                       label="offline Compose binding receipt")
    plan = plan_binding(
        mode, archive, expected_receipt_sha256=expected_receipt_sha256,
        root=root,
    )
    ids = _ids(bundle.verify_image_bundle(archive))
    data = _private_file(dest, FILE, maximum=MAX_OVERLAY_BYTES)
    if data != _overlay_bytes(ids):
        raise OfflineComposeError("offline Compose overlay bytes differ from pinned IDs")
    expected = _receipt(
        mode, plan["project"], plan["source_receipt_file_sha256"],
        ids, hashlib.sha256(data).hexdigest(), plan["platform"],
    )
    if observed != expected:
        raise OfflineComposeError("offline Compose receipt digest or hold fields changed")
    original = _original(mode, root)
    _render(mode, dest / FILE, original, ids, root)
    _installed(ids, root)
    return {
        **expected,
        "source_effective_compose_admitted": True,
        "all_four_image_ids_installed": True,
        "overlay_written": True,
        "actual_overlay_render_verified": True,
        "offline_up_authorized": False,
    }


def _isolated_pinned_model(mode: str, image_id: str, operation: str, *,
                           root: Path, extra: tuple[str, ...] = ()) -> list[str]:
    """Reuse canonical no-network, bounded one-shot engine by exact Docker ID."""
    if not bundle.IMAGE_ID.fullmatch(image_id) or operation not in (
        "preflight", "qualify"
    ):
        raise OfflineComposeError("offline model image or operation invalid")
    canonical = host.inspect_config(mode, root)
    ordinary_image = canonical.get("image")
    command = host._isolated_container(mode, operation, root=root, extra=extra)
    # The isolated command must be the canonical one, with only its exact
    # image reference replaced; never construct an independent command line
    # with weaker network/mount/device/resource admission.
    required_flags = ("--pull=never", "--read-only", "--cap-drop", "--memory",
                      "--cpus", "--pids-limit", "--shm-size", "--security-opt",
                      "--network")
    if (not isinstance(ordinary_image, str)
            or command.count(ordinary_image) != 1
            or command[:2] != ["docker", "run"]
            or any(flag not in command for flag in required_flags)
            or command[command.index("--network") + 1] != "none"
            or command[command.index("--cap-drop") + 1] != "ALL"):
        raise OfflineComposeError("canonical model isolation command changed")
    result = list(command)
    result[result.index(ordinary_image)] = image_id
    return result


def qualify_offline_model(mode: str, archive: Path,
                          overlay_directory: Path, *,
                          expected_receipt_sha256: str,
                          max_output_tokens: int = 32,
                          root: Path = host.ROOT) -> dict[str, Any]:
    """One real local GGUF generation, not a protected application chat turn.

    Only the canonical Jeeves image and guarded model executable run. No
    extra server, remote fallback, image pull, model acquisition or service
    startup is authorized by this operation.
    """
    if (type(max_output_tokens) is not int
            or not 1 <= max_output_tokens <= 128):
        raise OfflineComposeError("offline model output token budget invalid")
    admitted = verify_binding(
        mode, archive, overlay_directory,
        expected_receipt_sha256=expected_receipt_sha256, root=root,
    )
    ids = {row["service"]: row["image_id"] for row in admitted["images"]}
    engine = ids["skeleton"]
    preflight = _isolated_pinned_model(mode, engine, "preflight", root=root)
    before = host._decode_receipt(
        host._run(preflight, root=root, capture=True), "preflight"
    )
    host._validate_model_mode(mode, before)
    command = _isolated_pinned_model(
        mode, engine, "qualify", root=root,
        extra=("--max-output-tokens", str(max_output_tokens)),
    )
    qualified = host._decode_receipt(
        host._run(command, root=root, capture=True), "qualify"
    )
    host._require_same_model(before, qualified)
    final = verify_binding(
        mode, archive, overlay_directory,
        expected_receipt_sha256=expected_receipt_sha256, root=root,
    )
    if admitted != final:
        raise OfflineComposeError("offline binding changed during model generation")
    # Never leak prompts, generated text, local paths, environment or tokens.
    return {
        "schema": "skeleton.local-ai.docker.offline-gguf-one-shot.v1",
        "status": "native_offline_model_turn_verified_not_protected_chat",
        "mode": mode,
        "engine_image_id": engine,
        "source_receipt_file_sha256": admitted["source_receipt_file_sha256"],
        "model_sha256": qualified["model_sha256"],
        "executable_sha256": qualified["executable_sha256"],
        "manifest_sha256": qualified["manifest_sha256"],
        "native_receipt_digest": qualified["receipt_digest"],
        "model_turn_executed": True,
        "network_required": False,
        "runtime_kind": "llama.cpp-cli",
        "backend_guarded_chat_qualified": False,
        "active_gguf_tokenizer_attested": False,
        "independent_reviewer_attested": False,
        "writer_epoch_qualified": False,
        "physical_gpu_offload_qualified": False,
        "application_recovery_qualified": False,
        "release_qualified": False,
    }


__all__ = ["plan_binding", "prepare_binding", "verify_binding", "qualify_offline_model"]
