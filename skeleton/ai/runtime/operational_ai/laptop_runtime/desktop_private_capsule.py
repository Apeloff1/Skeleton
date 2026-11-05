"""Owner-private, source-complete *selected* cold capsule for offline Jeeves.

This is not an executable sandbox and is not a checkout clone. A human chooses
finite original source dependencies and a separately reviewed model patch.
The capsule copies those exact original bytes plus all final patch bytes into
a NEW 0700 directory, then writes a SHA-bound completion seal LAST. No code
is executed, no original path is changed, and Git is never invoked.

Partial/crashed or tampered capsules have no valid completion seal. Never
auto-resume, delete someone else's replacement, or treat a seal as testing.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat

from .desktop_workspace import (
    _canonical, _open_root, _parent, _relative, WorkspaceDeliveryHold,
)
from .desktop_workspace_index import _allowed_name
from .desktop_existing_edits import _read_original, ExistingEditHold
from .desktop_patch_bundle import PortablePatchPlan, revalidate_live_sources
from .desktop_patch_export import _pinned_private_directory, _identical_parent
from .desktop_source_graph import analyze_python_source_graph
from .desktop_capsule_source_closure import (
    ClosureSource, analyze_capsule_source_closure,
)
from .desktop_source_qualification import require_parseable_patch

SCHEMA = "jeeves.workspace.private-selected-source-capsule.v1"
SEAL_SCHEMA = "jeeves.workspace.private-selected-source-capsule-seal.v1"
MAX_SELECTED_FILES = 48
MAX_SELECTED_PATH_BYTES = 4096
MAX_SELECTED_TOTAL_BYTES = 1048576
MAX_TOTAL_CAPSULE_BYTES = 1572864
MAX_CAPSULE_FILES = 72
SEAL_NAME = ".jeeves-source-capsule-seal.json"
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")
_DIR = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
_READ = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
_WRITE = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)


class PrivateCapsuleHold(ValueError):
    """Unsafe, changed, incomplete, or unapproved source capsule."""


def _hash(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _sha(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(
        ch in "0123456789abcdef" for ch in value
    )


def _paths(raw: str) -> tuple[str, ...]:
    if type(raw) is not str or "\x00" in raw or "\r" in raw:
        raise PrivateCapsuleHold("explicit LF-separated selected source paths required")
    if not 1 <= len(raw.encode("utf-8", "strict")) <= MAX_SELECTED_PATH_BYTES:
        raise PrivateCapsuleHold("finite original source selection required")
    paths = tuple(line for line in raw.split("\n") if line)
    if not 1 <= len(paths) <= MAX_SELECTED_FILES:
        raise PrivateCapsuleHold("one to 48 original source dependencies required")
    if len({name.casefold() for name in paths}) != len(paths):
        raise PrivateCapsuleHold("duplicate or case-colliding original source")
    for name in paths:
        try:
            parts = _relative(name)
        except (WorkspaceDeliveryHold, ValueError) as exc:
            raise PrivateCapsuleHold("unsafe explicitly selected source path") from exc
        if not all(
            _allowed_name(part, directory=index < len(parts)-1)
            for index, part in enumerate(parts)
        ):
            raise PrivateCapsuleHold("credential or control file cannot enter capsule")
    return tuple(sorted(paths, key=lambda x: (x.casefold(), x)))


@dataclass(frozen=True, slots=True)
class FrozenSource:
    path: str
    source: bytes
    digest: str
    device: int
    inode: int
    ctime_ns: int
    mtime_ns: int
    mode: int

    def __post_init__(self):
        _relative(self.path)
        if (
            type(self.source) is not bytes
            or not 1 <= len(self.source) <= 65536
            or not _sha(self.digest) or _hash(self.source) != self.digest
            or any(type(getattr(self, key)) is not int or getattr(self, key) < 0
                   for key in ("device", "inode", "ctime_ns", "mtime_ns", "mode"))
            or self.inode < 1 or not stat.S_ISREG(self.mode)
            or self.mode & 0o022
        ):
            raise PrivateCapsuleHold("original dependency bytes or inode invalid")

    def public(self) -> dict[str, object]:
        return {"path": self.path, "sha256": self.digest, "bytes": len(self.source)}


@dataclass(frozen=True, slots=True)
class PrivateCapsulePlan:
    patch: PortablePatchPlan
    originals: tuple[FrozenSource, ...]
    capsule_sha256: str
    original_bytes: int
    total_bytes: int
    static_status: str
    python_graph_sha256: str
    python_closure_sha256: str

    def __post_init__(self):
        if type(self.patch) is not PortablePatchPlan:
            raise PrivateCapsuleHold("typed reviewed original source work required")
        self.patch.__post_init__()
        if (
            type(self.originals) is not tuple
            or not 1 <= len(self.originals) <= MAX_SELECTED_FILES
            or any(type(src) is not FrozenSource for src in self.originals)
        ):
            raise PrivateCapsuleHold("finite selected original source files required")
        for item in self.originals:
            item.__post_init__()
        all_paths = [x.path for x in self.originals] + [
            x.path for x in self.patch.entries
        ]
        if (
            len(all_paths) > MAX_CAPSULE_FILES
            or len({x.casefold() for x in all_paths}) != len(all_paths)
            or self.originals != tuple(sorted(
                self.originals, key=lambda e: (e.path.casefold(), e.path),
            ))
            or type(self.original_bytes) is not int
            or self.original_bytes != sum(len(s.source) for s in self.originals)
            or self.original_bytes > MAX_SELECTED_TOTAL_BYTES
            or type(self.total_bytes) is not int
            or self.total_bytes != self.original_bytes + sum(
                e.replacement_bytes for e in self.patch.entries
            )
            or self.total_bytes > MAX_TOTAL_CAPSULE_BYTES
            or self.static_status not in ("parse-clean", "mixed-unverified")
            or not _sha(self.python_graph_sha256)
            or not _sha(self.python_closure_sha256)
            or not _sha(self.capsule_sha256)
            or self.capsule_sha256 != _capsule_digest(
                self.patch, self.originals,
                self.python_graph_sha256, self.python_closure_sha256,
            )
        ):
            raise PrivateCapsuleHold("selected project capsule identity changed")
        if _closure(self.patch, self.originals).graph_sha256 != self.python_closure_sha256:
            raise PrivateCapsuleHold("selected original/import source closure changed")

    def public_review(self) -> dict[str, object]:
        closure = _closure(self.patch, self.originals)
        if closure.graph_sha256 != self.python_closure_sha256:
            raise PrivateCapsuleHold("public capsule review lacks exact source closure")
        return {
            "schema": SCHEMA,
            "status": "private-selected-source-capsule-planned-no-write",
            "capsule_sha256": self.capsule_sha256,
            "source_manifest_sha256": self.patch.manifest_sha256,
            "patch_sha256": self.patch.patch_sha256,
            "python_graph_sha256": self.python_graph_sha256,
            "python_closure_sha256": self.python_closure_sha256,
            "selected_python_closure_status": closure.status,
            "linked_original_imports": closure.linked_original_count,
            "linked_review_change_imports": closure.linked_change_count,
            "unverified_external_or_unselected_imports": closure.unverified_count,
            "static_source_status": self.static_status,
            "original_dependency_count": len(self.originals),
            "change_count": len(self.patch.entries),
            "total_file_count": len(self.originals) + len(self.patch.entries),
            "total_source_bytes": self.total_bytes,
            "originals": [x.public() for x in self.originals],
            "changes": [x.public() for x in self.patch.entries],
            "not_a_complete_project_or_sandbox": True,
            "unselected_imports_remain_unverified": True,
            "original_checkout_modified": False,
            "source_code_executed": False,
            "release_certified": False,
        }


def _closure(
    patch: PortablePatchPlan, originals: tuple[FrozenSource, ...],
):
    sources = tuple(
        [ClosureSource(
            item.path, "selected-original", item.source, item.digest,
        ) for item in originals]
        + [ClosureSource(
            item.path, item.kind,
            item.replacement_text.encode("utf-8", "strict"),
            item.replacement_sha256,
        ) for item in patch.entries]
    )
    return analyze_capsule_source_closure(
        sources, source_manifest_sha256=patch.manifest_sha256,
        source_patch_sha256=patch.patch_sha256,
    )


def _capsule_digest(
    patch: PortablePatchPlan, originals: tuple[FrozenSource, ...],
    python_graph_sha256: str, python_closure_sha256: str,
) -> str:
    return _hash(_canonical({
        "schema": SCHEMA,
        "original_root_device": patch.root_device,
        "original_root_inode": patch.root_inode,
        "source_manifest_sha256": patch.manifest_sha256,
        "patch_sha256": patch.patch_sha256,
        "python_graph_sha256": python_graph_sha256,
        "python_closure_sha256": python_closure_sha256,
        "originals": [
            {
                "path": s.path, "sha256": s.digest,
                "device": s.device, "inode": s.inode,
                "ctime_ns": s.ctime_ns, "mtime_ns": s.mtime_ns,
                "mode": s.mode,
            }
            for s in originals
        ],
        "changes": [e.public() for e in patch.entries],
    }))


def prepare_private_capsule(
    patch: PortablePatchPlan, selected_sources: str,
) -> PrivateCapsulePlan:
    """Independent read-only source selection and complete changed-source check."""
    if type(patch) is not PortablePatchPlan:
        raise PrivateCapsuleHold("reviewed patch required before source collection")
    patch.__post_init__()
    names = _paths(selected_sources)
    occupied = {e.path.casefold() for e in patch.entries}
    if any(name.casefold() in occupied for name in names):
        raise PrivateCapsuleHold("selected originals must exclude replaced source files")
    static = require_parseable_patch(patch)
    graph = analyze_python_source_graph(patch)
    if not static.permits_inert_export or not graph.permits_inert_export:
        raise PrivateCapsuleHold("source syntax/import graph does not permit cold staging")
    revalidate_live_sources(patch)
    root_fd = _open_root(patch.root)
    try:
        root = os.fstat(root_fd)
        if (root.st_dev, root.st_ino) != (patch.root_device, patch.root_inode):
            raise PrivateCapsuleHold("source root changed since reviewed model proposal")
        originals = []
        total = 0
        for path in names:
            directory, leaf = _parent(root_fd, path)
            try:
                raw, st = _read_original(directory, leaf)
            finally:
                os.close(directory)
            total += len(raw)
            if total > MAX_SELECTED_TOTAL_BYTES:
                raise PrivateCapsuleHold("selected original source byte budget exceeded")
            originals.append(FrozenSource(
                path, raw, _hash(raw), st.st_dev, st.st_ino,
                st.st_ctime_ns, st.st_mtime_ns, st.st_mode,
            ))
        current = os.stat(patch.root, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (root.st_dev, root.st_ino):
            raise PrivateCapsuleHold("project root was swapped during source review")
    except (OSError, WorkspaceDeliveryHold, ExistingEditHold) as exc:
        raise PrivateCapsuleHold("selected original source cannot be trusted") from exc
    finally:
        os.close(root_fd)
    selected = tuple(originals)
    closure = _closure(patch, selected)
    planned = PrivateCapsulePlan(
        patch=patch,
        originals=selected,
        capsule_sha256=_capsule_digest(
            patch, selected, graph.graph_sha256, closure.graph_sha256,
        ),
        original_bytes=total,
        total_bytes=total + sum(
            entry.replacement_bytes for entry in patch.entries
        ),
        static_status=static.status,
        python_graph_sha256=graph.graph_sha256,
        python_closure_sha256=closure.graph_sha256,
    )
    revalidate_live_sources(patch)
    _revalidate_selected(planned)
    return planned


def _revalidate_selected(plan: PrivateCapsulePlan) -> None:
    root_fd = _open_root(plan.patch.root)
    try:
        info = os.fstat(root_fd)
        if (info.st_dev, info.st_ino) != (
            plan.patch.root_device, plan.patch.root_inode,
        ):
            raise PrivateCapsuleHold("original project root replaced after review")
        for selected in plan.originals:
            directory, leaf = _parent(root_fd, selected.path)
            try:
                raw, st = _read_original(directory, leaf)
            finally:
                os.close(directory)
            if (
                raw != selected.source
                or (st.st_dev, st.st_ino, st.st_ctime_ns, st.st_mtime_ns, st.st_mode)
                != (selected.device, selected.inode, selected.ctime_ns,
                    selected.mtime_ns, selected.mode)
            ):
                raise PrivateCapsuleHold("original dependency changed after inspection")
        current = os.stat(plan.patch.root, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
            raise PrivateCapsuleHold("project path was replaced during verification")
    except (OSError, ExistingEditHold, WorkspaceDeliveryHold) as exc:
        raise PrivateCapsuleHold("original project dependency drift") from exc
    finally:
        os.close(root_fd)


def _new_destination(target: str | Path, root: str) -> Path:
    if not isinstance(target, (str, Path)):
        raise PrivateCapsuleHold("explicit owner-private new capsule destination required")
    path = Path(target)
    original = Path(root)
    if (
        not path.is_absolute() or ".." in path.parts or "\x00" in str(path)
        or not _NAME.fullmatch(path.name)
        or path.is_relative_to(original)
        or original.is_relative_to(path)
    ):
        raise PrivateCapsuleHold("new capsule must be outside original checkout")
    return path


def _dir(fd: int) -> None:
    st = os.fstat(fd)
    if (
        not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid()
        or st.st_mode & 0o077 or st.st_nlink < 1
    ):
        raise PrivateCapsuleHold("source capsule directory not private")


def _copy(root_fd: int, relative: str, raw: bytes, expected_sha: str) -> None:
    """No-follow owner-private mkdirat/openat copy, each file O_EXCL and fsync."""
    parts = relative.split("/")
    folder = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            try:
                os.mkdir(part, 0o700, dir_fd=folder)
            except FileExistsError:
                pass
            next_fd = os.open(part, _DIR, dir_fd=folder)
            os.close(folder)
            folder = next_fd
            _dir(folder)
        name = parts[-1]
        fd = os.open(name, _WRITE, 0o600, dir_fd=folder)
        try:
            offset = 0
            while offset < len(raw):
                count = os.write(fd, raw[offset:])
                if count <= 0:
                    raise PrivateCapsuleHold("incomplete private source publication")
                offset += count
            os.fsync(fd)
            st = os.fstat(fd)
            if (
                not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid()
                or st.st_nlink != 1 or st.st_mode & 0o077
                or st.st_size != len(raw) or _hash(raw) != expected_sha
            ):
                raise PrivateCapsuleHold("private source write metadata mismatch")
        finally:
            os.close(fd)
        check_fd = os.open(name, _READ, dir_fd=folder)
        try:
            observed = os.fstat(check_fd)
            current = os.stat(name, dir_fd=folder, follow_symlinks=False)
            if (
                (observed.st_dev, observed.st_ino, observed.st_size)
                != (current.st_dev, current.st_ino, len(raw))
                or not stat.S_ISREG(observed.st_mode)
                or observed.st_uid != os.getuid() or observed.st_mode & 0o077
                or observed.st_nlink != 1
            ):
                raise PrivateCapsuleHold("private source path changed after writing")
            receipt = bytearray()
            while len(receipt) <= len(raw):
                fragment = os.read(check_fd, min(16384, len(raw) + 1 - len(receipt)))
                if not fragment:
                    break
                receipt.extend(fragment)
            after = os.fstat(check_fd)
            if (
                bytes(receipt) != raw or _hash(receipt) != expected_sha
                or (observed.st_ino, observed.st_mtime_ns)
                != (after.st_ino, after.st_mtime_ns)
            ):
                raise PrivateCapsuleHold("read-back source hash or inode changed")
        finally:
            os.close(check_fd)
        os.fsync(folder)
    finally:
        os.close(folder)


def publish_private_capsule(
    plan: PrivateCapsulePlan, destination: str | Path, *,
    expected_capsule_sha256: str, expected_manifest_sha256: str,
    expected_patch_sha256: str, approve_private_capsule: bool,
) -> dict[str, object]:
    """Publish a NEW selected-source tree; seal LAST, never run or apply it."""
    if type(plan) is not PrivateCapsulePlan or approve_private_capsule is not True:
        raise PrivateCapsuleHold("explicit reviewed private source capsule approval required")
    plan.__post_init__()
    if (
        not _sha(expected_capsule_sha256)
        or expected_capsule_sha256 != plan.capsule_sha256
        or expected_manifest_sha256 != plan.patch.manifest_sha256
        or expected_patch_sha256 != plan.patch.patch_sha256
    ):
        raise PrivateCapsuleHold("full capsule + original source + patch SHA approval required")
    path = _new_destination(destination, plan.patch.root)
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise PrivateCapsuleHold("POSIX/WSL2 private descriptor publication required")
    # A caller can construct a typed dataclass; never trust cached static
    # qualification alone to authorize new private source publication.
    static = require_parseable_patch(plan.patch)
    graph = analyze_python_source_graph(plan.patch)
    if (
        not static.permits_inert_export
        or not graph.permits_inert_export
        or static.status != plan.static_status
        or graph.graph_sha256 != plan.python_graph_sha256
    ):
        raise PrivateCapsuleHold("source parser or import graph changed since review")
    closure = _closure(plan.patch, plan.originals)
    if closure.graph_sha256 != plan.python_closure_sha256:
        raise PrivateCapsuleHold("source closure diverged before private publication")
    _revalidate_selected(plan)
    revalidate_live_sources(plan.patch)
    parent = _pinned_private_directory(path)
    capsule = None
    try:
        _identical_parent(path, parent)
        os.mkdir(path.name, 0o700, dir_fd=parent)
        os.fsync(parent)
        capsule = os.open(path.name, _DIR, dir_fd=parent)
        _dir(capsule)
        actual = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        pinned = os.fstat(capsule)
        if (actual.st_dev, actual.st_ino) != (pinned.st_dev, pinned.st_ino):
            raise PrivateCapsuleHold("new capsule destination substituted")
        rows = []
        for source in plan.originals:
            _copy(capsule, source.path, source.source, source.digest)
            rows.append({"path": source.path, "kind": "selected-original",
                         "sha256": source.digest, "bytes": len(source.source)})
        for change in plan.patch.entries:
            raw = change.replacement_text.encode("utf-8", "strict")
            _copy(capsule, change.path, raw, change.replacement_sha256)
            rows.append({"path": change.path, "kind": change.kind,
                         "sha256": change.replacement_sha256, "bytes": len(raw)})
        # Changing originals while writing means NO completion seal. Partial
        # output remains owner-private and must be manually inspected/removed.
        _revalidate_selected(plan)
        revalidate_live_sources(plan.patch)
        _identical_parent(path, parent)
        latest = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if (latest.st_dev, latest.st_ino) != (pinned.st_dev, pinned.st_ino):
            raise PrivateCapsuleHold("private capsule replaced before final seal")
        rows.sort(key=lambda row: (row["path"].casefold(), row["path"]))
        seal = _canonical({
            "schema": SEAL_SCHEMA,
            "status": "private-source-capsule-complete-unexecuted",
            "capsule_sha256": plan.capsule_sha256,
            "source_manifest_sha256": plan.patch.manifest_sha256,
            "patch_sha256": plan.patch.patch_sha256,
            "python_graph_sha256": plan.python_graph_sha256,
            "python_closure_sha256": plan.python_closure_sha256,
            "unverified_source_import_count": closure.unverified_count,
            "file_count": len(rows),
            "files": rows,
            "source_code_executed": False,
            "original_checkout_modified": False,
            "full_project_or_device_qualified": False,
            "release_certified": False,
        })
        if len(seal) > 16384:
            raise PrivateCapsuleHold("capsule final seal exceeds metadata budget")
        _copy(capsule, SEAL_NAME, seal, _hash(seal))
        os.fsync(capsule)
        os.fsync(parent)
        return {
            "schema": SCHEMA,
            "status": "new-private-selected-source-capsule-sealed",
            "capsule_sha256": plan.capsule_sha256,
            "seal_sha256": _hash(seal),
            "source_manifest_sha256": plan.patch.manifest_sha256,
            "patch_sha256": plan.patch.patch_sha256,
            "python_closure_sha256": plan.python_closure_sha256,
            "unverified_source_import_count": closure.unverified_count,
            "file_count": len(rows),
            "source_bytes": plan.total_bytes,
            "private_file_mode": "0600",
            "private_directory_mode": "0700",
            "all_source_bytes_read_back": True,
            "source_code_executed": False,
            "original_checkout_modified": False,
            "git_commands_executed": False,
            "release_certified": False,
        }
    finally:
        if capsule is not None:
            os.close(capsule)
        os.close(parent)


__all__ = [
    "SCHEMA", "SEAL_SCHEMA", "PrivateCapsuleHold", "FrozenSource",
    "PrivateCapsulePlan", "prepare_private_capsule",
    "publish_private_capsule", "verify_private_capsule",
]


def _read_capsule_file(directory_fd: int, relative: str, max_bytes: int) -> bytes:
    """Pin each selected directory and read a private regular inode exactly."""
    parts = relative.split("/")
    parent_fd = os.dup(directory_fd)
    try:
        for component in parts[:-1]:
            opened = os.open(component, _DIR, dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = opened
            _dir(parent_fd)
        fd = os.open(parts[-1], _READ, dir_fd=parent_fd)
        try:
            first = os.fstat(fd)
            linked = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
            if (
                not stat.S_ISREG(first.st_mode)
                or first.st_uid != os.getuid() or first.st_nlink != 1
                or first.st_mode & 0o077
                or not 1 <= first.st_size <= max_bytes
                or (first.st_dev, first.st_ino, first.st_size)
                != (linked.st_dev, linked.st_ino, linked.st_size)
            ):
                raise PrivateCapsuleHold("sealed capsule contains unsafe source inode")
            buffer = bytearray()
            while len(buffer) <= first.st_size:
                part = os.read(fd, min(16384, first.st_size + 1 - len(buffer)))
                if not part:
                    break
                buffer.extend(part)
            second = os.fstat(fd)
            again = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
            if (
                len(buffer) != first.st_size
                or (first.st_dev, first.st_ino, first.st_size, first.st_mtime_ns)
                != (second.st_dev, second.st_ino, second.st_size, second.st_mtime_ns)
                or (first.st_dev, first.st_ino, first.st_size)
                != (again.st_dev, again.st_ino, again.st_size)
            ):
                raise PrivateCapsuleHold("source bytes changed while verifying sealed capsule")
            return bytes(buffer)
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def _capsule_tree(root_fd: int) -> tuple[set[str], set[str]]:
    """Bounded descriptor walk that rejects symlinks, aliases and extra files."""
    files: set[str] = set()
    folders: set[str] = set()
    pending: list[tuple[int, str]] = [(os.dup(root_fd), "")]
    try:
        while pending:
            fd, prefix = pending.pop()
            try:
                _dir(fd)
                # An iterator, not os.listdir(), bounds even an attacker
                # placing millions of entries inside a private directory.
                inspected = 0
                with os.scandir(fd) as entries:
                    for child in entries:
                        inspected += 1
                        if inspected + len(files) + len(folders) > 512:
                            raise PrivateCapsuleHold("unbounded or suspicious capsule tree")
                        name = child.name
                        if type(name) is not str or not name or "/" in name:
                            raise PrivateCapsuleHold("untrusted private source tree name")
                        relative = prefix + name
                        st = os.stat(name, dir_fd=fd, follow_symlinks=False)
                        if st.st_uid != os.getuid() or st.st_mode & 0o077:
                            raise PrivateCapsuleHold("shared or substituted capsule tree inode")
                        if stat.S_ISDIR(st.st_mode):
                            if len(folders) >= 256:
                                raise PrivateCapsuleHold("capsule directory depth or count exceeded")
                            folders.add(relative)
                            opened = os.open(name, _DIR, dir_fd=fd)
                            try:
                                check = os.fstat(opened)
                                if (check.st_dev, check.st_ino) != (st.st_dev, st.st_ino):
                                    raise PrivateCapsuleHold("private capsule directory replaced")
                                pending.append((opened, relative + "/"))
                                opened = None
                            finally:
                                if opened is not None:
                                    os.close(opened)
                        elif stat.S_ISREG(st.st_mode):
                            if st.st_nlink != 1:
                                raise PrivateCapsuleHold("aliased capsule file denied")
                            if len(files) >= MAX_CAPSULE_FILES + 1:
                                raise PrivateCapsuleHold("unreviewed source files exceed capsule bound")
                            files.add(relative)
                        else:
                            raise PrivateCapsuleHold("nonregular or symbolic capsule entry denied")
            finally:
                os.close(fd)
        return files, folders
    finally:
        for fd, _ in pending:
            os.close(fd)


def _strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PrivateCapsuleHold("duplicate private seal authority")
        result[key] = value
    return result


def _nonfinite(_):
    raise PrivateCapsuleHold("invalid nonfinite private seal")


def verify_private_capsule(
    destination: str | Path, *,
    original_project_root: str,
    expected_capsule_sha256: str,
    expected_seal_sha256: str,
) -> dict[str, object]:
    """Cold-open *all* selected source and verify the final seal independently.

    No project read, model call, Git, file write, source import, compilation or
    test process. Human must separately approve any use of these inert files.
    """
    if (
        type(original_project_root) is not str
        or not Path(original_project_root).is_absolute()
        or ".." in Path(original_project_root).parts
        or not _sha(expected_capsule_sha256)
        or not _sha(expected_seal_sha256)
    ):
        raise PrivateCapsuleHold("complete original root and SHA custody needed")
    path = _new_destination(destination, original_project_root)
    private_parent = _pinned_private_directory(path)
    capsule_fd = None
    try:
        _identical_parent(path, private_parent)
        capsule_fd = os.open(path.name, _DIR, dir_fd=private_parent)
        _dir(capsule_fd)
        before = os.fstat(capsule_fd)
        current = os.stat(path.name, dir_fd=private_parent, follow_symlinks=False)
        if (before.st_dev, before.st_ino) != (current.st_dev, current.st_ino):
            raise PrivateCapsuleHold("private capsule directory changed")
        raw = _read_capsule_file(capsule_fd, SEAL_NAME, 16384)
        if _hash(raw) != expected_seal_sha256:
            raise PrivateCapsuleHold("complete capsule seal not original approved bytes")
        try:
            seal = json.loads(
                raw.decode("utf-8", "strict"), object_pairs_hook=_strict_pairs,
                parse_constant=_nonfinite,
            )
        except (UnicodeError, ValueError, TypeError) as exc:
            raise PrivateCapsuleHold("private completion seal malformed") from exc
        keys = {
            "schema", "status", "capsule_sha256",
            "source_manifest_sha256", "patch_sha256", "python_graph_sha256",
            "python_closure_sha256", "unverified_source_import_count",
            "file_count", "files", "source_code_executed",
            "original_checkout_modified", "full_project_or_device_qualified",
            "release_certified",
        }
        if (
            type(seal) is not dict or set(seal) != keys
            or raw != _canonical(seal)
            or seal["schema"] != SEAL_SCHEMA
            or seal["status"] != "private-source-capsule-complete-unexecuted"
            or seal["capsule_sha256"] != expected_capsule_sha256
            or any(not _sha(seal[k]) for k in (
                "source_manifest_sha256", "patch_sha256", "python_graph_sha256",
                "python_closure_sha256",
            ))
            or any(seal[k] is not False for k in (
                "source_code_executed", "original_checkout_modified",
                "full_project_or_device_qualified", "release_certified",
            ))
            or type(seal["unverified_source_import_count"]) is not int
            or not 0 <= seal["unverified_source_import_count"] <= 2048
            or type(seal["file_count"]) is not int
            or not 2 <= seal["file_count"] <= MAX_CAPSULE_FILES
            or type(seal["files"]) is not list
            or len(seal["files"]) != seal["file_count"]
        ):
            raise PrivateCapsuleHold("unqualified or altered source capsule seal")
        approved = {}
        total = 0
        source_records = []
        for row in seal["files"]:
            if type(row) is not dict or set(row) != {
                "path", "kind", "sha256", "bytes",
            }:
                raise PrivateCapsuleHold("unsupported source capsule file inventory")
            name = row["path"]
            try:
                parts = _relative(name)
            except (WorkspaceDeliveryHold, ValueError) as exc:
                raise PrivateCapsuleHold("untrusted source path in seal") from exc
            if (
                name == SEAL_NAME or name.casefold() in approved
                or not all(_allowed_name(p, directory=i < len(parts)-1)
                           for i, p in enumerate(parts))
                or row["kind"] not in ("selected-original", "new", "edit")
                or not _sha(row["sha256"])
                or type(row["bytes"]) is not int
                or not 1 <= row["bytes"] <= 65536
            ):
                raise PrivateCapsuleHold("untrusted source file or digest in private seal")
            total += row["bytes"]
            if total > MAX_TOTAL_CAPSULE_BYTES:
                raise PrivateCapsuleHold("capsule source aggregate exceeded")
            approved[name.casefold()] = name
            # Byte count is verified by exact read, not a directory listing.
            data = _read_capsule_file(capsule_fd, name, row["bytes"])
            if len(data) != row["bytes"] or _hash(data) != row["sha256"]:
                raise PrivateCapsuleHold("sealed source file content differs")
            source_records.append(ClosureSource(
                name, row["kind"], data, row["sha256"],
            ))
        closure = analyze_capsule_source_closure(
            tuple(source_records),
            source_manifest_sha256=seal["source_manifest_sha256"],
            source_patch_sha256=seal["patch_sha256"],
        )
        if (
            closure.graph_sha256 != seal["python_closure_sha256"]
            or closure.unverified_count != seal["unverified_source_import_count"]
        ):
            raise PrivateCapsuleHold("sealed original/import graph differs from source")
        paths = [row["path"] for row in seal["files"]]
        if paths != sorted(paths, key=lambda x: (x.casefold(), x)):
            raise PrivateCapsuleHold("source inventory must be canonical sorted order")
        expected_files = set(paths) | {SEAL_NAME}
        expected_dirs = {
            "/".join(p.split("/")[:i])
            for p in paths for i in range(1, len(p.split("/")))
        }
        actual_files, actual_dirs = _capsule_tree(capsule_fd)
        if actual_files != expected_files or actual_dirs != expected_dirs:
            raise PrivateCapsuleHold("capsule contains missing or unapproved tree entries")
        # Reopen every byte after the whole tree walk. A directory entry
        # swapped between the first read and tree enumeration cannot become
        # silently accepted as the final source capsule.
        for row in seal["files"]:
            final_bytes = _read_capsule_file(
                capsule_fd, row["path"], row["bytes"],
            )
            if len(final_bytes) != row["bytes"] or _hash(final_bytes) != row["sha256"]:
                raise PrivateCapsuleHold("capsule source changed after tree audit")
        _identical_parent(path, private_parent)
        after = os.stat(path.name, dir_fd=private_parent, follow_symlinks=False)
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise PrivateCapsuleHold("private capsule replaced after cold verification")
        # Recheck fixed seal after the full directory walk to catch late swaps.
        if _read_capsule_file(capsule_fd, SEAL_NAME, 16384) != raw:
            raise PrivateCapsuleHold("final seal changed during cold verification")
        return {
            "schema": SCHEMA,
            "status": "cold-source-capsule-verified-unexecuted",
            "capsule_sha256": expected_capsule_sha256,
            "seal_sha256": expected_seal_sha256,
            "source_manifest_sha256": seal["source_manifest_sha256"],
            "patch_sha256": seal["patch_sha256"],
            "python_closure_sha256": closure.graph_sha256,
            "linked_original_source_imports": closure.linked_original_count,
            "unverified_external_or_unselected_imports": closure.unverified_count,
            "file_count": len(paths),
            "source_bytes": total,
            "all_sealed_source_bytes_verified": True,
            "original_project_modified": False,
            "source_code_executed": False,
            "all_source_dependencies_complete": False,
            "release_certified": False,
        }
    finally:
        if capsule_fd is not None:
            os.close(capsule_fd)
        os.close(private_parent)
