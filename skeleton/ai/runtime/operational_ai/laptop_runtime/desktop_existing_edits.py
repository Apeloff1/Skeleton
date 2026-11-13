"""Source-checked review of proposed edits to EXISTING local project files.

The AI supplies text, never filesystem authority. An operator selects a
trusted workspace, inspects the original byte hash and unified diff, then
approves publication of one no-clobber sibling CANDIDATE. The existing file
is never overwritten, truncated, renamed, deleted or executed. The operator
can subsequently apply reviewed changes in their own editor/version control.
This deliberately avoids claiming Linux offers a general conditional atomic
compare-and-swap rename against non-cooperating concurrent writers.
"""
from __future__ import annotations

from dataclasses import dataclass
import difflib
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import stat

from .desktop_workspace import (
    WorkspaceDeliveryHold,
    _canonical, _unique, _constant, _relative, _source,
    _open_root, _parent, _absent, _rename_no_replace,
)

SCHEMA = "jeeves.workspace.existing-file-edits.v1"
MAX_EDITS = 8
MAX_SOURCE_BYTES = 65536
MAX_AGGREGATE_REPLACEMENT = 196608
MAX_MANIFEST_BYTES = 262144
MAX_REVIEW_BYTES = 98304


class ExistingEditHold(WorkspaceDeliveryHold):
    """An existing-file edit cannot be reviewed or published safely."""


