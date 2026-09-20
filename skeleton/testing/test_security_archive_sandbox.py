from __future__ import annotations

import io
import json
import os
from pathlib import Path
import stat
import tarfile
import zipfile

import pytest

import skeleton.security.archive_sandbox as archive_sandbox
from skeleton.security.archive_sandbox import (
    ArchiveFormatError,
    ArchiveIntegrityError,
    ArchiveLimits,
    ArchivePolicyError,
    ArchiveSandboxError,
    extract_archive,
    load_extraction_manifest,
    plan_archive,
)


def write_zip(
    path: Path,
    members: list[tuple[str, bytes]],
    *,
    compression: int = zipfile.ZIP_DEFLATED,
) -> Path:
    raw_name_substitutions: list[tuple[bytes, bytes]] = []
    with zipfile.ZipFile(path, "w", compression=compression) as handle:
        for name, payload in members:
            if "\x00" in name:
                # ZipInfo's constructor truncates NUL names before serialization.
                # Write an equal-length placeholder, then patch both local and
                # central-directory filename bytes so the parser sees genuine
                # hostile archive evidence.
                placeholder = name.replace("\x00", "X")
                handle.writestr(placeholder, payload)
                raw_name_substitutions.append(
                    (placeholder.encode("utf-8"), name.encode("utf-8"))
                )
            else:
                handle.writestr(name, payload)
    if raw_name_substitutions:
        raw = path.read_bytes()
        for placeholder, hostile in raw_name_substitutions:
            if len(placeholder) != len(hostile) or raw.count(placeholder) < 2:
                raise AssertionError("unable to construct raw ZIP filename fixture")
            raw = raw.replace(placeholder, hostile)
        path.write_bytes(raw)
    return path


def write_tar(path: Path, members: list[tuple[str, bytes]]) -> Path:
    with tarfile.open(path, "w") as handle:
        for name, payload in members:
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mode = 0o644
            handle.addfile(info, io.BytesIO(payload))
    return path


@pytest.mark.parametrize(
    "name",
    [
        "../escape.txt",
        "../../escape.txt",
        "/absolute.txt",
        "C:/windows.txt",
        "C:\\windows.txt",
        "a/../../escape.txt",
        "safe/../../../escape.txt",
        "line\nbreak.txt",
        "nul\x00byte.txt",
    ],
)
def test_zip_rejects_traversal_absolute_or_ambiguous_paths(
    tmp_path: Path,
    name: str,
) -> None:
    archive = tmp_path / "bad.zip"
    write_zip(archive, [(name, b"x")])
    with pytest.raises(ArchivePolicyError):
        plan_archive(archive)


@pytest.mark.parametrize(
    "name",
    [
        "../escape.txt",
        "../../escape.txt",
        "/absolute.txt",
        "C:/windows.txt",
        "C:\\windows.txt",
        "a/../../escape.txt",
        "line\nbreak.txt",
    ],
)
def test_tar_rejects_traversal_absolute_or_ambiguous_paths(
    tmp_path: Path,
    name: str,
) -> None:
    archive = tmp_path / "bad.tar"
    write_tar(archive, [(name, b"x")])
    with pytest.raises(ArchivePolicyError):
        plan_archive(archive)


def test_zip_plan_is_deterministic(tmp_path: Path) -> None:
    archive = write_zip(
        tmp_path / "bundle.zip",
        [("a.txt", b"a"), ("dir/b.txt", b"bbb")],
        compression=zipfile.ZIP_STORED,
    )
    first = plan_archive(archive)
    second = plan_archive(archive)
    assert first == second
    assert first.kind == "zip"
    assert first.file_count == 2
    assert first.total_file_bytes == 4
    assert len(first.manifest_digest) == 64


def test_tar_plan_is_deterministic(tmp_path: Path) -> None:
    archive = write_tar(
        tmp_path / "bundle.tar",
        [("a.txt", b"a"), ("dir/b.txt", b"bbb")],
    )
    first = plan_archive(archive)
    second = plan_archive(archive)
    assert first == second
    assert first.kind == "tar"
    assert first.file_count == 2
    assert first.total_file_bytes == 4


