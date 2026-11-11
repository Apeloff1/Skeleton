import pytest

from skeleton.build.delivery._util import DeliveryError
from skeleton.build.delivery.packaging import build_tarball, build_zip, list_tarball, list_zip

FILES = {"bin/run.sh": b"#!/bin/sh\necho hi\n", "lib/a.py": b"print(1)\n", "README": b"r"}


def test_tarball_is_reproducible_and_readable():
    one = build_tarball("pkg.tar.gz", FILES, prefix="skel-1.0.0")
    two = build_tarball("pkg.tar.gz", dict(reversed(list(FILES.items()))), prefix="skel-1.0.0")
    assert one.data == two.data and one.sha256 == two.sha256
    assert one.file_count == 3
    content = list_tarball(one.data)
    assert content["skel-1.0.0/lib/a.py"] == b"print(1)\n"


def test_zip_is_reproducible_and_readable():
    one = build_zip("pkg.zip", FILES)
    two = build_zip("pkg.zip", FILES)
    assert one.data == two.data
    assert list_zip(one.data) == FILES


def test_entry_matches_package():
    pkg = build_zip("pkg.zip", FILES)
    entry = pkg.entry("zip")
    assert entry.size == len(pkg.data) and entry.sha256 == pkg.sha256


def test_rejects_bad_inputs():
    with pytest.raises(DeliveryError):
        build_tarball("pkg.tgz", FILES)
    with pytest.raises(DeliveryError):
        build_zip("pkg.zip", {})
    with pytest.raises(DeliveryError):
        build_zip("pkg.zip", {"../x": b""})
    with pytest.raises(DeliveryError):
        build_zip("pkg.zip", {"a": "text"})
    with pytest.raises(DeliveryError):
        build_zip("pkg.zip", FILES, epoch=0)


def test_packaging_input_total_budget_is_checked_before_compression(monkeypatch):
    from skeleton.build.delivery import packaging

    monkeypatch.setattr(packaging, "MAX_ARTIFACT_BYTES", 7)
    with pytest.raises(DeliveryError, match="uncompressed package input"):
        packaging.build_zip("small.zip", {"first": b"abcd", "second": b"efgh"})
    with pytest.raises(DeliveryError, match="uncompressed package input"):
        packaging.build_tarball("small.tar.gz", {"first": b"abcd", "second": b"efgh"})


@pytest.mark.parametrize("extension,builder,reader", [
    ("zip", build_zip, list_zip),
    ("tar.gz", build_tarball, list_tarball),
])
def test_archive_reader_rejects_compressed_expansion(monkeypatch, extension, builder, reader):
    from skeleton.build.delivery import packaging

    archive = builder("package." + extension, {"huge": b"X" * 8192}).data
    assert len(archive) < 512
    monkeypatch.setattr(packaging, "MAX_ARTIFACT_BYTES", 512)
    with pytest.raises(DeliveryError, match="expanded bytes exceed bound"):
        reader(archive)


@pytest.mark.parametrize("extension,builder,reader", [
    ("zip", build_zip, list_zip),
    ("tar.gz", build_tarball, list_tarball),
])
def test_archive_reader_does_not_accept_more_members_than_policy(
    monkeypatch, extension, builder, reader,
):
    from skeleton.build.delivery import packaging

    archive = builder("package." + extension, {"a": b"one", "b": b"two"}).data
    monkeypatch.setattr(packaging, "MAX_PACKAGE_FILES", 1)
    with pytest.raises(DeliveryError, match="member count exceeds bound"):
        reader(archive)


def test_zip_duplicate_members_and_noncanonical_aliases_are_rejected():
    import io
    import zipfile

    for names in (("same", "same"), ("ok//name",), ("../escape",)):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for name in names:
                z.writestr(name, b"x")
        with pytest.raises(DeliveryError):
            list_zip(buf.getvalue())


def test_tar_duplicate_members_are_rejected():
    import io
    import tarfile

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for _ in range(2):
            member = tarfile.TarInfo("same")
            member.size = 1
            tar.addfile(member, io.BytesIO(b"x"))
    with pytest.raises(DeliveryError, match="noncanonical or duplicated"):
        list_tarball(buf.getvalue())