@dataclass(frozen=True, slots=True)
class CheckedEdit:
    path: str
    original_sha256: str
    original_bytes: int
    original_device: int
    original_inode: int
    original_mtime_ns: int
    original_mode: int
    original_text: str
    replacement_text: str
    replacement_sha256: str
    replacement_bytes: int

    def __post_init__(self):
        _relative(self.path)
        if (
            type(self.original_sha256) is not str
            or len(self.original_sha256) != 64
            or type(self.replacement_sha256) is not str
            or len(self.replacement_sha256) != 64
            or any(
                char not in "0123456789abcdef"
                for digest in (self.original_sha256, self.replacement_sha256)
                for char in digest
            )
        ):
            raise ExistingEditHold("invalid original/replacement source identities")
        for name in (
            "original_bytes", "original_device", "original_inode",
            "original_mtime_ns", "original_mode", "replacement_bytes",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ExistingEditHold("invalid source filesystem snapshot")
        if not 1 <= self.original_bytes <= MAX_SOURCE_BYTES:
            raise ExistingEditHold("source edit original is outside finite bound")
        if not 1 <= self.replacement_bytes <= MAX_SOURCE_BYTES:
            raise ExistingEditHold("source edit replacement is outside finite bound")
        if self.original_inode < 1:
            raise ExistingEditHold("original inode identity missing")
        original = _checked_bytes(self.original_text)
        replacement = _checked_bytes(self.replacement_text)
        if (
            len(original) != self.original_bytes
            or len(replacement) != self.replacement_bytes
            or sha256(original).hexdigest() != self.original_sha256
            or sha256(replacement).hexdigest() != self.replacement_sha256
            or original == replacement
        ):
            raise ExistingEditHold("source change content/identity not verified")


@dataclass(frozen=True, slots=True)
class ExistingEditPlan:
    root: str
    root_device: int
    root_inode: int
    manifest_sha256: str
    edits: tuple[CheckedEdit, ...]

    def __post_init__(self):
        if type(self.root) is not str or not Path(self.root).is_absolute():
            raise ExistingEditHold("original trusted source root required")
        if ".." in Path(self.root).parts or chr(0) in self.root:
            raise ExistingEditHold("source root contains traversal")
        if (
            type(self.root_device) is not int or self.root_device < 0
            or type(self.root_inode) is not int or self.root_inode < 1
        ):
            raise ExistingEditHold("original source root identity is absent")
        if (
            type(self.edits) is not tuple
            or not 1 <= len(self.edits) <= MAX_EDITS
            or any(type(edit) is not CheckedEdit for edit in self.edits)
        ):
            raise ExistingEditHold("finite reviewed existing-file edit plan required")
        if (
            len({e.path.casefold() for e in self.edits}) != len(self.edits)
            or sum(e.replacement_bytes for e in self.edits)
            > MAX_AGGREGATE_REPLACEMENT
        ):
            raise ExistingEditHold("source edit paths or aggregate byte ceiling invalid")
        if _manifest_digest(self.edits) != self.manifest_sha256:
            raise ExistingEditHold("reviewed source edit manifest was modified")


def _checked_bytes(value: object) -> bytes:
    try:
        result = _source(value)
    except (UnicodeError, ValueError, WorkspaceDeliveryHold) as exc:
        raise ExistingEditHold("source change must be finite exact UTF-8 text") from exc
    if len(result) > MAX_SOURCE_BYTES:
        raise ExistingEditHold("source edit input exceeds bound")
    return result


def _manifest_digest(edits: tuple[CheckedEdit, ...]) -> str:
    return sha256(_canonical({
        "schema": SCHEMA,
        "files": [{
            "path": e.path,
            "expected_sha256": e.original_sha256,
            "replacement": e.replacement_text,
        } for e in edits],
    })).hexdigest()


def _read_original(parent_fd: int, name: str) -> tuple[bytes, os.stat_result]:
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise ExistingEditHold("safe POSIX source snapshots required")
    original_fd = os.open(
        name,
        os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_CLOEXEC", 0),
        dir_fd=parent_fd,
    )
    try:
        before = os.fstat(original_fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_mode & 0o022
            or before.st_nlink != 1
            or not 1 <= before.st_size <= MAX_SOURCE_BYTES
        ):
            raise ExistingEditHold("untrusted writable, aliased or unbounded original")
        raw = bytearray()
        while len(raw) < before.st_size + 1:
            fragment = os.read(
                original_fd, min(4096, before.st_size + 1 - len(raw)),
            )
            if not fragment:
                break
            raw.extend(fragment)
        after = os.fstat(original_fd)
        fingerprint = lambda s: (
            s.st_dev, s.st_ino, s.st_size, s.st_mode,
            s.st_mtime_ns, s.st_uid, s.st_nlink,
        )
        if len(raw) != before.st_size or fingerprint(before) != fingerprint(after):
            raise ExistingEditHold("existing source changed during exact snapshot")
        try:
            original = bytes(raw).decode("utf-8", "strict")
        except UnicodeError as exc:
            raise ExistingEditHold("original source is not UTF-8") from exc
        if chr(0) in original or not original.strip():
            raise ExistingEditHold("binary/empty original source denied")
        return bytes(raw), before
    finally:
        os.close(original_fd)


def parse_existing_edits(
    proposal: str | bytes, root: str | Path,
) -> ExistingEditPlan:
    """Read-only source snapshot; no destination paths are created."""
    if type(proposal) is str:
        try:
            raw = proposal.encode("utf-8", "strict")
        except UnicodeError as exc:
            raise ExistingEditHold("invalid source proposal Unicode") from exc
    elif type(proposal) is bytes:
        raw = proposal
    else:
        raise ExistingEditHold("strict existing-file edit JSON required")
    if not 2 <= len(raw) <= MAX_MANIFEST_BYTES:
        raise ExistingEditHold("existing-file proposal outside finite limit")
    try:
        doc = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_unique, parse_constant=_constant,
        )
    except (ValueError, UnicodeError, TypeError) as exc:
        raise ExistingEditHold("invalid strict source edit JSON") from exc
    if type(doc) is not dict or set(doc) != {"schema", "files"} or doc["schema"] != SCHEMA:
        raise ExistingEditHold("unsupported existing-file edit schema")
    rows = doc["files"]
    if type(rows) is not list or not 1 <= len(rows) <= MAX_EDITS:
        raise ExistingEditHold("invalid number of proposed existing-file edits")
    if not isinstance(root, (Path, str)):
        raise ExistingEditHold("explicit absolute trusted local root required")
    path = Path(root)
    if not path.is_absolute() or ".." in path.parts or chr(0) in str(path):
        raise ExistingEditHold("noncanonical local workspace root")
    anchored = _open_root(str(path))
    try:
        identity = os.fstat(anchored)
        entries: list[CheckedEdit] = []
        for row in rows:
            if (
                type(row) is not dict
                or set(row) != {"path", "expected_sha256", "replacement"}
            ):
                raise ExistingEditHold("unexpected source edit fields")
            relative = row["path"]
            _relative(relative)
            declared = row["expected_sha256"]
            if (
                type(declared) is not str
                or len(declared) != 64
                or any(x not in "0123456789abcdef" for x in declared)
            ):
                raise ExistingEditHold("source edit requires full expected SHA-256")
            replacement = row["replacement"]
            replacement_bytes = _checked_bytes(replacement)
            parent, filename = _parent(anchored, relative)
            try:
                source, info = _read_original(parent, filename)
            finally:
                os.close(parent)
            original_digest = sha256(source).hexdigest()
            if original_digest != declared:
                raise ExistingEditHold("source edit expected hash does not match current file")
            entries.append(CheckedEdit(
                path=relative,
                original_sha256=original_digest,
                original_bytes=len(source),
                original_device=info.st_dev,
                original_inode=info.st_ino,
                original_mtime_ns=info.st_mtime_ns,
                original_mode=info.st_mode,
                original_text=source.decode("utf-8", "strict"),
                replacement_text=replacement,
                replacement_sha256=sha256(replacement_bytes).hexdigest(),
                replacement_bytes=len(replacement_bytes),
            ))
        selected = tuple(entries)
        return ExistingEditPlan(
            root=str(path), root_device=identity.st_dev,
            root_inode=identity.st_ino,
            manifest_sha256=_manifest_digest(selected), edits=selected,
        )
    finally:
        os.close(anchored)


