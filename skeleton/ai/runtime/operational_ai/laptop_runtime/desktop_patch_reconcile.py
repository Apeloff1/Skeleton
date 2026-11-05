"""Non-destructive three-way source reconciliation for offline Jeeves patches.

A reviewed model proposal may become stale when an editor updates its original
project. This module rechecks pinned real descriptors and produces an entirely
NEW human-reviewed proposal for nonoverlapping line changes. It NEVER touches
original project bytes, stages changes, executes Git, accepts conflicting
changes automatically or reuses old SHA approval after a rebase.

Base = exact original source bytes independently reviewed by the operator.
Local = freshly read current project bytes.
Proposed = Jeeves' originally reviewed replacement bytes.
Every merge is line-level and conservative: ambiguous/overlapping changes
hold instead of inventing a conflict resolution.
"""
from __future__ import annotations

from dataclasses import dataclass
import difflib
from hashlib import sha256
import json
import os

from .desktop_patch_bundle import (
    PatchBundleHold, PatchEntry, PortablePatchPlan, _split_lines,
)
from .desktop_existing_edits import (
    SCHEMA as EDIT_SCHEMA, _read_original, MAX_SOURCE_BYTES,
    MAX_AGGREGATE_REPLACEMENT,
)
from .desktop_workspace import (
    SCHEMA as NEW_SCHEMA, WorkspaceDeliveryHold,
    _open_root, _parent, _absent, _canonical,
)

SCHEMA = "jeeves.workspace.conservative-three-way-reconcile.v1"
MAX_LINES = 2048
MAX_HUNKS = 256
MAX_DIAGNOSTICS = 24


class PatchReconcileHold(ValueError):
    """Original source has changed or a safe no-write rebase is impossible."""


@dataclass(frozen=True, slots=True)
class LineChange:
    start: int
    end: int
    replacement: tuple[str, ...]

    def __post_init__(self):
        if (
            type(self.start) is not int or type(self.end) is not int
            or not 0 <= self.start <= self.end <= MAX_LINES
            or type(self.replacement) is not tuple
            or any(type(line) is not str for line in self.replacement)
            or len(self.replacement) > MAX_LINES
        ):
            raise PatchReconcileHold("unbounded original source difference hunk")


@dataclass(frozen=True, slots=True)
class ReconcileFile:
    path: str
    kind: str
    status: str
    expected_original_sha256: str | None
    observed_current_sha256: str | None
    proposed_replacement_sha256: str
    rebased_replacement_sha256: str | None
    local_hunks: int
    model_hunks: int
    overlapping_hunks: int

    def __post_init__(self):
        if self.kind not in ("new", "edit"):
            raise PatchReconcileHold("unknown original source type")
        if self.status not in (
            "new-still-absent", "unchanged-original",
            "nonoverlap-rebased", "already-present",
            "conflict", "new-path-collision",
        ):
            raise PatchReconcileHold("unknown original source reconciliation state")
        for name in ("local_hunks", "model_hunks", "overlapping_hunks"):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= MAX_HUNKS:
                raise PatchReconcileHold("unbounded source conflict count")
        if self.status == "conflict" and self.overlapping_hunks == 0:
            raise PatchReconcileHold("source conflict must report overlap")
        if self.status in ("nonoverlap-rebased", "unchanged-original"):
            if (
                type(self.rebased_replacement_sha256) is not str
                or len(self.rebased_replacement_sha256) != 64
            ):
                raise PatchReconcileHold("rebased source missing exact SHA-256")

    def to_public(self) -> dict[str, object]:
        return {
            "path": self.path,
            "kind": self.kind,
            "status": self.status,
            "expected_original_sha256": self.expected_original_sha256,
            "observed_current_sha256": self.observed_current_sha256,
            "proposed_replacement_sha256": self.proposed_replacement_sha256,
            "rebased_replacement_sha256": self.rebased_replacement_sha256,
            "local_hunks": self.local_hunks,
            "model_hunks": self.model_hunks,
            "overlapping_hunks": self.overlapping_hunks,
            "original_source_modified": False,
        }