def test_zip_reader_rejects_unix_special_file_modes():
    import io
    import stat
    import zipfile

    for kind in (stat.S_IFLNK, stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFCHR, stat.S_IFBLK):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            entry = zipfile.ZipInfo("special")
            entry.create_system = 3
            entry.external_attr = (kind | 0o644) << 16
            z.writestr(entry, b"not an ordinary file")
        with pytest.raises(DeliveryError, match="nonregular"):
            list_zip(buf.getvalue())

    # Explicit regular-file metadata is still accepted.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        entry = zipfile.ZipInfo("regular")
        entry.create_system = 3
        entry.external_attr = (stat.S_IFREG | 0o644) << 16
        z.writestr(entry, b"ok")
    assert list_zip(buf.getvalue()) == {"regular": b"ok"}


def test_zip_central_directory_preflight_rejects_forged_counts():
    """Reject inconsistent index metadata before eager ZipFile allocation."""
    import struct

    archive = build_zip("safe.zip", {"a": b"one", "b": b"two"}).data
    eocd = archive.rfind(bytes((80, 75, 5, 6)))
    assert eocd > 0
    assert list_zip(archive) == {"a": b"one", "b": b"two"}
    for offset, value, fmt in (
        (10, 1, "<H"),  # Claimed total differs from disk count.
        (12, 1, "<I"),  # Truncated central directory size.
        (20, 99, "<H"),  # Impossible trailing comment length.
        (10, 0xFFFF, "<H"),  # ZIP64 sentinel is not admitted.
    ):
        forged = bytearray(archive)
        struct.pack_into(fmt, forged, eocd + offset, value)
        with pytest.raises(DeliveryError):
            list_zip(bytes(forged))
    forged = bytearray(archive)
    struct.pack_into("<H", forged, eocd + 8, 1)
    struct.pack_into("<H", forged, eocd + 10, 1)
    with pytest.raises(DeliveryError, match="count mismatch"):
        list_zip(bytes(forged))
    # A bounded executable stub before the ZIP payload remains parseable.
    assert list_zip(b"stub" + archive) == {"a": b"one", "b": b"two"}

@pytest.mark.parametrize("epoch", (True, False, 1.5, "315532800", -1, 1 << 32))
def test_package_builders_reject_noncanonical_epoch(epoch):
    with pytest.raises(DeliveryError, match="bounded integer"):
        build_zip("pkg.zip", FILES, epoch=epoch)
    with pytest.raises(DeliveryError, match="bounded integer"):
        build_tarball("pkg.tar.gz", FILES, epoch=epoch)


def test_tarball_accepts_portable_epoch_zero_but_zip_requires_1980():
    assert build_tarball("pkg.tar.gz", {"a": b"x"}, epoch=0).file_count == 1
    with pytest.raises(DeliveryError, match="1980"):
        build_zip("pkg.zip", {"a": b"x"}, epoch=0)


def test_package_builders_bound_malicious_mapping_iteration():
    from itertools import count
    from skeleton.ai.build.core.delivery import packaging as mirrored

    class UnboundedFiles(dict):
        def items(self):
            return ((f"file{i}", b"x") for i in count())

    for build, mirror_build in ((build_zip, mirrored.build_zip),
                                (build_tarball, mirrored.build_tarball)):
        name = "pkg.zip" if build is build_zip else "pkg.tar.gz"
        for fn in (build, mirror_build):
            with pytest.raises(DeliveryError, match="too many files"):
                fn(name, UnboundedFiles())


def test_package_combined_prefix_and_file_path_are_bounded():
    from skeleton.ai.build.core.delivery import packaging as mirrored

    for build in (build_zip, build_tarball, mirrored.build_zip, mirrored.build_tarball):
        name = "pkg.zip" if build in (build_zip, mirrored.build_zip) else "pkg.tar.gz"
        with pytest.raises(DeliveryError):
            build(name, {"a" * 100: b"x"}, prefix="b" * 4050)


def test_mapping_subclass_with_false_empty_length_still_validates_entries():
    """Do not mistake an empty backing dict for an empty custom mapping."""
    class VirtualFiles(dict):
        def items(self):
            yield "virtual.txt", b"source"

    from skeleton.ai.build.core.delivery import packaging as mirrored
    for builder in (build_zip, mirrored.build_zip):
        package = builder("virtual.zip", VirtualFiles())
        assert package.file_count == 1
        assert list_zip(package.data) == {"virtual.txt": b"source"}


def test_truly_empty_custom_mapping_is_still_rejected():
    class EmptyFiles(dict):
        def items(self):
            return iter(())

    from skeleton.ai.build.core.delivery import packaging as mirrored
    for builder in (build_zip, mirrored.build_zip):
        with pytest.raises(DeliveryError, match="non-empty"):
            builder("empty.zip", EmptyFiles())
