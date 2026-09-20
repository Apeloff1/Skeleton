from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
import stat

import pytest

from skeleton.security.rooted_fs import (
    FileReceipt,
    FilesystemBoundaryError,
    FilesystemLimits,
    FilesystemPathError,
    FilesystemQuotaError,
    FilesystemRaceError,
    RootedFilesystem,
    receipts_digest,
)


def fs(tmp_path: Path, **limits: int) -> RootedFilesystem:
    return RootedFilesystem(
        tmp_path,
        limits=FilesystemLimits(**limits) if limits else None,
    )


@pytest.mark.parametrize(
    "path",
    [
        "../escape",
        "../../escape",
        "/absolute",
        "C:/windows",
        "C:\\windows",
        "",
        ".",
        "./",
        "a/../../../escape",
        "safe/../../escape",
        "nul\x00byte",
        "line\nbreak",
    ],
)
def test_normalization_rejects_escape_or_ambiguous_paths(
    tmp_path: Path,
    path: str,
) -> None:
    boundary = fs(tmp_path)
    with pytest.raises((FilesystemPathError, FilesystemQuotaError)):
        boundary.normalize(path)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a/b.txt", "a/b.txt"),
        ("./a/b.txt", "a/b.txt"),
        ("a/./b.txt", "a/b.txt"),
        ("a/x/../b.txt", "a/b.txt"),
        ("folder\\child.txt", "folder/child.txt"),
    ],
)
def test_normalization_is_deterministic(
    tmp_path: Path,
    raw: str,
    expected: str,
) -> None:
    assert fs(tmp_path).normalize(raw) == expected


def test_path_byte_bound_is_enforced(tmp_path: Path) -> None:
    boundary = fs(tmp_path, max_path_bytes=8)
    with pytest.raises(FilesystemQuotaError, match="byte bound"):
        boundary.normalize("123456789")


def test_path_depth_bound_is_enforced(tmp_path: Path) -> None:
    boundary = fs(tmp_path, max_depth=2)
    with pytest.raises(FilesystemQuotaError, match="depth"):
        boundary.normalize("a/b/c")


def test_root_must_exist_and_be_directory(tmp_path: Path) -> None:
    with pytest.raises(FilesystemPathError):
        RootedFilesystem(tmp_path / "missing")
    file_path = tmp_path / "file"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(FilesystemPathError):
        RootedFilesystem(file_path)


def test_root_symlink_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(FilesystemPathError, match="symlink"):
        RootedFilesystem(link)


def test_root_fingerprint_is_stable_for_same_root(tmp_path: Path) -> None:
    left = RootedFilesystem(tmp_path)
    right = RootedFilesystem(tmp_path)
    assert left.root_fingerprint == right.root_fingerprint
    assert len(left.root_fingerprint) == 64


def test_write_and_read_bytes_roundtrip(tmp_path: Path) -> None:
    boundary = fs(tmp_path)
    receipt = boundary.write_bytes("artifact.bin", b"payload")
    assert receipt.path == "artifact.bin"
    assert receipt.size == 7
    assert receipt.sha256 == hashlib.sha256(b"payload").hexdigest()
    assert boundary.read_bytes("artifact.bin") == b"payload"


def test_write_text_roundtrip_and_receipt(tmp_path: Path) -> None:
    boundary = fs(tmp_path)
    receipt = boundary.write_text("note.txt", "hello Ω")
    assert boundary.read_text("note.txt") == "hello Ω"
    assert receipt.mode & 0o022 == 0
    assert receipt.size == len("hello Ω".encode())


def test_create_parents_is_explicit(tmp_path: Path) -> None:
    boundary = fs(tmp_path)
    with pytest.raises(FilesystemPathError):
        boundary.write_bytes("a/b/c.bin", b"x")
    receipt = boundary.write_bytes(
        "a/b/c.bin",
        b"x",
        create_parents=True,
    )
    assert receipt.path == "a/b/c.bin"
    assert (tmp_path / "a" / "b" / "c.bin").read_bytes() == b"x"


@pytest.mark.parametrize("mode", [0o666, 0o622, 0o606, 0o777])
def test_write_rejects_group_or_world_writable_modes(
    tmp_path: Path,
    mode: int,
) -> None:
    with pytest.raises(ValueError, match="writable"):
        fs(tmp_path).write_bytes("x", b"x", mode=mode)


