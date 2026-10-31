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
