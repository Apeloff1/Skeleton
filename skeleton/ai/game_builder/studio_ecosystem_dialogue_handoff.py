"""Private, integrity-checked handoff of authored NPC dialogue scene cards.

No external storage, implicit trust, network access or release qualification.
The consumer must recompile the cards against the exact canonical source.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from .studio_ecosystem_dialogue_staging import compile_dialogue_staging
from .studio_ecosystem_quest import StudioQuestError

HANDOFF_SCHEMA = "skeleton.game_builder.studio_dialogue_handoff.v1"
MAX_HANDOFF_BYTES = 256 * 1024
_FILES = frozenset({"dialogue.json", "receipt.json"})


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical dialogue handoff") from exc


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def _safe_directory(path: Path) -> None:
    if (not isinstance(path, Path) or ".." in path.parts
            or path.name in ("", ".", "..") or path.is_symlink()):
        raise StudioQuestError("invalid dialogue handoff path")


def _parent_fd(path: Path) -> int:
    # The immediate parent is held open while creating the child. Refuse
    # linked parents instead of resolving an untrusted destination silently.
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise StudioQuestError("invalid dialogue handoff parent")
    return os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)


def _strict_json(raw: bytes) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise StudioQuestError("duplicate dialogue handoff JSON key")
            output[key] = value
        return output
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite dialogue handoff JSON")),
        )
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise StudioQuestError("invalid dialogue handoff JSON") from exc
    if type(value) is not dict:
        raise StudioQuestError("invalid dialogue handoff root")
    return value


def export_dialogue_handoff(
    output: Path, documents: Mapping[str, Any], actions: list[list[str]], *,
    authorized: bool, scene_id: str | None = None,
    expected_source_digest: str | None = None,
) -> dict[str, object]:
    """Atomically create a private two-file source-leased editor handoff."""
    if authorized is not True:
        raise PermissionError("dialogue handoff export requires operator authorization")
    _safe_directory(output)
    if output.exists():
        raise StudioQuestError("dialogue handoff destination already exists")
    staging = compile_dialogue_staging(
        documents, actions, scene_id=scene_id, authorized=True,
        expected_source_digest=expected_source_digest)
    manifest = {
        "schema": HANDOFF_SCHEMA, "project_id": staging["project_id"],
        "source_digest": staging["source_digest"],
        "actions": actions, "scene_id": scene_id, "staging": staging,
    }
    manifest_bytes = _canonical(manifest) + b"\n"
    receipt: dict[str, object] = {
        "schema": HANDOFF_SCHEMA,
        "project_id": staging["project_id"],
        "source_digest": staging["source_digest"],
        "staging_digest": staging["staging_digest"],
        "manifest_sha256": sha256(manifest_bytes).hexdigest(),
        "file_write_performed": True,
        "external_evidence_verified": False,
        "release_certified": False,
    }
    receipt["receipt_digest"] = _digest(receipt)
    payloads = {
        "dialogue.json": manifest_bytes,
        "receipt.json": _canonical(receipt) + b"\n",
    }
    if any(len(data) > MAX_HANDOFF_BYTES for data in payloads.values()):
        raise StudioQuestError("dialogue handoff artifact exceeds byte budget")
    parent_fd = _parent_fd(output)
    directory_fd: int | None = None
    created: list[str] = []
    made = False
    try:
        os.mkdir(output.name, mode=0o700, dir_fd=parent_fd)
        made = True
        directory_fd = os.open(
            output.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=parent_fd)
        for name, data in payloads.items():
            handle = os.open(
                name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600, dir_fd=directory_fd)
            created.append(name)
            with os.fdopen(handle, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        os.fsync(directory_fd)
        os.fsync(parent_fd)
    except BaseException:
        for name in reversed(created):
            try:
                if directory_fd is not None:
                    os.unlink(name, dir_fd=directory_fd)
            except OSError:
                pass
        if made:
            try:
                os.rmdir(output.name, dir_fd=parent_fd)
            except OSError:
                pass
        raise
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
        os.close(parent_fd)
    return receipt


def import_dialogue_handoff(
    source_dir: Path, documents: Mapping[str, Any], *,
    authorized: bool, expected_source_digest: str | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    """Revalidate every imported byte against current original source."""
    if authorized is not True:
        raise PermissionError("dialogue handoff import requires operator authorization")
    _safe_directory(source_dir)
    parent_fd = _parent_fd(source_dir)
    directory_fd: int | None = None
    try:
        directory_fd = os.open(
            source_dir.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=parent_fd)
        if set(os.listdir(directory_fd)) != _FILES:
            raise StudioQuestError("dialogue handoff contains unexpected files")
        raw: dict[str, bytes] = {}
        for name in sorted(_FILES):
            handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
            with os.fdopen(handle, "rb") as stream:
                status = os.fstat(stream.fileno())
                if (not stat.S_ISREG(status.st_mode)
                        or status.st_size > MAX_HANDOFF_BYTES):
                    raise StudioQuestError("invalid dialogue handoff artifact")
                data = stream.read(MAX_HANDOFF_BYTES + 1)
                if len(data) > MAX_HANDOFF_BYTES:
                    raise StudioQuestError("dialogue handoff artifact grew during read")
                raw[name] = data
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
        os.close(parent_fd)
    manifest = _strict_json(raw["dialogue.json"])
    receipt = _strict_json(raw["receipt.json"])
    if (set(manifest) != {"schema", "project_id", "source_digest",
                         "actions", "scene_id", "staging"}
            or manifest.get("schema") != HANDOFF_SCHEMA
            or receipt.get("schema") != HANDOFF_SCHEMA
            or receipt.get("release_certified") is not False
            or receipt.get("file_write_performed") is not True
            or receipt.get("external_evidence_verified") is not False):
        raise StudioQuestError("invalid dialogue handoff schema or qualification")
    unsigned = dict(receipt)
    checksum = unsigned.pop("receipt_digest", None)
    if (type(checksum) is not str or checksum != _digest(unsigned)
            or receipt.get("manifest_sha256") != sha256(raw["dialogue.json"]).hexdigest()):
        raise StudioQuestError("dialogue handoff digest mismatch")
    staging = compile_dialogue_staging(
        documents, manifest["actions"], scene_id=manifest["scene_id"],
        authorized=True, expected_source_digest=expected_source_digest)
    if (staging != manifest["staging"]
            or staging["project_id"] != manifest["project_id"]
            or staging["source_digest"] != manifest["source_digest"]
            or staging["source_digest"] != receipt.get("source_digest")
            or staging["staging_digest"] != receipt.get("staging_digest")
            or staging["project_id"] != receipt.get("project_id")):
        raise StudioQuestError("dialogue handoff does not match current source")
    return staging, receipt
