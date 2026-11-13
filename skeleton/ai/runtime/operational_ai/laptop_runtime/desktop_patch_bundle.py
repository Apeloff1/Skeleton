"""Reviewable portable Git patch construction for offline Jeeves authorship.

Jeeves model output is *untrusted text*. This module combines its optional
new-file and existing-file proposals into a deterministic, finite patch with
both original/replacement SHA-256 receipts. It does not run Git, write project
files, grant filesystem tools, make commits, or authorize applying a patch.

Both proposal types reuse the actual laptop workspace's descriptor-rooted
source readers. The patch is Git-compatible for manually verified checkout
application, including files without a trailing newline and CRLF text.
"""
from __future__ import annotations

from dataclasses import dataclass
import difflib
from hashlib import sha256
from pathlib import Path
import os

from .desktop_workspace import (
    WorkspaceDeliveryHold, WorkspacePlan, _canonical, _open_root,
    _parent, _absent, _relative, _source, parse_plan,
)
from .desktop_existing_edits import (
    ExistingEditPlan, ExistingEditHold, _read_original, parse_existing_edits,
)

SCHEMA = "jeeves.workspace.portable-git-patch.v1"
MAX_ENTRIES = 24
MAX_PATCH_BYTES = 786432
MAX_PREVIEW_LINES = 12000
_ALLOWED_KINDS = frozenset(("new", "edit"))


class PatchBundleHold(ValueError):
    """A source proposal is not safely reviewable as one original Git patch."""


def _sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _is_sha(value: object) -> bool:
    return (
        type(value) is str and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
    )


def _review_text(value: str) -> bytes:
    # The canonical workspace source reader bans NUL and invalid Unicode.
    # CRLF, solitary CR and missing EOF newline remain original byte data.
    try:
        raw = _source(value)
    except (WorkspaceDeliveryHold, UnicodeError, ValueError) as exc:
        raise PatchBundleHold("noncanonical original or replacement source text") from exc
    if any(
        byte < 32 and byte not in (9, 10, 13)
        for byte in raw
    ):
        raise PatchBundleHold("source patch contains non-text control bytes")
    return raw


@dataclass(frozen=True, slots=True)
class PatchEntry:
    kind: str
    path: str
    original_text: str
    replacement_text: str
    original_sha256: str | None
    replacement_sha256: str
    original_device: int | None = None
    original_inode: int | None = None
    original_mtime_ns: int | None = None
    original_mode: int | None = None

    def __post_init__(self):
        if type(self.kind) is not str or self.kind not in _ALLOWED_KINDS:
            raise PatchBundleHold("unknown original source change type")
        try:
            _relative(self.path)
        except WorkspaceDeliveryHold as exc:
            raise PatchBundleHold("untrusted Git-relative source path") from exc
        new = _review_text(self.replacement_text)
        if not _is_sha(self.replacement_sha256) or _sha(new) != self.replacement_sha256:
            raise PatchBundleHold("replacement is not exact approved UTF-8 bytes")
        if self.kind == "new":
            if (
                self.original_text != "" or self.original_sha256 is not None
                or any(
                    getattr(self, name) is not None
                    for name in (
                        "original_device", "original_inode",
                        "original_mtime_ns", "original_mode",
                    )
                )
            ):
                raise PatchBundleHold("new file cannot authorize existing file overwrite")
        else:
            old = _review_text(self.original_text)
            if (
                not _is_sha(self.original_sha256)
                or _sha(old) != self.original_sha256
                or old == new
            ):
                raise PatchBundleHold("original edit digest changed or no real difference")
            for field in (
                "original_device", "original_inode",
                "original_mtime_ns", "original_mode",
            ):
                value = getattr(self, field)
                if type(value) is not int or value < 0:
                    raise PatchBundleHold("existing original inode metadata missing")
            if self.original_inode < 1:
                raise PatchBundleHold("existing original inode ID invalid")

    @property
    def replacement_bytes(self) -> int:
        return len(self.replacement_text.encode("utf-8", "strict"))

    def public(self) -> dict[str, object]:
        return {
            "path": self.path,
            "kind": self.kind,
            "original_sha256": self.original_sha256,
            "replacement_sha256": self.replacement_sha256,
            "replacement_bytes": self.replacement_bytes,
        }


def _split_lines(text: str) -> list[str]:
    """Split on actual LF only; U+2028 is source text, not a line separator."""
    if not text:
        return []
    chunks = text.split("\n")
    lines = [part + "\n" for part in chunks[:-1]]
    if chunks[-1]:
        lines.append(chunks[-1])
    return lines


