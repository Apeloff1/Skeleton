"""Fail-closed tests for the release artifact-plane evidence gate.

Fixtures stay in memory. No binaries, credentials, or network.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from skeleton.release.evidence import (
    SCHEMA_ID,
    SCHEMA_VERSION,
    ArtifactLocator,
    ArtifactRecord,
    DigestMismatchError,
    DuplicateArtifactError,
    EvidenceSchemaError,
    ReleaseEvidenceError,
    UploadMetadata,
    build_evidence,
    canonical_dumps,
    evidence_digest,
    evaluate_release_ready,
    from_v1_provenance,
    parse_evidence,
    require_release_ready,
    serialize_evidence,
    sha256_bytes,
)

COMMIT = "0123456789abcdef0123456789abcdef01234567"
OTHER_COMMIT = "abcdef0123456789abcdef0123456789abcdef01"
EPOCH = 1_700_000_000
WHEEL = b"deterministic-wheel"
SBOM = b'{"bomFormat":"CycloneDX","specVersion":"1.6"}\n'
INPUT = b"build==1.3.0\n"
TEST_LOG = b"collected 4 items\n4 passed\n"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _locator(name: str, kind: str = "release-store") -> dict[str, str]:
    return {"kind": kind, "uri": f"artifact://release/{name}"}


def _upload(data: bytes, *, status: str = "complete", transferred: int | None = None) -> dict[str, object]:
    return {
        "status": status,
        "bytes_transferred": len(data) if transferred is None else transferred,
        "sha256": _sha(data),
    }


def _artifact(
    artifact_id: str,
    name: str,
    data: bytes,
    *,
    asset_id: str = "",
    locator: dict[str, str] | None = None,
    upload: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "artifact_id": artifact_id,
        "name": name,
        "sha256": _sha(data),
        "size": len(data),
        "locator": locator or _locator(name),
        "upload": upload or _upload(data),
    }
    if asset_id:
        payload["asset_id"] = asset_id
    return payload


def _sbom(data: bytes = SBOM) -> dict[str, object]:
    return {
        "name": "release-sbom.cdx.json",
        "sha256": _sha(data),
        "size": len(data),
        "locator": _locator("release-sbom.cdx.json"),
    }


def _provenance(commit: str = COMMIT) -> dict[str, object]:
    return {
        "schema_version": 1,
        "digest": _sha(b"v1-provenance"),
        "source_commit": commit,
    }


def _test(evidence_id: str = "unit", data: bytes = TEST_LOG, result: str = "pass") -> dict[str, str]:
    return {
        "evidence_id": evidence_id,
        "name": f"{evidence_id}.xml",
        "sha256": _sha(data),
        "result": result,
    }


def _asset(
    asset_id: str = "hero",
    *,
    release_marked: bool = True,
    origin: str = "https://example.invalid/assets/hero.png",
    revision: str = COMMIT,
    status: str = "spdx",
    spdx: str = "CC0-1.0",
    rights_holder: str = "Apeloff1",
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    record = {
        "identity": {"asset_id": asset_id, "kind": "image", "logical_name": asset_id},
        "content": {
            "sha256": _sha(asset_id.encode("utf-8")),
            "size_bytes": len(asset_id),
            "media_type": "image/png",
        },
        "source": {"origin": origin, "revision": revision, "path": f"{asset_id}.png"},
        "license": {
            "status": status,
            "spdx": spdx,
            "rights_holder": rights_holder,
            "attribution": rights_holder,
        },
        "release_marked": release_marked,
    }
    if extra:
        record.update(extra)
    return record


def valid_kwargs(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_commit": COMMIT,
        "source_date_epoch": EPOCH,
        "build_inputs": [{"name": "requirements-build.txt", "sha256": _sha(INPUT), "size": len(INPUT)}],
        "artifacts": [_artifact("wheel", "skeleton-16.0.0-py3-none-any.whl", WHEEL)],
        "sbom": _sbom(),
        "provenance": _provenance(),
        "asset_provenance": [_asset()],
        "test_evidence": [_test()],
        "eval_evidence": [_test("eval", b"eval-pass")],
    }
    payload.update(overrides)
    return payload


def valid_evidence(**overrides: object):
    return build_evidence(**valid_kwargs(**overrides))


def valid_observed() -> dict[str, bytes]:
    return {"wheel": WHEEL}


@pytest.mark.parametrize(
    "bad_name",
    [
        "../escape.whl",
        "/absolute.whl",
        "dist\\windows.whl",
        "dist//double.whl",
        "dist/./dot.whl",
        "C:/drive.whl",
    ],
)
def test_noncanonical_release_paths_fail_closed(bad_name: str) -> None:
    artifact = _artifact("wheel", "skeleton-16.0.0-py3-none-any.whl", WHEEL)
    artifact["name"] = bad_name
    with pytest.raises(EvidenceSchemaError, match="name"):
        build_evidence(**valid_kwargs(artifacts=[artifact]))


def test_non_string_artifact_and_evidence_ids_fail_closed() -> None:
    bad_artifact = _artifact("wheel", "skeleton-16.0.0-py3-none-any.whl", WHEEL)
    bad_artifact["artifact_id"] = 7
    with pytest.raises(EvidenceSchemaError, match="artifact_id"):
        build_evidence(**valid_kwargs(artifacts=[bad_artifact]))

    bad_test = _test()
    bad_test["evidence_id"] = 7
    with pytest.raises(EvidenceSchemaError, match="test evidence id"):
        build_evidence(**valid_kwargs(test_evidence=[bad_test]))


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("schema_version", 2, "incompatible release evidence schema"),
        ("source_date_epoch", -1, "source_date_epoch must be a non-negative integer"),
        ("source_date_epoch", True, "source_date_epoch must be a non-negative integer"),
    ],
)
def test_typed_release_evidence_root_metadata_fails_closed(
    field: str,
    value: object,
    reason: str,
) -> None:
    evidence = valid_evidence()
    object.__setattr__(evidence, field, value)
    result = evaluate_release_ready(
        evidence,
        expected_commit=COMMIT,
        observed_artifacts=valid_observed(),
    )
    assert result.release_ready is False
    assert any(reason in item for item in result.reasons)


def test_schema_version_is_stable_and_canonical() -> None:
    evidence = valid_evidence()
    payload = json.loads(serialize_evidence(evidence))
    assert SCHEMA_VERSION == 1
    assert payload["schema_id"] == SCHEMA_ID
    assert payload["schema_version"] == 1
    assert set(payload) == {
        "schema_id",
        "schema_version",
        "source",
        "build_inputs",
        "artifacts",
        "sbom",
        "provenance",
        "asset_provenance",
        "test_evidence",
        "eval_evidence",
    }
    restored = parse_evidence(serialize_evidence(evidence))
    assert serialize_evidence(restored) == serialize_evidence(evidence)


def test_complete_bundle_is_release_ready() -> None:
    evidence = valid_evidence()
    result = evaluate_release_ready(
        evidence,
        expected_commit=COMMIT,
        observed_artifacts=valid_observed(),
    )
    assert result.release_ready is True
    assert result.reasons == ()
    assert result.evidence_digest == evidence_digest(evidence)
    require_release_ready(evidence, expected_commit=COMMIT, observed_artifacts=valid_observed())


def test_missing_sbom_blocks_release_ready() -> None:
    result = evaluate_release_ready(
        valid_evidence(sbom=None),
        expected_commit=COMMIT,
        observed_artifacts=valid_observed(),
    )
    assert result.release_ready is False
    assert any("missing required SBOM" in reason for reason in result.reasons)


def test_missing_provenance_blocks_release_ready() -> None:
    result = evaluate_release_ready(
        valid_evidence(provenance=None),
        expected_commit=COMMIT,
        observed_artifacts=valid_observed(),
    )
    assert result.release_ready is False
    assert any("missing required provenance" in reason for reason in result.reasons)


def test_missing_test_evidence_blocks_release_ready() -> None:
    result = evaluate_release_ready(
        valid_evidence(test_evidence=[]),
        expected_commit=COMMIT,
        observed_artifacts=valid_observed(),
    )
    assert result.release_ready is False
    assert any("missing required test evidence" in reason for reason in result.reasons)


def test_missing_eval_evidence_blocks_release_ready() -> None:
    result = evaluate_release_ready(
        valid_evidence(eval_evidence=[]),
        expected_commit=COMMIT,
        observed_artifacts=valid_observed(),
    )
    assert result.release_ready is False
    assert "missing required eval evidence" in result.reasons


def test_tampered_digest_fails_closed() -> None:
    evidence = valid_evidence()
    result = evaluate_release_ready(
        evidence,
        expected_commit=COMMIT,
        observed_artifacts={"wheel": WHEEL + b"-tampered"},
    )
    assert result.release_ready is False
    assert any("tampered or mismatched digest" in reason for reason in result.reasons)
    with pytest.raises(DigestMismatchError):
        require_release_ready(
            evidence,
            expected_commit=COMMIT,
            observed_artifacts={"wheel": WHEEL + b"-tampered"},
        )


def test_wrong_commit_fails_closed() -> None:
    result = evaluate_release_ready(
        valid_evidence(),
        expected_commit=OTHER_COMMIT,
        observed_artifacts=valid_observed(),
    )
    assert result.release_ready is False
    assert any("mismatched source commit" in reason for reason in result.reasons)
    assert any("provenance source commit does not match" in reason for reason in result.reasons)


def test_stale_commit_evidence_rejected() -> None:
    evidence = valid_evidence(
        provenance=_provenance(OTHER_COMMIT),
        asset_provenance=[_asset(revision=OTHER_COMMIT)],
    )
    result = evaluate_release_ready(
        evidence,
        expected_commit=COMMIT,
        observed_artifacts=valid_observed(),
    )
    assert result.release_ready is False
    assert any("provenance source commit" in reason for reason in result.reasons)
    assert any("asset revision does not match" in reason for reason in result.reasons)


def test_duplicate_artifact_ids_fail_closed() -> None:
    duplicate = _artifact("wheel", "skeleton-16.0.0-py3-none-any.whl", WHEEL)
    extra = _artifact("wheel", "skeleton-16.0.0-extra.whl", b"other-wheel")
    result = evaluate_release_ready(
        valid_evidence(artifacts=[duplicate, extra]),
        expected_commit=COMMIT,
        observed_artifacts={"wheel": WHEEL},
    )
    assert result.release_ready is False
    assert any("duplicate artifact id: wheel" in reason for reason in result.reasons)
    with pytest.raises(DuplicateArtifactError):
        require_release_ready(
            valid_evidence(artifacts=[duplicate, extra]),
            expected_commit=COMMIT,
            observed_artifacts={"wheel": WHEEL},
        )


def test_partial_upload_metadata_fails_closed() -> None:
    pending = _artifact(
        "wheel",
        "skeleton-16.0.0-py3-none-any.whl",
        WHEEL,
        upload=_upload(WHEEL, status="pending"),
    )
    truncated = _artifact(
        "wheel",
        "skeleton-16.0.0-py3-none-any.whl",
        WHEEL,
        upload=_upload(WHEEL, transferred=1),
    )
    pending_result = evaluate_release_ready(
        valid_evidence(artifacts=[pending]),
        expected_commit=COMMIT,
        observed_artifacts=valid_observed(),
    )
    truncated_result = evaluate_release_ready(
        valid_evidence(artifacts=[truncated]),
        expected_commit=COMMIT,
        observed_artifacts=valid_observed(),
    )
    assert pending_result.release_ready is False
    assert truncated_result.release_ready is False
    assert any("partial upload metadata" in reason for reason in pending_result.reasons)
    assert any("bytes_transferred" in reason for reason in truncated_result.reasons)
    with pytest.raises(EvidenceSchemaError, match="partial upload metadata"):
        build_evidence(
            **valid_kwargs(
                artifacts=[
                    {
                        "artifact_id": "wheel",
                        "name": "skeleton-16.0.0-py3-none-any.whl",
                        "sha256": _sha(WHEEL),
                        "size": len(WHEEL),
                        "locator": _locator("skeleton-16.0.0-py3-none-any.whl"),
                        "upload": {"status": "complete"},
                    }
                ]
            )
        )


def test_reproducible_canonical_serialization() -> None:
    left = valid_evidence(
        artifacts=[
            _artifact("wheel", "skeleton-16.0.0-py3-none-any.whl", WHEEL),
            _artifact("sdist", "skeleton-16.0.0.tar.gz", b"sdist-bytes"),
        ],
        test_evidence=[_test("b"), _test("a")],
    )
    right = valid_evidence(
        artifacts=[
            _artifact("sdist", "skeleton-16.0.0.tar.gz", b"sdist-bytes"),
            _artifact("wheel", "skeleton-16.0.0-py3-none-any.whl", WHEEL),
        ],
        test_evidence=[_test("a"), _test("b")],
    )
    assert serialize_evidence(left) == serialize_evidence(right)
    assert evidence_digest(left) == evidence_digest(right)
    assert canonical_dumps({"b": 1, "a": {"y": 2, "x": 1}}) == '{"a":{"x":1,"y":2},"b":1}'
    with pytest.raises(EvidenceSchemaError):
        canonical_dumps({"x": float("nan")})
    with pytest.raises(EvidenceSchemaError):
        canonical_dumps({"x": 1.5})


def test_large_artifact_uses_locator_not_git_history() -> None:
    large_size = 11 * 1024 * 1024
    large = ArtifactRecord(
        artifact_id="weights",
        name="model.safetensors",
        sha256=_sha(b"weights"),
        size=large_size,
        locator=ArtifactLocator(kind="git-lfs", uri="lfs://models/model.safetensors"),
        upload=UploadMetadata(status="complete", bytes_transferred=large_size, sha256=_sha(b"weights")),
    )
    ready = evaluate_release_ready(
        valid_evidence(artifacts=[large], asset_provenance=[]),
        expected_commit=COMMIT,
    )
    assert ready.release_ready is True

    git_lane = ArtifactRecord(
        artifact_id="weights",
        name="model.safetensors",
        sha256=_sha(b"weights"),
        size=large_size,
        locator=ArtifactLocator(kind="git", uri="git://repo/model.safetensors"),
        upload=UploadMetadata(status="complete", bytes_transferred=large_size, sha256=_sha(b"weights")),
    )
    blocked = evaluate_release_ready(
        valid_evidence(artifacts=[git_lane], asset_provenance=[]),
        expected_commit=COMMIT,
    )
    assert blocked.release_ready is False
    assert any("must not use normal Git history" in reason for reason in blocked.reasons)


def test_artifact_asset_reference_binds_exact_provenance_digest() -> None:
    artifact = _artifact(
        "hero-artifact",
        "hero.png",
        b"different-bytes",
        asset_id="hero",
    )
    result = evaluate_release_ready(
        valid_evidence(artifacts=[artifact]),
        expected_commit=COMMIT,
        observed_artifacts={"hero-artifact": b"different-bytes"},
    )
    assert result.release_ready is False
    assert any(
        "digest does not match asset provenance hero" in reason
        for reason in result.reasons
    )


def test_generated_package_cannot_use_git_lfs_lane() -> None:
    wheel = _artifact(
        "wheel",
        "skeleton-16.0.0-py3-none-any.whl",
        WHEEL,
        locator={"kind": "git-lfs", "uri": "lfs://dist/wheel.whl"},
    )
    result = evaluate_release_ready(
        valid_evidence(artifacts=[wheel]),
        expected_commit=COMMIT,
        observed_artifacts=valid_observed(),
    )
    assert result.release_ready is False
    assert any("must use a release-store locator" in reason for reason in result.reasons)


def test_inlined_bytes_fail_closed() -> None:
    result = evaluate_release_ready(
        valid_evidence(asset_provenance=[_asset(extra={"bytes": "YmluYXJ5"})]),
        expected_commit=COMMIT,
        observed_artifacts=valid_observed(),
    )
    assert result.release_ready is False
    assert any("inlines artifact bytes" in reason for reason in result.reasons)


def test_unreproducible_timestamps_fail_closed() -> None:
    result = evaluate_release_ready(
        valid_evidence(
            asset_provenance=[_asset(extra={"created_at": "2026-09-17T10:00:00Z"})]
        ),
        expected_commit=COMMIT,
        observed_artifacts=valid_observed(),
    )
    assert result.release_ready is False
    assert any("unreproducible timestamp" in reason for reason in result.reasons)
    with pytest.raises(EvidenceSchemaError, match="source_date_epoch"):
        build_evidence(**valid_kwargs(source_date_epoch="1700000000"))


def test_unknown_schema_version_fails_closed() -> None:
    payload = json.loads(serialize_evidence(valid_evidence()))
    payload["schema_version"] = 99
    with pytest.raises(EvidenceSchemaError, match="incompatible release evidence schema"):
        parse_evidence(payload)
    payload["schema_version"] = 1
    payload["schema_id"] = "other.schema"
    with pytest.raises(EvidenceSchemaError, match="schema id"):
        parse_evidence(payload)


def test_digest_binds_exact_artifact_bytes() -> None:
    evidence = valid_evidence()
    assert sha256_bytes(WHEEL) == json.loads(serialize_evidence(evidence))["artifacts"][0]["sha256"]
    missing = evaluate_release_ready(
        evidence,
        expected_commit=COMMIT,
        observed_artifacts={},
    )
    assert missing.release_ready is False
    assert any("missing observed bytes" in reason for reason in missing.reasons)
    extra = evaluate_release_ready(
        evidence,
        expected_commit=COMMIT,
        observed_artifacts={"wheel": WHEEL, "ghost": b"nope"},
    )
    assert extra.release_ready is False
    assert any("undeclared observed artifact id: ghost" in reason for reason in extra.reasons)


def test_release_marked_asset_without_rights_fails_closed() -> None:
    result = evaluate_release_ready(
        valid_evidence(
            asset_provenance=[
                _asset(origin="", status="unknown", spdx="", rights_holder=""),
            ]
        ),
        expected_commit=COMMIT,
        observed_artifacts=valid_observed(),
    )
    assert result.release_ready is False
    joined = " ".join(result.reasons)
    assert "source origin" in joined
    assert "unknown licensing" in joined
    assert "rights holder" in joined


def test_failing_eval_evidence_is_not_release_ready() -> None:
    result = evaluate_release_ready(
        valid_evidence(eval_evidence=[_test("eval", result="fail")]),
        expected_commit=COMMIT,
        observed_artifacts=valid_observed(),
    )
    assert result.release_ready is False
    assert any("eval_evidence eval result is not passing" in reason for reason in result.reasons)


def test_from_v1_provenance_keeps_schema_version_1_callers() -> None:
    v1 = {
        "schema_version": 1,
        "source": {"commit": COMMIT, "source_date_epoch": EPOCH},
        "toolchain": {"python": "3.11.11"},
        "inputs": [{"name": "requirements-build.txt", "sha256": _sha(INPUT), "size": len(INPUT)}],
        "sbom_refs": [
            {
                "name": "release-sbom.cdx.json",
                "sha256": _sha(SBOM),
                "size": len(SBOM),
            }
        ],
        "artifacts": [
            {
                "name": "skeleton-16.0.0-py3-none-any.whl",
                "sha256": _sha(WHEEL),
                "size": len(WHEEL),
            }
        ],
    }
    missing_tests = from_v1_provenance(v1)
    blocked = evaluate_release_ready(
        missing_tests,
        expected_commit=COMMIT,
        observed_artifacts={"skeleton-16.0.0-py3-none-any.whl": WHEEL},
    )
    assert blocked.release_ready is False
    assert any("missing required test evidence" in reason for reason in blocked.reasons)

    tests_only = from_v1_provenance(v1, test_evidence=[_test()])
    tests_only_result = evaluate_release_ready(
        tests_only,
        expected_commit=COMMIT,
        observed_artifacts={"skeleton-16.0.0-py3-none-any.whl": WHEEL},
    )
    assert tests_only_result.release_ready is False
    assert "missing required eval evidence" in tests_only_result.reasons

    evidence = from_v1_provenance(
        v1,
        test_evidence=[_test()],
        eval_evidence=[_test("eval", b"eval-pass")],
    )
    payload = json.loads(serialize_evidence(evidence))
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["provenance"]["schema_version"] == 1
    assert v1["schema_version"] == 1
    result = evaluate_release_ready(
        evidence,
        expected_commit=COMMIT,
        observed_artifacts={"skeleton-16.0.0-py3-none-any.whl": WHEEL},
    )
    assert result.release_ready is True
    with pytest.raises(EvidenceSchemaError, match="schema_version 1"):
        from_v1_provenance({**v1, "schema_version": 2})


def test_require_release_ready_is_fail_closed() -> None:
    with pytest.raises(ReleaseEvidenceError):
        require_release_ready(valid_evidence(sbom=None), expected_commit=COMMIT)
