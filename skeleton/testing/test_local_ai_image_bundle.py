"""Offline Docker image bundle custody, never image loading or app readiness."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
from unittest import mock

import pytest

from scripts import local_ai_image_bundle as bundle
from scripts import local_ai_docker as host

_CONFIG = b'{"architecture":"amd64","os":"linux","rootfs":{"type":"layers","diff_ids":[]}}'
_IMAGE = "sha256:" + hashlib.sha256(_CONFIG).hexdigest()


def _private(tmp_path: Path) -> Path:
    parent = tmp_path / "private"
    parent.mkdir(mode=0o700)
    return parent / "images-2026"


def _image_tar(path: Path, *, corrupt_config=False, missing_layer=False,
               link=False, tags=None, duplicate=False):
    manifest = [{
        "Config": _IMAGE[7:] + ".json",
        "RepoTags": ["skeleton-test:offline"] if tags is None else tags,
        "Layers": ["layers/one.tar"],
    }]
    with tarfile.open(path, "w") as file:
        entries = [
            ("manifest.json", json.dumps(manifest).encode()),
            (_IMAGE[7:] + ".json", b'{"tampered":true}' if corrupt_config else _CONFIG),
        ]
        if not missing_layer:
            entries.append(("layers/one.tar", b"synthetic layer without live model"))
        for name, data in entries:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o600
            file.addfile(info, io.BytesIO(data))
            if duplicate and name == "manifest.json":
                file.addfile(info, io.BytesIO(data))
        if link:
            bad = tarfile.TarInfo("bad-link")
            bad.type = tarfile.SYMTYPE
            bad.linkname = "../secrets"
            file.addfile(bad)


def _fake_runtime(monkeypatch, *, changing=False):
    topology = {
        "name": "skeleton-test",
        "services": {
            "mongo": {"image": "mongo:7@sha256:" + "c" * 64},
            "skeleton": {"image": "skeleton-local-ai:dev"},
            "backend": {"build": {"context": "."}},
            "frontend": {"build": {"context": "."}},
        },
    }
    calls = []
    inspected = 0

    def run(argv, *, root=host.ROOT, capture=False):
        nonlocal inspected
        calls.append(tuple(argv))
        if "config" in argv:
            return json.dumps(topology)
        if argv[:3] == ["docker", "image", "inspect"]:
            inspected += 1
            if changing and inspected > 4 and argv[-1] == "skeleton-local-ai:dev":
                return "sha256:" + "c" * 64
            return _IMAGE + "\n"
        if argv[:3] == ["docker", "image", "save"]:
            assert "--output" in argv
            assert argv[-1] == _IMAGE
            _image_tar(Path(argv[argv.index("--output") + 1]))
            return ""
        raise AssertionError("unexpected Docker access: " + str(argv))

    monkeypatch.setattr(host, "inspect_config", lambda mode, root: {"ok": True})
    monkeypatch.setattr(host, "_validate_config", lambda mode, config: None)
    monkeypatch.setattr(host, "compose_command",
                        lambda mode, root: ["docker", "compose"])
    monkeypatch.setattr(host, "_run", run)
    return calls


def test_all_four_local_images_export_and_independent_offline_rehash(tmp_path, monkeypatch):
    calls = _fake_runtime(monkeypatch)
    dest = _private(tmp_path)
    result = bundle.export_image_bundle("cpu", dest, root=tmp_path)
    assert result["schema"] == bundle.SCHEMA
    assert result["status"] == "offline_image_bytes_verified_only"
    assert [r["service"] for r in result["images"]] == list(bundle.ROLES)
    assert [r["image_id"] for r in result["images"]] == [_IMAGE] * 4
    assert all(r["bytes"] > 0 and r["members"] == 3 for r in result["images"])
    assert result["docker_images_loaded"] is False
    assert result["load_authorized"] is False
    assert result["guarded_chat_qualified"] is False
    assert result["app_recovery_qualified"] is False
    assert result["release_provenance_qualified"] is False
    assert len([c for c in calls if c[:3] == ("docker", "image", "save")]) == 4
    assert not any("pull" in c or "load" in c or "run" in c for c in calls)

    with mock.patch.object(host, "_run", side_effect=AssertionError("offline verifier used Docker")):
        assert bundle.verify_image_bundle(dest) == result
    assert dest.stat().st_mode & 0o777 == 0o700
    assert all(item.stat().st_mode & 0o777 == 0o600 for item in dest.iterdir())


@pytest.mark.parametrize("mode", ["cpu", "nvidia", "rocm"])
def test_inventory_never_builds_pulls_or_mutates(mode, tmp_path, monkeypatch):
    calls = _fake_runtime(monkeypatch)
    report = bundle.image_inventory(mode, root=tmp_path)
    assert report["mode"] == mode
    assert report["image_bytes_copied"] is False
    assert len(report["images"]) == 4
    assert len([c for c in calls if c[:3] == ("docker", "image", "inspect")]) == 4


def test_rejects_corrupt_image_bytes_after_export(tmp_path, monkeypatch):
    _fake_runtime(monkeypatch)
    dest = _private(tmp_path)
    bundle.export_image_bundle("cpu", dest, root=tmp_path)
    with (dest / "backend.tar").open("ab") as output:
        output.write(b"corruption")
    with pytest.raises(bundle.ImageBundleError, match="changed"):
        bundle.verify_image_bundle(dest)


def test_rejects_forged_receipt_digest(tmp_path, monkeypatch):
    _fake_runtime(monkeypatch)
    dest = _private(tmp_path)
    bundle.export_image_bundle("cpu", dest, root=tmp_path)
    receipt = dest / bundle.RECEIPT
    data = json.loads(receipt.read_text())
    data["guarded_chat_qualified"] = True
    receipt.write_text(json.dumps(data))
    with pytest.raises(bundle.ImageBundleError, match="receipt"):
        bundle.verify_image_bundle(dest)


@pytest.mark.parametrize("tamper", ["link", "config", "missing_layer", "duplicate"])
def test_rejects_hostile_docker_tars(tmp_path, tamper):
    target = _private(tmp_path)
    target.parent.mkdir(exist_ok=True)
    tar = target.parent / "hostile.tar"
    _image_tar(tar, link=tamper == "link", corrupt_config=tamper == "config",
               missing_layer=tamper == "missing_layer", duplicate=tamper == "duplicate")
    with pytest.raises(bundle.ImageBundleError):
        bundle._archive_identity(tar, _IMAGE)


def test_archive_excess_tags_denied(tmp_path):
    tar = tmp_path / "tags.tar"
    _image_tar(tar, tags=["tag:" + str(i) for i in range(65)])
    with pytest.raises(bundle.ImageBundleError, match="tags"):
        bundle._archive_identity(tar, _IMAGE)


def test_export_fails_closed_when_tag_changes_during_copy(tmp_path, monkeypatch):
    _fake_runtime(monkeypatch, changing=True)
    dest = _private(tmp_path)
    with pytest.raises(bundle.ImageBundleError, match="incomplete"):
        bundle.export_image_bundle("cpu", dest, root=tmp_path)
    assert dest.exists()
    assert not (dest / bundle.RECEIPT).exists()


def test_never_reuses_or_overwrites_existing_bundle(tmp_path, monkeypatch):
    _fake_runtime(monkeypatch)
    dest = _private(tmp_path)
    bundle.export_image_bundle("cpu", dest, root=tmp_path)
    before = (dest / "mongo.tar").read_bytes()
    with pytest.raises(bundle.ImageBundleError, match="must not exist"):
        bundle.export_image_bundle("cpu", dest, root=tmp_path)
    assert (dest / "mongo.tar").read_bytes() == before


def test_rejects_symlink_and_undeclared_archive_members(tmp_path, monkeypatch):
    _fake_runtime(monkeypatch)
    dest = _private(tmp_path)
    bundle.export_image_bundle("cpu", dest, root=tmp_path)
    extra = dest / "unexpected"
    extra.write_text("unlisted")
    with pytest.raises(bundle.ImageBundleError, match="undeclared"):
        bundle.verify_image_bundle(dest)
    extra.unlink()
    (dest / "backend.tar").unlink()
    (dest / "backend.tar").symlink_to(dest / "mongo.tar")
    with pytest.raises(bundle.ImageBundleError):
        bundle.verify_image_bundle(dest)


def test_rejects_insecure_parent_before_any_docker_access(tmp_path, monkeypatch):
    calls = _fake_runtime(monkeypatch)
    outside = tmp_path / "world"
    outside.mkdir(mode=0o755)
    with pytest.raises(bundle.ImageBundleError, match="0700"):
        bundle.export_image_bundle("cpu", outside / "archive", root=tmp_path)
    assert not calls


def test_rejects_incorrect_tar_file_identity(tmp_path):
    tar = tmp_path / "one.tar"
    _image_tar(tar)
    with pytest.raises(bundle.ImageBundleError, match="config"):
        bundle._archive_identity(tar, "sha256:" + "a" * 64)


def test_empty_archives_are_not_source_verified(tmp_path):
    with pytest.raises((bundle.ImageBundleError, OSError)):
        bundle._archive_identity(tmp_path / "no.tar", _IMAGE)


def test_verifier_requires_real_receipt_and_never_recovers_partial(tmp_path):
    target = _private(tmp_path)
    target.mkdir(mode=0o700)
    with pytest.raises((bundle.ImageBundleError, OSError)):
        bundle.verify_image_bundle(target)
