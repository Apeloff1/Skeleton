"""Independent external Ed25519 release CLAIM verification; never release authority.

Uses ephemeral test-only Ed25519 keys. The production verifier only accepts
public keys supplied outside an owner-private evidence bundle and never
generates keys or signs content itself.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from scripts import local_ai_release_attestation as release

HEAD = "a" * 40
SOURCE_SHA = "b" * 64


def _openssl(*args):
    return subprocess.run(
        ["openssl", *map(str, args)], capture_output=True, text=True,
        timeout=20, check=True,
    )


@pytest.fixture(scope="module")
def external_keys(tmp_path_factory):
    if shutil.which("openssl") is None:
        pytest.skip("Ed25519 source qualification requires OpenSSL")
    root = tmp_path_factory.mktemp("independent-signers")
    output = {}
    for domain in release.SIGNATURES:
        private = root / (domain + ".private.pem")
        public = root / (domain + ".public.pem")
        _openssl("genpkey", "-algorithm", "ED25519", "-out", private)
        _openssl("pkey", "-in", private, "-pubout", "-out", public)
        output[domain] = (private, public)
    return output


def _manifest():
    return {
        "schema": release.SCHEMA,
        "status": "signed_claims_only_not_release_authorized",
        "source_head": HEAD,
        "mode": "cpu",
        "signer_domains": ["release", "security"],
        "release_authorized": False,
        "protected_chat_qualified": False,
        "coherent_recovery_qualified": False,
        **{key: SOURCE_SHA for key in release.EVIDENCE},
    }


def _create(tmp_path, keys, *, altered=None):
    evidence = tmp_path / "private-claims"
    evidence.mkdir(mode=0o700)
    record = _manifest()
    if altered:
        altered(record)
    content = release._canonical(record)
    file = evidence / release.MANIFEST
    file.write_bytes(content)
    file.chmod(0o600)
    for domain, filename in release.SIGNATURES.items():
        _openssl("pkeyutl", "-sign", "-inkey", keys[domain][0],
                 "-rawin", "-in", file, "-out", evidence / filename)
        (evidence / filename).chmod(0o600)
    return evidence


def _verify(directory, keys, *, head=HEAD, source=SOURCE_SHA):
    return release.verify_signed_release_claims(
        directory, keys["security"][1], keys["release"][1],
        expected_head=head, expected_image_receipt_sha256=source,
    )


def test_distinct_real_ed25519_signatures_only_verify_claims(
    tmp_path, external_keys,
):
    directory = _create(tmp_path, external_keys)
    record = _verify(directory, external_keys)
    assert record["openssl_ed25519_verified"] is True
    assert record["distinct_external_authorities_verified"] is True
    assert record["release_authorized"] is False
    assert record["merge_authorized"] is False
    assert record["referenced_physical_receipts_independently_checked"] is False
    assert record["protected_chat_qualified"] is False
    assert record["coherent_database_recovery_qualified"] is False
    assert record["device_qualified"] is False
    assert record["expected_source_head"] == HEAD
    assert "PRIVATE" not in json.dumps(record)
    assert str(external_keys["security"][0]) not in json.dumps(record)


@pytest.mark.parametrize("name", ["security", "release"])
def test_wrong_signature_payload_denied(tmp_path, external_keys, name):
    directory = _create(tmp_path, external_keys)
    sig = directory / release.SIGNATURES[name]
    body = bytearray(sig.read_bytes())
    body[0] ^= 0x40
    sig.write_bytes(body)
    with pytest.raises(release.ProvenanceError, match="signature"):
        _verify(directory, external_keys)


@pytest.mark.parametrize("name", ["security", "release"])
def test_short_or_malformed_signature_denied(tmp_path, external_keys, name):
    directory = _create(tmp_path, external_keys)
    (directory / release.SIGNATURES[name]).write_bytes(b"x")
    with pytest.raises(release.ProvenanceError, match="length"):
        _verify(directory, external_keys)


def test_untrusted_public_key_cannot_be_inside_archive(tmp_path, external_keys):
    directory = _create(tmp_path, external_keys)
    public = directory / "security-public.pem"
    public.write_bytes(external_keys["security"][1].read_bytes())
    with pytest.raises(release.ProvenanceError):
        release.verify_signed_release_claims(
            directory, public, external_keys["release"][1],
            expected_head=HEAD, expected_image_receipt_sha256=SOURCE_SHA,
        )


def test_both_domains_must_use_distinct_public_keys(tmp_path, external_keys):
    directory = _create(tmp_path, external_keys)
    with pytest.raises(release.ProvenanceError, match="distinct"):
        release.verify_signed_release_claims(
            directory, external_keys["security"][1],
            external_keys["security"][1], expected_head=HEAD,
            expected_image_receipt_sha256=SOURCE_SHA,
        )


def test_modified_claims_denied_even_when_structurally_valid(
    tmp_path, external_keys,
):
    directory = _create(tmp_path, external_keys)
    path = directory / release.MANIFEST
    claim = json.loads(path.read_bytes())
    claim["device_pressure_receipt_sha256"] = "c" * 64
    path.write_bytes(release._canonical(claim))
    with pytest.raises(release.ProvenanceError, match="signature"):
        _verify(directory, external_keys)


@pytest.mark.parametrize("head", ["a" * 39, "f" * 40, "Z" * 40])
def test_expected_head_must_be_exact_and_trusted(tmp_path, external_keys, head):
    directory = _create(tmp_path, external_keys)
    with pytest.raises(release.ProvenanceError, match="authority"):
        _verify(directory, external_keys, head=head)


def test_out_of_band_image_receipt_is_part_of_signed_claims(
    tmp_path, external_keys,
):
    directory = _create(tmp_path, external_keys)
    with pytest.raises(release.ProvenanceError, match="evidence"):
        _verify(directory, external_keys, source="0" * 64)


def test_manifest_cannot_claim_release_or_protected_chat(
    tmp_path, external_keys,
):
    directory = _create(
        tmp_path, external_keys,
        altered=lambda row: row.update({"release_authorized": True}),
    )
    with pytest.raises(release.ProvenanceError, match="authority"):
        _verify(directory, external_keys)


def test_manifest_with_unlisted_extra_role_denied(tmp_path, external_keys):
    directory = _create(
        tmp_path, external_keys,
        altered=lambda row: row.update({"extra": "forged"}),
    )
    with pytest.raises(release.ProvenanceError, match="shape"):
        _verify(directory, external_keys)


def test_archive_with_unlisted_file_is_not_trusted(tmp_path, external_keys):
    directory = _create(tmp_path, external_keys)
    (directory / "unlisted-secret").write_text("not admitted")
    with pytest.raises(release.ProvenanceError, match="undeclared"):
        _verify(directory, external_keys)


def test_reordered_or_trailing_json_denied_before_signature_check(
    tmp_path, external_keys,
):
    directory = _create(tmp_path, external_keys)
    path = directory / release.MANIFEST
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(release.ProvenanceError, match="noncanonical"):
        _verify(directory, external_keys)


def test_manifest_symlink_is_not_admitted(tmp_path, external_keys):
    directory = _create(tmp_path, external_keys)
    file = directory / release.MANIFEST
    data = tmp_path / "content"
    data.write_bytes(file.read_bytes())
    file.unlink()
    file.symlink_to(data)
    with pytest.raises(release.ProvenanceError):
        _verify(directory, external_keys)


def test_external_public_keys_must_be_owner_readable(tmp_path, external_keys):
    directory = _create(tmp_path, external_keys)
    public = tmp_path / "replacement.pem"
    public.symlink_to(external_keys["release"][1])
    with pytest.raises(release.ProvenanceError):
        release.verify_signed_release_claims(
            directory, external_keys["security"][1], public,
            expected_head=HEAD,
            expected_image_receipt_sha256=SOURCE_SHA,
        )
