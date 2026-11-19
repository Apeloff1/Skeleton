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
    docker = _command(["docker", "info", "--format",
                       "{{.OSType}}/{{.Architecture}}"], timeout=30).lower()
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
        _rootfs(source, nonce)
        try:
            # docker image import consumes a local tar without pulling a base
            # image or accessing an upstream registry.
            imported = _command(["docker", "image", "import",
                                 str(source), tag])
            if not bundle.IMAGE_ID.fullmatch(imported):
                raise EphemeralTransferError("synthetic import did not yield an image ID")
            identity = _command([
                "docker", "image", "inspect", "--format", "{{.Id}}", tag,
            ])
            if imported != identity:
                raise EphemeralTransferError("synthetic source image identity differs")
            _command(["docker", "image", "save", "--output", str(saved), identity])
            saved.chmod(0o600)
            transfer.strip_source_tags(saved, identity)
            first, first_bytes = bundle._digest(saved, bundle.MAX_ARCHIVE)
            platform = transfer._image_platform_and_layers(saved, identity)
            if platform not in transfer.PLATFORMS:
                raise EphemeralTransferError("synthetic archive platform unsupported")
            if not _command(["docker", "image", "rm", tag]):
                raise EphemeralTransferError("synthetic source tag was not removed")
            removed_source = True
            if _command(["docker", "image", "inspect", "--format",
                         "{{.Id}}", identity], may_fail=True):
                raise EphemeralTransferError("synthetic source image still exists")
            second, second_bytes = bundle._digest(saved, bundle.MAX_ARCHIVE)
            if second != first or second_bytes != first_bytes:
                raise EphemeralTransferError("synthetic transport bytes changed")
            _command(["docker", "image", "load", "--input", str(saved)])
            restored = _command([
                "docker", "image", "inspect", "--format", "{{.Id}}", identity,
            ])
            if restored != identity:
                raise EphemeralTransferError("physical restored image identity changed")
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
            ValueError, tarfile.TarError):
        print(json.dumps({
            "ok": False, "schema": SCHEMA,
            "error": "physical synthetic Docker image transfer unavailable",
        }), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