@pytest.mark.parametrize("mode", [-1, 0o1000, True, "600"])
def test_write_rejects_invalid_modes(tmp_path: Path, mode: object) -> None:
    with pytest.raises(ValueError):
        fs(tmp_path).write_bytes("x", b"x", mode=mode)  # type: ignore[arg-type]


def test_write_bound_is_checked_before_disk_mutation(tmp_path: Path) -> None:
    boundary = fs(tmp_path, max_write_bytes=4)
    with pytest.raises(FilesystemQuotaError):
        boundary.write_bytes("too-big", b"12345")
    assert not (tmp_path / "too-big").exists()


def test_read_bound_uses_metadata_and_stream_limit(tmp_path: Path) -> None:
    (tmp_path / "large").write_bytes(b"12345")
    boundary = fs(tmp_path, max_read_bytes=4)
    with pytest.raises(FilesystemQuotaError):
        boundary.read_bytes("large")


def test_caller_cannot_raise_read_bound_above_cap(tmp_path: Path) -> None:
    (tmp_path / "large").write_bytes(b"12345")
    boundary = fs(tmp_path, max_read_bytes=4)
    with pytest.raises(FilesystemQuotaError):
        boundary.read_bytes("large", max_bytes=999)


@pytest.mark.parametrize("bound", [-1, True, 1.5, "5"])
def test_invalid_read_bound_is_rejected(
    tmp_path: Path,
    bound: object,
) -> None:
    (tmp_path / "x").write_bytes(b"x")
    with pytest.raises(ValueError):
        fs(tmp_path).read_bytes("x", max_bytes=bound)  # type: ignore[arg-type]


