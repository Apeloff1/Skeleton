#!/usr/bin/env python3
"""Prepare and stage *untagged* Docker images for a disconnected local Jeeves host.

Export removes all source tags before sealing the archive. Import requires an
independently communicated receipt hash and exact daemon platform admission.
A staged image remains untagged, cannot replace an existing tag, and cannot
start a container or qualify guarded Jeeves inference.

Only the canonical Docker operator is permitted to invoke these helpers.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import tarfile
from typing import Any

from scripts import local_ai_docker as host
from scripts import local_ai_image_bundle as bundle

PLATFORMS = frozenset({"linux/amd64", "linux/arm64"})
DIFF_ID = re.compile(r"sha256:[a-f0-9]{64}\Z")
MAX_READ = 1024 * 1024
MAX_IMAGE_COUNT = len(bundle.ROLES)
CHUNK = 1024 * 1024


class TransferError(bundle.ImageBundleError):
    """Untrusted transfer data or destination runtime does not meet admission."""


def _load_member(tar: tarfile.TarFile, name: str, *, maximum: int = MAX_READ) -> bytes:
    try:
        info = tar.getmember(name)
    except KeyError as exc:
        raise TransferError("Docker archive metadata member is unavailable") from exc
    if not info.isfile() or not 0 < info.size <= maximum:
        raise TransferError("Docker archive metadata exceeds bounded regular-file admission")
    handle = tar.extractfile(info)
    if handle is None:
        raise TransferError("Docker archive metadata cannot be read")
    value = handle.read(maximum + 1)
    if len(value) != info.size:
        raise TransferError("Docker archive metadata was truncated")
    return value


def _manifest(tar: tarfile.TarFile) -> dict[str, Any]:
    raw = _load_member(tar, "manifest.json", maximum=bundle.MAX_MANIFEST)
    value = bundle._json_bytes(raw, bundle.MAX_MANIFEST)
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise TransferError("Docker save manifest must declare exactly one image")
    record = value[0]
    if (set(record) - {"Config", "Layers", "RepoTags"}
            or not {"Config", "Layers"}.issubset(record)
            or not isinstance(record["Config"], str)
            or not isinstance(record["Layers"], list)
            or not record["Layers"] or len(record["Layers"]) > bundle.MAX_ENTRIES):
        raise TransferError("Docker save single-image manifest is malformed")
    bundle._tar_name(record["Config"])
    for layer in record["Layers"]:
        bundle._tar_name(layer)
    return record


def strip_source_tags(path: Path, expected_image_id: str) -> None:
    """Repack a Docker-save tar with zero repository tags and no legacy index.

    Writes a new same-directory temporary file and replaces only this newly
    exported archive. Existing user archives are not accepted as export input
    by the public operator. No layer extraction and no full-layer buffering.
    """
    if not bundle.IMAGE_ID.fullmatch(expected_image_id):
        raise TransferError("expected Docker image identity invalid")
    bundle._archive_identity(path, expected_image_id)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise TransferError("exported image archive is not a regular private file")
    temporary = path.with_name(path.name + ".untagged-partial")
    if temporary.exists() or temporary.is_symlink():
        raise TransferError("staging path already exists")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL |
        getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    completed = False
    try:
        with os.fdopen(descriptor, "wb") as output:
            with tarfile.open(path, "r:") as original, tarfile.open(
                fileobj=output, mode="w:"
            ) as target:
                manifest = _manifest(original)
                # Preserve exactly one image and the original model of layers
                # while avoiding any tag manipulation on destination Docker.
                changed = dict(manifest)
                changed["RepoTags"] = []
                encoded = json.dumps(
                    [changed], sort_keys=True, separators=(",", ":"),
                    ensure_ascii=True, allow_nan=False,
                ).encode("ascii")
                seen: set[str] = set()
                for member in original:
                    name = bundle._tar_name(member.name)
                    if name in seen or not (member.isfile() or member.isdir()):
                        raise TransferError("unsafe or duplicate saved image member")
                    seen.add(name)
                    if name == "repositories":
                        # Docker's pre-manifest legacy tag mapping must not
                        # reintroduce an image name on the destination.
                        continue
                    cleaned = copy.copy(member)
                    cleaned.uid = cleaned.gid = cleaned.mtime = 0
                    cleaned.uname = cleaned.gname = ""
                    cleaned.pax_headers = {}
                    cleaned.mode = 0o755 if member.isdir() else 0o644
                    if name == "manifest.json":
                        cleaned.size = len(encoded)
                        target.addfile(cleaned, io.BytesIO(encoded))
                    elif member.isdir():
                        target.addfile(cleaned)
                    else:
                        reader = original.extractfile(member)
                        if reader is None:
                            raise TransferError("Docker image member payload unavailable")
                        target.addfile(cleaned, reader)
            output.flush()
            os.fsync(output.fileno())
        bundle._archive_identity(temporary, expected_image_id)
        with tarfile.open(temporary, "r:") as normalized:
            if _manifest(normalized).get("RepoTags") != []:
                raise TransferError("Docker archive still contains source tags")
            try:
                normalized.getmember("repositories")
            except KeyError:
                pass
            else:
                raise TransferError("legacy repository tag index remains in archive")
        os.replace(temporary, path)
        completed = True
    except (tarfile.TarError, OSError, ValueError, EOFError) as exc:
        raise TransferError("cannot safely neutralize Docker source tags") from exc
    finally:
        if not completed:
            # Failed replacement produces no qualified export receipt.
            # The original raw export is still preserved; do not load it.
            try:
                temporary.unlink()
            except OSError:
                pass


def _normalized_arch(name: str) -> str:
    return {
        "x86_64": "amd64", "x86-64": "amd64", "aarch64": "arm64",
        "arm64/v8": "arm64", "amd64": "amd64", "arm64": "arm64",
    }.get(name, "")


def _image_platform_and_layers(path: Path, image_id: str) -> str:
    """Read the pinned image config and rehash all uncompressed layer payloads.

    Docker's image identity proves the config bytes, but the SHA-256 of the
    entire archive alone does not establish that its included layer payloads
    match the image's declared rootfs diff IDs. Assert both independently.
    """
    bundle._archive_identity(path, image_id)
    try:
        with tarfile.open(path, "r:") as saved:
            row = _manifest(saved)
            if row.get("RepoTags") != []:
                raise TransferError("offline image archive has active source tags")
            if "repositories" in saved.getnames():
                raise TransferError("legacy Docker repository tag metadata forbidden")
            # Admit only normal Docker-save metadata and declared layers.
            # A forged archive must not smuggle arbitrary unlisted payloads.
            allowed = {"manifest.json", row["Config"], *row["Layers"]}
            for layer in row["Layers"]:
                parent = Path(layer).parent
                if Path(layer).name == "layer.tar":
                    allowed.add((parent / "json").as_posix())
                    allowed.add((parent / "VERSION").as_posix())
            extras = {
                member.name for member in saved
                if member.isfile() and member.name not in allowed
            }
            if extras:
                raise TransferError("Docker image archive contains undeclared payload files")
            config = _load_member(saved, row["Config"], maximum=bundle.MAX_MANIFEST)
            if hashlib.sha256(config).hexdigest() != image_id.removeprefix("sha256:"):
                raise TransferError("Docker image config differs from immutable identity")
            parsed = bundle._json_bytes(config, bundle.MAX_MANIFEST)
            if not isinstance(parsed, dict):
                raise TransferError("Docker image configuration must be a JSON object")
            os_name = parsed.get("os")
            arch = _normalized_arch(parsed.get("architecture", ""))
            variant = parsed.get("variant")
            if (os_name != "linux" or not arch or
                    (arch == "amd64" and variant not in (None, "")) or
                    (arch == "arm64" and variant not in (None, "", "v8"))):
                raise TransferError("unsupported image architecture or operating system")
            platform = os_name + "/" + arch
            if platform not in PLATFORMS:
                raise TransferError("image platform not in offline admission policy")
            rootfs = parsed.get("rootfs")
            diff_ids = rootfs.get("diff_ids") if isinstance(rootfs, dict) else None
            layers = row["Layers"]
            if (not isinstance(diff_ids, list) or len(diff_ids) != len(layers)
                    or any(not isinstance(digest, str) or
                           not DIFF_ID.fullmatch(digest) for digest in diff_ids)):
                raise TransferError("Docker image rootfs layer digest list inconsistent")
            for path_name, wanted in zip(layers, diff_ids):
                info = saved.getmember(path_name)
                if not info.isfile() or not 0 < info.size <= bundle.MAX_ARCHIVE:
                    raise TransferError("Docker layer is missing or not a regular payload")
                reader = saved.extractfile(info)
                if reader is None:
                    raise TransferError("Docker layer bytes unavailable")
                digest = hashlib.sha256()
                size = 0
                while True:
                    block = reader.read(CHUNK)
                    if not block:
                        break
                    digest.update(block)
                    size += len(block)
                    if size > info.size:
                        raise TransferError("Docker layer exceeded declared size")
                if size != info.size or digest.hexdigest() != wanted[7:]:
                    raise TransferError("Docker uncompressed layer disagrees with config diffID")
            return platform
    except TransferError:
        # Keep bounded policy-denial categories stable for operators and tests.
        raise
    except (tarfile.TarError, OSError, KeyError, EOFError, ValueError) as exc:
        raise TransferError("offline Docker image platform/layer validation failed") from exc


def validate_archive_layers(directory: Path, receipt: dict[str, Any]) -> str:
    """Require all four complete images to contain one compatible Linux platform."""
    platforms = []
    for row in receipt["images"]:
        platforms.append(_image_platform_and_layers(
            directory / row["archive"], row["image_id"]
        ))
    if len(platforms) != MAX_IMAGE_COUNT or len(set(platforms)) != 1:
        raise TransferError("offline bundle images have mixed platforms")
    return platforms[0]


def receipt_digest(directory: Path) -> str:
    """Out-of-band trust fingerprint over the exact sealed receipt bytes."""
    archive = bundle._private_path(directory, existing=True)
    path = archive / bundle.RECEIPT
    value, _ = bundle._digest(path, bundle.MAX_RECEIPT)
    return value


def verify_transfer(directory: Path) -> dict[str, Any]:
    """Daemon-free integrity checks including config, tags and every rootfs layer."""
    receipt = bundle.verify_image_bundle(directory)
    platform = validate_archive_layers(directory, receipt)
    return {
        "schema": "skeleton.local-ai.docker.offline-transfer.v1",
        "status": "verified_untrusted_origin_no_import",
        "receipt_file_sha256": receipt_digest(directory),
        "mode": receipt["mode"],
        "platform": platform,
        "images": [
            {"service": row["service"], "image_id": row["image_id"],
             "sha256": row["sha256"], "bytes": row["bytes"]}
            for row in receipt["images"]
        ],
        "images_loaded": False,
        "tags_changed": False,
        "guarded_chat_qualified": False,
        "recovery_qualified": False,
        "release_qualified": False,
    }


def _daemon_platform(root: Path) -> str:
    """Read only the Docker daemon platform; never inspect host secrets."""
    value = host._run([
        "docker", "info", "--format", "{{.OSType}}/{{.Architecture}}"
    ], root=root, capture=True).strip().lower()
    if len(value) > 64 or value.count("/") != 1:
        raise TransferError("Docker daemon platform unreadable")
    os_name, arch_name = value.split("/")
    arch = _normalized_arch(arch_name)
    observed = os_name + "/" + arch
    if observed not in PLATFORMS:
        raise TransferError("Docker daemon not an admitted Linux architecture")
    return observed


def _trusted_receipt(expected: str, actual: str) -> None:
    if not isinstance(expected, str) or not bundle.HEX.fullmatch(expected):
        raise TransferError("independent expected receipt SHA-256 required")
    if expected != actual:
        raise TransferError("independent expected receipt SHA-256 mismatch")


def plan_import(
    directory: Path, *, expected_receipt_sha256: str,
    mode: str, root: Path = host.ROOT,
) -> dict[str, Any]:
    """Read-only admission before modifying Docker's local image store."""
    report = verify_transfer(directory)
    _trusted_receipt(expected_receipt_sha256, report["receipt_file_sha256"])
    if mode != report["mode"]:
        raise TransferError("selected local model accelerator differs from image bundle mode")
    if _daemon_platform(root) != report["platform"]:
        raise TransferError("destination Docker engine platform differs from saved images")
    return {
        **report,
        "status": "destination_platform_and_image_bytes_admitted_no_load",
        "daemon_platform_matched": True,
        "load_permitted_only_with_explicit_operator_ack": True,
        "source_cryptographic_authentication_verified": False,
    }


