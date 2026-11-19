#!/usr/bin/env python3
"""Real Docker CI-only isolated source-tag-neutral offline transport qualification.

Creates only one uniquely named disposable synthetic image, never an app
container, named volume, GGUF, persistent state or model inference. This is
not a user-facing destructive image cleanup command. Do not invoke it against
an application host: it intentionally deletes only the probe image it creates.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import sys
import tarfile
import tempfile
from typing import Sequence

from scripts import local_ai_image_bundle as bundle
from scripts import local_ai_image_transfer as transfer

SCHEMA = "skeleton.local-ai.docker.physical-synthetic-image-transfer.v1"
STAGES = frozenset({
    "daemon-platform", "prepare-rootfs", "source-image-import",
    "source-image-inspect", "archive-export", "archive-neutralization",
    "archive-layer-validation", "source-image-removal", "source-removal-verification",
    "archive-rehash", "image-load", "loaded-image-inspect",
    "source-tag-collision-check", "unclassified",
})


class EphemeralTransferError(RuntimeError):
    """A real Docker synthetic probe could not be safely qualified."""


def _command(args: Sequence[str], *, timeout: int = 300, may_fail: bool = False) -> str:
    if any(not isinstance(value, str) or not value for value in args):
        raise EphemeralTransferError("synthetic Docker argv invalid")
    try:
        done = subprocess.run(list(args), text=True, capture_output=True,
                              check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EphemeralTransferError("synthetic Docker daemon unavailable") from exc
    if len(done.stdout) > 8192 or len(done.stderr) > 8192:
        raise EphemeralTransferError("synthetic Docker diagnostic exceeds bound")
    if done.returncode != 0:
        if may_fail:
            return ""
        raise EphemeralTransferError("synthetic Docker command failed")
    return done.stdout.strip()


def _rootfs(path: Path, nonce: str) -> None:
    data = ("offline image custody nonce: " + nonce + "\n").encode()
    with tarfile.open(path, "w:") as archive:
        info = tarfile.TarInfo("offline-image-integrity.txt")
        info.size = len(data)
        info.mode = 0o644
        info.uid = info.gid = 0
        info.mtime = 0
        archive.addfile(info, io.BytesIO(data))
    path.chmod(0o600)


def qualify_physical_image_transfer() -> dict[str, object]:
    """One ephemeral daemon image proves actual save/sanitize/load, never app readiness."""
    try:
        docker = _command(["docker", "info", "--format",
                           "{{.OSType}}/{{.Architecture}}"], timeout=30).lower()
    except EphemeralTransferError:
        raise EphemeralTransferError("daemon-platform") from None
    if docker not in ("linux/x86_64", "linux/amd64", "linux/aarch64", "linux/arm64"):
        raise EphemeralTransferError("Docker CI physical platform unavailable")
    nonce = secrets.token_hex(16)
    tag = "skl-ephemeral-offline-" + nonce + ":ci"
    identity: str | None = None
    removed_source = False
    stage_completed = False
    with tempfile.TemporaryDirectory(prefix="skl-physical-offline-") as folder:
        root = Path(folder)
        root.chmod(0o700)
        source = root / "synthetic-rootfs.tar"
        saved = root / "saved-image.tar"
        try:
            stage = "prepare-rootfs"
            _rootfs(source, nonce)
            # docker image import consumes a local tar without pulling a base
            # image or accessing an upstream registry.
            stage = "source-image-import"
            imported = _command(["docker", "image", "import",
                                 str(source), tag])
            if not bundle.IMAGE_ID.fullmatch(imported):
                raise EphemeralTransferError("synthetic import did not yield an image ID")
            stage = "source-image-inspect"
            identity = _command([
                "docker", "image", "inspect", "--format", "{{.Id}}", tag,
            ])
            if imported != identity:
                raise EphemeralTransferError("synthetic source image identity differs")
            stage = "archive-export"
            _command(["docker", "image", "save", "--output", str(saved), identity])
            saved.chmod(0o600)
            stage = "archive-neutralization"
            transfer.strip_source_tags(saved, identity)
            stage = "archive-layer-validation"
            first, first_bytes = bundle._digest(saved, bundle.MAX_ARCHIVE)
            platform = transfer._image_platform_and_layers(saved, identity)
            if platform not in transfer.PLATFORMS:
                raise EphemeralTransferError("synthetic archive platform unsupported")
            stage = "source-image-removal"
            if not _command(["docker", "image", "rm", tag]):
                raise EphemeralTransferError("synthetic source tag was not removed")
            removed_source = True
            stage = "source-removal-verification"
            if _command(["docker", "image", "inspect", "--format",
                         "{{.Id}}", identity], may_fail=True):
                raise EphemeralTransferError("synthetic source image still exists")
            stage = "archive-rehash"
            second, second_bytes = bundle._digest(saved, bundle.MAX_ARCHIVE)
            if second != first or second_bytes != first_bytes:
                raise EphemeralTransferError("synthetic transport bytes changed")
            stage = "image-load"
            _command(["docker", "image", "load", "--input", str(saved)])
            stage = "loaded-image-inspect"
            restored = _command([
                "docker", "image", "inspect", "--format", "{{.Id}}", identity,
            ])
            if restored != identity:
                raise EphemeralTransferError("physical restored image identity changed")
            stage = "source-tag-collision-check"
            if _command(["docker", "image", "inspect", "--format",
                         "{{.Id}}", tag], may_fail=True):
                raise EphemeralTransferError("unsafe source tag restored on load")
            stage_completed = True
            return {
                "schema": SCHEMA,
                "status": "physical_synthetic_untagged_image_transfer_verified",
                "actual_docker_daemon_executed": True,
                "synthetic_image_id": identity,
                "transport_sha256": second,
                "transport_bytes": second_bytes,
                "platform": platform,
                "original_source_tag_absent_after_load": True,
                "tagless_load_executed": True,
                "model_inference_executed": False,
                "real_application_image_loaded": False,
                "real_application_volume_accessed": False,
                "guarded_chat_qualified": False,
                "real_world_platform_portability_qualified": False,
                "release_qualified": False,
            }
        except (EphemeralTransferError, bundle.ImageBundleError,
                OSError, ValueError, tarfile.TarError) as exc:
            # The source policy produces only these fixed messages. Never
            # report arbitrary Docker output or confidential host paths.
            category = {
                "Docker save must contain exactly one image": "manifest-count",
                "Docker save manifest shape invalid": "manifest-shape",
                "Docker save config, layers or source tags invalid": "layer-index",
                "Docker image config does not match pinned image ID": "config-identity",
                "Docker image config malformed": "config-json",
                "duplicate or nonregular image archive member": "member-type",
                "unsafe image archive member path": "member-path",
                "invalid or truncated Docker image archive": "tar-parser",
                "Docker archive metadata member is unavailable": "metadata-path",
                "Docker archive metadata exceeds bounded regular-file admission": "metadata-size",
                "Docker archive metadata was truncated": "metadata-truncated",
                "Docker save single-image manifest is malformed": "manifest-fields",
                "unsafe or duplicate saved image member": "copy-member-shape",
                "Docker image member payload unavailable": "copy-file-reader",
                "Docker archive still contains source tags": "source-tags-remain",
                "legacy repository tag index remains in archive": "legacy-tags-remain",
                "cannot safely neutralize Docker source tags": "tar-repack",
                "Docker image archive contains undeclared payload files": "undeclared-payload",
                "Docker image rootfs layer digest list inconsistent": "diffid-list",
            }.get(str(exc))
            if stage == "archive-neutralization" and category:
                stage = "archive-" + category
            raise EphemeralTransferError(stage) from None
        finally:
            # Strictly isolated randomized CI asset cleanup; never touch the
            # repository's canonical images, running services or any volume.
            if identity and bundle.IMAGE_ID.fullmatch(identity):
                if stage_completed or removed_source:
                    _command(["docker", "image", "rm", identity],
                             timeout=60, may_fail=True)
                else:
                    _command(["docker", "image", "rm", tag],
                             timeout=60, may_fail=True)


def main() -> int:
    try:
        print(json.dumps(qualify_physical_image_transfer(), sort_keys=True))
        return 0
    except (EphemeralTransferError, bundle.ImageBundleError, OSError,
            ValueError, tarfile.TarError) as exc:
        fixed_stage = str(exc)
        if fixed_stage not in STAGES and not fixed_stage.startswith("archive-"):
            fixed_stage = "unclassified"
        if len(fixed_stage) > 64 or not all(
            ch.islower() or ch.isdigit() or ch == "-" for ch in fixed_stage
        ):
            fixed_stage = "unclassified"
        print(json.dumps({
            "ok": False, "schema": SCHEMA, "stage": fixed_stage,
            "error": "physical synthetic Docker image transfer unavailable",
        }), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