def test_format_is_detected_from_content_not_suffix(tmp_path: Path) -> None:
    archive = write_zip(tmp_path / "not-a-zip.bin", [("x", b"x")])
    assert plan_archive(archive).kind == "zip"


def test_rejects_unknown_format(tmp_path: Path) -> None:
    archive = tmp_path / "data.bin"
    archive.write_bytes(b"not an archive")
    with pytest.raises(ArchiveFormatError, match="unsupported"):
        plan_archive(archive)


def test_rejects_empty_archive_file(tmp_path: Path) -> None:
    archive = tmp_path / "empty"
    archive.write_bytes(b"")
    with pytest.raises(ArchiveFormatError, match="empty"):
        plan_archive(archive)


def test_rejects_archive_symlink(tmp_path: Path) -> None:
    real = write_zip(tmp_path / "real.zip", [("x", b"x")])
    link = tmp_path / "link.zip"
    try:
        link.symlink_to(real)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(ArchivePolicyError, match="symlink"):
        plan_archive(link)


def test_rejects_archive_directory(tmp_path: Path) -> None:
    with pytest.raises(ArchivePolicyError, match="regular"):
        plan_archive(tmp_path)


def test_archive_byte_bound_is_enforced(tmp_path: Path) -> None:
    archive = write_zip(
        tmp_path / "bundle.zip",
        [("x", b"123456789")],
        compression=zipfile.ZIP_STORED,
    )
    with pytest.raises(ArchivePolicyError, match="archive exceeds"):
        plan_archive(
            archive,
            limits=ArchiveLimits(max_archive_bytes=4),
        )


def test_member_count_bound_is_enforced(tmp_path: Path) -> None:
    archive = write_zip(
        tmp_path / "bundle.zip",
        [("a", b"a"), ("b", b"b"), ("c", b"c")],
    )
    with pytest.raises(ArchivePolicyError, match="member-count"):
        plan_archive(archive, limits=ArchiveLimits(max_members=2))


def test_member_size_bound_is_enforced(tmp_path: Path) -> None:
    archive = write_zip(tmp_path / "bundle.zip", [("x", b"12345")])
    with pytest.raises(ArchivePolicyError, match="member exceeds"):
        plan_archive(
            archive,
            limits=ArchiveLimits(max_member_bytes=4),
        )


def test_total_expanded_size_bound_is_enforced(tmp_path: Path) -> None:
    archive = write_zip(
        tmp_path / "bundle.zip",
        [("a", b"123"), ("b", b"456")],
    )
    with pytest.raises(ArchivePolicyError, match="expanded-size"):
        plan_archive(
            archive,
            limits=ArchiveLimits(max_total_bytes=5),
        )


def test_zip_compression_ratio_bound_is_enforced(tmp_path: Path) -> None:
    archive = write_zip(
        tmp_path / "bomb.zip",
        [("zeros.bin", b"0" * 100_000)],
        compression=zipfile.ZIP_DEFLATED,
    )
    with pytest.raises(ArchivePolicyError, match="compression-ratio"):
        plan_archive(
            archive,
            limits=ArchiveLimits(
                max_compression_ratio=2.0,
                max_archive_expansion_ratio=10_000.0,
            ),
        )


def test_archive_expansion_ratio_bound_is_enforced(tmp_path: Path) -> None:
    archive = write_zip(
        tmp_path / "bundle.zip",
        [("zeros.bin", b"0" * 100_000)],
        compression=zipfile.ZIP_DEFLATED,
    )
    with pytest.raises(ArchivePolicyError, match="expansion-ratio"):
        plan_archive(
            archive,
            limits=ArchiveLimits(
                max_compression_ratio=10_000.0,
                max_archive_expansion_ratio=2.0,
            ),
        )


def test_duplicate_zip_member_path_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "dupe.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("same.txt", b"a")
        with pytest.warns(UserWarning):
            handle.writestr("same.txt", b"b")
    with pytest.raises(ArchivePolicyError, match="duplicate"):
        plan_archive(archive)