def import_untagged_images(
    directory: Path, *, expected_receipt_sha256: str,
    mode: str, allow_image_store_mutation: bool = False,
    root: Path = host.ROOT,
) -> dict[str, Any]:
    """Explicit no-network image staging; never tag, run, pull or replace volumes.

    This function is *not atomic*. A failed later import leaves previously
    loaded untagged images alone for manual inspection; never blindly remove
    objects potentially shared by other Docker clients.
    """
    if allow_image_store_mutation is not True:
        raise TransferError("explicit permission to modify Docker image store required")
    plan = plan_import(directory, expected_receipt_sha256=expected_receipt_sha256,
                       mode=mode, root=root)
    loaded: list[str] = []
    reused: list[str] = []
    receipt = bundle.verify_image_bundle(directory)
    for row in receipt["images"]:
        identity = row["image_id"]
        try:
            found = host._run([
                "docker", "image", "inspect", "--format", "{{.Id}}", identity,
            ], root=root, capture=True).strip()
        except host.LocalDockerError:
            found = ""
        if found:
            if found != identity:
                raise TransferError("Docker image ID conflicts with pinned manifest")
            reused.append(row["service"])
            continue
        # Recheck one immutable archived tar immediately before image loading.
        # The private archive is owner-only. Same-UID adversarial writes remain
        # outside a portable filesystems-only TOCTOU guarantee.
        sha, length = bundle._digest(
            directory / row["archive"], bundle.MAX_ARCHIVE,
        )
        if sha != row["sha256"] or length != row["bytes"]:
            raise TransferError("offline image changed after import preflight")
        if _image_platform_and_layers(
            directory / row["archive"], identity,
        ) != plan["platform"]:
            raise TransferError("image platform changed after admission")
        # The archive manifest has [] RepoTags and no legacy repositories
        # mapping. Docker load creates ONLY image-store objects by ID.
        host._run(["docker", "image", "load",
                   "--input", str(directory / row["archive"])], root=root)
        actual = host._run([
            "docker", "image", "inspect", "--format", "{{.Id}}", identity,
        ], root=root, capture=True).strip()
        if actual != identity:
            raise TransferError("Docker loaded image ID does not match pinned archive")
        loaded.append(row["service"])
    return {
        "schema": "skeleton.local-ai.docker.offline-import.v1",
        "status": "untagged_images_loaded_not_deployment_qualified",
        "receipt_file_sha256": plan["receipt_file_sha256"],
        "platform": plan["platform"],
        "mode": mode,
        "images_loaded": loaded,
        "images_reused": reused,
        "image_store_mutated": bool(loaded),
        "image_store_atomic": False,
        "tags_changed": False,
        "containers_started": False,
        "model_inference_qualified": False,
        "guarded_chat_qualified": False,
        "recovery_qualified": False,
        "release_qualified": False,
    }


__all__ = [
    "strip_source_tags", "verify_transfer", "plan_import",
    "import_untagged_images", "receipt_digest",
]
