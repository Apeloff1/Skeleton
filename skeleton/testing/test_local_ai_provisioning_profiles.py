"""Pinned operator acquisition profiles; no network, inference or service launch."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tarfile
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("profile_provisioner", ROOT / "scripts/provision_local_ai.py")
assert SPEC and SPEC.loader
provisioner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(provisioner)


def test_provisioning_help_runs_before_site_packages_or_application_dependencies_exist():
    result = subprocess.run(
        [sys.executable, "-S", str(ROOT / "scripts/provision_local_ai.py"), "--help"],
        cwd=ROOT, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "--profile" in result.stdout and "--download" in result.stdout
    assert result.stderr == ""


def test_coding_recipe_is_official_revision_pinned_and_declared_without_changing_chat_default():
    declared = json.loads((ROOT / "machine/ai_local_model_provisioning.json").read_text())
    assert provisioner.DEFAULT_PROFILE == declared["model_profiles"]["default"] == "chat"
    assert provisioner._model_recipe() is provisioner.MODEL
    for profile in provisioner.MODEL_PROFILES:
        recipe = provisioner._model_recipe(profile)
        entry = declared["model_profiles"][profile]
        assert recipe["url"] == (
            "https://huggingface.co/" + entry["repository"] + "/resolve/"
            + entry["revision"] + "/" + entry["filename"]
        )
        for key in ("filename", "sha256", "bytes", "license"):
            assert recipe[key] == entry[key]
        assert provisioner.MODEL_IDS[profile] == entry["model_id"]
    assert provisioner.CODING_MODEL["sha256"] == "cc324af070c2ecbfd324a30884d2f951a7ff756aba85cb811a6ec436933bb046"
    assert provisioner.CODING_MODEL["bytes"] == 1_117_320_768
    assert provisioner.RUNTIME["sha256"] == "f6d25dde8f51133143d1453da4fd5f73b145127177612a283bf7995957af3392"


def test_coding_template_does_not_inject_qwen3_thinking_tokens_and_preserves_runtime_flags():
    from skeleton.ai.runtime.inference.deployment import QWEN3_COMPLETION_CHAT_TEMPLATE
    from skeleton.ai.runtime.inference.llama_cpp import (
        CODING_COMPLETION_CHAT_TEMPLATE, COMPLETION_CHAT_FLAGS,
    )
    assert provisioner.CODING_COMPLETION_CHAT_TEMPLATE == CODING_COMPLETION_CHAT_TEMPLATE
    assert tuple(provisioner.PROFILE_ARGS) == COMPLETION_CHAT_FLAGS
    chat, coding = provisioner._profile_args("chat"), provisioner._profile_args("coding")
    assert chat[:-1] == coding[:-1]
    assert chat[-1] == QWEN3_COMPLETION_CHAT_TEMPLATE
    assert "<think>" not in coding[-1] and "</think>" not in coding[-1]
    assert "<|im_start|>assistant" in coding[-1]
    assert "--single-turn" in coding and "--no-escape" in coding
    assert coding[coding.index("--reasoning") + 1] == "off"
    assert not any(option.startswith(("--hf", "--url", "--model-url")) for option in coding)


@pytest.fixture
def artifacts(tmp_path, monkeypatch):
    executable = b"#!/usr/bin/env python3\nraise SystemExit('must never execute during preparation')\n"
    model = (struct.pack("<4sIQQ", b"GGUF", 3, 2, 1)
             + struct.pack("<Q", len(b"general.architecture")) + b"general.architecture"
             + struct.pack("<I", 8) + struct.pack("<Q", len(b"qwen2")) + b"qwen2")
    model += b"\0" * (8192-len(model))
    model_path = tmp_path / "operator-source.gguf"
    model_path.write_bytes(model)
    archive = tmp_path / "operator-runtime.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        for name, data in (("llama-completion", executable), ("LICENSE", b"MIT fixture license\n"),
                           ("libfixture.so", b"operator test fixture library")):
            member = tarfile.TarInfo("llama-b11429/" + name)
            member.size = len(data)
            bundle.addfile(member, io.BytesIO(data))
    def recipe(name, source):
        return {"filename": name, "url": "https://example.invalid/pinned-fixture",
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "bytes": source.stat().st_size, "license": "test-only"}
    monkeypatch.setattr(provisioner, "MODEL", recipe("small-chat.gguf", model_path))
    monkeypatch.setattr(provisioner, "CODING_MODEL", recipe("optional-coder.gguf", model_path))
    monkeypatch.setattr(provisioner, "RUNTIME", recipe("fixture-runtime.tar.gz", archive))
    monkeypatch.setattr(provisioner, "EXECUTABLE_SHA256", hashlib.sha256(executable).hexdigest())
    monkeypatch.setattr(provisioner.subprocess, "Popen", lambda *a, **kw: pytest.fail("No inference, transfer or service process may start"))
    monkeypatch.setattr(provisioner.shutil, "disk_usage", lambda path: SimpleNamespace(free=8*1024**3))
    monkeypatch.setattr(provisioner.platform, "system", lambda: "Linux")
    monkeypatch.setattr(provisioner.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(provisioner.platform, "libc_ver", lambda: ("glibc", "2.36"))
    return model_path, archive


def args(target, artifacts, profile="chat"):
    model, archive = artifacts
    return argparse.Namespace(output=target, target=provisioner.TARGET, prepare_for_container=False,
                              profile=profile, download=False, model=model, runtime_archive=archive,
                              threads=2, context_size=12288)


@pytest.mark.parametrize("profile", ["chat", "coding"])
def test_offline_profile_is_admitted_by_real_loader_and_reuses_exact_receipt(tmp_path, artifacts, profile):
    from skeleton.ai.runtime.inference.deployment import LocalModelDeployment
    target = tmp_path / (profile + "-deployment")
    request = args(target, artifacts, profile)
    created = provisioner.provision(request)
    assert created["status"] == "provisioned" and created["profile"] == profile
    assert created["inference_executed"] is False
    assert not (target / ".incomplete").exists()
    manifest = LocalModelDeployment.load(target / "deployment.json")
    assert manifest.model_id == provisioner.MODEL_IDS[profile]
    assert manifest.context_size == 12288 and manifest.timeout_seconds == 600
    assert manifest.extra_args == tuple(provisioner._profile_args(profile))
    snapshot = {p.relative_to(target).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in target.rglob("*") if p.is_file()}
    reused = provisioner.provision(request)
    assert reused["status"] == "verified_existing"
    assert reused["receipt_digest"] == created["receipt_digest"]
    assert snapshot == {p.relative_to(target).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in target.rglob("*") if p.is_file()}


def test_old_namespace_without_profile_keeps_chat_default(tmp_path, artifacts):
    request = args(tmp_path / "default-deployment", artifacts)
    del request.profile
    created = provisioner.provision(request)
    assert created["profile"] == "chat"
    assert json.loads((request.output / "deployment.json").read_text())["model_id"] == provisioner.MODEL_IDS["chat"]


def test_existing_coding_directory_cannot_be_retargeted_or_reconfigured(tmp_path, artifacts):
    target = tmp_path / "coding-deployment"
    request = args(target, artifacts, "coding")
    provisioner.provision(request)
    receipt = (target / "provisioning.json").read_bytes()
    request.profile = "chat"
    with pytest.raises(ValueError, match="recipe differs"):
        provisioner.provision(request)
    assert (target / "provisioning.json").read_bytes() == receipt
    request.profile = "coding"
    request.context_size = 16384
    with pytest.raises(ValueError, match="profile differs"):
        provisioner.provision(request)
    assert (target / "provisioning.json").read_bytes() == receipt


def test_profile_specific_hash_bound_accepts_selected_coding_recipe_only(tmp_path, monkeypatch):
    candidate = tmp_path / "coding.gguf"
    candidate.write_bytes(b"pinned source" * 100)
    monkeypatch.setattr(provisioner, "MODEL", {"bytes": 128})
    coding = {"bytes": candidate.stat().st_size,
              "sha256": hashlib.sha256(candidate.read_bytes()).hexdigest()}
    provisioner._verify(candidate, coding)
    with pytest.raises(ValueError, match="bytes or SHA256"):
        provisioner._verify(candidate, {**coding, "bytes": 128})
    candidate.write_bytes(b"tampered data" * 100)
    with pytest.raises(ValueError, match="bytes or SHA256"):
        provisioner._verify(candidate, coding)


def test_acquisition_reserves_space_for_selected_model_before_claim(tmp_path, monkeypatch, artifacts):
    request = args(tmp_path / "coding-deployment", artifacts, "coding")
    required = 2*1024**3 + provisioner.CODING_MODEL["bytes"] + provisioner.RUNTIME["bytes"] + provisioner.MAX_EXTRACTED
    monkeypatch.setattr(provisioner.shutil, "disk_usage", lambda path: SimpleNamespace(free=required-1))
    with pytest.raises(ValueError, match="retain two GiB"):
        provisioner.provision(request)
    assert not request.output.exists()


@pytest.mark.parametrize("profile", ["other", "", True, None])
def test_unknown_profile_is_rejected_before_destination_or_transfer(tmp_path, artifacts, profile):
    request = args(tmp_path / "unknown-profile", artifacts, profile)
    with pytest.raises(ValueError, match="profile"):
        provisioner.provision(request)
    assert not request.output.exists()


def test_truncated_offline_coding_artifact_never_publishes_deployment(tmp_path, artifacts):
    model, archive = artifacts
    model.write_bytes(model.read_bytes()[:-1])
    request = args(tmp_path / "coding-deployment", (model, archive), "coding")
    with pytest.raises(ValueError, match="exact-size"):
        provisioner.provision(request)
    assert (request.output / ".incomplete").is_file()
    assert not (request.output / "deployment.json").exists()


def test_coding_reuses_verified_chat_runtime_without_retargeting_or_network(tmp_path, artifacts):
    source = tmp_path / "existing-chat"
    provisioner.provision(args(source, artifacts))
    before = {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in source.rglob("*") if p.is_file()}
    source_receipt = json.loads((source / "provisioning.json").read_text())
    request = args(tmp_path / "optional-coding", artifacts, "coding")
    request.runtime_archive = None
    request.runtime_from = source
    request.context_size = 16384
    result = provisioner.provision(request)
    assert result["status"] == "provisioned"
    receipt = json.loads((request.output / "provisioning.json").read_text())
    assert receipt["runtime_source_receipt_digest"] == source_receipt["receipt_digest"]
    assert {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in source.rglob("*") if p.is_file()} == before
    assert (request.output / "runtime/llama-completion").read_bytes() == (source / "runtime/llama-completion").read_bytes()
    assert provisioner.provision(request)["status"] == "verified_existing"


def test_runtime_reuse_rejects_modified_source_before_acquisition(tmp_path, artifacts):
    source = tmp_path / "existing-chat"
    provisioner.provision(args(source, artifacts))
    library = source / "runtime/libfixture.so"
    library.chmod(0o644)
    library.write_bytes(b"x" * library.stat().st_size)
    request = args(tmp_path / "optional-coding", artifacts, "coding")
    request.runtime_archive = None
    request.runtime_from = source
    with pytest.raises(ValueError, match="bytes or SHA256"):
        provisioner.provision(request)
    assert not request.output.exists()


def test_runtime_reuse_under_private_umask_remains_nonroot_traversable(tmp_path, artifacts):
    private_parent = tmp_path / "private-operator-directory"
    private_parent.mkdir(mode=0o700)
    source = private_parent / "existing-chat"
    old_umask = os.umask(0o077)
    try:
        provisioner.provision(args(source, artifacts))
        request = args(private_parent / "optional-coding", artifacts, "coding")
        request.runtime_archive = None
        request.runtime_from = source
        result = provisioner.provision(request)
    finally:
        os.umask(old_umask)
    assert result["status"] == "provisioned"
    assert stat.S_IMODE(private_parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(request.output.stat().st_mode) == 0o755
    assert stat.S_IMODE((request.output / "runtime").stat().st_mode) == 0o755
    assert stat.S_IMODE((request.output / "runtime/llama-completion").stat().st_mode) == 0o555
    assert stat.S_IMODE((request.output / "runtime/LICENSE").stat().st_mode) == 0o444
    assert stat.S_IMODE((request.output / provisioner.CODING_MODEL["filename"]).stat().st_mode) == 0o444


def test_runtime_source_and_archive_are_explicitly_exclusive(tmp_path, artifacts):
    request = args(tmp_path / "optional-coding", artifacts, "coding")
    request.runtime_from = tmp_path / "runtime-source"
    with pytest.raises(ValueError, match="not both"):
        provisioner.provision(request)
    assert not request.output.exists()


def test_pinned_transfer_is_published_without_second_weight_copy(tmp_path, monkeypatch, artifacts):
    model, archive = artifacts
    source_bytes = {provisioner.CODING_MODEL["filename"]: model.read_bytes(),
                    provisioner.RUNTIME["filename"]: archive.read_bytes()}
    staged_inodes = {}
    def transfer(destination, recipe):
        assert destination.name == "." + recipe["filename"] + ".pending"
        assert (destination.parent / ".incomplete").is_file()
        assert not (destination.parent / recipe["filename"]).exists()
        destination.write_bytes(source_bytes[recipe["filename"]])
        staged_inodes[recipe["filename"]] = destination.stat().st_ino
    monkeypatch.setattr(provisioner, "_download_pinned", transfer)
    request = args(tmp_path / "download-target", artifacts, "coding")
    request.model = request.runtime_archive = None
    request.download = True
    result = provisioner.provision(request)
    assert result["status"] == "provisioned"
    assert (request.output / provisioner.CODING_MODEL["filename"]).stat().st_ino == staged_inodes[provisioner.CODING_MODEL["filename"]]
    assert not list(request.output.glob("*.pending"))


def test_atomic_publication_never_overwrites_a_concurrent_destination(tmp_path, monkeypatch):
    target = tmp_path / "model.gguf"
    payload = b"pinned fixture"
    recipe = {"filename": target.name, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
    def transfer(staged, expected):
        staged.write_bytes(payload)
        target.write_bytes(b"concurrent operator file")
    monkeypatch.setattr(provisioner, "_download_pinned", transfer)
    with pytest.raises(FileExistsError):
        provisioner._acquire(target, recipe, None, download=True)
    assert target.read_bytes() == b"concurrent operator file"