def test_casefold_zip_collision_is_rejected(tmp_path: Path) -> None:
    archive = write_zip(
        tmp_path / "case.zip",
        [("Readme.txt", b"a"), ("README.TXT", b"b")],
    )
    with pytest.raises(ArchivePolicyError, match="case-fold"):
        plan_archive(archive)


def test_casefold_tar_collision_is_rejected(tmp_path: Path) -> None:
    archive = write_tar(
        tmp_path / "case.tar",
        [("Readme.txt", b"a"), ("README.TXT", b"b")],
    )
    with pytest.raises(ArchivePolicyError, match="case-fold"):
        plan_archive(archive)


def test_file_parent_collision_is_rejected(tmp_path: Path) -> None:
    archive = write_zip(
        tmp_path / "shadow.zip",
        [("dir", b"file"), ("dir/child", b"child")],
    )
    with pytest.raises(ArchivePolicyError, match="shadows"):
        plan_archive(archive)


def test_reverse_file_parent_collision_is_rejected(tmp_path: Path) -> None:
    archive = write_zip(
        tmp_path / "shadow.zip",
        [("dir/child", b"child"), ("dir", b"file")],
    )
    with pytest.raises(ArchivePolicyError, match="shadows"):
        plan_archive(archive)


def test_reserved_manifest_name_is_rejected(tmp_path: Path) -> None:
    archive = write_zip(
        tmp_path / "manifest.zip",
        [(".skeleton-extraction-manifest.json", b"fake")],
    )
    with pytest.raises(ArchivePolicyError, match="reserved"):
        plan_archive(archive)


def test_path_depth_bound_is_enforced(tmp_path: Path) -> None:
    archive = write_zip(tmp_path / "deep.zip", [("a/b/c/d", b"x")])
    with pytest.raises(ArchivePolicyError, match="depth"):
        plan_archive(archive, limits=ArchiveLimits(max_depth=3))


def test_path_byte_bound_is_enforced(tmp_path: Path) -> None:
    archive = write_zip(tmp_path / "long.zip", [("abcdefghij", b"x")])
    with pytest.raises(ArchivePolicyError, match="byte bound"):
        plan_archive(archive, limits=ArchiveLimits(max_path_bytes=8))


