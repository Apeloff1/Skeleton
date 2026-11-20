"""Real ephemeral Ed25519 dual-signature proof over synthetic custody receipt.

The tests create only temporary private keys inside pytest-owned fixtures,
never commit key files, connect to Mongo/Chroma/Docker or authorize release.
The real OpenSSL command verifies detached 64-byte Ed25519 signatures;
the independent actual byte-restore/recovery ledger has its own suite.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from scripts import local_ai_signed_custody as signer

SOURCE_HEAD = "a" * 40
COLD_SHA = "b" * 64
EVIDENCE_SHA = "c" * 64


def _v2():
    return {
        "schema": signer.three.SCHEMA,
        "status": "independent_mongo_sqlite_chroma_file_custody_not_recovery",
        "cold_source_bytes_reverified_after_each_subgate": True,
        "mongo_wiredtiger_catalog_file_custody_verified": True,
        "mongo_wiredtiger_files_hashed": 9,
        "mongo_journal_files_observed": 1,
        "sqlite_structural_integrity_verified": True,
        "sqlite_databases_checked": 2,
        "chroma_hnsw_file_custody_verified": True,
        "chroma_persistent_segment_files_hashed": 5,
        "aggregate_evidence_sha256": EVIDENCE_SHA,
        **{key: False for key in signer._PHYSICAL_FALSE},
    }


def _claim():
    return {
        "schema": signer.SCHEMA,
        "status": "signed_file_custody_not_database_recovery",
        "source_head_sha": SOURCE_HEAD,
        "cold_source_receipt_sha256": COLD_SHA,
        "aggregate_evidence_sha256": EVIDENCE_SHA,
        "signer_domains": ["operator", "auditor"],
        **{key: False for key in signer._FALSE},
    }


def _canonical(claim):
    return (json.dumps(claim, sort_keys=True, ensure_ascii=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")


def _openssl(*args):
    p = subprocess.run(
        ["openssl", *map(str, args)],
        check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=20,
    )
    assert p.returncode == 0, p.stderr.decode("utf-8", errors="replace")[:400]


def _fixture(tmp_path, monkeypatch):
    if shutil.which("openssl") is None:
        pytest.skip("OpenSSL is required to physically verify Ed25519")
    tmp_path.chmod(0o700)
    folder = tmp_path / "signed-custody"
    folder.mkdir(mode=0o700)
    folder.chmod(0o700)
    keys = tmp_path / "external-auditor-keys"
    keys.mkdir(mode=0o700)
    keys.chmod(0o700)
    manifest = folder / signer.MANIFEST
    manifest.write_bytes(_canonical(_claim()))
    manifest.chmod(0o600)
    public = {}
    private = {}
    for role in signer.SIGNATURES:
        secret = keys / (role + ".private.pem")
        trusted = keys / (role + ".public.pem")
        _openssl("genpkey", "-algorithm", "ED25519", "-out", secret)
        _openssl("pkey", "-in", secret, "-pubout", "-out", trusted)
        secret.chmod(0o600)
        trusted.chmod(0o600)
        signature = folder / signer.SIGNATURES[role]
        _openssl("pkeyutl", "-sign", "-inkey", secret,
                 "-rawin", "-in", manifest, "-out", signature)
        signature.chmod(0o600)
        assert signature.stat().st_size == 64
        public[role], private[role] = trusted, secret
    calls = []
    def physically_rechecked(source, destination, *, expected_receipt_sha256):
        calls.append((source, destination, expected_receipt_sha256))
        assert expected_receipt_sha256 == COLD_SHA
        return copy.deepcopy(_v2())
    monkeypatch.setattr(
        signer.three, "inspect_offline_three_store_evidence",
        physically_rechecked,
    )
    return folder, public, private, calls


def _run(folder, keys, *, source=None, destination=None, head=SOURCE_HEAD,
         cold=COLD_SHA, operator_pin=None, auditor_pin=None):
    return signer.verify_double_signed_offline_custody(
        folder, keys["operator"], keys["auditor"],
        source or Path("/no-live-original"),
        destination or Path("/no-live-restored"),
        expected_source_head_sha=head,
        expected_receipt_sha256=cold,
        expected_operator_public_key_sha256=operator_pin or hashlib.sha256(
            keys["operator"].read_bytes()
        ).hexdigest(),
        expected_auditor_public_key_sha256=auditor_pin or hashlib.sha256(
            keys["auditor"].read_bytes()
        ).hexdigest(),
    )


def test_two_real_external_ed25519_signatures_and_fresh_v2_file_evidence(
        tmp_path, monkeypatch, capsys):
    folder, keys, private, calls = _fixture(tmp_path, monkeypatch)
    result = _run(folder, keys)
    assert result["schema"] == signer.RESULT_SCHEMA
    assert result["two_distinct_out_of_band_key_pins_matched"] is True
    assert result["fresh_three_store_file_evidence_rechecked"] is True
    assert result["openssl_ed25519_signatures_verified"] is True
    assert result["offline_file_evidence_sha256"] == EVIDENCE_SHA
    assert result["source_head_sha"] == SOURCE_HEAD
    assert result["private_keys_accessed"] is False
    assert result["database_process_started"] is False
    for key in (
        "source_archive_modified", "mongo_logical_recovery_qualified",
        "cross_store_transaction_coherence_qualified",
        "application_restore_qualified",
        "protected_jeeves_chat_qualified",
        "release_authorized", "merge_authorized",
    ):
        assert result[key] is False
    assert len(calls) == 2
    assert result["operator_public_key_sha256"] != (
        result["auditor_public_key_sha256"]
    )
    text = str(result) + str(capsys.readouterr())
    assert str(folder) not in text
    assert str(private["operator"]) not in text
    assert "BEGIN PRIVATE KEY" not in text


def test_signed_file_custody_is_deterministic_with_fresh_rechecks(
        tmp_path, monkeypatch):
    folder, keys, _, calls = _fixture(tmp_path, monkeypatch)
    assert _run(folder, keys) == _run(folder, keys)
    assert len(calls) == 4


@pytest.mark.parametrize("role", ["operator", "auditor"])
def test_one_swapped_or_tampered_signature_fails(
        tmp_path, monkeypatch, role):
    folder, keys, _, calls = _fixture(tmp_path, monkeypatch)
    path = folder / signer.SIGNATURES[role]
    raw = bytearray(path.read_bytes())
    raw[0] ^= 1
    path.write_bytes(raw)
    path.chmod(0o600)
    with pytest.raises(signer.SignedCustodyError, match="signature"):
        _run(folder, keys)


def test_reuse_of_same_public_authority_key_denied(
        tmp_path, monkeypatch):
    folder, keys, _, calls = _fixture(tmp_path, monkeypatch)
    keys["auditor"] = keys["operator"]
    with pytest.raises(signer.SignedCustodyError, match="identical pinned"):
        _run(folder, keys)
    assert calls == []


def test_identical_key_material_under_two_paths_is_denied(
        tmp_path, monkeypatch):
    folder, keys, _, calls = _fixture(tmp_path, monkeypatch)
    keys["auditor"].write_bytes(keys["operator"].read_bytes())
    with pytest.raises(signer.SignedCustodyError, match="identical pinned"):
        _run(folder, keys)
    assert calls == []


def test_public_key_inside_untrusted_bundle_denied(
        tmp_path, monkeypatch):
    folder, keys, _, calls = _fixture(tmp_path, monkeypatch)
    forged = folder / "attacker.public.pem"
    forged.write_bytes(keys["operator"].read_bytes())
    forged.chmod(0o600)
    keys["operator"] = forged
    with pytest.raises(signer.SignedCustodyError):
        _run(folder, keys)
    assert calls == []


def test_signatures_are_not_keys_and_private_material_rejected(
        tmp_path, monkeypatch):
    folder, keys, private, calls = _fixture(tmp_path, monkeypatch)
    keys["operator"] = private["operator"]
    with pytest.raises(signer.SignedCustodyError, match="public"):
        _run(folder, keys)
    assert calls == []


@pytest.mark.parametrize("change", [
    {"status": "release_ready"},
    {"source_head_sha": "d" * 40},
    {"cold_source_receipt_sha256": "d" * 64},
    {"aggregate_evidence_sha256": "d" * 64},
    {"signer_domains": ["operator"]},
    {"signer_domains": ["auditor", "operator"]},
    {"release_authorized": True},
    {"application_restore_qualified": True},
    {"mongo_logical_recovery_qualified": True},
    {"cross_store_transaction_coherence_qualified": True},
    {"extra_private_claim": "secret"},
])
def test_manifest_cannot_claim_unknown_authority_even_when_signed(
        tmp_path, monkeypatch, change):
    folder, keys, private, calls = _fixture(tmp_path, monkeypatch)
    manifest = folder / signer.MANIFEST
    manifest.write_bytes(_canonical({**_claim(), **change}))
    manifest.chmod(0o600)
    with pytest.raises(signer.SignedCustodyError):
        _run(folder, keys)
    assert calls == []


def test_noncanonical_json_or_duplicate_field_rejected_before_signatures(
        tmp_path, monkeypatch):
    folder, keys, private, calls = _fixture(tmp_path, monkeypatch)
    path = folder / signer.MANIFEST
    path.write_bytes(
        b'{"schema":"x","schema":"x","release_authorized":false}\n'
    )
    with pytest.raises(signer.SignedCustodyError, match="duplicate"):
        _run(folder, keys)
    assert calls == []


def test_manifest_extra_whitespace_is_not_accepted_as_canonical(
        tmp_path, monkeypatch):
    folder, keys, private, calls = _fixture(tmp_path, monkeypatch)
    path = folder / signer.MANIFEST
    path.write_bytes(json.dumps(_claim(), indent=2).encode() + b"\n")
    with pytest.raises(signer.SignedCustodyError):
        _run(folder, keys)
    assert calls == []


def test_non_authoritative_signed_claim_is_denied_if_real_bytes_differ(
        tmp_path, monkeypatch):
    folder, keys, private, calls = _fixture(tmp_path, monkeypatch)
    def changed(*args, **kw):
        wrong = _v2()
        wrong["aggregate_evidence_sha256"] = "d" * 64
        return wrong
    monkeypatch.setattr(signer.three,
                        "inspect_offline_three_store_evidence", changed)
    with pytest.raises(signer.SignedCustodyError, match="disagrees"):
        _run(folder, keys)


def test_post_signature_source_drift_fails_even_with_valid_signatures(
        tmp_path, monkeypatch):
    folder, keys, private, calls = _fixture(tmp_path, monkeypatch)
    steps = 0
    def drift(*args, **kw):
        nonlocal steps
        steps += 1
        result = _v2()
        if steps == 2:
            result["aggregate_evidence_sha256"] = "d" * 64
        return result
    monkeypatch.setattr(signer.three,
                        "inspect_offline_three_store_evidence", drift)
    with pytest.raises(signer.SignedCustodyError, match="drifted"):
        _run(folder, keys)
    assert steps == 2


@pytest.mark.parametrize("bad", [
    {"schema": "other"}, {"status": "recovered"},
    {"release_authorized": True},
    {"mongo_majority_journal_durability_qualified": True},
    {"source_writer_quiescence_verified": True},
    {"mongo_wiredtiger_catalog_file_custody_verified": False},
    {"sqlite_databases_checked": "yes"},
    {"chroma_persistent_segment_files_hashed": -1},
    {"new_private_secret": "token"},
])
def test_forged_v2_physical_receipt_denied_before_openssl(
        tmp_path, monkeypatch, bad):
    folder, keys, private, calls = _fixture(tmp_path, monkeypatch)
    def falsified(*args, **kw):
        return {**_v2(), **bad}
    monkeypatch.setattr(signer.three,
                        "inspect_offline_three_store_evidence", falsified)
    with pytest.raises(signer.SignedCustodyError):
        _run(folder, keys)


def test_bad_cold_receipt_denied_before_keys_or_physical_data(
        tmp_path, monkeypatch):
    folder, keys, private, calls = _fixture(tmp_path, monkeypatch)
    with pytest.raises(signer.SignedCustodyError):
        _run(folder, keys, cold="notsha")
    assert calls == []


def test_only_exact_signed_bundle_three_files_admitted(
        tmp_path, monkeypatch):
    folder, keys, private, calls = _fixture(tmp_path, monkeypatch)
    extra = folder / "secret.pem"
    extra.write_text("untrusted", encoding="utf-8")
    extra.chmod(0o600)
    with pytest.raises(signer.SignedCustodyError, match="untrusted"):
        _run(folder, keys)
    assert calls == []


def test_credential_bearing_subprocess_error_is_never_exposed(
        tmp_path, monkeypatch):
    folder, keys, private, calls = _fixture(tmp_path, monkeypatch)
    def failure(*args, **kwargs):
        raise OSError("mongodb://administrator:PRIVATESECRET@local")
    monkeypatch.setattr(signer.subprocess, "run", failure)
    with pytest.raises(signer.SignedCustodyError) as error:
        _run(folder, keys)
    assert "PRIVATESECRET" not in str(error.value)


def test_canonical_offline_operator_uses_two_external_signers_no_docker(
        tmp_path, monkeypatch, capsys):
    from scripts import local_ai_docker as operator
    folder, keys, _, calls = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(operator, "_run", lambda *a, **kw:
                        pytest.fail("signed offline custody reached Docker"))
    original = tmp_path / "offline-original"
    restored = tmp_path / "offline-restored"
    argv = [
        "--mode", "cpu", "verify-signed-offline-custody",
        "--claims-directory", str(folder),
        "--operator-public-key", str(keys["operator"]),
        "--auditor-public-key", str(keys["auditor"]),
        "--source", str(original),
        "--destination", str(restored),
        "--expected-source-head-sha", SOURCE_HEAD,
        "--expected-receipt-sha256", COLD_SHA,
        "--expected-operator-public-key-sha256",
        hashlib.sha256(keys["operator"].read_bytes()).hexdigest(),
        "--expected-auditor-public-key-sha256",
        hashlib.sha256(keys["auditor"].read_bytes()).hexdigest(),
    ]
    assert operator.main(argv) == 0
    out, err = capsys.readouterr()
    assert err == ""
    result = json.loads(out)
    assert result["schema"] == signer.RESULT_SCHEMA
    assert result["openssl_ed25519_signatures_verified"] is True
    assert result["release_authorized"] is False
    assert result["application_restore_qualified"] is False
    assert len(calls) == 2
    assert calls[0] == (original, restored, COLD_SHA)
    assert out.count("PRIVATE KEY") == 0
    assert str(folder) not in out


def test_substituted_cryptographically_valid_public_key_denied_by_prior_pin(
        tmp_path, monkeypatch):
    folder, keys, private, calls = _fixture(tmp_path, monkeypatch)
    original_pin = hashlib.sha256(keys["operator"].read_bytes()).hexdigest()
    # Both key files are otherwise valid PEMs. Without independent pins,
    # a replacement key plus replacement signature could be accepted.
    keys["operator"].write_bytes(keys["auditor"].read_bytes())
    with pytest.raises(signer.SignedCustodyError, match="fingerprint"):
        _run(folder, keys, operator_pin=original_pin)
    assert calls == []


def test_independently_pinned_fingerprint_mismatch_denied_before_file_scan(
        tmp_path, monkeypatch):
    folder, keys, private, calls = _fixture(tmp_path, monkeypatch)
    with pytest.raises(signer.SignedCustodyError, match="fingerprint"):
        _run(folder, keys, auditor_pin="d" * 64)
    assert calls == []


def test_identical_out_of_band_pin_values_refuse_two_authority_claim(
        tmp_path, monkeypatch):
    folder, keys, private, calls = _fixture(tmp_path, monkeypatch)
    same_pin = hashlib.sha256(keys["operator"].read_bytes()).hexdigest()
    with pytest.raises(signer.SignedCustodyError, match="identical pinned"):
        _run(folder, keys, operator_pin=same_pin, auditor_pin=same_pin)
    assert calls == []


def test_malformed_independent_pin_does_not_read_signatures_or_archive(
        tmp_path, monkeypatch):
    folder, keys, private, calls = _fixture(tmp_path, monkeypatch)
    with pytest.raises(signer.SignedCustodyError, match="digest"):
        _run(folder, keys, operator_pin="not-sha256")
    assert calls == []
