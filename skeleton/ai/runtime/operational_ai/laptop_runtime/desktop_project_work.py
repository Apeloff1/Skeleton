"""One exact mixed original source-work package for local Jeeves project edits.

A local model may need to update an existing module while creating new
supporting source files. The older agent only accepted ONE of two proposal
schemas per native SQLite request. This module defines a single strict
envelope that composes those already-authored and independently guarded
reviewers, rather than granting model filesystem or Git authority.

The model's response is untrusted JSON text. Parsing never creates files,
imports model code, reads secrets, starts another model, executes a shell
or mutates any source; the operator's original project root and the
existing descriptor-anchored old-file hashes remain authoritative.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from .desktop_workspace import (
    SCHEMA as NEW_SCHEMA, MAX_FILES as MAX_NEW_FILES,
    WorkspaceDeliveryHold, _canonical, _relative, _source,
)
from .desktop_existing_edits import (
    SCHEMA as EDIT_SCHEMA, MAX_EDITS as MAX_EXISTING_EDITS,
)
from .desktop_patch_bundle import (
    PatchBundleHold, PortablePatchPlan, review_patch_bundle,
)

SCHEMA = "jeeves.workspace.mixed-project-work.v1"
# Match the actual already-enforced MAX_COMMITTED_PROPOSAL_BYTES in the
# same GGUF/SQLite source-repair lane. Do not offer a larger alternate parser
# path which bypasses its original bounded native model-output contract.
MAX_INPUT_BYTES = 16384
MAX_FILES = 24
MAX_ALLOWED_KEYS = frozenset({"schema", "new_files", "existing_edits"})
_NEW_KEYS = frozenset({"path", "content"})
_EDIT_KEYS = frozenset({"path", "expected_sha256", "replacement"})


class MixedWorkHold(ValueError):
    """An untrusted native mixed-work proposal cannot be admitted as source."""


def _strict_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    record = {}
    for key, value in pairs:
        if key in record:
            raise MixedWorkHold("ambiguous duplicate native project-work JSON field")
        record[key] = value
    return record


def _deny_nonfinite(_value: str):
    raise MixedWorkHold("nonfinite number in source work package")


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def _sha(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(ch in "0123456789abcdef" for ch in value)
    )


@dataclass(frozen=True, slots=True)
class MixedNewSource:
    path: str
    content: str
    sha256: str
    bytes: int

    def __post_init__(self):
        try:
            _relative(self.path)
            raw = _source(self.content)
        except (UnicodeError, ValueError, WorkspaceDeliveryHold) as exc:
            raise MixedWorkHold("invalid bounded new original source text/path") from exc
        if (
            not _sha(self.sha256)
            or self.sha256 != sha256(raw).hexdigest()
            or type(self.bytes) is not int or self.bytes != len(raw)
        ):
            raise MixedWorkHold("new source content differs from model proposal digest")

    def portable(self) -> dict[str, str]:
        return {"path": self.path, "content": self.content}


@dataclass(frozen=True, slots=True)
class MixedExistingSource:
    path: str
    expected_sha256: str
    replacement: str
    replacement_sha256: str
    bytes: int

    def __post_init__(self):
        try:
            _relative(self.path)
            raw = _source(self.replacement)
        except (UnicodeError, ValueError, WorkspaceDeliveryHold) as exc:
            raise MixedWorkHold("invalid bounded existing source replacement") from exc
        if (
            not _sha(self.expected_sha256)
            or not _sha(self.replacement_sha256)
            or self.replacement_sha256 != sha256(raw).hexdigest()
            or type(self.bytes) is not int or self.bytes != len(raw)
        ):
            raise MixedWorkHold("old/new source digest or replacement bytes missing")

    def portable(self) -> dict[str, str]:
        return {
            "path": self.path,
            "expected_sha256": self.expected_sha256,
            "replacement": self.replacement,
        }


@dataclass(frozen=True, slots=True)
class MixedWorkPackage:
    new_files: tuple[MixedNewSource, ...]
    existing_edits: tuple[MixedExistingSource, ...]
    package_sha256: str
    source_bytes: int

    def __post_init__(self):
        if (
            type(self.new_files) is not tuple
            or type(self.existing_edits) is not tuple
            or not self.new_files and not self.existing_edits
            or not 1 <= len(self.new_files) + len(self.existing_edits) <= MAX_FILES
            or len(self.new_files) > MAX_NEW_FILES
            or len(self.existing_edits) > MAX_EXISTING_EDITS
            or any(type(x) is not MixedNewSource for x in self.new_files)
            or any(type(x) is not MixedExistingSource for x in self.existing_edits)
        ):
            raise MixedWorkHold("untrusted finite project-work file count")
        for f in (*self.new_files, *self.existing_edits):
            f.__post_init__()
        paths = [f.path.casefold() for f in (*self.new_files, *self.existing_edits)]
        if len(set(paths)) != len(paths):
            raise MixedWorkHold("mixed original new/old paths collide")
        aggregate = sum(x.bytes for x in (*self.new_files, *self.existing_edits))
        if (
            type(self.source_bytes) is not int
            or self.source_bytes != aggregate
            or not 1 <= aggregate <= MAX_INPUT_BYTES
        ):
            raise MixedWorkHold("unbounded mixed source aggregate bytes")
        if (
            not _sha(self.package_sha256)
            or self.package_sha256 != _digest(self.as_canonical())
        ):
            raise MixedWorkHold("mixed project-work envelope digest changed")

    def as_canonical(self) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "new_files": [f.portable() for f in self.new_files],
            "existing_edits": [f.portable() for f in self.existing_edits],
        }

    def to_public(self) -> dict[str, object]:
        return {
            "schema": "jeeves.workspace.mixed-project-work-review.v1",
            "package_sha256": self.package_sha256,
            "new_file_count": len(self.new_files),
            "existing_edit_count": len(self.existing_edits),
            "total_source_bytes": self.source_bytes,
            "new_files": [{
                "path": f.path,
                "replacement_sha256": f.sha256,
                "bytes": f.bytes,
            } for f in self.new_files],
            "existing_edits": [{
                "path": f.path,
                "expected_original_sha256": f.expected_sha256,
                "replacement_sha256": f.replacement_sha256,
                "bytes": f.bytes,
            } for f in self.existing_edits],
            "model_file_write_authorized": False,
            "project_files_modified": False,
            "git_commands_executed": False,
            "operator_review_required": True,
            "release_certified": False,
        }

    def new_plan(self) -> str | None:
        if not self.new_files:
            return None
        return _canonical({
            "schema": NEW_SCHEMA,
            "files": [f.portable() for f in self.new_files],
        }).decode("utf-8", "strict")

    def edits_plan(self) -> str | None:
        if not self.existing_edits:
            return None
        return _canonical({
            "schema": EDIT_SCHEMA,
            "files": [f.portable() for f in self.existing_edits],
        }).decode("utf-8", "strict")


def parse_mixed_work(raw: str | bytes) -> MixedWorkPackage:
    """Strict bounded decoder; reject every unknown permission-bearing field."""
    if type(raw) is str:
        try:
            encoded = raw.encode("utf-8", "strict")
        except UnicodeError as exc:
            raise MixedWorkHold("invalid Unicode native source package") from exc
    elif type(raw) is bytes:
        encoded = raw
    else:
        raise MixedWorkHold("original native mixed package must be JSON text")
    if not 1 <= len(encoded) <= MAX_INPUT_BYTES:
        raise MixedWorkHold("bounded local model response length required")
    try:
        obj = json.loads(
            encoded.decode("utf-8", "strict"),
            object_pairs_hook=_strict_pairs,
            parse_constant=_deny_nonfinite,
        )
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise MixedWorkHold("strict native project-work JSON parsing failed") from exc
    if (
        type(obj) is not dict or frozenset(obj) != MAX_ALLOWED_KEYS
        or obj["schema"] != SCHEMA
        or type(obj["new_files"]) is not list
        or type(obj["existing_edits"]) is not list
    ):
        raise MixedWorkHold("unknown or unsupported combined source-work authority")
    if (
        len(obj["new_files"]) > MAX_NEW_FILES
        or len(obj["existing_edits"]) > MAX_EXISTING_EDITS
        or not 1 <= len(obj["new_files"]) + len(obj["existing_edits"]) <= MAX_FILES
    ):
        raise MixedWorkHold("mixed source files outside original bounded review scope")
    additions = []
    for row in obj["new_files"]:
        if type(row) is not dict or frozenset(row) != _NEW_KEYS:
            raise MixedWorkHold("unapproved new file schema in model project work")
        try:
            data = _source(row["content"])
        except (ValueError, WorkspaceDeliveryHold) as exc:
            raise MixedWorkHold("new source bytes invalid or oversized") from exc
        additions.append(MixedNewSource(
            path=row["path"], content=row["content"],
            sha256=sha256(data).hexdigest(), bytes=len(data),
        ))
    replacements = []
    for row in obj["existing_edits"]:
        if type(row) is not dict or frozenset(row) != _EDIT_KEYS:
            raise MixedWorkHold("unapproved existing edit schema in model work")
        try:
            replacement = _source(row["replacement"])
        except (ValueError, WorkspaceDeliveryHold) as exc:
            raise MixedWorkHold("existing edit bytes invalid or oversized") from exc
        replacements.append(MixedExistingSource(
            path=row["path"],
            expected_sha256=row["expected_sha256"],
            replacement=row["replacement"],
            replacement_sha256=sha256(replacement).hexdigest(),
            bytes=len(replacement),
        ))
    selected_new = tuple(additions)
    selected_existing = tuple(replacements)
    temporary = MixedWorkPackage(
        new_files=selected_new, existing_edits=selected_existing,
        package_sha256=_digest({
            "schema": SCHEMA,
            "new_files": [f.portable() for f in selected_new],
            "existing_edits": [f.portable() for f in selected_existing],
        }),
        source_bytes=sum(f.bytes for f in (*selected_new, *selected_existing)),
    )
    return temporary


def review_mixed_work(
    raw: str | bytes,
    root: str,
) -> tuple[MixedWorkPackage, PortablePatchPlan]:
    """Use original source-specific readers; never accept a fake old digest."""
    parsed = parse_mixed_work(raw)
    try:
        plan = review_patch_bundle(
            root, new_files=parsed.new_plan(),
            existing_edits=parsed.edits_plan(),
        )
    except (ValueError, PatchBundleHold, OSError) as exc:
        raise MixedWorkHold(
            "actual original source bytes or new destination rejected mixed work",
        ) from exc
    if (
        len(plan.entries) != len(parsed.new_files) + len(parsed.existing_edits)
        or sum(e.kind == "new" for e in plan.entries) != len(parsed.new_files)
        or sum(e.kind == "edit" for e in plan.entries) != len(parsed.existing_edits)
    ):
        raise MixedWorkHold("combined project work lost exact original entries")
    return parsed, plan


__all__ = [
    "SCHEMA", "MixedWorkHold", "MixedNewSource", "MixedExistingSource",
    "MixedWorkPackage", "parse_mixed_work", "review_mixed_work",
]
