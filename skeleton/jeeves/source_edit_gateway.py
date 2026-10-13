"""Jeeves source editing through an injected host editor and exact-change receipts.

This adapter plans narrow, deterministic string replacements against one
host-indexed source file. The host is the only actor that may write bytes. A
model cannot obtain write authority from the source atlas, a patch preview,
or an authorization receipt. Actual dispatch requires:
  * an existing ToolExecutor HIGH_IMPACT grant for exact arguments;
  * an independent per-call host authorization;
  * a trusted host source-edit handler with its own filesystem/project lease;
  * proof that the committed bytes match the exact proposed output digest.

Successful edits trigger incremental atlas refresh, never a full rescan.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .repository_file_atlas import JeevesRepositoryFileAtlas, RepositoryAtlasError

MAX_EDIT_FILE = 256 * 1024
MAX_EDIT_PATCHES = 16
MAX_PATCH_TEXT = 8192
MAX_PLAN_BYTES = 64 * 1024
EDITABLE_SUFFIXES = frozenset({
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".yml",
    ".yaml", ".css", ".html", ".rs", ".go", ".java", ".cs", ".cpp",
    ".h", ".toml", ".ini", ".txt", ".sh",
})


class JeevesSourceEditError(ValueError):
    """Invalid source edit plan, outdated index or missing host authority."""


def _hash(data: bytes) -> str:
    return sha256(data).hexdigest()


def _sha(value: Any, name: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)):
        raise JeevesSourceEditError(f"{name} must be SHA-256")
    return value


def _canonical(value: object) -> bytes:
    try:
        data = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise JeevesSourceEditError("source edit intent must be canonical JSON") from exc
    if len(data) > MAX_PLAN_BYTES:
        raise JeevesSourceEditError("source edit plan exceeds byte budget")
    return data


def _read_original(atlas: JeevesRepositoryFileAtlas, path: str,
                   expected_index: str, expected_content: str) -> str:
    if (not isinstance(path, str) or not 1 <= len(path) <= 2048
            or path.startswith("/") or "\\" in path
            or any(part in {"", ".", ".."} for part in path.split("/"))):
        raise JeevesSourceEditError("edit path must be canonical and relative")
    meta = atlas.metadata()
    if meta["index_sha256"] != expected_index:
        raise JeevesSourceEditError("file atlas snapshot changed since edit proposal")
    node = atlas.lookup(path)
    if node is None or node.owner_root == "unresolved":
        raise JeevesSourceEditError("source edit requires declared file ownership")
    if node.suffix not in EDITABLE_SUFFIXES or node.bytes > MAX_EDIT_FILE:
        raise JeevesSourceEditError("source format or byte count is outside edit policy")
    if node.content_sha256 != expected_content:
        raise JeevesSourceEditError("source must be content-hashed in atlas before edit")
    full = atlas.root / path
    if any(
        (atlas.root / Path(*Path(path).parts[:i])).is_symlink()
        for i in range(1, len(Path(path).parts))
    ) or full.is_symlink() or not full.resolve().is_relative_to(atlas.root):
        raise JeevesSourceEditError("source edit path crosses symlink boundary")
    # This read is strictly preparatory; the host edit handler must repeat the
    # hash/mtime/lease preconditions inside its own atomic write transaction.
    try:
        import os
        import stat
        fd = os.open(full, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode)
                    or info.st_size != node.bytes or info.st_mtime_ns != node.modified_ns):
                raise JeevesSourceEditError("source changed after atlas observation")
            data = stream.read(MAX_EDIT_FILE + 1)
            after = os.fstat(stream.fileno())
            if (after.st_size != info.st_size or after.st_mtime_ns != info.st_mtime_ns
                    or len(data) != info.st_size or _hash(data) != node.content_sha256):
                raise JeevesSourceEditError("source content diverged during edit planning")
        return data.decode("utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        raise JeevesSourceEditError("source is unavailable or not UTF-8") from exc


@dataclass(frozen=True, slots=True)
class SourceReplacement:
    before: str
    after: str

    def __post_init__(self) -> None:
        if not isinstance(self.before, str) or not 1 <= len(self.before) <= MAX_PATCH_TEXT:
            raise JeevesSourceEditError("replacement search text must be 1..8192 characters")
        if not isinstance(self.after, str) or len(self.after) > MAX_PATCH_TEXT:
            raise JeevesSourceEditError("replacement output must be <=8192 characters")
        if self.before == self.after:
            raise JeevesSourceEditError("source replacement does not change content")


@dataclass(frozen=True, slots=True)
class SourceEditPlan:
    project_id: str
    path: str
    index_sha256: str
    before_sha256: str
    after_sha256: str
    replacements: tuple[SourceReplacement, ...]

    def __post_init__(self) -> None:
        if (not isinstance(self.project_id, str) or not self.project_id
                or len(self.project_id) > 192):
            raise JeevesSourceEditError("edit project identity is missing")
        for name in ("index_sha256", "before_sha256", "after_sha256"):
            _sha(getattr(self, name), name)
        if not isinstance(self.replacements, tuple) or not 1 <= len(self.replacements) <= MAX_EDIT_PATCHES:
            raise JeevesSourceEditError("edit plan requires 1..16 bounded replacements")
        if any(not isinstance(x, SourceReplacement) for x in self.replacements):
            raise JeevesSourceEditError("all replacement items must be typed")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "jeeves.source_edit_plan.v1",
            "project_id": self.project_id,
            "path": self.path,
            "index_sha256": self.index_sha256,
            "before_sha256": self.before_sha256,
            "after_sha256": self.after_sha256,
            "replacements": [
                {"before": item.before, "after": item.after}
                for item in self.replacements
            ],
            "dispatch_performed": False,
            "authority": "host_editor_only",
        }

    @property
    def digest(self) -> str:
        return _hash(_canonical(self.to_dict()))


@dataclass(frozen=True, slots=True)
class SourceEditReceipt:
    plan_digest: str
    project_id: str
    path: str
    before_sha256: str
    after_sha256: str
    committed: bool
    host_event_digest: str

    def __post_init__(self) -> None:
        for name in ("plan_digest", "before_sha256", "after_sha256", "host_event_digest"):
            _sha(getattr(self, name), name)
        if type(self.committed) is not bool:
            raise JeevesSourceEditError("source edit receipt committed must be boolean")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "jeeves.source_edit_receipt.v1",
            "plan_digest": self.plan_digest,
            "project_id": self.project_id,
            "path": self.path,
            "before_sha256": self.before_sha256,
            "after_sha256": self.after_sha256,
            "committed": self.committed,
            "host_event_digest": self.host_event_digest,
        }


def plan_source_edit(
    atlas: JeevesRepositoryFileAtlas, *, path: str,
    project_id: str, expected_index_sha256: str,
    expected_source_sha256: str, replacements: tuple[SourceReplacement, ...],
) -> SourceEditPlan:
    if not isinstance(atlas, JeevesRepositoryFileAtlas):
        raise TypeError("host scoped file atlas required")
    _sha(expected_index_sha256, "expected_index_sha256")
    _sha(expected_source_sha256, "expected_source_sha256")
    if (not isinstance(replacements, tuple)
            or not 1 <= len(replacements) <= MAX_EDIT_PATCHES
            or any(not isinstance(item, SourceReplacement) for item in replacements)):
        raise JeevesSourceEditError("typed bounded source replacements required")
    original = _read_original(
        atlas, path, expected_index_sha256, expected_source_sha256,
    )
    updated = original
    for patch in replacements:
        if updated.count(patch.before) != 1:
            raise JeevesSourceEditError("source replacement must target exactly one occurrence")
        updated = updated.replace(patch.before, patch.after, 1)
    encoded = updated.encode("utf-8")
    if len(encoded) > MAX_EDIT_FILE:
        raise JeevesSourceEditError("updated source exceeds edit size limit")
    return SourceEditPlan(
        project_id=project_id, path=path,
        index_sha256=expected_index_sha256,
        before_sha256=_hash(original.encode("utf-8")),
        after_sha256=_hash(encoded), replacements=replacements,
    )


HostEdit = Callable[[SourceEditPlan, Any], SourceEditReceipt]
HostAuthorize = Callable[[SourceEditPlan, Any], bool]


def register_source_edit_tools(
    registry: Any, *, atlas: JeevesRepositoryFileAtlas,
    authorize: HostAuthorize, edit: HostEdit,
    read_authorize: Callable[[str, str, Any], bool] | None = None,
) -> tuple[str, ...]:
    """Explicitly register a high-impact, host-committed source editor."""
    from skeleton.jeeves.agent.tools import (
        ArgumentRule, ToolDenied, ToolRegistry, ToolSpec,
    )
    from skeleton.jeeves.agent.types import RiskTier
    if not isinstance(registry, ToolRegistry) or not isinstance(atlas, JeevesRepositoryFileAtlas):
        raise TypeError("host registry and atlas required")
    if not callable(authorize) or not callable(edit):
        raise TypeError("independent host edit authorization and handler required")
    if read_authorize is not None and not callable(read_authorize):
        raise TypeError("read_authorize must be a host callback")

    def _parse(args: Mapping[str, Any]) -> SourceEditPlan:
        raw = args["replacements"]
        if not isinstance(raw, list) or len(raw) > MAX_EDIT_PATCHES:
            raise JeevesSourceEditError("source replacement array exceeds bound")
        patches = []
        for entry in raw:
            if not isinstance(entry, dict) or set(entry) != {"before", "after"}:
                raise JeevesSourceEditError("source replacement has unsupported fields")
            patches.append(SourceReplacement(**entry))
        return plan_source_edit(
            atlas, path=args["path"], project_id=args["project_id"],
            expected_index_sha256=args["expected_index_sha256"],
            expected_source_sha256=args["expected_source_sha256"],
            replacements=tuple(patches),
        )

    def _perform(args: Mapping[str, Any], context: Any) -> dict[str, object]:
        at_ns = context.metadata.get("observed_at_ns")
        if type(at_ns) is not int or at_ns < 0:
            raise JeevesSourceEditError("host observation timestamp required before edit")
        plan = _parse(args)
        if authorize(plan, context) is not True:
            raise ToolDenied("host denied exact source edit proposal")
        receipt = edit(plan, context)
        if not isinstance(receipt, SourceEditReceipt):
            raise JeevesSourceEditError("host edit handler did not supply typed receipt")
        if (
            not receipt.committed or receipt.plan_digest != plan.digest
            or receipt.project_id != plan.project_id or receipt.path != plan.path
            or receipt.before_sha256 != plan.before_sha256
            or receipt.after_sha256 != plan.after_sha256
        ):
            raise JeevesSourceEditError("host receipt diverges from exact proposed edit")
        # An accepted receipt is not enough to update an index to guessed data.
        # Resample the actual edited file through the host atlas owner.
        atlas.apply_changes(
            [plan.path],
            observed_at_ns=at_ns,
            hash_contents=True,
        )
        actual = atlas.lookup(plan.path)
        if actual is None or actual.content_sha256 != plan.after_sha256:
            raise JeevesSourceEditError("host reported commit but source bytes do not match")
        return receipt.to_dict()

    if read_authorize is not None:
        def _preview(args: Mapping[str, Any], context: Any) -> dict[str, Any]:
            request = {
                "project_id": args["project_id"],
                "path": args["path"],
                "expected_index_sha256": args["expected_index_sha256"],
                "expected_source_sha256": args["expected_source_sha256"],
                "replacements": args["replacements"],
            }
            request_digest = _hash(_canonical(request))
            if read_authorize("app.prepare_source_edit", request_digest, context) is not True:
                raise ToolDenied("host denied scoped edit planning")
            plan = _parse(args)
            return {
                "schema": "jeeves.source_edit_preview.v1",
                "plan": plan.to_dict(),
                "plan_digest": plan.digest,
                "change_count": len(plan.replacements),
                "dispatch_performed": False,
                "execution_authority": "none",
            }

        preview_spec = ToolSpec(
            name="app.prepare_source_edit",
            description="Prepare exact-hash bounded source replacements without committing.",
            risk=RiskTier.READ_ONLY,
            arguments=(
                ArgumentRule("project_id", "string", max_length=192),
                ArgumentRule("path", "string", max_length=2048),
                ArgumentRule("expected_index_sha256", "string", max_length=64),
                ArgumentRule("expected_source_sha256", "string", max_length=64),
                ArgumentRule("replacements", "array", max_length=MAX_EDIT_PATCHES),
            ),
        )
        registry.register(preview_spec, _preview)

    spec = ToolSpec(
        name="app.patch_source_authorized",
        description="Host-authorized exact source replacement with lease/CAS and post-commit index refresh.",
        risk=RiskTier.HIGH_IMPACT,
        idempotent=False, cache_ttl_seconds=None, produces_evidence=True,
        arguments=(
            ArgumentRule("project_id", "string", max_length=192),
            ArgumentRule("path", "string", max_length=2048),
            ArgumentRule("expected_index_sha256", "string", max_length=64),
            ArgumentRule("expected_source_sha256", "string", max_length=64),
            ArgumentRule("replacements", "array", max_length=MAX_EDIT_PATCHES),
        ),
    )
    registry.register(spec, _perform)
    return ("app.prepare_source_edit", spec.name) if read_authorize is not None else (spec.name,)


__all__ = [
    "JeevesSourceEditError", "SourceReplacement", "SourceEditPlan",
    "SourceEditReceipt", "plan_source_edit", "register_source_edit_tools",
]