@dataclass(frozen=True, slots=True)
class ReconcileReport:
    original_manifest_sha256: str
    original_patch_sha256: str
    rebase_sha256: str
    files: tuple[ReconcileFile, ...]
    status: str
    new_proposal: str | None
    existing_proposal: str | None

    def __post_init__(self):
        for digest in (
            self.original_manifest_sha256,
            self.original_patch_sha256,
            self.rebase_sha256,
        ):
            if (
                type(digest) is not str or len(digest) != 64
                or any(c not in "0123456789abcdef" for c in digest)
            ):
                raise PatchReconcileHold("reconciled source lacks exact SHA evidence")
        if (
            type(self.files) is not tuple
            or not 1 <= len(self.files) <= 24
            or any(type(f) is not ReconcileFile for f in self.files)
            or self.status not in (
                "rebased-review-required", "conflicts-held",
                "already-present-no-work",
            )
        ):
            raise PatchReconcileHold("invalid finite source reconciliation receipt")
        if self.status == "conflicts-held" and not any(
            f.status in ("conflict", "new-path-collision") for f in self.files
        ):
            raise PatchReconcileHold("unproven source conflict hold")
        if self.status == "rebased-review-required" and not (
            self.new_proposal is not None or self.existing_proposal is not None
        ):
            raise PatchReconcileHold("rebased source has no exact proposed work")
        if self.status != "rebased-review-required" and (
            self.new_proposal is not None or self.existing_proposal is not None
        ):
            raise PatchReconcileHold("conflicted work cannot publish partial rebase")
        expected = sha256(_canonical({
            "schema": SCHEMA,
            "original_manifest_sha256": self.original_manifest_sha256,
            "original_patch_sha256": self.original_patch_sha256,
            "files": [file.to_public() for file in self.files],
            "new_proposal": self.new_proposal,
            "existing_proposal": self.existing_proposal,
        })).hexdigest()
        if expected != self.rebase_sha256:
            raise PatchReconcileHold("proposed conflict recovery modified after review")

    def to_public(self) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "original_manifest_sha256": self.original_manifest_sha256,
            "original_patch_sha256": self.original_patch_sha256,
            "rebase_sha256": self.rebase_sha256,
            "status": self.status,
            "files": [x.to_public() for x in self.files],
            "conflict_count": sum(
                f.status in ("conflict", "new-path-collision") for f in self.files
            ),
            "rebased_count": sum(
                f.status == "nonoverlap-rebased" for f in self.files
            ),
            "already_present_count": sum(
                f.status == "already-present" for f in self.files
            ),
            "source_contents_disclosed": False,
            "original_source_modified": False,
            "git_index_modified": False,
            "automatic_conflict_resolution": False,
            "new_operator_review_required": True,
            "patch_applied": False,
            "release_certified": False,
        }


def _sha(text: str) -> str:
    return sha256(text.encode("utf-8", "strict")).hexdigest()


def _hunks(base: list[str], target: list[str]) -> tuple[LineChange, ...]:
    if len(base) > MAX_LINES or len(target) > MAX_LINES:
        raise PatchReconcileHold("three-way source exceeds finite line ceiling")
    matcher = difflib.SequenceMatcher(
        a=base, b=target, autojunk=False,
    )
    result = []
    for tag, start, end, new_start, new_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        result.append(LineChange(
            start=start, end=end,
            replacement=tuple(target[new_start:new_end]),
        ))
        if len(result) > MAX_HUNKS:
            raise PatchReconcileHold("three-way source has too many change hunks")
    return tuple(result)


def _intersect(first: LineChange, second: LineChange) -> bool:
    """Equal-position inserts and edits touching an insertion are conflicts."""
    a_insert = first.start == first.end
    b_insert = second.start == second.end
    if a_insert and b_insert:
        return first.start == second.start
    if a_insert:
        return second.start <= first.start <= second.end
    if b_insert:
        return first.start <= second.start <= first.end
    return max(first.start, second.start) < min(first.end, second.end)


def rebase_line_edits(
    original: str,
    current: str,
    proposed: str,
) -> tuple[str | None, int, int, int]:
    """Pure conservative line rebase: never drop local or model hunks.

    Returns (merged_text_or_None, local_hunk_count, proposed_hunk_count,
    overlap_count). None is an explicit conflict, not a silent resolution.
    """
    if any(type(x) is not str for x in (original, current, proposed)):
        raise PatchReconcileHold("UTF-8 original/current/proposed text required")
    base = _split_lines(original)
    mine = _split_lines(current)
    theirs = _split_lines(proposed)
    if any(len(lines) > MAX_LINES for lines in (base, mine, theirs)):
        raise PatchReconcileHold("source exceeds finite line-level reconciliation")
    local = _hunks(base, mine)
    suggested = _hunks(base, theirs)
    overlapping = 0
    duplicates = set()
    for i, src in enumerate(suggested):
        for local_change in local:
            if not _intersect(src, local_change):
                continue
            if src == local_change:
                duplicates.add(i)
                continue
            overlapping += 1
            if overlapping > MAX_HUNKS:
                raise PatchReconcileHold("unbounded conflicting source hunks")
    if overlapping:
        return None, len(local), len(suggested), overlapping
    if current == proposed:
        return current, len(local), len(suggested), 0
    selected = [*local, *(
        src for i, src in enumerate(suggested) if i not in duplicates
    )]
    # Reverse-index application preserves original offset positions.
    selected.sort(key=lambda h: (h.start, h.end), reverse=True)
    merged = base[:]
    for change in selected:
        merged[change.start:change.end] = list(change.replacement)
    result = "".join(merged)
    if len(result.encode("utf-8", "strict")) > MAX_SOURCE_BYTES:
        raise PatchReconcileHold("rebased source exceeds original finite byte ceiling")
    return result, len(local), len(suggested), 0