def test_existing_symlink_file_is_never_read(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.write_text("secret", encoding="utf-8")
    link = tmp_path / "link"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(FilesystemPathError, match="symlink"):
        fs(tmp_path).read_bytes("link")


def test_symlink_parent_is_never_traversed_for_write(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside-dir"
    outside.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(FilesystemPathError, match="symlink"):
        fs(tmp_path).write_bytes("link/payload", b"unsafe")
    assert not (outside / "payload").exists()


@pytest.mark.skipif(
    os.open not in os.supports_dir_fd,
    reason="descriptor-relative open is unavailable",
)
def test_read_remains_bound_when_parent_path_is_swapped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    safe = tmp_path / "safe"
    safe.mkdir()
    (safe / "payload").write_bytes(b"inside")
    outside = tmp_path.parent / f"{tmp_path.name}-read-race-outside"
    outside.mkdir()
    (outside / "payload").write_bytes(b"outside")

    probe = tmp_path / "symlink-probe"
    try:
        probe.symlink_to(outside, target_is_directory=True)
        probe.unlink()
    except OSError:
        pytest.skip("symlinks unavailable")

    boundary = fs(tmp_path)
    real_open = os.open
    swapped = False

    def racing_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        if path == "payload" and dir_fd is not None and not swapped:
            swapped = True
            moved = tmp_path / "safe-moved"
            safe.rename(moved)
            safe.symlink_to(outside, target_is_directory=True)
        if dir_fd is None:
            return real_open(path, flags, mode)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", racing_open)
    assert boundary.read_bytes("safe/payload") == b"inside"
    assert swapped
    assert (outside / "payload").read_bytes() == b"outside"


@pytest.mark.skipif(
    os.open not in os.supports_dir_fd,
    reason="descriptor-relative open is unavailable",
)
def test_stream_write_cannot_escape_after_parent_path_swap(
    tmp_path: Path,
) -> None:
    safe = tmp_path / "safe"
    safe.mkdir()
    moved = tmp_path / "safe-moved"
    outside = tmp_path.parent / f"{tmp_path.name}-write-race-outside"
    outside.mkdir()
    probe = tmp_path / "symlink-probe"
    try:
        probe.symlink_to(outside, target_is_directory=True)
        probe.unlink()
    except OSError:
        pytest.skip("symlinks unavailable")
    boundary = fs(tmp_path)

    def chunks():
        yield b"inside-"
        safe.rename(moved)
        safe.symlink_to(outside, target_is_directory=True)
        yield b"only"

    receipt = boundary.write_stream(
        "safe/payload",
        chunks(),
        expected_size=len(b"inside-only"),
    )
    assert receipt.size == len(b"inside-only")
    assert (moved / "payload").read_bytes() == b"inside-only"
    assert not (outside / "payload").exists()


def test_atomic_write_replaces_regular_file(tmp_path: Path) -> None:
    target = tmp_path / "value"
    target.write_bytes(b"old")
    boundary = fs(tmp_path)
    receipt = boundary.write_bytes("value", b"new")
    assert target.read_bytes() == b"new"
    assert receipt.sha256 == hashlib.sha256(b"new").hexdigest()


def test_atomic_write_rejects_directory_target(tmp_path: Path) -> None:
    (tmp_path / "value").mkdir()
    with pytest.raises(FilesystemPathError):
        fs(tmp_path).write_bytes("value", b"new")


def test_atomic_write_rejects_symlink_target(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-write-outside"
    outside.write_text("old", encoding="utf-8")
    link = tmp_path / "value"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(FilesystemPathError):
        fs(tmp_path).write_bytes("value", b"new")
    assert outside.read_text(encoding="utf-8") == "old"


def test_stream_write_is_bounded_and_hashed(tmp_path: Path) -> None:
    boundary = fs(tmp_path, max_write_bytes=16, max_stream_chunks=4)
    receipt = boundary.write_stream("stream", [b"ab", b"cd", b"ef"])
    assert receipt.size == 6
    assert receipt.sha256 == hashlib.sha256(b"abcdef").hexdigest()
    assert (tmp_path / "stream").read_bytes() == b"abcdef"


def test_stream_write_expected_size_is_enforced(tmp_path: Path) -> None:
    boundary = fs(tmp_path)
    with pytest.raises(FilesystemBoundaryError, match="declared"):
        boundary.write_stream("stream", [b"abc"], expected_size=4)
    assert not (tmp_path / "stream").exists()


def test_stream_write_declared_size_cannot_exceed_policy(tmp_path: Path) -> None:
    boundary = fs(tmp_path, max_write_bytes=3)
    with pytest.raises(FilesystemQuotaError):
        boundary.write_stream("stream", [b"x"], expected_size=4)


def test_stream_write_runtime_size_cannot_exceed_policy(tmp_path: Path) -> None:
    boundary = fs(tmp_path, max_write_bytes=3)
    with pytest.raises(FilesystemQuotaError):
        boundary.write_stream("stream", [b"12", b"34"])
    assert not (tmp_path / "stream").exists()


def test_stream_chunk_count_is_bounded(tmp_path: Path) -> None:
    boundary = fs(tmp_path, max_stream_chunks=2)
    with pytest.raises(FilesystemQuotaError, match="chunk-count"):
        boundary.write_stream("stream", [b"a", b"b", b"c"])
    assert not (tmp_path / "stream").exists()


def test_failed_stream_does_not_leave_temp_files(tmp_path: Path) -> None:
    boundary = fs(tmp_path, max_write_bytes=1)
    with pytest.raises(FilesystemQuotaError):
        boundary.write_stream("artifact", [b"too large"])
    assert list(tmp_path.iterdir()) == []


def test_mkdir_is_bounded_and_non_writable(tmp_path: Path) -> None:
    boundary = fs(tmp_path)
    assert boundary.mkdir("a/b", parents=True) == "a/b"
    assert (tmp_path / "a" / "b").is_dir()
    assert stat.S_IMODE((tmp_path / "a" / "b").stat().st_mode) & 0o022 == 0


def test_mkdir_without_parents_fails_for_missing_parent(tmp_path: Path) -> None:
    with pytest.raises(FilesystemPathError):
        fs(tmp_path).mkdir("a/b")


def test_mkdir_rejects_symlink_component(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-mkdir-outside"
    outside.mkdir()
    link = tmp_path / "a"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(FilesystemPathError):
        fs(tmp_path).mkdir("a/b", parents=True)


@pytest.mark.skipif(
    os.open not in os.supports_dir_fd,
    reason="descriptor-relative open is unavailable",
)
def test_mkdir_remains_bound_when_parent_path_is_swapped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    safe = tmp_path / "safe"
    safe.mkdir()
    moved = tmp_path / "safe-moved"
    outside = tmp_path.parent / f"{tmp_path.name}-mkdir-race-outside"
    outside.mkdir()
    probe = tmp_path / "symlink-probe"
    try:
        probe.symlink_to(outside, target_is_directory=True)
        probe.unlink()
    except OSError:
        pytest.skip("symlinks unavailable")

    boundary = fs(tmp_path)
    real_mkdir = os.mkdir
    swapped = False

    def racing_mkdir(path, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        if path == "child" and dir_fd is not None and not swapped:
            swapped = True
            safe.rename(moved)
            safe.symlink_to(outside, target_is_directory=True)
        if dir_fd is None:
            return real_mkdir(path, mode)
        return real_mkdir(path, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "mkdir", racing_mkdir)
    assert boundary.mkdir("safe/child") == "safe/child"
    assert swapped
    assert (moved / "child").is_dir()
    assert not (outside / "child").exists()


@pytest.mark.skipif(
    os.open not in os.supports_dir_fd,
    reason="descriptor-relative open is unavailable",
)
def test_list_remains_bound_when_parent_path_is_swapped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    safe = tmp_path / "safe"
    safe.mkdir()
    (safe / "inside").write_bytes(b"inside")
    moved = tmp_path / "safe-moved"
    outside = tmp_path.parent / f"{tmp_path.name}-list-race-outside"
    outside.mkdir()
    (outside / "outside").write_bytes(b"outside")
    probe = tmp_path / "symlink-probe"
    try:
        probe.symlink_to(outside, target_is_directory=True)
        probe.unlink()
    except OSError:
        pytest.skip("symlinks unavailable")

    boundary = fs(tmp_path)
    real_scandir = os.scandir
    swapped = False

    def racing_scandir(path):
        nonlocal swapped
        if isinstance(path, int) and not swapped:
            swapped = True
            safe.rename(moved)
            safe.symlink_to(outside, target_is_directory=True)
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", racing_scandir)
    assert boundary.list_files("safe", recursive=True) == ("safe/inside",)
    assert swapped


@pytest.mark.skipif(
    os.open not in os.supports_dir_fd,
    reason="descriptor-relative open is unavailable",
)
def test_remove_remains_bound_when_parent_path_is_swapped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    safe = tmp_path / "safe"
    safe.mkdir()
    (safe / "payload").write_bytes(b"inside")
    moved = tmp_path / "safe-moved"
    outside = tmp_path.parent / f"{tmp_path.name}-remove-race-outside"
    outside.mkdir()
    (outside / "payload").write_bytes(b"outside")
    probe = tmp_path / "symlink-probe"
    try:
        probe.symlink_to(outside, target_is_directory=True)
        probe.unlink()
    except OSError:
        pytest.skip("symlinks unavailable")

    boundary = fs(tmp_path)
    real_unlink = os.unlink
    swapped = False

    def racing_unlink(path, *, dir_fd=None):
        nonlocal swapped
        if path == "payload" and dir_fd is not None and not swapped:
            swapped = True
            safe.rename(moved)
            safe.symlink_to(outside, target_is_directory=True)
        if dir_fd is None:
            return real_unlink(path)
        return real_unlink(path, dir_fd=dir_fd)

    monkeypatch.setattr(os, "unlink", racing_unlink)
    boundary.remove_file("safe/payload")
    assert swapped
    assert not (moved / "payload").exists()
    assert (outside / "payload").read_bytes() == b"outside"


def test_snapshot_returns_identity_without_following_links(tmp_path: Path) -> None:
    path = tmp_path / "x"
    path.write_bytes(b"abc")
    snapshot = fs(tmp_path).snapshot("x")
    stat_result = path.stat()
    assert snapshot.path == "x"
    assert snapshot.size == 3
    assert snapshot.inode == stat_result.st_ino
    assert snapshot.device == stat_result.st_dev


def test_snapshot_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_bytes(b"x")
    link = tmp_path / "link"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(FilesystemPathError):
        fs(tmp_path).snapshot("link")


def test_remove_file_removes_only_regular_file(tmp_path: Path) -> None:
    (tmp_path / "x").write_bytes(b"x")
    boundary = fs(tmp_path)
    boundary.remove_file("x")
    assert not (tmp_path / "x").exists()


def test_remove_file_rejects_directory(tmp_path: Path) -> None:
    (tmp_path / "x").mkdir()
    with pytest.raises(FilesystemPathError):
        fs(tmp_path).remove_file("x")
    assert (tmp_path / "x").is_dir()


def test_remove_file_rejects_symlink_without_touching_target(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_bytes(b"safe")
    link = tmp_path / "link"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(FilesystemPathError):
        fs(tmp_path).remove_file("link")
    assert target.read_bytes() == b"safe"


def test_list_files_is_sorted_and_non_recursive_by_default(tmp_path: Path) -> None:
    (tmp_path / "b").write_bytes(b"")
    (tmp_path / "a").write_bytes(b"")
    (tmp_path / "dir").mkdir()
    (tmp_path / "dir" / "z").write_bytes(b"")
    boundary = fs(tmp_path)
    assert boundary.list_files() == ("a", "b")
    assert boundary.list_files(recursive=True) == ("a", "b", "dir/z")


def test_list_files_from_subdirectory(tmp_path: Path) -> None:
    (tmp_path / "dir").mkdir()
    (tmp_path / "dir" / "x").write_bytes(b"")
    assert fs(tmp_path).list_files("dir", recursive=True) == ("dir/x",)


def test_list_files_rejects_symlink_entries(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_bytes(b"x")
    link = tmp_path / "link"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(FilesystemPathError, match="symlink"):
        fs(tmp_path).list_files()


def test_list_file_count_is_bounded(tmp_path: Path) -> None:
    for index in range(3):
        (tmp_path / f"f{index}").write_bytes(b"")
    boundary = fs(tmp_path, max_directory_entries=2)
    with pytest.raises(FilesystemQuotaError):
        boundary.list_files()


def test_temporary_directory_is_rooted_and_removed(tmp_path: Path) -> None:
    boundary = fs(tmp_path)
    child_root: Path | None = None
    with boundary.temporary_directory(prefix=".secure-") as child:
        child_root = child.root
        assert child.root.parent == tmp_path.resolve()
        child.write_text("value", "secret")
        assert child.read_text("value") == "secret"
    assert child_root is not None
    assert not child_root.exists()


@pytest.mark.parametrize("prefix", ["", "../x", "a/b", "a\\b", ".", ".."])
def test_temporary_directory_prefix_is_validated(
    tmp_path: Path,
    prefix: str,
) -> None:
    with pytest.raises(FilesystemPathError):
        with fs(tmp_path).temporary_directory(prefix=prefix):
            pass


@pytest.mark.skipif(
    os.open not in os.supports_dir_fd
    or not getattr(shutil.rmtree, "avoids_symlink_attacks", False),
    reason="descriptor-safe temporary directories are unavailable",
)
def test_temporary_directory_fails_closed_on_root_path_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    boundary = fs(tmp_path)
    moved = tmp_path.parent / f"{tmp_path.name}-temp-race-moved"
    outside = tmp_path.parent / f"{tmp_path.name}-temp-race-outside"
    outside.mkdir()
    probe = tmp_path / "symlink-probe"
    try:
        probe.symlink_to(outside, target_is_directory=True)
        probe.unlink()
    except OSError:
        pytest.skip("symlinks unavailable")

    real_mkdir = os.mkdir
    swapped = False
    attacker_child: Path | None = None

    def racing_mkdir(path, mode=0o777, *, dir_fd=None):
        nonlocal swapped, attacker_child
        if dir_fd is not None and not swapped and str(path).startswith(".work-"):
            swapped = True
            tmp_path.rename(moved)
            tmp_path.symlink_to(outside, target_is_directory=True)
            attacker_child = outside / str(path)
            attacker_child.mkdir()
        if dir_fd is None:
            return real_mkdir(path, mode)
        return real_mkdir(path, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "mkdir", racing_mkdir)
    with pytest.raises(FilesystemRaceError):
        with boundary.temporary_directory():
            raise AssertionError("swapped root must never yield a capability")

    assert swapped
    assert attacker_child is not None
    assert attacker_child.is_dir()
    assert not any(moved.iterdir())


def test_temporary_directory_cleanup_is_recursive(tmp_path: Path) -> None:
    boundary = fs(tmp_path)
    with boundary.temporary_directory() as child:
        child.mkdir("a/b", parents=True)
        child.write_bytes("a/b/c", b"x")
        root = child.root
    assert not root.exists()


def test_receipts_digest_is_order_independent() -> None:
    a = FileReceipt("a", 1, "a" * 64, 0o600)
    b = FileReceipt("b", 2, "b" * 64, 0o600)
    assert receipts_digest([a, b]) == receipts_digest([b, a])
    assert len(receipts_digest([a, b])) == 64


def test_receipts_digest_rejects_non_receipt() -> None:
    with pytest.raises(TypeError):
        receipts_digest([object()])  # type: ignore[list-item]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_read_bytes": 0},
        {"max_write_bytes": -1},
        {"max_stream_chunks": True},
        {"max_path_bytes": 0},
        {"max_depth": 0},
        {"max_directory_entries": 0},
    ],
)
def test_limits_require_positive_integers(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        FilesystemLimits(**kwargs)  # type: ignore[arg-type]


def test_file_receipt_validates_digest() -> None:
    with pytest.raises(ValueError):
        FileReceipt("x", 1, "bad", 0o600)


def test_file_receipt_validates_size() -> None:
    with pytest.raises(ValueError):
        FileReceipt("x", -1, "a" * 64, 0o600)


def test_file_receipt_validates_mode() -> None:
    with pytest.raises(ValueError):
        FileReceipt("x", 1, "a" * 64, 0o1000)


def test_exists_distinguishes_missing_from_unsafe_symlink(tmp_path: Path) -> None:
    boundary = fs(tmp_path)
    assert boundary.exists("missing") is False
    target = tmp_path / "target"
    target.write_bytes(b"x")
    link = tmp_path / "link"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(FilesystemPathError):
        boundary.exists("link")


def test_read_rejects_directory(tmp_path: Path) -> None:
    (tmp_path / "dir").mkdir()
    with pytest.raises(FilesystemPathError):
        fs(tmp_path).read_bytes("dir")


def test_text_decode_failure_is_sanitized(tmp_path: Path) -> None:
    (tmp_path / "x").write_bytes(b"\xff")
    with pytest.raises(FilesystemBoundaryError, match="decoding"):
        fs(tmp_path).read_text("x", encoding="utf-8")


def test_text_encode_failure_is_sanitized(tmp_path: Path) -> None:
    with pytest.raises(FilesystemBoundaryError, match="encoding"):
        fs(tmp_path).write_text("x", "\udcff", encoding="utf-8")
    assert not (tmp_path / "x").exists()


def test_write_receipt_tracks_requested_secure_mode(tmp_path: Path) -> None:
    receipt = fs(tmp_path).write_bytes("x", b"x", mode=0o640)
    assert receipt.mode == 0o640


def test_parent_directory_that_is_regular_file_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "a").write_bytes(b"x")
    with pytest.raises(FilesystemPathError):
        fs(tmp_path).write_bytes("a/b", b"x", create_parents=True)


def test_root_identity_change_is_detected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    boundary = fs(tmp_path)
    original = Path.stat

    class FakeStat:
        st_dev = 999999999
        st_ino = 999999998

    def changed(self: Path, *args, **kwargs):
        if self == boundary.root:
            return FakeStat()
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", changed)
    with pytest.raises(FilesystemRaceError, match="identity"):
        boundary.normalize("still-normal")  # normalization itself is pure
        boundary._assert_root_identity()


def test_write_empty_file_is_supported(tmp_path: Path) -> None:
    receipt = fs(tmp_path).write_bytes("empty", b"")
    assert receipt.size == 0
    assert receipt.sha256 == hashlib.sha256(b"").hexdigest()
    assert (tmp_path / "empty").read_bytes() == b""


def test_empty_stream_is_supported_when_declared_empty(tmp_path: Path) -> None:
    receipt = fs(tmp_path).write_stream("empty", [], expected_size=0)
    assert receipt.size == 0
    assert (tmp_path / "empty").read_bytes() == b""


def test_list_files_rejects_fifo_when_available(tmp_path: Path) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO unavailable")
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    with pytest.raises(FilesystemPathError, match="unsupported"):
        fs(tmp_path).list_files()


def test_read_rejects_fifo_when_available(tmp_path: Path) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO unavailable")
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    with pytest.raises(FilesystemPathError):
        fs(tmp_path).read_bytes("pipe")


def test_remove_rejects_fifo_when_available(tmp_path: Path) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO unavailable")
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    with pytest.raises(FilesystemPathError):
        fs(tmp_path).remove_file("pipe")


def test_snapshot_does_not_expose_file_content(tmp_path: Path) -> None:
    secret = "SUPER_SECRET_CONTENT"
    (tmp_path / "x").write_text(secret, encoding="utf-8")
    snapshot = fs(tmp_path).snapshot("x")
    assert secret not in repr(snapshot)


def test_error_does_not_echo_invalid_path_payload(tmp_path: Path) -> None:
    secret = "SECRET_PATH_PAYLOAD"
    with pytest.raises(FilesystemPathError) as caught:
        fs(tmp_path).read_bytes(f"../{secret}")
    assert secret not in str(caught.value)
