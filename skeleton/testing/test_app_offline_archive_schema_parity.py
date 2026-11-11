"""Studio source archive inspection parity with the canonical source verifier.

A valid Studio package is verifiable as *source custody*, never an executable
installer, signed package, hardware test, or consumer release.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from zipfile import ZipFile

import pytest

from skeleton.ai.game_builder.contracts import canonical_digest
from skeleton.ai.game_builder.dual_runtime_verify import _canonical_bytes
from skeleton.app.cli import run_app_cli
from skeleton.app.offline_delivery_archive import (
    OfflineGameArchiveError, _canonical_zip, inspect_offline_game_archive,
)
from skeleton.testing.test_app_offline_delivery_archive import _build, _package


pytestmark = pytest.mark.skipif(
    os.name != "posix" or not hasattr(os, "O_NOFOLLOW"),
    reason="descriptor-safe POSIX archive custody required",
)


def _studio_archive(tmp_path, capsys):
    source, manifest_pin = _build(tmp_path, capsys)
    destination = tmp_path / "reviewed-studio.zip"
    assert run_app_cli(_package(source, manifest_pin, destination)) == 0
    receipt = json.loads(capsys.readouterr().out)
    with ZipFile(destination, "r") as archive:
        files = {item.filename: archive.read(item) for item in archive.infolist()}
    release = json.loads(files["release.json"])
    assert release["schema"] == "skeleton.game_builder.studio_package.v1"
    return destination, receipt, files, release


def test_studio_source_archive_inspection_retains_all_release_denials(tmp_path, capsys):
    destination, published, _, _ = _studio_archive(tmp_path, capsys)
    verified = inspect_offline_game_archive(
        destination,
        expected_archive_sha256=published["independent_archive_sha256"],
        expected_manifest_sha256=published["manifest_sha256"],
        authorized=True,
    )
    assert verified["archive_integrity_verified"] is True
    assert verified["source_gameplay_reexecuted_now"] is False
    assert verified["native_device_qualified"] is False
    assert verified["rights_certified"] is False
    assert verified["package_signed"] is False
    assert verified["release_certified"] is False


@pytest.mark.parametrize("attack", [
    "missing_studio_provenance",
    "false_not_automatically_published",
    "foreign_studio_project",
    "foreign_studio_claim",
    "foreign_studio_schema",
    "unsupported_schema",
    "noncanonical_manifest",
])
def test_resealed_source_archive_cannot_bypass_studio_custody(
    tmp_path, capsys, attack,
):
    destination, _, files, release = _studio_archive(tmp_path, capsys)
    if attack == "missing_studio_provenance":
        del files["studio/pipeline.json"]
        del release["files"]["studio/pipeline.json"]
    elif attack in ("false_not_automatically_published", "foreign_studio_project",
                    "foreign_studio_claim", "foreign_studio_schema"):
        studio = json.loads(files["studio/pipeline.json"])
        if attack == "false_not_automatically_published":
            studio["not_automatically_published"] = False
        elif attack == "foreign_studio_project":
            studio["project_id"] = "unrelated-studio-project"
        elif attack == "foreign_studio_claim":
            studio["original_game_claim"] = "third-party-unreviewed-geometry"
        else:
            studio["schema"] = "skeleton.game_builder.studio_pipeline.v999"
        files["studio/pipeline.json"] = _canonical_bytes(studio)
        release["files"]["studio/pipeline.json"] = sha256(
            files["studio/pipeline.json"],
        ).hexdigest()
    elif attack == "unsupported_schema":
        release["schema"] = "skeleton.game_builder.untrusted_source.v999"
    elif attack != "noncanonical_manifest":
        raise AssertionError("unhandled adversarial case")

    release["manifest_digest"] = canonical_digest({
        key: value for key, value in release.items()
        if key != "manifest_digest"
    })
    if attack == "noncanonical_manifest":
        # Valid contents and independent re-pins are not enough: source
        # manifests must retain canonical serialization.
        files["release.json"] = json.dumps(
            release, sort_keys=True, indent=2,
        ).encode("utf-8")
    else:
        files["release.json"] = _canonical_bytes(release)

    raw = _canonical_zip(files)
    destination.write_bytes(raw)
    with pytest.raises(OfflineGameArchiveError):
        inspect_offline_game_archive(
            destination,
            expected_archive_sha256=sha256(raw).hexdigest(),
            expected_manifest_sha256=sha256(files["release.json"]).hexdigest(),
            authorized=True,
        )
