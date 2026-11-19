"""Tag-neutral offline Docker transport and fail-closed destination import tests.

No real Docker daemon, network, GGUF runtime, GPU or service is involved here.
The physical and protected-chat gates require independent native evidence.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
from unittest import mock

import pytest

from scripts import local_ai_docker as host
from scripts import local_ai_image_bundle as bundle
from scripts import local_ai_image_transfer as transfer
from skeleton.testing.test_local_ai_image_bundle import (
    _IMAGE, _CONFIG, _LAYER, _fake_runtime, _image_tar, _private,
)


def _export(tmp_path: Path, monkeypatch):
    calls = _fake_runtime(monkeypatch)
    directory = _private(tmp_path)
    bundle.export_image_bundle("cpu", directory, root=tmp_path)
    digest = transfer.receipt_digest(directory)
    return directory, digest, calls


def _destination_daemon(monkeypatch, calls, *, platform="linux/x86_64",
                        image_present=False, load_fails=False):
    upstream = host._run
    state = {"present": image_present, "load_calls": 0, "inspect_by_id": 0}

    def invoke(argv, *, root=host.ROOT, capture=False):
        args = tuple(argv)
        calls.append(args)
        if args[:3] == ("docker", "info", "--format"):
            return platform + "\n"
        if args[:3] == ("docker", "image", "inspect") and args[-1] == _IMAGE:
            state["inspect_by_id"] += 1
            if state["present"]:
                return _IMAGE + "\n"
            raise host.LocalDockerError("no local image yet")
        if args[:3] == ("docker", "image", "load"):
            state["load_calls"] += 1
            assert args[3] == "--input"
            if load_fails:
                raise host.LocalDockerError("load failure")
            state["present"] = True
            return ""
        return upstream(argv, root=root, capture=capture)

    monkeypatch.setattr(host, "_run", invoke)
    return state


def test_export_normalizes_tags_and_checks_every_layer(tmp_path, monkeypatch):
    directory, actual, calls = _export(tmp_path, monkeypatch)
    assert len(actual) == 64
    report = transfer.verify_transfer(directory)
    assert report["mode"] == "cpu"
    assert report["platform"] == "linux/amd64"
    assert report["receipt_file_sha256"] == actual
    assert report["images_loaded"] is False
    assert report["tags_changed"] is False
    assert len(report["images"]) == 4
    for service in bundle.ROLES:
        with tarfile.open(directory / (service + ".tar"), "r:") as tar:
            row = transfer._manifest(tar)
            assert row["RepoTags"] == []
            assert "repositories" not in tar.getnames()
            assert hashlib.sha256(
                transfer._load_member(tar, row["Config"])
            ).hexdigest() == _IMAGE[7:]
    assert not any("load" in c or "tag" in c for c in calls)


def test_real_legacy_tag_index_is_deleted_before_sealing(tmp_path):
    directory = _private(tmp_path)
    directory.mkdir(mode=0o700)
    saved = directory / "mono.tar"
    _image_tar(saved)
    with tarfile.open(saved, "a") as tar:
        value = b'{"skeleton-test":{"offline":"layers/one.tar"}}'
        member = tarfile.TarInfo("repositories")
        member.size = len(value)
        tar.addfile(member, io.BytesIO(value))
    transfer.strip_source_tags(saved, _IMAGE)
    assert transfer._image_platform_and_layers(saved, _IMAGE) == "linux/amd64"
    with tarfile.open(saved, "r:") as tar:
        assert "repositories" not in tar.getnames()
        assert transfer._manifest(tar)["RepoTags"] == []


def test_verifier_requires_private_directory_and_sealed_receipt(tmp_path, monkeypatch):
    directory, digest, _ = _export(tmp_path, monkeypatch)
    assert transfer.receipt_digest(directory) == digest
    (directory / bundle.RECEIPT).unlink()
    with pytest.raises((bundle.ImageBundleError, OSError)):
        transfer.verify_transfer(directory)


def test_read_only_preflight_checks_known_platform_no_image_store_mutation(
    tmp_path, monkeypatch,
):
    directory, digest, calls = _export(tmp_path, monkeypatch)
    _destination_daemon(monkeypatch, calls)
    report = transfer.plan_import(
        directory, expected_receipt_sha256=digest, mode="cpu", root=tmp_path,
    )
    assert report["status"] == "destination_platform_and_image_bytes_admitted_no_load"
    assert report["daemon_platform_matched"] is True
    assert report["source_cryptographic_authentication_verified"] is False
    assert report["load_permitted_only_with_explicit_operator_ack"] is True
    assert not any(
        c[:3] == ("docker", "image", "load") for c in calls
    )


@pytest.mark.parametrize("platform", [
    "windows/amd64", "linux/arm64", "linux/s390x", "unknown",
    "linux/x86_64/extra", "linux/riscv64",
])
def test_unsupported_or_incompatible_daemon_rejected_before_image_load(
    tmp_path, monkeypatch, platform,
):
    directory, digest, calls = _export(tmp_path, monkeypatch)
    _destination_daemon(monkeypatch, calls, platform=platform)
    with pytest.raises(transfer.TransferError):
        transfer.plan_import(
            directory, expected_receipt_sha256=digest, mode="cpu", root=tmp_path,
        )
    assert not any(c[:3] == ("docker", "image", "load") for c in calls)


@pytest.mark.parametrize("bad", [
    "", "0" * 64, "z" * 64, "A" * 64, "sha256:" + "0" * 64,
    "../../secrets", "0" * 63,
])
def test_expected_hash_must_be_correct_independent_64_hex_sha(
    tmp_path, monkeypatch, bad,
):
    directory, digest, calls = _export(tmp_path, monkeypatch)
    _destination_daemon(monkeypatch, calls)
    with pytest.raises(transfer.TransferError):
        transfer.plan_import(
            directory, expected_receipt_sha256=bad, mode="cpu", root=tmp_path,
        )
    assert not any(c[:3] == ("docker", "info", "--format") for c in calls)


def test_model_accelerator_mode_must_match_source_bundle(tmp_path, monkeypatch):
    directory, digest, calls = _export(tmp_path, monkeypatch)
    _destination_daemon(monkeypatch, calls)
    with pytest.raises(transfer.TransferError, match="accelerator"):
        transfer.plan_import(
            directory, expected_receipt_sha256=digest,
            mode="nvidia", root=tmp_path,
        )


def test_import_refused_without_explicit_mutation_ack_even_with_valid_bytes(
    tmp_path, monkeypatch,
):
    directory, digest, calls = _export(tmp_path, monkeypatch)
    # No runtime access should occur when the user did not authorize the step.
    with pytest.raises(transfer.TransferError, match="permission"):
        transfer.import_untagged_images(
            directory, expected_receipt_sha256=digest,
            mode="cpu", root=tmp_path,
        )
    assert not any(c[:3] == ("docker", "image", "load") for c in calls)


def test_exact_image_id_import_is_idempotent_and_never_sets_tags(
    tmp_path, monkeypatch,
):
    directory, digest, calls = _export(tmp_path, monkeypatch)
    state = _destination_daemon(monkeypatch, calls)
    result = transfer.import_untagged_images(
        directory, expected_receipt_sha256=digest, mode="cpu",
        allow_image_store_mutation=True, root=tmp_path,
    )
    # Synthetic test uses the same pinned test config for all four services;
    # after one image ID is loaded, subsequent services reuse the exact ID.
    assert result["images_loaded"] == ["mongo"]
    assert result["images_reused"] == ["skeleton", "backend", "frontend"]
    assert state["load_calls"] == 1
    assert result["image_store_mutated"] is True
    assert result["image_store_atomic"] is False
    assert result["tags_changed"] is False
    assert result["containers_started"] is False
    assert result["guarded_chat_qualified"] is False
    assert result["release_qualified"] is False
    assert not any(
        "tag" in c or "push" in c or "pull" in c or "run" in c
        for c in calls
    )
    second = transfer.import_untagged_images(
        directory, expected_receipt_sha256=digest, mode="cpu",
        allow_image_store_mutation=True, root=tmp_path,
    )
    assert second["images_loaded"] == []
    assert second["images_reused"] == list(bundle.ROLES)
    assert second["image_store_mutated"] is False
    assert state["load_calls"] == 1


def test_docker_load_failure_does_not_start_app_or_remove_images(
    tmp_path, monkeypatch,
):
    directory, digest, calls = _export(tmp_path, monkeypatch)
    state = _destination_daemon(monkeypatch, calls, load_fails=True)
    with pytest.raises(host.LocalDockerError):
        transfer.import_untagged_images(
            directory, expected_receipt_sha256=digest, mode="cpu",
            allow_image_store_mutation=True, root=tmp_path,
        )
    assert state["load_calls"] == 1
    assert not any(
        c[:2] == ("docker", "run") or
        c[:3] == ("docker", "image", "rm") or
        c[:3] == ("docker", "image", "tag")
        for c in calls
    )


def test_preexisting_image_is_not_reloaded_or_retagged(
    tmp_path, monkeypatch,
):
    directory, digest, calls = _export(tmp_path, monkeypatch)
    state = _destination_daemon(monkeypatch, calls, image_present=True)
    response = transfer.import_untagged_images(
        directory, expected_receipt_sha256=digest, mode="cpu",
        allow_image_store_mutation=True, root=tmp_path,
    )
    assert state["load_calls"] == 0
    assert response["images_reused"] == list(bundle.ROLES)
    assert response["image_store_mutated"] is False


def test_tampered_layer_payload_is_rejected_even_if_config_is_pinned(tmp_path):
    saved = tmp_path / "changed-layer.tar"
    manifest = [{
        "Config": _IMAGE[7:] + ".json", "RepoTags": [],
        "Layers": ["layers/one.tar"],
    }]
    with tarfile.open(saved, "w:") as tar:
        members = [
            ("manifest.json", json.dumps(manifest).encode()),
            (_IMAGE[7:] + ".json", _CONFIG),
            ("layers/one.tar", _LAYER + b"ATTACK"),
        ]
        for name, value in members:
            member = tarfile.TarInfo(name)
            member.size = len(value)
            tar.addfile(member, io.BytesIO(value))
    # Config identity still matches; independently verify uncompressed layer.
    with pytest.raises(transfer.TransferError, match="diffID"):
        transfer._image_platform_and_layers(saved, _IMAGE)


def test_unsanitized_source_tags_cannot_pass_layer_transfer_gate(tmp_path):
    target = tmp_path / "tagged.tar"
    _image_tar(target)
    with pytest.raises(transfer.TransferError, match="tags"):
        transfer._image_platform_and_layers(target, _IMAGE)


def test_unsupported_or_incompatible_image_config_rejected(tmp_path):
    config = json.dumps({
        "architecture": "arm64", "os": "windows", "rootfs": {
            "diff_ids": ["sha256:" + hashlib.sha256(_LAYER).hexdigest()],
        },
    }, sort_keys=True, separators=(",", ":")).encode()
    identity = "sha256:" + hashlib.sha256(config).hexdigest()
    manifest = [{
        "Config": identity[7:] + ".json",
        "RepoTags": [],
        "Layers": ["layers/one.tar"],
    }]
    path = tmp_path / "windows.tar"
    with tarfile.open(path, "w:") as tar:
        for name, content in [
            ("manifest.json", json.dumps(manifest).encode()),
            (identity[7:] + ".json", config),
            ("layers/one.tar", _LAYER),
        ]:
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    with pytest.raises(transfer.TransferError, match="architecture"):
        transfer._image_platform_and_layers(path, identity)


def test_docker_archive_with_surprise_symlink_never_stages(tmp_path):
    directory = _private(tmp_path)
    directory.mkdir(mode=0o700)
    tar = directory / "malicious.tar"
    _image_tar(tar, link=True)
    with pytest.raises(bundle.ImageBundleError):
        transfer.strip_source_tags(tar, _IMAGE)
    assert not (directory / "malicious.tar.untagged-partial").exists()



def test_unlisted_payload_in_saved_image_is_denied(tmp_path):
    directory = _private(tmp_path)
    directory.mkdir(mode=0o700)
    saved = directory / "payload.tar"
    _image_tar(saved)
    transfer.strip_source_tags(saved, _IMAGE)
    with tarfile.open(saved, "a") as tar:
        extra = tarfile.TarInfo("secrets/private-blob.dat")
        extra.size = 8
        tar.addfile(extra, io.BytesIO(b"not-data"))
    with pytest.raises(transfer.TransferError, match="undeclared payload"):
        transfer._image_platform_and_layers(saved, _IMAGE)



def test_modern_oci_blob_config_and_gzip_layer_are_normalized_tagless(tmp_path):
    parent = _private(tmp_path)
    parent.mkdir(mode=0o700)
    saved = parent / "modern-oci.tar"
    zipped = gzip.compress(_LAYER, mtime=0)
    layer_name = "blobs/sha256/" + hashlib.sha256(zipped).hexdigest()
    config_name = "blobs/sha256/" + _IMAGE[7:]
    diffid = "sha256:" + hashlib.sha256(_LAYER).hexdigest()
    row = {
        "Config": config_name,
        "RepoTags": ["docker.io/library/should-not-import:latest"],
        "Layers": [layer_name],
        "LayerSources": {
            diffid: {
                "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
                "digest": "sha256:" + hashlib.sha256(zipped).hexdigest(),
                "size": len(zipped),
                "urls": ["https://forbidden.invalid/registry-credentials"],
                "annotations": {"secret": "must-not-travel"},
            },
        },
    }
    entries = [
        ("manifest.json", json.dumps([row]).encode()),
        ("index.json", b'{"manifests":[{"annotations":{"org.opencontainers.image.ref.name":"hijacked"}}]}'),
        ("oci-layout", b'{"imageLayoutVersion":"1.0.0"}'),
        (config_name, _CONFIG),
        (layer_name, zipped),
        ("blobs/sha256/" + "c" * 64, b"unrelated OCI manifest"),
    ]
    with tarfile.open(saved, "w:") as tar:
        for name, content in entries:
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    transfer.strip_source_tags(saved, _IMAGE)
    assert transfer._image_platform_and_layers(saved, _IMAGE) == "linux/amd64"
    with tarfile.open(saved, "r:") as tar:
        names = set(tar.getnames())
        assert names == {"manifest.json", config_name, layer_name}
        normalized = transfer._manifest(tar)
        assert normalized["RepoTags"] == []
        descriptor = normalized["LayerSources"][diffid]
        assert set(descriptor) == {"mediaType", "digest", "size"}
        assert "urls" not in descriptor
        assert "annotations" not in descriptor


def test_modern_oci_blob_digest_mismatch_is_denied(tmp_path):
    saved = tmp_path / "modern-invalid-layer.tar"
    zipped = gzip.compress(_LAYER, mtime=0)
    wrong = "blobs/sha256/" + "0" * 64
    row = {
        "Config": "blobs/sha256/" + _IMAGE[7:],
        "RepoTags": [],
        "Layers": [wrong],
    }
    with tarfile.open(saved, "w:") as tar:
        for name, content in [
            ("manifest.json", json.dumps([row]).encode()),
            (row["Config"], _CONFIG),
            (wrong, zipped),
        ]:
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    with pytest.raises(transfer.TransferError, match="compressed layer blob hash mismatch"):
        transfer._image_platform_and_layers(saved, _IMAGE)


def test_cli_provides_all_transfer_actions_without_network_fallback():
    import inspect
    source = inspect.getsource(host.main)
    for action in [
        "verify-image-transfer", "plan-image-import", "import-images",
        "--allow-image-store-mutation", "--expected-receipt-sha256",
    ]:
        assert action in source
    assert "docker image pull" not in source