def preview_existing_edit(plan: ExistingEditPlan, index: int) -> dict[str, object]:
    if (
        type(plan) is not ExistingEditPlan
        or type(index) is not int
        or not 0 <= index < len(plan.edits)
    ):
        raise ExistingEditHold("typed reviewed existing-file edit index required")
    plan.__post_init__()
    item = plan.edits[index]
    rendered = "".join(difflib.unified_diff(
        item.original_text.splitlines(keepends=True),
        item.replacement_text.splitlines(keepends=True),
        fromfile="a/" + item.path,
        tofile="b/" + item.path,
        lineterm="\n",
    ))
    if len(rendered.encode("utf-8", "strict")) > MAX_REVIEW_BYTES:
        raise ExistingEditHold("change diff too large to review in this UI")
    return {
        "schema": "jeeves.workspace.existing-edit-review.v1",
        "path": item.path,
        "original_sha256": item.original_sha256,
        "replacement_sha256": item.replacement_sha256,
        "original_bytes": item.original_bytes,
        "replacement_bytes": item.replacement_bytes,
        "manifest_sha256": plan.manifest_sha256,
        "diff": rendered,
        "existing_file_modified": False,
        "review_before_candidate": True,
        "operator_must_apply_to_original_separately": True,
        "release_certified": False,
    }


def _candidate_absent(parent: int, destination: str) -> None:
    """Unify no-clobber refusal with existing-source typed API holds."""
    try:
        _absent(parent, destination)
    except WorkspaceDeliveryHold as exc:
        raise ExistingEditHold("reviewed candidate already exists; no overwrite") from exc