def _make_report(
    original: PortablePatchPlan,
    files: list[ReconcileFile],
    new_proposal: str | None,
    existing_proposal: str | None,
) -> ReconcileReport:
    if len(files) != len(original.entries):
        raise PatchReconcileHold("incomplete reconciliation across reviewed files")
    if any(f.status in ("conflict", "new-path-collision") for f in files):
        status = "conflicts-held"
        new_proposal = None
        existing_proposal = None
    elif new_proposal is not None or existing_proposal is not None:
        status = "rebased-review-required"
    else:
        status = "already-present-no-work"
    digest = sha256(_canonical({
        "schema": SCHEMA,
        "original_manifest_sha256": original.manifest_sha256,
        "original_patch_sha256": original.patch_sha256,
        "files": [file.to_public() for file in files],
        "new_proposal": new_proposal,
        "existing_proposal": existing_proposal,
    })).hexdigest()
    return ReconcileReport(
        original_manifest_sha256=original.manifest_sha256,
        original_patch_sha256=original.patch_sha256,
        rebase_sha256=digest, files=tuple(files), status=status,
        new_proposal=new_proposal, existing_proposal=existing_proposal,
    )


def reconcile_reviewed_patch(plan: PortablePatchPlan) -> ReconcileReport:
    """Read only current project bytes; produce NEW proposals or explicit holds.

    Every independently proposed source entry is inspected even if an early
    entry conflicts. Partial successes cannot become an exportable proposal.
    The original source descriptors are pinned once for the complete scan.
    """
    if type(plan) is not PortablePatchPlan:
        raise PatchReconcileHold("previously reviewed exact Git patch required")
    plan.__post_init__()
    fd = _open_root(plan.root)
    decisions: list[ReconcileFile] = []
    new_rows: list[dict] = []
    edited_rows: list[dict] = []
    try:
        root = os.fstat(fd)
        if (root.st_dev, root.st_ino) != (plan.root_device, plan.root_inode):
            raise PatchReconcileHold("project root source changed after review")
        for item in plan.entries:
            parent, name = _parent(fd, item.path)
            try:
                if item.kind == "new":
                    try:
                        _absent(parent, name)
                    except WorkspaceDeliveryHold:
                        decisions.append(ReconcileFile(
                            path=item.path, kind=item.kind,
                            status="new-path-collision",
                            expected_original_sha256=None,
                            observed_current_sha256=None,
                            proposed_replacement_sha256=item.replacement_sha256,
                            rebased_replacement_sha256=None,
                            local_hunks=0, model_hunks=0, overlapping_hunks=0,
                        ))
                        continue
                    new_rows.append({
                        "path": item.path, "content": item.replacement_text,
                    })
                    decisions.append(ReconcileFile(
                        path=item.path, kind="new", status="new-still-absent",
                        expected_original_sha256=None,
                        observed_current_sha256=None,
                        proposed_replacement_sha256=item.replacement_sha256,
                        rebased_replacement_sha256=item.replacement_sha256,
                        local_hunks=0, model_hunks=0, overlapping_hunks=0,
                    ))
                    continue
                raw, _stat = _read_original(parent, name)
                current = raw.decode("utf-8", "strict")
                observed_sha = sha256(raw).hexdigest()
                if observed_sha == item.original_sha256:
                    status = "unchanged-original"
                    combined = item.replacement_text
                    mine_count = 0
                    proposed_count = 0
                    conflict_count = 0
                else:
                    combined, mine_count, proposed_count, conflict_count = (
                        rebase_line_edits(
                            item.original_text, current, item.replacement_text,
                        )
                    )
                    status = (
                        "conflict" if combined is None
                        else "already-present" if combined == current
                        else "nonoverlap-rebased"
                    )
                decisions.append(ReconcileFile(
                    path=item.path, kind=item.kind, status=status,
                    expected_original_sha256=item.original_sha256,
                    observed_current_sha256=observed_sha,
                    proposed_replacement_sha256=item.replacement_sha256,
                    rebased_replacement_sha256=(
                        _sha(combined) if combined is not None else None
                    ),
                    local_hunks=mine_count, model_hunks=proposed_count,
                    overlapping_hunks=conflict_count,
                ))
                if combined is not None and combined != current:
                    edited_rows.append({
                        "path": item.path,
                        "expected_sha256": observed_sha,
                        "replacement": combined,
                    })
            finally:
                os.close(parent)
    except (OSError, UnicodeError, WorkspaceDeliveryHold, PatchBundleHold) as exc:
        raise PatchReconcileHold(
            "original project changed or is unsafe for source reconciliation",
        ) from exc
    finally:
        os.close(fd)
    if sum(len(row["replacement"].encode("utf-8", "strict"))
           for row in edited_rows) > MAX_AGGREGATE_REPLACEMENT:
        raise PatchReconcileHold("combined rebased source exceeds original quota")
    new_json = (
        _canonical({"schema": NEW_SCHEMA, "files": new_rows}).decode("utf-8")
        if new_rows else None
    )
    edits_json = (
        _canonical({"schema": EDIT_SCHEMA, "files": edited_rows}).decode("utf-8")
        if edited_rows else None
    )
    return _make_report(plan, decisions, new_json, edits_json)


__all__ = [
    "SCHEMA", "PatchReconcileHold", "LineChange", "ReconcileFile",
    "ReconcileReport", "rebase_line_edits", "reconcile_reviewed_patch",
]