def _git_hunks(entry: PatchEntry) -> str:
    original = _split_lines(entry.original_text)
    replacement = _split_lines(entry.replacement_text)
    a = "/dev/null" if entry.kind == "new" else "a/" + entry.path
    b = "b/" + entry.path
    lines = [f"diff --git a/{entry.path} b/{entry.path}\n"]
    if entry.kind == "new":
        # Immutable model proposals are delivered as INERT sources; normal
        # 100644 mode prevents accidental executable-bit escalation.
        lines.append("new file mode 100644\n")
    diff = difflib.unified_diff(
        original, replacement, fromfile=a, tofile=b,
        n=3, lineterm="\n",
    )
    saw_hunk = False
    for row in diff:
        if row.startswith("@@ "):
            saw_hunk = True
        if row.startswith(("--- ", "+++ ", "@@ ")):
            lines.append(row if row.endswith("\n") else row + "\n")
            continue
        # A change containing no EOF newline must use Git's explicit
        # no-newline marker, not silently add a newline or corrupt the patch.
        if not row.endswith("\n"):
            if not row or row[0] not in ("+", "-", " "):
                raise PatchBundleHold("invalid source unified diff")
            lines.append(row + "\n\\ No newline at end of file\n")
        else:
            lines.append(row)
    if not saw_hunk:
        raise PatchBundleHold("approved source edit has no visible Git hunk")
    return "".join(lines)


def _manifest_digest(entries: tuple[PatchEntry, ...]) -> str:
    return _sha(_canonical({
        "schema": SCHEMA,
        "files": [{
            "kind": e.kind,
            "path": e.path,
            "original_sha256": e.original_sha256,
            "original_text": e.original_text,
            "replacement_sha256": e.replacement_sha256,
            "replacement_text": e.replacement_text,
        } for e in entries],
    }))


@dataclass(frozen=True, slots=True)
class PortablePatchPlan:
    root: str
    root_device: int
    root_inode: int
    entries: tuple[PatchEntry, ...]
    manifest_sha256: str
    patch_sha256: str
    patch_bytes: int

    def __post_init__(self):
        if (
            type(self.root) is not str
            or not Path(self.root).is_absolute()
            or ".." in Path(self.root).parts
            or "\x00" in self.root
            or type(self.root_device) is not int
            or type(self.root_inode) is not int
            or self.root_device < 0 or self.root_inode < 1
        ):
            raise PatchBundleHold("trusted checked original project root required")
        if (
            type(self.entries) is not tuple
            or not 1 <= len(self.entries) <= MAX_ENTRIES
            or any(type(item) is not PatchEntry for item in self.entries)
            or len({item.path.casefold() for item in self.entries})
            != len(self.entries)
        ):
            raise PatchBundleHold("finite unique cross-type source changes required")
        # A Git patch is order-sensitive; sorting once makes review, digest,
        # source verification and final export share the exact same bytes.
        if self.entries != tuple(sorted(
            self.entries, key=lambda e: (e.path.casefold(), e.path),
        )):
            raise PatchBundleHold("unordered Git source manifest")
        if self.manifest_sha256 != _manifest_digest(self.entries):
            raise PatchBundleHold("original approved source manifest altered")
        rendered = _patch_bytes(self.entries)
        if (
            not _is_sha(self.patch_sha256)
            or self.patch_sha256 != _sha(rendered)
            or type(self.patch_bytes) is not int
            or self.patch_bytes != len(rendered)
            or not 1 <= len(rendered) <= MAX_PATCH_BYTES
        ):
            raise PatchBundleHold("original Git patch bytes differ from review")

    def public_review(self) -> dict[str, object]:
        """No source contents or private absolute project paths in receipt."""
        return {
            "schema": "jeeves.workspace.portable-patch-review.v1",
            "manifest_sha256": self.manifest_sha256,
            "patch_sha256": self.patch_sha256,
            "patch_bytes": self.patch_bytes,
            "file_count": len(self.entries),
            "new_files": sum(e.kind == "new" for e in self.entries),
            "existing_edits": sum(e.kind == "edit" for e in self.entries),
            "files": [e.public() for e in self.entries],
            "project_files_modified": False,
            "native_model_authorized_to_write": False,
            "patch_applied": False,
            "release_certified": False,
        }


def _patch_bytes(entries: tuple[PatchEntry, ...]) -> bytes:
    pieces = []
    size = 0
    for entry in entries:
        section = _git_hunks(entry).encode("utf-8", "strict")
        size += len(section)
        if size > MAX_PATCH_BYTES:
            raise PatchBundleHold("reviewed Git patch exceeds finite source byte budget")
        pieces.append(section)
    if not pieces:
        raise PatchBundleHold("empty source patch is not work")
    return b"".join(pieces)


