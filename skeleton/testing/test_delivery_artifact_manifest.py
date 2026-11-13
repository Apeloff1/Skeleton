import hashlib

import pytest

from skeleton.build.delivery._util import DeliveryError
from skeleton.build.delivery.artifact_manifest import (
    ArtifactEntry,
    ArtifactManifest,
    build_manifest,
    diff_manifests,
    verify_files,
)

COMMIT = "a" * 40


def _entry(path, data=b"x", kind="other"):
    return ArtifactEntry(path, kind, len(data), hashlib.sha256(data).hexdigest())


def _manifest(*entries, version="1.0.0"):
    return build_manifest(release_id="skel-1", version=version, source_commit=COMMIT, artifacts=entries)


def test_manifest_sorted_and_digest_stable():
    m1 = _manifest(_entry("b.bin"), _entry("a.bin"))
    m2 = _manifest(_entry("a.bin"), _entry("b.bin"))
    assert [a.path for a in m1.artifacts] == ["a.bin", "b.bin"]
    assert m1.digest == m2.digest


def test_roundtrip_and_tamper_detection():
    m = _manifest(_entry("a.bin"))
    data = m.to_dict()
    assert ArtifactManifest.from_dict(data) == m
    data["artifacts"][0]["size"] = 99
    with pytest.raises(DeliveryError, match="digest"):
        ArtifactManifest.from_dict(data)


@pytest.mark.parametrize("path", ["/abs", "../up", "a/../../b", "a\\b", ""])
def test_rejects_unsafe_paths(path):
    with pytest.raises(DeliveryError):
        _entry(path)


def test_rejects_duplicates_and_oversize():
    with pytest.raises(DeliveryError):
        _manifest(_entry("a"), _entry("./a"))
    with pytest.raises(DeliveryError):
        ArtifactEntry("big", "other", 51 * 1024 * 1024, "0" * 64)


def test_rejects_bad_commit_and_version():
    with pytest.raises(DeliveryError):
        build_manifest(release_id="r", version="1.0.0", source_commit="abc", artifacts=[_entry("a")])
    with pytest.raises(DeliveryError):
        _manifest(_entry("a"), version="1.0")


def test_diff():
    old = _manifest(_entry("a", b"1"), _entry("b"))
    new = _manifest(_entry("a", b"2"), _entry("c"))
    d = diff_manifests(old, new)
    assert (d.added, d.removed, d.changed) == (("c",), ("b",), ("a",))
    assert diff_manifests(old, old).empty


def test_verify_files():
    m = _manifest(_entry("a", b"hello"), _entry("b", b"zz"))
    assert verify_files(m, {"a": b"hello", "b": b"zz"}) == ()
    problems = verify_files(m, {"a": b"hellO", "x": b""})
    assert problems == ("digest:a", "missing:b", "unexpected:x")
