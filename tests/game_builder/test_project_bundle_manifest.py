import pytest

from skeleton.ai.game_builder.project_bundle.manifest import (
    BUNDLE_SCHEMA_VERSION, BundleError, BundleFile, BundleManifest)
from skeleton.kernel.game_save_plane import SAVE_SCHEMA_VERSION

ROOT = "a" * 64


def make(**kw):
    base = dict(project_id="hero", genre="platformer", receipt_root=ROOT, sequence=1,
                files=(BundleFile("game/a.md", "b" * 64, 3), BundleFile("project.json", "c" * 64, 9)))
    return BundleManifest(**{**base, **kw})


def test_payload_roundtrip_and_stable_digest():
    m = make()
    assert m.save_schema_version == SAVE_SCHEMA_VERSION and m.bundle_schema_version == BUNDLE_SCHEMA_VERSION
    again = BundleManifest.from_payload(m.payload())
    assert again == m and again.content_digest == make().content_digest
    assert make(label="v1").content_digest != m.content_digest


def test_validation():
    for kw in (dict(project_id="../x"), dict(receipt_root="nope"),
               dict(files=(BundleFile("b", "b" * 64, 1), BundleFile("a", "b" * 64, 1))),
               dict(bundle_schema_version=BUNDLE_SCHEMA_VERSION + 1), dict(label="")):
        with pytest.raises(BundleError):
            make(**kw)


def test_tampered_payload_rejected():
    p = make().payload()
    p["genre"] = "racing"
    with pytest.raises(BundleError):
        BundleManifest.from_payload(p)
    with pytest.raises(BundleError):
        BundleManifest.from_payload({**make().payload(), "schema": "other"})