def test_zip_symlink_member_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "symlink.zip"
    info = zipfile.ZipInfo("link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr(info, "../outside")
    with pytest.raises(ArchivePolicyError, match="symlink"):
        plan_archive(archive)


def test_zip_fifo_member_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "fifo.zip"
    info = zipfile.ZipInfo("pipe")
    info.create_system = 3
    info.external_attr = (stat.S_IFIFO | 0o600) << 16
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr(info, b"")
    with pytest.raises(ArchivePolicyError, match="special"):
        plan_archive(archive)


def test_zip_encrypted_flag_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = write_zip(tmp_path / "normal.zip", [("x", b"x")])
    original = zipfile.ZipFile.infolist

    def encrypted(self):
        infos = original(self)
        infos[0].flag_bits |= 0x1
        return infos

    monkeypatch.setattr(zipfile.ZipFile, "infolist", encrypted)
    with pytest.raises(ArchivePolicyError, match="encrypted"):
        plan_archive(archive)


def tar_special(path: Path, kind: bytes, linkname: str = "") -> Path:
    with tarfile.open(path, "w") as handle:
        info = tarfile.TarInfo("special")
        info.type = kind
        info.linkname = linkname
        info.mode = 0o777
        handle.addfile(info)
        payload = tarfile.TarInfo("safe")
        payload.size = 1
        handle.addfile(payload, io.BytesIO(b"x"))
    return path


@pytest.mark.parametrize(
    ("kind", "message"),
    [
        (tarfile.SYMTYPE, "symlink"),
        (tarfile.LNKTYPE, "hard-link"),
        (tarfile.CHRTYPE, "device"),
        (tarfile.BLKTYPE, "device"),
        (tarfile.FIFOTYPE, "device"),
    ],
)
def test_tar_special_members_are_rejected(
    tmp_path: Path,
    kind: bytes,
    message: str,
) -> None:
    archive = tar_special(tmp_path / "special.tar", kind, "../outside")
    with pytest.raises(ArchivePolicyError, match=message):
        plan_archive(archive)


def test_tar_unsupported_member_type_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "special.tar"
    with tarfile.open(archive, "w") as handle:
        info = tarfile.TarInfo("other")
        info.type = tarfile.GNUTYPE_LONGNAME
        handle.addfile(info, io.BytesIO(b""))
        safe = tarfile.TarInfo("safe")
        safe.size = 1
        handle.addfile(safe, io.BytesIO(b"x"))
    with pytest.raises(ArchivePolicyError):
        plan_archive(archive)


def test_directory_only_zip_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "dirs.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("dir/", b"")
    with pytest.raises(ArchivePolicyError, match="no regular files"):
        plan_archive(archive)


def test_zip_extracts_member_by_member_and_writes_manifest(tmp_path: Path) -> None:
    archive = write_zip(
        tmp_path / "bundle.zip",
        [
            ("readme.txt", b"hello"),
            ("dir/value.bin", b"\x00\x01\x02"),
        ],
        compression=zipfile.ZIP_STORED,
    )
    destination = tmp_path / "out"

    receipt = extract_archive(archive, destination)

    assert receipt.archive_kind == "zip"
    assert receipt.file_count == 2
    assert receipt.total_file_bytes == 8
    assert (destination / "readme.txt").read_bytes() == b"hello"
    assert (destination / "dir" / "value.bin").read_bytes() == b"\x00\x01\x02"
    manifest = load_extraction_manifest(destination)
    assert manifest["plan_digest"] == receipt.plan_digest
    assert manifest["content_digest"] == receipt.content_digest
    assert manifest["file_count"] == 2


def test_tar_extracts_member_by_member_and_writes_manifest(tmp_path: Path) -> None:
    archive = write_tar(
        tmp_path / "bundle.tar",
        [("readme.txt", b"hello"), ("dir/value", b"value")],
    )
    destination = tmp_path / "out"

    receipt = extract_archive(archive, destination)

    assert receipt.archive_kind == "tar"
    assert receipt.file_count == 2
    assert (destination / "readme.txt").read_text(encoding="utf-8") == "hello"
    assert (destination / "dir" / "value").read_text(encoding="utf-8") == "value"
    manifest = load_extraction_manifest(destination)
    assert manifest["archive_kind"] == "tar"


def test_explicit_directory_members_are_created(tmp_path: Path) -> None:
    archive = tmp_path / "dirs.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("empty/", b"")
        handle.writestr("payload", b"x")
    destination = tmp_path / "out"
    extract_archive(archive, destination)
    assert (destination / "empty").is_dir()


def test_destination_must_be_absent(tmp_path: Path) -> None:
    archive = write_zip(tmp_path / "bundle.zip", [("x", b"x")])
    destination = tmp_path / "out"
    destination.mkdir()
    with pytest.raises(ArchivePolicyError, match="must not already exist"):
        extract_archive(archive, destination)


def test_destination_parent_must_exist(tmp_path: Path) -> None:
    archive = write_zip(tmp_path / "bundle.zip", [("x", b"x")])
    with pytest.raises(ArchivePolicyError, match="parent"):
        extract_archive(archive, tmp_path / "missing" / "out")


def test_archive_publication_uses_pinned_parent_dirfds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = write_zip(tmp_path / "bundle.zip", [("x", b"x")])
    destination = tmp_path / "out"
    original_replace = archive_sandbox.os.replace
    calls: list[tuple[object, object, object, object]] = []

    def observed_replace(
        src,
        dst,
        *,
        src_dir_fd=None,
        dst_dir_fd=None,
    ):
        calls.append((src, dst, src_dir_fd, dst_dir_fd))
        return original_replace(
            src,
            dst,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    monkeypatch.setattr(archive_sandbox.os, "replace", observed_replace)
    extract_archive(archive, destination)

    publish = [
        call
        for call in calls
        if isinstance(call[0], str)
        and call[0].startswith(".out.extract-")
        and call[1] == "out"
    ]
    assert len(publish) == 1
    assert isinstance(publish[0][2], int)
    assert publish[0][2] == publish[0][3]


def test_parent_identity_swap_before_publish_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = write_zip(tmp_path / "bundle.zip", [("x", b"x")])
    destination = tmp_path / "out"
    moved = tmp_path.with_name(tmp_path.name + "-moved")
    original_stage = archive_sandbox._stage_filesystem

    def swapping_stage(stage: Path, policy: ArchiveLimits):
        boundary = original_stage(stage, policy)
        original_write = boundary.write_text

        def write_then_swap(*args, **kwargs):
            result = original_write(*args, **kwargs)
            tmp_path.rename(moved)
            tmp_path.mkdir()
            return result

        boundary.write_text = write_then_swap
        return boundary

    monkeypatch.setattr(archive_sandbox, "_stage_filesystem", swapping_stage)
    with pytest.raises(ArchiveSandboxError, match="parent identity changed"):
        extract_archive(archive, destination)

    assert not destination.exists()
    assert not (moved / "out").exists()
    assert not any(
        child.name.startswith(".out.extract-")
        for child in moved.iterdir()
    )

def test_destination_parent_symlink_is_rejected(tmp_path: Path) -> None:
    archive = write_zip(tmp_path / "bundle.zip", [("x", b"x")])
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "parent-link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(ArchivePolicyError, match="parent"):
        extract_archive(archive, link / "out")


def test_failed_preflight_never_creates_destination(tmp_path: Path) -> None:
    archive = write_zip(tmp_path / "bad.zip", [("../escape", b"x")])
    destination = tmp_path / "out"
    with pytest.raises(ArchivePolicyError):
        extract_archive(archive, destination)
    assert not destination.exists()
    assert not (tmp_path / "escape").exists()


def test_failed_extraction_removes_staging_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = write_zip(tmp_path / "bundle.zip", [("x", b"x")])
    destination = tmp_path / "out"

    original_open = zipfile.ZipFile.open

    def explode(self, *args, **kwargs):
        raise RuntimeError("SECRET_STREAM_FAILURE")

    monkeypatch.setattr(zipfile.ZipFile, "open", explode)
    with pytest.raises(ArchiveIntegrityError) as caught:
        extract_archive(archive, destination)
    assert "SECRET_STREAM_FAILURE" not in str(caught.value)
    assert not destination.exists()
    assert not any(".out.extract-" in child.name for child in tmp_path.iterdir())
    monkeypatch.setattr(zipfile.ZipFile, "open", original_open)


def test_member_modes_strip_group_and_world_write(tmp_path: Path) -> None:
    archive = tmp_path / "modes.zip"
    info = zipfile.ZipInfo("script.sh")
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr(info, b"echo safe")
    destination = tmp_path / "out"
    extract_archive(archive, destination)
    mode = stat.S_IMODE((destination / "script.sh").stat().st_mode)
    assert mode & 0o022 == 0


def test_extraction_content_digest_is_deterministic(tmp_path: Path) -> None:
    archive = write_zip(
        tmp_path / "bundle.zip",
        [("b", b"two"), ("a", b"one")],
        compression=zipfile.ZIP_STORED,
    )
    first = extract_archive(archive, tmp_path / "one")
    second = extract_archive(archive, tmp_path / "two")
    assert first.plan_digest == second.plan_digest
    assert first.content_digest == second.content_digest


def test_extraction_does_not_publish_partial_tree_on_size_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = write_zip(tmp_path / "bundle.zip", [("x", b"payload")])
    plan = plan_archive(archive)
    assert plan.members[0].size == 7

    original_open = zipfile.ZipFile.open

    class ShortStream:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, _size=-1):
            if getattr(self, "done", False):
                return b""
            self.done = True
            return b"x"

    monkeypatch.setattr(zipfile.ZipFile, "open", lambda *_args, **_kwargs: ShortStream())
    destination = tmp_path / "out"
    with pytest.raises(ArchiveIntegrityError, match="size differs"):
        extract_archive(archive, destination)
    assert not destination.exists()
    monkeypatch.setattr(zipfile.ZipFile, "open", original_open)


def test_manifest_loader_rejects_invalid_json(tmp_path: Path) -> None:
    destination = tmp_path / "out"
    destination.mkdir()
    (destination / ".skeleton-extraction-manifest.json").write_text(
        "{broken",
        encoding="utf-8",
    )
    with pytest.raises(ArchiveIntegrityError, match="invalid JSON"):
        load_extraction_manifest(destination)


def test_manifest_loader_rejects_wrong_schema(tmp_path: Path) -> None:
    destination = tmp_path / "out"
    destination.mkdir()
    (destination / ".skeleton-extraction-manifest.json").write_text(
        json.dumps({"schema_version": 99}),
        encoding="utf-8",
    )
    with pytest.raises(ArchiveIntegrityError, match="schema"):
        load_extraction_manifest(destination)


def test_manifest_loader_rejects_incomplete_manifest(tmp_path: Path) -> None:
    destination = tmp_path / "out"
    destination.mkdir()
    (destination / ".skeleton-extraction-manifest.json").write_text(
        json.dumps({"schema_version": 1}),
        encoding="utf-8",
    )
    with pytest.raises(ArchiveIntegrityError, match="incomplete"):
        load_extraction_manifest(destination)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_archive_bytes": 0},
        {"max_members": 0},
        {"max_member_bytes": 0},
        {"max_total_bytes": 0},
        {"max_path_bytes": 0},
        {"max_depth": 0},
        {"max_stream_chunks_per_member": 0},
        {"max_members": True},
        {"max_compression_ratio": 0.0},
        {"max_archive_expansion_ratio": -1.0},
        {"max_compression_ratio": float("nan")},
        {"max_compression_ratio": float("inf")},
        {"max_archive_expansion_ratio": float("nan")},
        {"max_archive_expansion_ratio": float("inf")},
        {"max_compression_ratio": True},
    ],
)
def test_limits_fail_closed_on_invalid_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        ArchiveLimits(**kwargs)  # type: ignore[arg-type]


