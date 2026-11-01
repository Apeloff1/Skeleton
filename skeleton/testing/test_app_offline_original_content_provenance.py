"""Real browser/Godot source inventory, pinned claims and nofollow acceptance."""
from __future__ import annotations

from hashlib import sha256
import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_original_content_provenance import (
    SCHEMA, OriginalContentProvenanceError, inspect_original_content_provenance,
)
from skeleton.testing.test_app_offline_archive_install import _archive


@pytest.fixture
def provenance(tmp_path, capsys):
    source, _, _, manifest_pin = _archive(tmp_path, capsys)
    entries = []
    for path in ("godot/project.godot", "index.html"):
        entries.append({
            "path": path,
            "sha256": sha256((source / path).read_bytes()).hexdigest(),
            "origin": "ai_generated_original",
        })
    claims = {
        "schema": SCHEMA,
        "project_id": "install-original",
        "manifest_sha256": manifest_pin,
        "rights_review_status": "unreviewed",
        "files": entries,
    }
    path = tmp_path / "original-claims.json"
    path.write_text(json.dumps(claims, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)
    return {
        "installed_source": source,
        "claim_file": path,
        "expected_manifest_sha256": manifest_pin,
        "expected_claim_sha256": sha256(path.read_bytes()).hexdigest(),
        "authorized": True,
    }, claims


def _rewrite(data, claims):
    path = data["claim_file"]
    path.write_text(json.dumps(claims, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)
    data["expected_claim_sha256"] = sha256(path.read_bytes()).hexdigest()


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_original_browser_godot_claims_bound_to_playable_source(provenance):
    data, _ = provenance
    before = data["claim_file"].read_bytes()
    result = inspect_original_content_provenance(**data)
    assert result["claimed_file_count"] == 2
    assert result["canonical_source_replay_verified"] is True
    assert result["claimed_source_hashes_verified"] is True
    assert result["claimed_source_inodes_stable"] is True
    assert result["rights_review_status"] == "unreviewed"
    assert result["plagiarism_cleared"] is False
    assert result["rights_certified"] is False
    assert result["claims_cover_entire_game"] is False
    assert result["release_certified"] is False
    assert data["claim_file"].read_bytes() == before


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_claim_hash_tamper_rejected(provenance):
    data, claims = provenance
    claims["files"][0]["sha256"] = "0" * 64
    _rewrite(data, claims)
    with pytest.raises(ValueError):
        inspect_original_content_provenance(**data)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_unpinned_claim_update_denied(provenance):
    data, claims = provenance
    claims["rights_review_status"] = "unreviewed"
    data["claim_file"].write_bytes(data["claim_file"].read_bytes() + b" ")
    with pytest.raises(OriginalContentProvenanceError, match="pin mismatch"):
        inspect_original_content_provenance(**data)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
@pytest.mark.parametrize("origin", ["third_party", "unknown", "", 42])
def test_unreviewed_external_origin_never_admitted(provenance, origin):
    data, claims = provenance
    claims["files"][0]["origin"] = origin
    _rewrite(data, claims)
    with pytest.raises(OriginalContentProvenanceError):
        inspect_original_content_provenance(**data)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_duplicate_or_unsorted_source_claims_rejected(provenance):
    data, claims = provenance
    claims["files"] = list(reversed(claims["files"]))
    _rewrite(data, claims)
    with pytest.raises(OriginalContentProvenanceError):
        inspect_original_content_provenance(**data)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_claim_file_symlink_rejected(provenance, tmp_path):
    data, _ = provenance
    alias = tmp_path / "claims-alias.json"
    alias.symlink_to(data["claim_file"])
    with pytest.raises((ValueError, OSError)):
        inspect_original_content_provenance(
            **{**data, "claim_file": alias},
        )


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_same_byte_claim_inode_replacement_rejected(provenance, tmp_path, monkeypatch):
    import skeleton.app.offline_original_content_provenance as module
    data, _ = provenance
    original = module.verify_exported_package
    count = 0

    def swap(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            replacement = tmp_path / "replacement-claims.json"
            replacement.write_bytes(data["claim_file"].read_bytes())
            replacement.chmod(0o600)
            os.replace(replacement, data["claim_file"])
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "verify_exported_package", swap)
    with pytest.raises(OriginalContentProvenanceError, match="changed"):
        inspect_original_content_provenance(**data)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_authority_checked_before_provenance_io(provenance, monkeypatch):
    import skeleton.app.offline_original_content_provenance as module
    data, _ = provenance

    def forbidden(*args, **kwargs):
        raise AssertionError("unauthorized claim access")

    monkeypatch.setattr(module, "_read_policy", forbidden)
    with pytest.raises(PermissionError):
        inspect_original_content_provenance(**{**data, "authorized": False})


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_cli_provenance_acceptance_and_denial(provenance, capsys):
    data, _ = provenance
    args = [
        "inspect-original-provenance",
        "--installed", str(data["installed_source"]),
        "--claims", str(data["claim_file"]),
        "--expected-manifest-sha256", data["expected_manifest_sha256"],
        "--expected-claim-sha256", data["expected_claim_sha256"],
    ]
    assert run_app_cli(args) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert run_app_cli(args + ["--trusted-local-operator"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["claimed_source_hashes_verified"] is True
    assert result["rights_certified"] is False


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_same_byte_source_inode_replacement_during_replay_rejected(
    provenance, tmp_path, monkeypatch,
):
    """Canonical replay returning identical bytes is not inode custody."""
    import skeleton.app.offline_original_content_provenance as module

    data, _ = provenance
    source = data["installed_source"] / "index.html"
    original_bytes = source.read_bytes()
    original_mode = source.stat().st_mode & 0o777
    original_verify = module.verify_exported_package
    calls = 0

    def replace_during_second_replay(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            replacement = tmp_path / "same-byte-source.html"
            replacement.write_bytes(original_bytes)
            replacement.chmod(original_mode)
            os.replace(replacement, source)
        return original_verify(*args, **kwargs)

    monkeypatch.setattr(module, "verify_exported_package", replace_during_second_replay)
    with pytest.raises(OriginalContentProvenanceError, match="inode replaced"):
        inspect_original_content_provenance(**data)
    assert source.read_bytes() == original_bytes


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_same_byte_source_inode_replacement_during_first_read_rejected(
    provenance, tmp_path, monkeypatch,
):
    """A read can see the right digest from a different inode."""
    import skeleton.app.offline_original_content_provenance as module

    data, _ = provenance
    source = data["installed_source"] / "index.html"
    original_bytes = source.read_bytes()
    original_mode = source.stat().st_mode & 0o777
    original_read = module._read
    swapped = False

    def swap_on_claimed_read(fd, path, limit, *, owner_controlled=False):
        nonlocal swapped
        if path == "index.html" and not swapped:
            swapped = True
            replacement = tmp_path / "same-byte-first-read.html"
            replacement.write_bytes(original_bytes)
            replacement.chmod(original_mode)
            os.replace(replacement, source)
        return original_read(fd, path, limit, owner_controlled=owner_controlled)

    monkeypatch.setattr(module, "_read", swap_on_claimed_read)
    with pytest.raises(OriginalContentProvenanceError, match="inode replaced"):
        inspect_original_content_provenance(**data)
    assert swapped is True
    assert source.read_bytes() == original_bytes


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_same_file_inodes_with_replaced_parent_directory_rejected(
    provenance, tmp_path, monkeypatch,
):
    """Replacing godot/ while moving its original files is not stable custody."""
    import skeleton.app.offline_original_content_provenance as module

    data, _ = provenance
    source_root = data["installed_source"]
    godot = source_root / "godot"
    original_directory = tmp_path / "moved-original-godot"
    original_file = godot / "project.godot"
    original_inode = original_file.stat().st_ino
    original_verify = module.verify_exported_package
    calls = 0

    def replace_parent_during_replay(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            os.rename(godot, original_directory)
            godot.mkdir(mode=0o755)
            for child in original_directory.iterdir():
                os.rename(child, godot / child.name)
            original_directory.rmdir()
            assert (godot / "project.godot").stat().st_ino == original_inode
        return original_verify(*args, **kwargs)

    monkeypatch.setattr(module, "verify_exported_package", replace_parent_during_replay)
    with pytest.raises(OriginalContentProvenanceError, match="inode replaced"):
        inspect_original_content_provenance(**data)