def review_patch_bundle(
    root: str | Path,
    *, new_files: str | bytes | None = None,
    existing_edits: str | bytes | None = None,
) -> PortablePatchPlan:
    """Read-only descriptor admission of mixed new and existing model changes."""
    if not isinstance(root, (str, Path)):
        raise PatchBundleHold("operator-selected source project root required")
    selected = Path(root)
    if not selected.is_absolute() or ".." in selected.parts or "\x00" in str(selected):
        raise PatchBundleHold("source project root must be absolute and canonical")
    has_new = new_files is not None and new_files != "" and new_files != b""
    has_edits = existing_edits is not None and existing_edits != "" and existing_edits != b""
    if not has_new and not has_edits:
        raise PatchBundleHold("original source change proposal required")
    incoming: list[PatchEntry] = []
    identities: list[tuple[int, int]] = []
    if has_new:
        try:
            additions: WorkspacePlan = parse_plan(new_files, selected)
        except (OSError, ValueError, WorkspaceDeliveryHold) as exc:
            raise PatchBundleHold("new-file source review did not pass") from exc
        identities.append((additions.root_device, additions.root_inode))
        incoming.extend(
            PatchEntry(
                kind="new", path=item.path,
                original_text="", replacement_text=item.text,
                original_sha256=None, replacement_sha256=item.sha256,
            ) for item in additions.entries
        )
    if has_edits:
        try:
            edits: ExistingEditPlan = parse_existing_edits(existing_edits, selected)
        except (OSError, ValueError, ExistingEditHold) as exc:
            raise PatchBundleHold("existing-file source review did not pass") from exc
        identities.append((edits.root_device, edits.root_inode))
        incoming.extend(
            PatchEntry(
                kind="edit", path=item.path,
                original_text=item.original_text,
                replacement_text=item.replacement_text,
                original_sha256=item.original_sha256,
                replacement_sha256=item.replacement_sha256,
                original_device=item.original_device,
                original_inode=item.original_inode,
                original_mtime_ns=item.original_mtime_ns,
                original_mode=item.original_mode,
            ) for item in edits.edits
        )
    if len(set(identities)) != 1:
        raise PatchBundleHold("original source root changed between two reviews")
    entries = tuple(sorted(incoming, key=lambda x: (x.path.casefold(), x.path)))
    if not 1 <= len(entries) <= MAX_ENTRIES:
        raise PatchBundleHold("too many original source files in one patch")
    if len({item.path.casefold() for item in entries}) != len(entries):
        raise PatchBundleHold("new/existing proposals conflict in same project path")
    diff = _patch_bytes(entries)
    return PortablePatchPlan(
        root=str(selected),
        root_device=identities[0][0], root_inode=identities[0][1],
        entries=entries,
        manifest_sha256=_manifest_digest(entries),
        patch_sha256=_sha(diff), patch_bytes=len(diff),
    )


def revalidate_live_sources(plan: PortablePatchPlan) -> None:
    """Before any export ensure no source changed since original review."""
    if type(plan) is not PortablePatchPlan:
        raise PatchBundleHold("immutable original source plan required")
    plan.__post_init__()
    root_fd = _open_root(plan.root)
    try:
        source_stat = os.fstat(root_fd)
        if (source_stat.st_dev, source_stat.st_ino) != (
            plan.root_device, plan.root_inode,
        ):
            raise PatchBundleHold("original project root changed since review")
        for entry in plan.entries:
            parent, name = _parent(root_fd, entry.path)
            try:
                if entry.kind == "new":
                    _absent(parent, name)
                    continue
                current, st = _read_original(parent, name)
                if (
                    st.st_dev != entry.original_device
                    or st.st_ino != entry.original_inode
                    or st.st_mtime_ns != entry.original_mtime_ns
                    or st.st_mode != entry.original_mode
                    or _sha(current) != entry.original_sha256
                    or current != entry.original_text.encode("utf-8", "strict")
                ):
                    raise PatchBundleHold(
                        "existing original source diverged after review",
                    )
            finally:
                os.close(parent)
    except (OSError, WorkspaceDeliveryHold, ExistingEditHold) as exc:
        raise PatchBundleHold("source changed or became unsafe after review") from exc
    finally:
        os.close(root_fd)


def get_reviewed_patch(plan: PortablePatchPlan, *, verify_sources: bool = True) -> bytes:
    """Obtain exact reviewed patch bytes (no mutation, no implicit execution)."""
    if type(plan) is not PortablePatchPlan:
        raise PatchBundleHold("review before constructing Git patch")
    plan.__post_init__()
    if verify_sources is not True:
        raise PatchBundleHold("cannot bypass original source re-verification")
    revalidate_live_sources(plan)
    patch = _patch_bytes(plan.entries)
    if _sha(patch) != plan.patch_sha256:
        raise PatchBundleHold("source patch changed after operator review")
    return patch


__all__ = [
    "SCHEMA", "PatchBundleHold", "PatchEntry", "PortablePatchPlan",
    "review_patch_bundle", "revalidate_live_sources", "get_reviewed_patch",
]