def test_archive_error_does_not_echo_secret_filename(tmp_path: Path) -> None:
    secret = "SECRET_ARCHIVE_PATH"
    with pytest.raises(ArchiveFormatError) as caught:
        plan_archive(tmp_path / secret)
    assert secret not in str(caught.value)


def test_traversal_error_does_not_echo_malicious_member(tmp_path: Path) -> None:
    secret = "SECRET_MEMBER_PAYLOAD"
    archive = write_zip(tmp_path / "bad.zip", [(f"../{secret}", b"x")])
    with pytest.raises(ArchivePolicyError) as caught:
        plan_archive(archive)
    assert secret not in str(caught.value)


def test_safe_nested_paths_remain_nested(tmp_path: Path) -> None:
    archive = write_zip(
        tmp_path / "nested.zip",
        [("a/b/c.txt", b"nested")],
        compression=zipfile.ZIP_STORED,
    )
    destination = tmp_path / "out"
    extract_archive(archive, destination)
    assert (destination / "a" / "b" / "c.txt").read_bytes() == b"nested"


def test_dot_components_are_canonicalized(tmp_path: Path) -> None:
    archive = write_zip(
        tmp_path / "dots.zip",
        [("a/./b.txt", b"x")],
        compression=zipfile.ZIP_STORED,
    )
    plan = plan_archive(archive)
    assert plan.members[0].path == "a/b.txt"


