#!/usr/bin/env python3
"""Create and independently verify an offline Docker IMAGE byte bundle.

This complements, but does not replace, the GGUF model backup and application
cold-byte archive. An image bundle is intentionally NOT imported/loaded, not
signed, not a portable installation approval, and never contains live volumes.
All Docker interactions are read-only except writing a NEW private host archive.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tarfile
from typing import Any

from scripts import local_ai_docker as host

SCHEMA = "skeleton.local-ai.docker.offline-images.v1"
RECEIPT = "offline-images.receipt.json"
ROLES = ("mongo", "skeleton", "backend", "frontend")
HEX = re.compile(r"[0-9a-f]{64}\Z")
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")
REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9./_:@-]{0,239}\Z")
PROJECT = re.compile(r"[a-z0-9][a-z0-9_-]{0,127}\Z")
MAX_ARCHIVE = 2 * 1024**4
MAX_TOTAL = 8 * 1024**4
MAX_ENTRIES = 200000
MAX_RECEIPT = 128 * 1024
MAX_MANIFEST = 2 * 1024 * 1024
CHUNK = 1024 * 1024


class ImageBundleError(host.LocalDockerError):
    """Image bytes or their owner boundaries are not safely attested."""


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for k, value in items:
        if k in result:
            raise ImageBundleError("duplicate image bundle metadata key")
        result[k] = value
    return result


def _reject_constant(value: str) -> None:
    raise ImageBundleError("nonfinite image bundle metadata value")


def _json_bytes(data: bytes, limit: int) -> Any:
    if not data or len(data) > limit:
        raise ImageBundleError("image bundle metadata exceeds limit")
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_constant=_reject_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ImageBundleError("image bundle metadata malformed") from exc


def _canonical(data: dict[str, Any]) -> bytes:
    return json.dumps(data, sort_keys=True, ensure_ascii=True,
                      allow_nan=False, separators=(",", ":")).encode("ascii")


def _private_path(target: Path, *, existing: bool) -> Path:
    if not isinstance(target, Path) or not target.is_absolute() or len(str(target)) > 2048:
        raise ImageBundleError("image bundle path must be absolute and bounded")
    if any(ord(x) < 32 for x in str(target)):
        raise ImageBundleError("image bundle path contains controls")
    if not hasattr(os, "getuid"):
        raise ImageBundleError("image bundle requires a Unix owner-checked filesystem")
    for part in (target.parent, *target.parent.parents):
        if part.is_symlink():
            raise ImageBundleError("image bundle path may not contain symlinks")
    parent = target.parent
    try:
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ImageBundleError("image bundle parent must be owner-private 0700")
        if existing:
            info = target.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_mode & 0o077 or info.st_nlink < 2):
                raise ImageBundleError("image bundle root must be owner-private 0700")
        elif target.exists() or target.is_symlink():
            raise ImageBundleError("image bundle target must not exist")
    except OSError as exc:
        raise ImageBundleError("image bundle directory unavailable") from exc
    return target


def _file(path: Path, *, maximum: int) -> os.stat_result:
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_uid != os.getuid() or info.st_size <= 0
            or info.st_size > maximum or info.st_mode & 0o077):
        raise ImageBundleError("image bundle file not private and regular")
    return info


def _digest(path: Path, maximum: int) -> tuple[str, int]:
    before = _file(path, maximum=maximum)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_CLOEXEC", 0))
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
                before.st_dev, before.st_ino, before.st_size):
            raise ImageBundleError("image bundle file replaced during open")
        sha = hashlib.sha256()
        total = 0
        while True:
            block = os.read(fd, CHUNK)
            if not block:
                break
            total += len(block)
            if total > maximum:
                raise ImageBundleError("image bundle exceeds byte ceiling")
            sha.update(block)
        after = os.fstat(fd)
        current = path.lstat()
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if identity(before) != identity(after) or identity(after) != identity(current):
            raise ImageBundleError("image bundle changed while hashing")
        return sha.hexdigest(), total
    finally:
        os.close(fd)


def _tar_name(name: object) -> str:
    if not isinstance(name, str) or len(name) > 1024 or not name or "\\" in name:
        raise ImageBundleError("unsafe image archive member path")
    value = name.removesuffix("/")
    path = PurePosixPath(value)
    if (path.is_absolute() or len(path.parts) > 12
            or any(p in ("", ".", "..") for p in value.split("/"))
            or any(ord(c) < 32 for c in value)):
        raise ImageBundleError("unsafe image archive member path")
    return value


def _archive_identity(path: Path, image_id: str) -> dict[str, int]:
    """Parse standard Docker save manifest without extracting even one layer."""
    if not IMAGE_ID.fullmatch(image_id):
        raise ImageBundleError("invalid pinned Docker image ID")
    total = 0
    seen: set[str] = set()
    files: set[str] = set()
    count = 0
    manifest: Any = None
    config_digest = ""
    try:
        with tarfile.open(path, "r:") as bundle:
            for member in bundle:
                count += 1
                if count > MAX_ENTRIES:
                    raise ImageBundleError("too many image archive members")
                name = _tar_name(member.name)
                if name in seen or not (member.isfile() or member.isdir()):
                    raise ImageBundleError("duplicate or nonregular image archive member")
                seen.add(name)
                if member.isdir():
                    continue
                files.add(name)
                total += member.size
                if member.size < 0 or total > MAX_ARCHIVE:
                    raise ImageBundleError("expanded image archive metadata exceeds limits")
                if name == "manifest.json":
                    if member.size > MAX_MANIFEST:
                        raise ImageBundleError("Docker image manifest exceeds size ceiling")
                    reader = bundle.extractfile(member)
                    if reader is None:
                        raise ImageBundleError("Docker image manifest unreadable")
                    manifest = _json_bytes(reader.read(MAX_MANIFEST + 1), MAX_MANIFEST)
            if not isinstance(manifest, list) or len(manifest) != 1:
                raise ImageBundleError("Docker save must contain exactly one image")
            row = manifest[0]
            if (not isinstance(row, dict) or set(row) - {"Config", "RepoTags", "Layers"}
                    or not {"Config", "Layers"}.issubset(row)):
                raise ImageBundleError("Docker save manifest shape invalid")
            config = _tar_name(row["Config"])
            layers = row["Layers"]
            tags = row.get("RepoTags")
            if (config not in files or not config.endswith(".json")
                    or not isinstance(layers, list) or not layers or len(layers) > 100000
                    or len(set(map(str, layers))) != len(layers)
                    or any(_tar_name(value) not in files for value in layers)
                    or (tags is not None and (not isinstance(tags, list)
                        or len(tags) > 64 or any(
                            not isinstance(tag, str) or not REFERENCE.fullmatch(tag)
                            for tag in tags)))):
                raise ImageBundleError("Docker save config, layers or source tags invalid")
            if config in layers:
                raise ImageBundleError("Docker save config overlaps a layer")
            metadata = bundle.getmember(config)
            if metadata.size > MAX_MANIFEST:
                raise ImageBundleError("Docker image configuration exceeds limit")
            stream = bundle.extractfile(metadata)
            if stream is None:
                raise ImageBundleError("Docker image config unreadable")
            raw = stream.read(MAX_MANIFEST + 1)
            config_digest = hashlib.sha256(raw).hexdigest()
            if len(raw) > MAX_MANIFEST or config_digest != image_id[7:]:
                raise ImageBundleError("Docker image config does not match pinned image ID")
            config_data = _json_bytes(raw, MAX_MANIFEST)
            if not isinstance(config_data, dict):
                raise ImageBundleError("Docker image config malformed")
    except ImageBundleError:
        # Policy denials are already redacted, deliberate and specific;
        # do not turn them into an ambiguous generic tar read error.
        raise
    except (tarfile.TarError, EOFError, OSError, OverflowError, ValueError) as exc:
        raise ImageBundleError("invalid or truncated Docker image archive") from exc
    return {"members": count, "payload_bytes": total}


def _inventory(mode: str, root: Path) -> list[dict[str, str]]:
    """Derive four locally present images from validated effective Compose."""
    host.inspect_config(mode, root)
    raw = host._run([*host.compose_command(mode, root), "config",
                     "--format", "json"], root=root, capture=True)
    if not isinstance(raw, str) or len(raw) > 2 * 1024 * 1024:
        raise ImageBundleError("effective Compose image topology unavailable")
    topology = _json_bytes(raw.encode("utf-8"), 2 * 1024 * 1024)
    host._validate_config(mode, topology)
    project = topology.get("name") if isinstance(topology, dict) else None
    services = topology.get("services") if isinstance(topology, dict) else None
    if (not isinstance(project, str) or not PROJECT.fullmatch(project)
            or not isinstance(services, dict)
            or set(services) not in (set(ROLES), set(ROLES) | {"chroma"})):
        raise ImageBundleError("canonical Docker image service topology invalid")
    images: list[dict[str, str]] = []
    for role in ROLES:
        service = services[role]
        if not isinstance(service, dict):
            raise ImageBundleError("canonical image service metadata invalid")
        source = service.get("image") or project + "-" + role
        if not isinstance(source, str) or not REFERENCE.fullmatch(source):
            raise ImageBundleError("unsafe image reference in effective Compose")
        value = host._run(["docker", "image", "inspect", "--format",
                           "{{.Id}}", source], root=root, capture=True).strip()
        if not IMAGE_ID.fullmatch(value):
            raise ImageBundleError("locally built image digest unavailable")
        images.append({"service": role, "source_reference": source, "image_id": value})
    return images


def image_inventory(mode: str, root: Path = host.ROOT) -> dict[str, Any]:
    """Read-only installed image inventory; no registry queries or pulls."""
    rows = _inventory(mode, root)
    return {"schema": SCHEMA, "mode": mode, "images": rows,
            "image_bytes_copied": False, "load_authorized": False,
            "model_inference_qualified": False, "guarded_chat_qualified": False}


def _receipt(rows: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": SCHEMA, "mode": mode, "status": "offline_image_bytes_verified_only",
        "images": rows, "docker_images_loaded": False, "load_authorized": False,
        "model_inference_qualified": False, "guarded_chat_qualified": False,
        "app_recovery_qualified": False, "release_provenance_qualified": False,
    }
    result["receipt_sha256"] = hashlib.sha256(_canonical(result)).hexdigest()
    return result


def verify_image_bundle(directory: Path) -> dict[str, Any]:
    """Verify an existing offline bundle without requiring a Docker daemon."""
    dest = _private_path(directory, existing=True)
    receipt_path = dest / RECEIPT
    _, size = _digest(receipt_path, MAX_RECEIPT)
    if size > MAX_RECEIPT:
        raise ImageBundleError("image bundle receipt too large")
    receipt = _json_bytes(receipt_path.read_bytes(), MAX_RECEIPT)
    if not isinstance(receipt, dict):
        raise ImageBundleError("image bundle receipt must be an object")
    rows = receipt.get("images")
    mode = receipt.get("mode")
    if (mode not in host.GPU_OVERLAYS or not isinstance(rows, list)
            or len(rows) != len(ROLES)):
        raise ImageBundleError("image bundle role/mode declaration invalid")
    expected = {"service", "source_reference", "image_id", "archive", "sha256",
                "bytes", "members", "payload_bytes"}
    total = 0
    clean: list[dict[str, Any]] = []
    for index, role in enumerate(ROLES):
        row = rows[index]
        if (not isinstance(row, dict) or set(row) != expected
                or row.get("service") != role
                or not isinstance(row.get("source_reference"), str)
                or not REFERENCE.fullmatch(row["source_reference"])
                or not isinstance(row.get("image_id"), str)
                or not IMAGE_ID.fullmatch(row["image_id"])
                or row.get("archive") != role + ".tar"
                or not isinstance(row.get("sha256"), str)
                or not HEX.fullmatch(row["sha256"])
                or type(row.get("bytes")) is not int or not 0 < row["bytes"] <= MAX_ARCHIVE
                or type(row.get("members")) is not int or not 1 <= row["members"] <= MAX_ENTRIES
                or type(row.get("payload_bytes")) is not int
                or not 0 < row["payload_bytes"] <= MAX_ARCHIVE):
            raise ImageBundleError("image bundle row lacks bounded canonical identity")
        sha, length = _digest(dest / row["archive"], MAX_ARCHIVE)
        if sha != row["sha256"] or length != row["bytes"]:
            raise ImageBundleError("offline Docker image archive changed")
        identity = _archive_identity(dest / row["archive"], row["image_id"])
        if identity != {"members": row["members"], "payload_bytes": row["payload_bytes"]}:
            raise ImageBundleError("offline Docker archive structure changed")
        total += length
        if total > MAX_TOTAL:
            raise ImageBundleError("offline bundle aggregate byte ceiling exceeded")
        clean.append(dict(row))
    if {entry.name for entry in dest.iterdir()} != {RECEIPT} | {
            role + ".tar" for role in ROLES}:
        raise ImageBundleError("offline bundle contains undeclared members")
    if receipt != _receipt(clean, mode):
        raise ImageBundleError("offline bundle receipt or no-load holds changed")
    return receipt


def export_image_bundle(mode: str, destination: Path,
                        root: Path = host.ROOT) -> dict[str, Any]:
    """Write a new private four-image bundle. Never load, pull or retag images."""
    dest = _private_path(destination, existing=False)
    initial = _inventory(mode, root)
    dest.mkdir(mode=0o700)
    rows: list[dict[str, Any]] = []
    try:
        for row in initial:
            role = row["service"]
            archive = dest / (role + ".tar")
            # Docker save is a local-daemon export. Suppress stdout and stderr:
            # diagnostics may include credentials in unrelated daemon settings.
            host._run(["docker", "image", "save", "--output", str(archive),
                       row["image_id"]], root=root)
            archive.chmod(0o600)
            # A foreign source tag must never mutate a destination tag.
            from scripts.local_ai_image_transfer import strip_source_tags
            strip_source_tags(archive, row["image_id"])
            sha, size = _digest(archive, MAX_ARCHIVE)
            structure = _archive_identity(archive, row["image_id"])
            rows.append({**row, "archive": role + ".tar", "sha256": sha,
                         "bytes": size, **structure})
        if _inventory(mode, root) != initial:
            raise ImageBundleError("image reference moved during offline export")
        receipt = _receipt(rows, mode)
        with (dest / RECEIPT).open("x", encoding="utf-8") as output:
            output.write(_canonical(receipt).decode("ascii") + "\n")
        (dest / RECEIPT).chmod(0o600)
        from scripts.local_ai_image_transfer import verify_transfer
        verify_transfer(dest)  # independently attest layer diffIDs + no tags
        return verify_image_bundle(dest)
    except Exception:
        # Preserve partial output for manual investigation. Without the last
        # receipt it is unqualified and never eligible for automatic loading.
        raise ImageBundleError("offline image export incomplete; partial archive preserved") from None


__all__ = ["image_inventory", "export_image_bundle", "verify_image_bundle"]
