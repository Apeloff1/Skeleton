"""Deterministic exact-anchor edit engine for autonomous feature builds.

Large existing files should not require a model to reproduce their entire
contents. This module accepts bounded edit data, never executable patches.
Every edit uses an exact literal anchor, requires an unambiguous match, and is
applied by host code to an immutable base or an already-admitted candidate.

There is deliberately no regex replacement, shell patch command, fuzzy match,
path creation, or model-controlled file-system access in this layer.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Callable, Mapping, Sequence

from .build_contracts import (
    BuildBudget,
    CandidateFile,
)


EDIT_KINDS = frozenset(
    {
        "replace",
        "insert_before",
        "insert_after",
        "delete",
    }
)
MAX_EDITS_PER_FILE = 24
MAX_EDIT_FILES = 36
MAX_ANCHOR_BYTES = 24_000
MAX_REPLACEMENT_BYTES = 100_000
MAX_TOTAL_EDIT_BYTES = 600_000


class BuildEditError(ValueError):
    """Structured edit data could not be applied deterministically."""


def _bounded_text(
    value: object,
    *,
    label: str,
    limit: int,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        raise BuildEditError(f"{label} must be text")
    if "\x00" in value:
        raise BuildEditError(f"{label} contains NUL")
    if not value and not allow_empty:
        raise BuildEditError(f"{label} must not be empty")
    if len(value.encode("utf-8")) > limit:
        raise BuildEditError(f"{label} exceeds byte budget")
    return value


def _path(value: object) -> str:
    text = _bounded_text(
        value,
        label="edit path",
        limit=320,
    )
    if (
        text.startswith("/")
        or "\\" in text
        or "//" in text
    ):
        raise BuildEditError("invalid edit path")
    parts = text.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise BuildEditError("invalid edit path component")
    return text


def _strict_mapping(
    value: object,
    *,
    label: str,
    required: set[str],
    optional: set[str] | None = None,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise BuildEditError(f"{label} must be an object")
    optional = optional or set()
    keys = set(value)
    missing = required - keys
    unknown = keys - required - optional
    if missing:
        raise BuildEditError(
            f"{label} missing fields: {sorted(missing)!r}"
        )
    if unknown:
        raise BuildEditError(
            f"{label} has unsupported fields: {sorted(unknown)!r}"
        )
    return value


@dataclass(frozen=True, slots=True)
class TextEdit:
    kind: str
    anchor: str
    replacement: str = ""

    def __post_init__(self) -> None:
        if self.kind not in EDIT_KINDS:
            raise BuildEditError("unsupported edit kind")
        object.__setattr__(
            self,
            "anchor",
            _bounded_text(
                self.anchor,
                label="edit anchor",
                limit=MAX_ANCHOR_BYTES,
            ),
        )
        object.__setattr__(
            self,
            "replacement",
            _bounded_text(
                self.replacement,
                label="edit replacement",
                limit=MAX_REPLACEMENT_BYTES,
                allow_empty=True,
            ),
        )
        if self.kind == "delete" and self.replacement:
            raise BuildEditError(
                "delete edit cannot contain replacement text"
            )
        if (
            self.kind in {"insert_before", "insert_after"}
            and not self.replacement
        ):
            raise BuildEditError(
                "insert edit requires replacement text"
            )

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(
            (
                self.kind
                + "\0"
                + self.anchor
                + "\0"
                + self.replacement
            ).encode("utf-8")
        ).hexdigest()

    @classmethod
    def from_payload(
        cls,
        value: object,
    ) -> "TextEdit":
        item = _strict_mapping(
            value,
            label="text edit",
            required={"kind", "anchor"},
            optional={"replacement"},
        )
        return cls(
            kind=item["kind"],
            anchor=item["anchor"],
            replacement=item.get("replacement", ""),
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "anchor": self.anchor,
            "replacement": self.replacement,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class FileEditPlan:
    path: str
    edits: tuple[TextEdit, ...]
    intent: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _path(self.path))
        if not self.edits:
            raise BuildEditError("file edit plan has no edits")
        if len(self.edits) > MAX_EDITS_PER_FILE:
            raise BuildEditError(
                "file edit plan exceeds edit-count budget"
            )
        object.__setattr__(
            self,
            "intent",
            _bounded_text(
                self.intent,
                label="edit intent",
                limit=4_000,
                allow_empty=True,
            ),
        )
        fingerprints = [
            item.fingerprint
            for item in self.edits
        ]
        if len(fingerprints) != len(set(fingerprints)):
            raise BuildEditError(
                "file edit plan contains duplicate edit operations"
            )

    @property
    def fingerprint(self) -> str:
        digest = hashlib.sha256()
        digest.update(self.path.encode("utf-8"))
        digest.update(b"\0")
        for edit in self.edits:
            digest.update(edit.fingerprint.encode("ascii"))
            digest.update(b"\0")
        return digest.hexdigest()

    @classmethod
    def from_payload(
        cls,
        value: object,
    ) -> "FileEditPlan":
        item = _strict_mapping(
            value,
            label="file edit plan",
            required={"path", "edits"},
            optional={"intent"},
        )
        raw_edits = item["edits"]
        if (
            not isinstance(raw_edits, Sequence)
            or isinstance(raw_edits, (str, bytes))
        ):
            raise BuildEditError(
                "file edit operations must be a list"
            )
        return cls(
            path=item["path"],
            edits=tuple(
                TextEdit.from_payload(edit)
                for edit in raw_edits
            ),
            intent=item.get("intent", ""),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "intent": self.intent,
            "fingerprint": self.fingerprint,
            "edits": [
                item.as_dict()
                for item in self.edits
            ],
        }


@dataclass(frozen=True, slots=True)
class AppliedEdit:
    path: str
    before_digest: str
    after_digest: str
    edit_plan_fingerprint: str
    before_bytes: int
    after_bytes: int

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "before_digest": self.before_digest,
            "after_digest": self.after_digest,
            "edit_plan_fingerprint": self.edit_plan_fingerprint,
            "before_bytes": self.before_bytes,
            "after_bytes": self.after_bytes,
        }


@dataclass(frozen=True, slots=True)
class NormalizedImplementation:
    summary: str
    files: tuple[CandidateFile, ...]
    tests: tuple[str, ...]
    applied_edits: tuple[AppliedEdit, ...]

    def to_shard_payload(self) -> dict[str, object]:
        return {
            "summary": self.summary,
            "files": [
                {
                    "path": item.path,
                    "content": item.content,
                    "intent": item.intent,
                }
                for item in self.files
            ],
            "tests": list(self.tests),
        }


def _sha256(text: str) -> str:
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


def _apply_one(
    content: str,
    edit: TextEdit,
    *,
    path: str,
) -> str:
    count = content.count(edit.anchor)
    if count != 1:
        raise BuildEditError(
            f"edit anchor for {path} matched {count} times; exactly one required"
        )
    index = content.index(edit.anchor)
    end = index + len(edit.anchor)

    if edit.kind == "replace":
        return (
            content[:index]
            + edit.replacement
            + content[end:]
        )
    if edit.kind == "insert_before":
        return (
            content[:index]
            + edit.replacement
            + content[index:]
        )
    if edit.kind == "insert_after":
        return (
            content[:end]
            + edit.replacement
            + content[end:]
        )
    if edit.kind == "delete":
        return content[:index] + content[end:]
    raise BuildEditError("unreachable edit kind")


def apply_edit_plan(
    content: str,
    plan: FileEditPlan,
    *,
    budget: BuildBudget,
) -> tuple[CandidateFile, AppliedEdit]:
    """Apply exact literal edits in listed order with post-edit byte bounds."""
    if not isinstance(content, str):
        raise BuildEditError("edit base content must be text")

    before_digest = _sha256(content)
    before_bytes = len(content.encode("utf-8"))
    current = content

    edit_bytes = 0
    for edit in plan.edits:
        edit_bytes += len(edit.anchor.encode("utf-8"))
        edit_bytes += len(edit.replacement.encode("utf-8"))
        if edit_bytes > MAX_TOTAL_EDIT_BYTES:
            raise BuildEditError(
                "file edit plan exceeds aggregate edit byte budget"
            )
        current = _apply_one(
            current,
            edit,
            path=plan.path,
        )
        if len(current.encode("utf-8")) > budget.max_file_bytes:
            raise BuildEditError(
                f"edited file exceeds configured byte budget: {plan.path}"
            )

    candidate = CandidateFile(
        path=plan.path,
        content=current,
        intent=plan.intent or "structured exact-anchor edit",
    )
    evidence = AppliedEdit(
        path=plan.path,
        before_digest=before_digest,
        after_digest=candidate.digest,
        edit_plan_fingerprint=plan.fingerprint,
        before_bytes=before_bytes,
        after_bytes=len(current.encode("utf-8")),
    )
    return candidate, evidence


def _parse_full_files(
    raw_files: object,
    *,
    budget: BuildBudget,
) -> tuple[CandidateFile, ...]:
    if raw_files is None:
        return ()
    if (
        not isinstance(raw_files, Sequence)
        or isinstance(raw_files, (str, bytes))
    ):
        raise BuildEditError(
            "implementation files must be a list"
        )
    if len(raw_files) > budget.max_files:
        raise BuildEditError(
            "implementation files exceed file budget"
        )

    files = []
    total = 0
    for raw in raw_files:
        item = _strict_mapping(
            raw,
            label="implementation file",
            required={"path", "content"},
            optional={"intent"},
        )
        candidate = CandidateFile(
            path=item["path"],
            content=item["content"],
            intent=item.get("intent", ""),
        )
        size = len(candidate.content.encode("utf-8"))
        if size > budget.max_file_bytes:
            raise BuildEditError(
                f"implementation file exceeds byte budget: {candidate.path}"
            )
        total += size
        if total > budget.max_total_bytes:
            raise BuildEditError(
                "implementation files exceed total byte budget"
            )
        files.append(candidate)
    return tuple(files)


def _parse_edit_plans(
    raw_edits: object,
) -> tuple[FileEditPlan, ...]:
    if raw_edits is None:
        return ()
    if (
        not isinstance(raw_edits, Sequence)
        or isinstance(raw_edits, (str, bytes))
    ):
        raise BuildEditError(
            "implementation edits must be a list"
        )
    if len(raw_edits) > MAX_EDIT_FILES:
        raise BuildEditError(
            "implementation edit files exceed budget"
        )
    result = tuple(
        FileEditPlan.from_payload(item)
        for item in raw_edits
    )
    paths = [item.path for item in result]
    if len(paths) != len(set(paths)):
        raise BuildEditError(
            "implementation contains duplicate edit plans"
        )
    return result


def normalize_implementation_payload(
    payload: object,
    *,
    assigned_paths: Sequence[str],
    budget: BuildBudget,
    source_reader: Callable[[str], str],
    require_all: bool = True,
) -> NormalizedImplementation:
    """Normalize full files plus exact-anchor edits into complete candidate files.

    The source reader is host-owned. It may read immutable HEAD or the current
    admitted candidate during repair. Model data never controls a command.
    """
    item = _strict_mapping(
        payload,
        label="implementation payload",
        required={"summary", "tests"},
        optional={"files", "edits"},
    )
    summary = _bounded_text(
        item["summary"],
        label="implementation summary",
        limit=8_000,
        allow_empty=True,
    )
    raw_tests = item["tests"]
    if (
        not isinstance(raw_tests, Sequence)
        or isinstance(raw_tests, (str, bytes))
    ):
        raise BuildEditError(
            "implementation tests must be a list"
        )
    if len(raw_tests) > budget.max_test_intents:
        raise BuildEditError(
            "implementation tests exceed budget"
        )
    tests = tuple(
        _bounded_text(
            value,
            label="implementation test",
            limit=2_000,
        )
        for value in raw_tests
    )

    full_files = _parse_full_files(
        item.get("files", ()),
        budget=budget,
    )
    edit_plans = _parse_edit_plans(
        item.get("edits", ()),
    )
    full_by_path = {
        candidate.path: candidate
        for candidate in full_files
    }
    edit_by_path = {
        plan.path: plan
        for plan in edit_plans
    }
    overlap = set(full_by_path) & set(edit_by_path)
    if overlap:
        raise BuildEditError(
            "implementation cannot provide both full content and edits "
            "for the same path"
        )

    if not isinstance(require_all, bool):
        raise BuildEditError("require_all must be boolean")
    expected = set(assigned_paths)
    emitted = set(full_by_path) | set(edit_by_path)
    if require_all:
        valid_paths = emitted == expected
    else:
        valid_paths = bool(emitted) and emitted.issubset(expected)
    if not valid_paths:
        missing = sorted(expected - emitted) if require_all else []
        extra = sorted(emitted - expected)
        raise BuildEditError(
            "implementation path set differs from admitted paths: "
            f"missing={missing!r} extra={extra!r}"
        )

    candidates: dict[str, CandidateFile] = dict(full_by_path)
    evidence: list[AppliedEdit] = []
    for path in sorted(edit_by_path):
        try:
            source = source_reader(path)
        except Exception as exc:
            raise BuildEditError(
                f"unable to read admitted edit base for {path}"
            ) from exc
        candidate, applied = apply_edit_plan(
            source,
            edit_by_path[path],
            budget=budget,
        )
        candidates[path] = candidate
        evidence.append(applied)

    total = sum(
        len(candidate.content.encode("utf-8"))
        for candidate in candidates.values()
    )
    if total > budget.max_total_bytes:
        raise BuildEditError(
            "normalized implementation exceeds total byte budget"
        )

    return NormalizedImplementation(
        summary=summary,
        files=tuple(
            candidates[path]
            for path in sorted(candidates)
        ),
        tests=tests,
        applied_edits=tuple(evidence),
    )