def test_dot_canonicalization_collision_is_rejected(tmp_path: Path) -> None:
    archive = write_zip(
        tmp_path / "dots.zip",
        [("a/./b.txt", b"x"), ("a/b.txt", b"y")],
        compression=zipfile.ZIP_STORED,
    )
    with pytest.raises(ArchivePolicyError, match="duplicate"):
        plan_archive(archive)


def test_absolute_destination_name_cannot_replace_existing_parent(
    tmp_path: Path,
) -> None:
    archive = write_zip(tmp_path / "bundle.zip", [("x", b"x")])
    target = tmp_path / "out"
    extract_archive(archive, target)
    with pytest.raises(ArchivePolicyError):
        extract_archive(archive, target)


def test_tar_file_permissions_are_sanitized(tmp_path: Path) -> None:
    archive = tmp_path / "mode.tar"
    with tarfile.open(archive, "w") as handle:
        info = tarfile.TarInfo("script")
        info.size = 1
        info.mode = 0o777
        handle.addfile(info, io.BytesIO(b"x"))
    destination = tmp_path / "out"
    extract_archive(archive, destination)
    mode = stat.S_IMODE((destination / "script").stat().st_mode)
    assert mode & 0o022 == 0


def test_zip_stored_member_uses_ratio_one(tmp_path: Path) -> None:
    archive = write_zip(
        tmp_path / "stored.zip",
        [("x", b"payload")],
        compression=zipfile.ZIP_STORED,
    )
    plan = plan_archive(
        archive,
        limits=ArchiveLimits(
            max_compression_ratio=2.0,
            max_archive_expansion_ratio=2.0,
        ),
    )
    assert plan.file_count == 1