def stage_existing_edit_candidate(
    plan: ExistingEditPlan, index: int, *,
    expected_manifest_sha256: str, expected_original_sha256: str,
    expected_replacement_sha256: str, approved: bool,
) -> dict[str, object]:
    """Publish a NEW inert source candidate; NEVER overwrite the original.

    This cannot race an existing source file into being overwritten: the
    conditional hash is applied to a pinned descriptor, while publication
    targets a distinct no-clobber filename. The candidate alone is not a
    modification to existing source; actual application remains human-owned.
    """
    if approved is not True:
        raise ExistingEditHold("explicit operator digest approval required")
    if (
        type(plan) is not ExistingEditPlan
        or type(index) is not int
        or not 0 <= index < len(plan.edits)
    ):
        raise ExistingEditHold("finite typed source edit plan required")
    plan.__post_init__()
    item = plan.edits[index]
    if (
        type(expected_manifest_sha256) is not str
        or expected_manifest_sha256 != plan.manifest_sha256
        or type(expected_original_sha256) is not str
        or expected_original_sha256 != item.original_sha256
        or type(expected_replacement_sha256) is not str
        or expected_replacement_sha256 != item.replacement_sha256
    ):
        raise ExistingEditHold("operator-approved original/replacement identity changed")
    root_fd = _open_root(plan.root)
    try:
        root = os.fstat(root_fd)
        if (root.st_dev, root.st_ino) != (plan.root_device, plan.root_inode):
            raise ExistingEditHold("reviewed workspace root was replaced")
        parent, filename = _parent(root_fd, item.path)
        try:
            original, original_stat = _read_original(parent, filename)
            if (
                sha256(original).hexdigest() != item.original_sha256
                or original_stat.st_dev != item.original_device
                or original_stat.st_ino != item.original_inode
                or original_stat.st_mtime_ns != item.original_mtime_ns
                or original_stat.st_mode != item.original_mode
            ):
                raise ExistingEditHold("existing source changed after review")
            # A controlled candidate basename cannot execute by extension.
            # It is visibly distinct from the original and excluded from
            # the search index's supported source file extensions.
            binding = sha256(
                (item.path + item.original_sha256 + item.replacement_sha256)
                .encode("utf-8", "strict")
            ).hexdigest()
            destination = ".jeeves-edit-candidate-" + binding[:32] + ".txt"
            _candidate_absent(parent, destination)
            temporary = ".jeeves-stage-" + secrets.token_hex(16)
            stage_fd = os.open(
                temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
                0o600, dir_fd=parent,
            )
            try:
                try:
                    new_bytes = _checked_bytes(item.replacement_text)
                    written = 0
                    while written < len(new_bytes):
                        count = os.write(stage_fd, new_bytes[written:])
                        if type(count) is not int or count <= 0:
                            raise ExistingEditHold("incomplete private candidate staging")
                        written += count
                    os.fsync(stage_fd)
                    stage = os.fstat(stage_fd)
                    if (
                        not stat.S_ISREG(stage.st_mode)
                        or stage.st_uid != os.getuid()
                        or stage.st_nlink != 1
                        or stage.st_mode & 0o077
                        or stage.st_size != len(new_bytes)
                    ):
                        raise ExistingEditHold("candidate staging integrity changed")
                finally:
                    os.close(stage_fd)
                # Do not claim the original is unchanged merely because it
                # matched earlier: check the same pinned original path again.
                rechecked, observed = _read_original(parent, filename)
                if (
                    sha256(rechecked).hexdigest() != item.original_sha256
                    or observed.st_dev != item.original_device
                    or observed.st_ino != item.original_inode
                    or observed.st_mtime_ns != item.original_mtime_ns
                ):
                    raise ExistingEditHold("source changed during candidate publication")
                _candidate_absent(parent, destination)
                _rename_no_replace(parent, temporary, destination)
                os.fsync(parent)
            finally:
                try:
                    os.unlink(temporary, dir_fd=parent)
                except FileNotFoundError:
                    pass
            # Verify exact committed candidate bytes before publishing
            # the single-file, non-application receipt.
            candidate_fd = os.open(
                destination, os.O_RDONLY | os.O_NOFOLLOW
                | getattr(os, "O_CLOEXEC", 0), dir_fd=parent,
            )
            try:
                state = os.fstat(candidate_fd)
                if (
                    not stat.S_ISREG(state.st_mode)
                    or state.st_uid != os.getuid()
                    or state.st_mode & 0o077
                    or state.st_nlink != 1
                    or state.st_size != item.replacement_bytes
                ):
                    raise ExistingEditHold("published edit candidate metadata changed")
                received = bytearray()
                while len(received) < item.replacement_bytes:
                    chunk = os.read(
                        candidate_fd, min(4096, item.replacement_bytes - len(received)),
                    )
                    if not chunk:
                        break
                    received.extend(chunk)
                if sha256(received).hexdigest() != item.replacement_sha256:
                    raise ExistingEditHold("published edit candidate bytes changed")
            finally:
                os.close(candidate_fd)
            return {
                "schema": "jeeves.workspace.existing-edit-candidate.v1",
                "status": "candidate-atomically-created-no-original-write",
                "original_path": item.path,
                "original_sha256": item.original_sha256,
                "candidate_name": destination,
                "replacement_sha256": item.replacement_sha256,
                "candidate_bytes": item.replacement_bytes,
                "manifest_sha256": plan.manifest_sha256,
                "existing_file_modified": False,
                "source_review_required_before_manual_application": True,
                "native_model_authorized_file_write": False,
                "release_certified": False,
            }
        finally:
            os.close(parent)
    finally:
        os.close(root_fd)


__all__ = [
    "ExistingEditHold", "CheckedEdit", "ExistingEditPlan",
    "parse_existing_edits", "preview_existing_edit",
    "stage_existing_edit_candidate",
]
