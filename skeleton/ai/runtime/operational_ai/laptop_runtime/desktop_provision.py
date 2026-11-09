"""First-run *local* model and SQLite directory provisioning for Jeeves.

Never downloads weights, guesses rights, weakens native source admission or
creates a second state store. Installation uses the original descriptor-
anchored ordered-bundle installer; native startup performs principal binding.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat

from .contracts import identifier


class DesktopProvisionHold(ValueError):
    """Private install/state creation cannot be safely authorized."""


def private_path(value: str | Path) -> Path:
    if not isinstance(value, (str, Path)):
        raise DesktopProvisionHold("absolute private path required")
    path = Path(value)
    if (not path.is_absolute() or ".." in path.parts or chr(0) in str(path)
            or not path.name or path.name in (".", "..")):
        raise DesktopProvisionHold("noncanonical local source/state path")
    return path


def prepare_private_root(value: str | Path) -> dict[str, object]:
    """Create exactly one private directory under an already-trusted parent.

    No recursive mkdir, follow-symlink recovery, permission rewrite, implicit
    migration or adoption of unbound old SQLite content. The native startup
    still owns the exact tenant/model/tokenizer state binding.
    """
    from skeleton.ai.runtime.operational_ai.model.gguf.file_guard import (
        open_trusted_root,
    )

    if os.name != "posix" or not hasattr(os, "getuid"):
        raise DesktopProvisionHold(
            "POSIX/WSL2 descriptor-anchored private provisioning required"
        )
    path = private_path(value)
    parent = open_trusted_root(path.parent)
    directory = None
    created = False
    try:
        try:
            os.mkdir(path.name, mode=0o700, dir_fd=parent)
            created = True
            os.fsync(parent)
        except FileExistsError:
            pass
        directory = os.open(
            path.name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent,
        )
        details = os.fstat(directory)
        if (
            not stat.S_ISDIR(details.st_mode)
            or details.st_uid != os.getuid()
            or details.st_mode & 0o077
            or details.st_nlink < 1
        ):
            raise DesktopProvisionHold("private state root ownership or mode unsafe")
        # Creation is not a principal binding and never becomes proof that an
        # existing state may be rebound or adopted by a new user.
        return {
            "schema": "jeeves.desktop.private-root.v1",
            "status": "new-private-root" if created else "existing-private-root",
            "native_model_started": False,
            "principal_binding_established": False,
            "release_certified": False,
        }
    finally:
        if directory is not None:
            os.close(directory)
        os.close(parent)


def install_local_approved_archive(
    archive: str | Path, install_root: str | Path,
    *, model_id: str, install_id: str,
) -> dict[str, object]:
    """Only the canonical approved ordered-bundle installer may publish GGUF."""
    from skeleton.ai.runtime.operational_ai.deployment.install.installer import (
        install_approved_model,
    )

    archive_path = private_path(archive)
    destination_root = private_path(install_root)
    identifier(model_id, "model ID")
    identifier(install_id, "installation ID")
    receipt = install_approved_model(
        archive_path, destination_root, model_id=model_id, install_id=install_id,
    )
    return {
        "schema": "jeeves.desktop.local-install.v1",
        "status": "installed-content-checked-not-licensed-by-this-tool",
        "destination": receipt.destination,
        "model_sha256": receipt.model_sha256,
        "manifest_sha256": receipt.manifest_sha256,
        "archive_sha256": receipt.archive_sha256,
        "source_sha": receipt.source_sha,
        "installed_bytes": receipt.installed_bytes,
        "installed_files": receipt.installed_files,
        "rights_review_independent": False,
        "native_model_started": False,
        "release_certified": False,
    }


def inspect_existing_model(model_root: str | Path) -> dict[str, object]:
    """Read independently installed source receipt without loading GGUF."""
    from skeleton.ai.runtime.operational_ai.deployment.install.doctor import (
        inspect_installed_model,
    )

    report = inspect_installed_model(private_path(model_root))
    return {
        "schema": "jeeves.desktop.source-inspection.v1",
        "status": "installed-source-inspected",
        "model_id": report.model_id,
        "model_sha256": report.model_sha256,
        "manifest_sha256": report.manifest_sha256,
        "source_sha": report.source_sha,
        "archive_sha256": report.archive_sha256,
        "installed_model_bytes": report.model_bytes,
        "installed_shard_count": report.shard_count,
        "content_verified": report.content_verified is True,
        "package_rights_marked_approved": report.rights_approved is True,
        "native_model_started": False,
        "release_certified": False,
    }


__all__ = [
    "DesktopProvisionHold", "private_path", "prepare_private_root",
    "install_local_approved_archive", "inspect_existing_model",
]