def test_file_count_excludes_directories(tmp_path: Path) -> None:
    archive = tmp_path / "mixed.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("a/", b"")
        handle.writestr("a/x", b"x")
        handle.writestr("b/", b"")
        handle.writestr("b/y", b"y")
    plan = plan_archive(archive)
    assert plan.file_count == 2
    assert plan.directory_count == 2


def test_manifest_file_is_not_counted_as_archive_member(tmp_path: Path) -> None:
    archive = write_zip(tmp_path / "bundle.zip", [("x", b"x")])
    destination = tmp_path / "out"
    receipt = extract_archive(archive, destination)
    assert receipt.member_count == 1
    assert receipt.file_count == 1
    assert len(list(destination.iterdir())) == 2


def test_plan_digest_changes_when_member_content_size_changes(tmp_path: Path) -> None:
    one = write_zip(
        tmp_path / "one.zip",
        [("x", b"x")],
        compression=zipfile.ZIP_STORED,
    )
    two = write_zip(
        tmp_path / "two.zip",
        [("x", b"xx")],
        compression=zipfile.ZIP_STORED,
    )
    assert plan_archive(one).manifest_digest != plan_archive(two).manifest_digest


def test_content_digest_changes_when_content_changes_same_size(tmp_path: Path) -> None:
    one = write_zip(
        tmp_path / "one.zip",
        [("x", b"a")],
        compression=zipfile.ZIP_STORED,
    )
    two = write_zip(
        tmp_path / "two.zip",
        [("x", b"b")],
        compression=zipfile.ZIP_STORED,
    )
    r1 = extract_archive(one, tmp_path / "out1")
    r2 = extract_archive(two, tmp_path / "out2")
    assert r1.content_digest != r2.content_digest


def test_destination_receipt_uses_resolved_published_path(tmp_path: Path) -> None:
    archive = write_zip(tmp_path / "bundle.zip", [("x", b"x")])
    destination = tmp_path / "out"
    receipt = extract_archive(archive, destination)
    assert Path(receipt.destination) == destination.resolve()


def test_safe_empty_file_is_supported(tmp_path: Path) -> None:
    archive = write_zip(
        tmp_path / "empty-member.zip",
        [("empty", b"")],
        compression=zipfile.ZIP_STORED,
    )
    destination = tmp_path / "out"
    receipt = extract_archive(archive, destination)
    assert receipt.total_file_bytes == 0
    assert (destination / "empty").read_bytes() == b""


def test_empty_file_plus_directory_counts_as_regular_archive(tmp_path: Path) -> None:
    archive = tmp_path / "mixed.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("dir/", b"")
        handle.writestr("empty", b"")
    plan = plan_archive(archive)
    assert plan.file_count == 1
    assert plan.total_file_bytes == 0
