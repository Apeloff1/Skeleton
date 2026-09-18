"""Canonical release-ready evidence manifest and fail-closed provenance gate.

This module links a source Git object, build inputs, artifacts, digests,
SBOM/provenance records, test/eval evidence, and large-artifact locators into
one deterministic document. Generated binaries are never inlined or stored in
Git; they are referenced by SHA-256 plus an artifact/LFS/external locator.

The SCHEMA_VERSION 1 document emitted by ``scripts/release_provenance.py``
remains the build-metadata contract. This module consumes that document and
produces a separate release-ready evidence document. Callers of provenance
schema 1 are unchanged.

Asset provenance follows the #946 / ``skeleton.assets.manifest`` contract when
that package is importable, and a structural subset of the same rules otherwise.
This file does not generate assets, publish releases, or relocate Godot binaries.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from skeleton.kernel.errors import KernelError

SCHEMA_ID = "skeleton.release.evidence"
SCHEMA_VERSION = 1
PROVENANCE_V1_SCHEMA_VERSION = 1
ASSET_MANIFEST_SCHEMA_ID = "skeleton.assets.manifest"

# Match docs/ARTIFACT_POLICY.md without rewriting that policy surface.
REGULAR_GIT_MAX_BYTES = 10 * 1024 * 1024
GENERATED_PACKAGE_SUFFIXES = (
    ".apk",
    ".aab",
    ".ipa",
    ".whl",
    ".zip",
    ".7z",
    ".tar",
    ".tgz",
    ".tar.gz",
)

LOCATOR_KINDS = frozenset({"git-lfs", "release-store", "external"})
UPLOAD_COMPLETE = "complete"
LICENSE_STATUSES = frozenset({"spdx", "owner-controlled", "unknown"})

_COMMIT_RE = re.compile(r"^[0-9a-f]{40,64}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_SPDX_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]*$")

_EVIDENCE_KEYS = (
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
)
_SOURCE_KEYS = ("commit", "source_date_epoch")
_FILE_KEYS = ("name", "sha256", "size")
_LOCATOR_KEYS = ("kind", "uri")
_UPLOAD_KEYS = ("status", "bytes_transferred", "sha256")
_ARTIFACT_KEYS = ("artifact_id", "name", "sha256", "size", "locator", "upload")
_OPTIONAL_ARTIFACT_KEYS = frozenset({"asset_id"})
_SBOM_KEYS = ("name", "sha256", "size", "locator")
_PROVENANCE_KEYS = ("schema_version", "digest", "source_commit")
_TEST_KEYS = ("evidence_id", "name", "sha256", "result")
_INLINE_FORBIDDEN = frozenset({"bytes", "payload", "blob", "base64", "inline"})
_INLINE_IF_NOT_OBJECT = frozenset({"content", "data"})
_TIME_KEYS = frozenset(
    {
        "timestamp",
        "created_at",
        "updated_at",
        "uploaded_at",
        "mtime",
        "ctime",
        "date",
        "datetime",
        "built_at",
        "published_at",
    }
)

_PASS_RESULTS = frozenset({"pass", "passed", "ok"})


class ReleaseEvidenceError(KernelError):
    code = "RELEASE.EVIDENCE"
    http_status = 422


class EvidenceSchemaError(ReleaseEvidenceError):
    code = "RELEASE.EVIDENCE_SCHEMA"
    http_status = 422


class DigestMismatchError(ReleaseEvidenceError):
    code = "RELEASE.DIGEST_MISMATCH"
    http_status = 409


class DuplicateArtifactError(ReleaseEvidenceError):
    code = "RELEASE.DUPLICATE_ARTIFACT"
    http_status = 409


@dataclass(frozen=True, slots=True)
class ArtifactLocator:
    kind: str
    uri: str

    def to_payload(self) -> dict[str, str]:
        return {"kind": self.kind, "uri": self.uri}


@dataclass(frozen=True, slots=True)
class UploadMetadata:
    status: str
    bytes_transferred: int
    sha256: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "bytes_transferred": self.bytes_transferred,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class FileRef:
    name: str
    sha256: str
    size: int

    def to_payload(self) -> dict[str, Any]:
        return {"name": self.name, "sha256": self.sha256, "size": self.size}


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    artifact_id: str
    name: str
    sha256: str
    size: int
    locator: ArtifactLocator
    upload: UploadMetadata
    asset_id: str = ""

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "artifact_id": self.artifact_id,
            "name": self.name,
            "sha256": self.sha256,
            "size": self.size,
            "locator": self.locator.to_payload(),
            "upload": self.upload.to_payload(),
        }
        if self.asset_id:
            payload["asset_id"] = self.asset_id
        return payload


@dataclass(frozen=True, slots=True)
class SbomRecord:
    name: str
    sha256: str
    size: int
    locator: ArtifactLocator

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "sha256": self.sha256,
            "size": self.size,
            "locator": self.locator.to_payload(),
        }


@dataclass(frozen=True, slots=True)
class ProvenanceRef:
    schema_version: int
    digest: str
    source_commit: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "digest": self.digest,
            "source_commit": self.source_commit,
        }


@dataclass(frozen=True, slots=True)
class TestEvidence:
    evidence_id: str
    name: str
    sha256: str
    result: str

    def to_payload(self) -> dict[str, str]:
        return {
            "evidence_id": self.evidence_id,
            "name": self.name,
            "sha256": self.sha256,
            "result": self.result,
        }


@dataclass(frozen=True, slots=True)
class ReleaseEvidence:
    source_commit: str
    source_date_epoch: int
    build_inputs: tuple[FileRef, ...]
    artifacts: tuple[ArtifactRecord, ...]
    sbom: SbomRecord | None
    provenance: ProvenanceRef | None
    asset_provenance: tuple[dict[str, Any], ...]
    test_evidence: tuple[TestEvidence, ...]
    eval_evidence: tuple[TestEvidence, ...]
    schema_version: int = SCHEMA_VERSION

    def to_payload(self) -> dict[str, Any]:
        artifacts = tuple(sorted(self.artifacts, key=lambda item: item.artifact_id))
        inputs = tuple(sorted(self.build_inputs, key=lambda item: item.name))
        tests = tuple(sorted(self.test_evidence, key=lambda item: item.evidence_id))
        evals = tuple(sorted(self.eval_evidence, key=lambda item: item.evidence_id))
        assets = _sorted_asset_records(self.asset_provenance)
        return {
            "schema_id": SCHEMA_ID,
            "schema_version": self.schema_version,
            "source": {
                "commit": self.source_commit,
                "source_date_epoch": self.source_date_epoch,
            },
            "build_inputs": [item.to_payload() for item in inputs],
            "artifacts": [item.to_payload() for item in artifacts],
            "sbom": None if self.sbom is None else self.sbom.to_payload(),
            "provenance": None if self.provenance is None else self.provenance.to_payload(),
            "asset_provenance": assets,
            "test_evidence": [item.to_payload() for item in tests],
            "eval_evidence": [item.to_payload() for item in evals],
        }


@dataclass(frozen=True, slots=True)
class GateResult:
    release_ready: bool
    reasons: tuple[str, ...]
    evidence_digest: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "release_ready": self.release_ready,
            "reasons": list(self.reasons),
            "evidence_digest": self.evidence_digest,
            "schema_id": SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
        }


def canonical_dumps(value: Any) -> str:
    """Return canonical JSON, failing closed on non-canonical input."""

    try:
        return json.dumps(
            _canonicalize(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise EvidenceSchemaError("value is not canonically serializable") from exc


def serialize_evidence(evidence: ReleaseEvidence) -> str:
    return canonical_dumps(evidence.to_payload())


def evidence_digest(evidence: ReleaseEvidence | Mapping[str, Any] | str) -> str:
    if isinstance(evidence, ReleaseEvidence):
        payload = serialize_evidence(evidence)
    elif isinstance(evidence, str):
        payload = evidence
    else:
        payload = canonical_dumps(dict(evidence))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    if not isinstance(data, (bytes, bytearray)):
        raise EvidenceSchemaError("digest binding requires bytes")
    return hashlib.sha256(bytes(data)).hexdigest()


def build_evidence(
    *,
    source_commit: str,
    source_date_epoch: int,
    build_inputs: Sequence[Mapping[str, Any] | FileRef] = (),
    artifacts: Sequence[Mapping[str, Any] | ArtifactRecord] = (),
    sbom: Mapping[str, Any] | SbomRecord | None,
    provenance: Mapping[str, Any] | ProvenanceRef | None,
    asset_provenance: Sequence[Mapping[str, Any]] = (),
    test_evidence: Sequence[Mapping[str, Any] | TestEvidence] = (),
    eval_evidence: Sequence[Mapping[str, Any] | TestEvidence] = (),
) -> ReleaseEvidence:
    """Construct a canonical evidence document from typed or mapping inputs."""

    return ReleaseEvidence(
        source_commit=_require_commit(source_commit),
        source_date_epoch=_require_epoch(source_date_epoch),
        build_inputs=tuple(_coerce_file_ref(item) for item in build_inputs),
        artifacts=tuple(_coerce_artifact(item) for item in artifacts),
        sbom=None if sbom is None else _coerce_sbom(sbom),
        provenance=None if provenance is None else _coerce_provenance(provenance),
        asset_provenance=tuple(dict(item) for item in asset_provenance),
        test_evidence=tuple(_coerce_test(item) for item in test_evidence),
        eval_evidence=tuple(_coerce_test(item) for item in eval_evidence),
    )


def parse_evidence(raw: bytes | str | Mapping[str, Any]) -> ReleaseEvidence:
    payload = _load_payload(raw)
    _require_mapping(payload, "evidence")
    version = payload.get("schema_version")
    schema_id = payload.get("schema_id")
    if schema_id != SCHEMA_ID:
        raise EvidenceSchemaError(
            "incompatible release evidence schema id",
            context={"schema_id": schema_id, "supported": SCHEMA_ID},
        )
    if isinstance(version, bool) or not isinstance(version, int) or version != SCHEMA_VERSION:
        raise EvidenceSchemaError(
            "incompatible release evidence schema",
            context={"schema_version": version, "supported": SCHEMA_VERSION},
        )
    unknown = set(payload) - set(_EVIDENCE_KEYS)
    if unknown:
        raise EvidenceSchemaError(
            "evidence document has unknown fields",
            context={"fields": sorted(unknown)},
        )
    missing = [key for key in _EVIDENCE_KEYS if key not in payload]
    if missing:
        raise EvidenceSchemaError(
            "evidence document is missing required fields",
            context={"fields": missing},
        )
    source = payload["source"]
    _require_mapping(source, "source")
    _require_exact_keys(source, _SOURCE_KEYS, "source")
    return build_evidence(
        source_commit=source["commit"],
        source_date_epoch=source["source_date_epoch"],
        build_inputs=_require_list(payload["build_inputs"], "build_inputs"),
        artifacts=_require_list(payload["artifacts"], "artifacts"),
        sbom=payload["sbom"],
        provenance=payload["provenance"],
        asset_provenance=_require_list(payload["asset_provenance"], "asset_provenance"),
        test_evidence=_require_list(payload["test_evidence"], "test_evidence"),
        eval_evidence=_require_list(payload["eval_evidence"], "eval_evidence"),
    )


def evaluate_release_ready(
    evidence: ReleaseEvidence | Mapping[str, Any] | str | bytes,
    *,
    expected_commit: str,
    observed_artifacts: Mapping[str, bytes] | None = None,
) -> GateResult:
    """Classify a bundle as release-ready. Incomplete evidence fails closed."""

    if isinstance(evidence, ReleaseEvidence):
        document = evidence
    else:
        document = parse_evidence(evidence)

    reasons: list[str] = []
    payload = document.to_payload()
    reasons.extend(_reasons_unreproducible_time(payload, document.source_date_epoch))
    reasons.extend(_reasons_inlined_content(payload))

    expected = _require_commit(expected_commit)
    if document.source_commit != expected:
        reasons.append(
            f"stale or mismatched source commit: evidence={document.source_commit} expected={expected}"
        )

    if document.sbom is None:
        reasons.append("missing required SBOM evidence")
    else:
        reasons.extend(_reasons_locator("sbom", document.sbom.locator, document.sbom.size, document.sbom.name))
        reasons.extend(_reasons_file_ref("sbom", document.sbom.name, document.sbom.sha256, document.sbom.size))

    if document.provenance is None:
        reasons.append("missing required provenance record")
    else:
        if document.provenance.schema_version != PROVENANCE_V1_SCHEMA_VERSION:
            reasons.append(
                "provenance schema_version must remain "
                f"{PROVENANCE_V1_SCHEMA_VERSION} for SCHEMA_VERSION 1 callers"
            )
        if not _SHA256_RE.fullmatch(document.provenance.digest or ""):
            reasons.append("provenance digest must be a SHA-256 hex digest")
        if document.provenance.source_commit != expected:
            reasons.append(
                "provenance source commit does not match expected release commit"
            )

    if not document.test_evidence:
        reasons.append("missing required test evidence")
    if not document.eval_evidence:
        reasons.append("missing required eval evidence")
    reasons.extend(_reasons_test_records("test_evidence", document.test_evidence, require_pass=True))
    reasons.extend(_reasons_test_records("eval_evidence", document.eval_evidence, require_pass=True))

    if not document.build_inputs:
        reasons.append("missing required build inputs")
    seen_inputs: set[str] = set()
    for item in document.build_inputs:
        reasons.extend(_reasons_file_ref("build_inputs", item.name, item.sha256, item.size))
        if item.name in seen_inputs:
            reasons.append(f"duplicate build input name: {item.name}")
        seen_inputs.add(item.name)

    if not document.artifacts:
        reasons.append("missing required artifacts")
    seen_ids: set[str] = set()
    asset_digests = _asset_digests(document.asset_provenance)
    for artifact in document.artifacts:
        if not isinstance(artifact.artifact_id, str):
            reasons.append("artifact id must be a string")
        elif artifact.artifact_id in seen_ids:
            reasons.append(f"duplicate artifact id: {artifact.artifact_id}")
        elif not _TOKEN_RE.fullmatch(artifact.artifact_id):
            reasons.append(f"artifact id is not a canonical token: {artifact.artifact_id}")
        if isinstance(artifact.artifact_id, str):
            seen_ids.add(artifact.artifact_id)
        reasons.extend(
            _reasons_file_ref("artifact", artifact.name, artifact.sha256, artifact.size)
        )
        reasons.extend(
            _reasons_locator("artifact", artifact.locator, artifact.size, artifact.name)
        )
        reasons.extend(_reasons_upload(artifact))
        if artifact.asset_id:
            asset_digest = asset_digests.get(artifact.asset_id)
            if asset_digest is None:
                reasons.append(
                    f"artifact {artifact.artifact_id} references missing asset provenance {artifact.asset_id}"
                )
            elif artifact.sha256 != asset_digest:
                reasons.append(
                    f"artifact {artifact.artifact_id} digest does not match asset provenance {artifact.asset_id}"
                )

    reasons.extend(_consume_asset_provenance(document.asset_provenance, expected_commit=expected))

    if observed_artifacts is not None:
        reasons.extend(_reasons_digest_binding(document.artifacts, observed_artifacts))

    unique_reasons = tuple(dict.fromkeys(reasons))
    digest = evidence_digest(document)
    return GateResult(
        release_ready=not unique_reasons,
        reasons=unique_reasons,
        evidence_digest=digest,
    )


def require_release_ready(
    evidence: ReleaseEvidence | Mapping[str, Any] | str | bytes,
    *,
    expected_commit: str,
    observed_artifacts: Mapping[str, bytes] | None = None,
) -> GateResult:
    result = evaluate_release_ready(
        evidence,
        expected_commit=expected_commit,
        observed_artifacts=observed_artifacts,
    )
    if not result.release_ready:
        context = {"reasons": list(result.reasons), "digest": result.evidence_digest}
        if any("duplicate artifact id" in reason for reason in result.reasons):
            raise DuplicateArtifactError(
                "release evidence is not release-ready",
                context=context,
            )
        if any("mismatched digest" in reason or "tampered" in reason for reason in result.reasons):
            raise DigestMismatchError(
                "release evidence is not release-ready",
                context=context,
            )
        raise ReleaseEvidenceError(
            "release evidence is not release-ready",
            context=context,
        )
    return result


def from_v1_provenance(
    provenance: Mapping[str, Any],
    *,
    test_evidence: Sequence[Mapping[str, Any] | TestEvidence] = (),
    eval_evidence: Sequence[Mapping[str, Any] | TestEvidence] = (),
    asset_provenance: Sequence[Mapping[str, Any]] = (),
    locators: Mapping[str, Mapping[str, Any] | ArtifactLocator] | None = None,
    uploads: Mapping[str, Mapping[str, Any] | UploadMetadata] | None = None,
) -> ReleaseEvidence:
    """Adapt a SCHEMA_VERSION 1 provenance document into release evidence.

    The v1 document is left untouched. Missing locators default to the
    release-store lane so generated packages never enter Git history.
    """

    _require_mapping(provenance, "provenance")
    version = provenance.get("schema_version")
    if version != PROVENANCE_V1_SCHEMA_VERSION:
        raise EvidenceSchemaError(
            "v1 provenance adapter requires schema_version 1",
            context={"schema_version": version},
        )
    source = provenance.get("source")
    _require_mapping(source, "source")
    commit = _require_commit(source.get("commit"))
    epoch = _require_epoch(source.get("source_date_epoch"))

    raw_artifacts = _require_list(provenance.get("artifacts"), "artifacts")
    artifacts: list[ArtifactRecord] = []
    for item in raw_artifacts:
        _require_mapping(item, "artifact")
        name = _require_name(item.get("name"))
        digest = _require_digest(item.get("sha256"))
        size = _require_size(item.get("size"))
        artifact_id = str(item.get("artifact_id") or name)
        locator = _resolve_locator(artifact_id, name, locators)
        upload = _resolve_upload(artifact_id, digest, size, uploads)
        artifacts.append(
            ArtifactRecord(
                artifact_id=artifact_id,
                name=name,
                sha256=digest,
                size=size,
                locator=locator,
                upload=upload,
                asset_id=str(item.get("asset_id") or ""),
            )
        )

    sbom_refs = _require_list(provenance.get("sbom_refs"), "sbom_refs")
    sbom = None
    if sbom_refs:
        first = sbom_refs[0]
        _require_mapping(first, "sbom_refs[0]")
        sbom_name = _require_name(first.get("name"))
        sbom = SbomRecord(
            name=sbom_name,
            sha256=_require_digest(first.get("sha256")),
            size=_require_size(first.get("size")),
            locator=_resolve_locator(sbom_name, sbom_name, locators),
        )

    inputs = []
    for item in _require_list(provenance.get("inputs"), "inputs"):
        _require_mapping(item, "input")
        inputs.append(
            FileRef(
                name=_require_name(item.get("name")),
                sha256=_require_digest(item.get("sha256")),
                size=_require_size(item.get("size")),
            )
        )

    canonical_v1 = canonical_dumps(_v1_canonical_subset(provenance))
    provenance_ref = ProvenanceRef(
        schema_version=PROVENANCE_V1_SCHEMA_VERSION,
        digest=hashlib.sha256(canonical_v1.encode("utf-8")).hexdigest(),
        source_commit=commit,
    )
    return build_evidence(
        source_commit=commit,
        source_date_epoch=epoch,
        build_inputs=inputs,
        artifacts=artifacts,
        sbom=sbom,
        provenance=provenance_ref,
        asset_provenance=asset_provenance,
        test_evidence=test_evidence,
        eval_evidence=eval_evidence,
    )


def _v1_canonical_subset(provenance: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("schema_version", "source", "toolchain", "inputs", "sbom_refs", "artifacts")
    return {key: provenance.get(key) for key in keys}


def _resolve_locator(
    artifact_id: str,
    name: str,
    locators: Mapping[str, Mapping[str, Any] | ArtifactLocator] | None,
) -> ArtifactLocator:
    if locators and artifact_id in locators:
        return _coerce_locator(locators[artifact_id])
    if locators and name in locators:
        return _coerce_locator(locators[name])
    return ArtifactLocator(kind="release-store", uri=f"artifact://release/{name}")


def _resolve_upload(
    artifact_id: str,
    digest: str,
    size: int,
    uploads: Mapping[str, Mapping[str, Any] | UploadMetadata] | None,
) -> UploadMetadata:
    if uploads and artifact_id in uploads:
        return _coerce_upload(uploads[artifact_id])
    return UploadMetadata(status=UPLOAD_COMPLETE, bytes_transferred=size, sha256=digest)


def _reasons_digest_binding(
    artifacts: Sequence[ArtifactRecord],
    observed: Mapping[str, bytes],
) -> list[str]:
    reasons: list[str] = []
    declared = {item.artifact_id: item for item in artifacts}
    extra = sorted(set(observed) - set(declared))
    for artifact_id in extra:
        reasons.append(f"undeclared observed artifact id: {artifact_id}")
    for artifact in artifacts:
        data = observed.get(artifact.artifact_id)
        if data is None:
            reasons.append(f"missing observed bytes for artifact {artifact.artifact_id}")
            continue
        actual = sha256_bytes(data)
        if actual != artifact.sha256:
            reasons.append(
                f"tampered or mismatched digest for {artifact.artifact_id}: "
                f"declared={artifact.sha256} observed={actual}"
            )
        if len(data) != artifact.size:
            reasons.append(
                f"size mismatch for {artifact.artifact_id}: "
                f"declared={artifact.size} observed={len(data)}"
            )
    return reasons


def _reasons_upload(artifact: ArtifactRecord) -> list[str]:
    upload = artifact.upload
    reasons: list[str] = []
    if upload.status != UPLOAD_COMPLETE:
        reasons.append(
            f"partial upload metadata for {artifact.artifact_id}: status={upload.status!r}"
        )
    if upload.bytes_transferred != artifact.size:
        reasons.append(
            f"partial upload metadata for {artifact.artifact_id}: "
            f"bytes_transferred={upload.bytes_transferred} size={artifact.size}"
        )
    if upload.sha256 != artifact.sha256:
        reasons.append(
            f"upload digest does not bind artifact {artifact.artifact_id}"
        )
    return reasons


def _reasons_locator(label: str, locator: ArtifactLocator, size: int, name: str) -> list[str]:
    reasons: list[str] = []
    if locator.kind not in LOCATOR_KINDS:
        reasons.append(f"{label} locator kind must be one of {sorted(LOCATOR_KINDS)}")
    if not isinstance(locator.uri, str) or not locator.uri.strip():
        reasons.append(f"{label} locator uri must be a non-empty reference")
    if locator.kind == "git" or locator.uri.startswith("git://") or locator.uri.startswith("git+"):
        reasons.append(f"{label} must not use normal Git history as an artifact store")
    generated = _is_generated_package(name)
    if generated and locator.kind != "release-store":
        reasons.append(
            f"{label} generated package {name} must use a release-store locator, not {locator.kind}"
        )
    if size > REGULAR_GIT_MAX_BYTES and locator.kind not in {"git-lfs", "release-store", "external"}:
        reasons.append(f"{label} large file must use artifact/LFS/external locator")
    if "github.com" in locator.uri and "/blob/" in locator.uri:
        reasons.append(f"{label} must not point at a Git blob URL")
    return reasons


def _reasons_file_ref(label: str, name: str, digest: str, size: int) -> list[str]:
    reasons: list[str] = []
    name_error = _canonical_name_error(name)
    if name_error is not None:
        reasons.append(f"{label} name {name_error}")
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        reasons.append(f"{label} digest must be a lowercase SHA-256")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        reasons.append(f"{label} size must be a non-negative integer")
    return reasons


def _reasons_test_records(
    label: str,
    records: Sequence[TestEvidence],
    *,
    require_pass: bool,
) -> list[str]:
    reasons: list[str] = []
    seen: set[str] = set()
    for item in records:
        evidence_id = item.evidence_id
        if not isinstance(evidence_id, str):
            reasons.append(f"{label} id must be a string")
        else:
            if evidence_id in seen:
                reasons.append(f"duplicate {label} id: {evidence_id}")
            seen.add(evidence_id)
            if not _TOKEN_RE.fullmatch(evidence_id):
                reasons.append(f"{label} id is not a canonical token: {evidence_id}")
        name_error = _canonical_name_error(item.name)
        if name_error is not None:
            reasons.append(f"{label} {evidence_id} name {name_error}")
        if not isinstance(item.sha256, str) or not _SHA256_RE.fullmatch(item.sha256):
            reasons.append(f"{label} {evidence_id} digest must be a lowercase SHA-256")
        if not isinstance(item.result, str) or (
            require_pass and item.result not in _PASS_RESULTS
        ):
            reasons.append(f"{label} {evidence_id} result is not passing")
    return reasons


def _reasons_inlined_content(value: Any, *, path: str = "evidence") -> list[str]:
    reasons: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if key in _INLINE_FORBIDDEN or (
                key in _INLINE_IF_NOT_OBJECT and not isinstance(nested, Mapping)
            ):
                reasons.append(f"{path}.{key} inlines artifact bytes; use digest + locator")
            reasons.extend(_reasons_inlined_content(nested, path=f"{path}.{key}"))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            reasons.extend(_reasons_inlined_content(nested, path=f"{path}[{index}]"))
    elif isinstance(value, (bytes, bytearray)):
        reasons.append(f"{path} inlines artifact bytes; use digest + locator")
    return reasons


def _reasons_unreproducible_time(value: Any, epoch: int, *, path: str = "evidence") -> list[str]:
    reasons: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if key == "source_date_epoch":
                if nested != epoch:
                    reasons.append(f"{path}.{key} does not match source_date_epoch")
            elif key in _TIME_KEYS:
                reasons.append(
                    f"{path}.{key} is an unreproducible timestamp; bind SOURCE_DATE_EPOCH only"
                )
            reasons.extend(_reasons_unreproducible_time(nested, epoch, path=f"{path}.{key}"))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            reasons.extend(
                _reasons_unreproducible_time(nested, epoch, path=f"{path}[{index}]")
            )
    return reasons


def _consume_asset_provenance(
    records: Sequence[Mapping[str, Any]],
    *,
    expected_commit: str,
) -> list[str]:
    if not records:
        return []
    reasons = _structural_asset_provenance(records, expected_commit=expected_commit)
    validator = _asset_manifest_validator()
    full_records = [record for record in records if _is_full_asset_record(record)]
    if validator is not None and full_records and len(full_records) == len(records):
        try:
            validator(full_records)
        except Exception as exc:  # fail closed on any #946 rejection
            reasons.append(f"asset provenance rejected: {exc}")
    return reasons


def _is_full_asset_record(record: Any) -> bool:
    if not isinstance(record, Mapping):
        return False
    return {"identity", "content", "source", "license", "lineage", "targets", "fingerprint"} <= set(record)


def _structural_asset_provenance(
    records: Sequence[Mapping[str, Any]],
    *,
    expected_commit: str,
) -> list[str]:
    reasons: list[str] = []
    seen: set[str] = set()
    for index, record in enumerate(records):
        label = f"asset_provenance[{index}]"
        if not isinstance(record, Mapping):
            reasons.append(f"{label} must be an object")
            continue
        identity = record.get("identity") if isinstance(record.get("identity"), Mapping) else record
        content = record.get("content") if isinstance(record.get("content"), Mapping) else record
        source = record.get("source") if isinstance(record.get("source"), Mapping) else {}
        license_meta = record.get("license") if isinstance(record.get("license"), Mapping) else {}
        asset_id = identity.get("asset_id") if isinstance(identity, Mapping) else None
        if not isinstance(asset_id, str) or not _TOKEN_RE.fullmatch(asset_id):
            reasons.append(f"{label} asset_id must be a canonical token")
            continue
        if asset_id in seen:
            reasons.append(f"duplicate asset identity: {asset_id}")
        seen.add(asset_id)
        digest = content.get("sha256") if isinstance(content, Mapping) else None
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            reasons.append(f"{label} content digest must be a lowercase SHA-256")
        release_marked = bool(record.get("release_marked", False))
        origin = ""
        if isinstance(source, Mapping):
            origin = str(source.get("origin") or "")
            revision = str(source.get("revision") or "")
            if revision and _COMMIT_RE.fullmatch(revision) and revision != expected_commit:
                reasons.append(f"{label} asset revision does not match release commit")
        status = str(license_meta.get("status") or "unknown") if isinstance(license_meta, Mapping) else "unknown"
        spdx = str(license_meta.get("spdx") or "") if isinstance(license_meta, Mapping) else ""
        rights_holder = (
            str(license_meta.get("rights_holder") or "") if isinstance(license_meta, Mapping) else ""
        )
        if status not in LICENSE_STATUSES:
            reasons.append(f"{label} license status is not recognized")
        if release_marked:
            if not origin.strip():
                reasons.append(f"{label} release-marked asset is missing required source origin")
            if status == "unknown":
                reasons.append(f"{label} release-marked asset cannot have unknown licensing")
            if status == "spdx" and not _SPDX_RE.fullmatch(spdx):
                reasons.append(f"{label} release-marked asset is missing required SPDX identifier")
            if not rights_holder.strip():
                reasons.append(f"{label} release-marked asset is missing required rights holder")
        reasons.extend(_reasons_inlined_content(record, path=label))
    return reasons


def _asset_manifest_validator():
    try:
        from skeleton.assets.manifest import SCHEMA_VERSION as asset_schema
        from skeleton.assets.manifest import parse_manifest
    except ImportError:
        return None

    def _validate(records: Sequence[Mapping[str, Any]]) -> None:
        parse_manifest({"schema_version": asset_schema, "assets": list(records)})

    return _validate


def _asset_digests(records: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    digests: dict[str, str] = {}
    for record in records:
        if not isinstance(record, Mapping):
            continue
        identity = record.get("identity") if isinstance(record.get("identity"), Mapping) else record
        content = record.get("content") if isinstance(record.get("content"), Mapping) else record
        asset_id = identity.get("asset_id") if isinstance(identity, Mapping) else None
        digest = content.get("sha256") if isinstance(content, Mapping) else None
        if isinstance(asset_id, str) and isinstance(digest, str):
            digests[asset_id] = digest
    return digests


def _sorted_asset_records(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    def _key(record: Mapping[str, Any]) -> str:
        identity = record.get("identity") if isinstance(record.get("identity"), Mapping) else record
        asset_id = identity.get("asset_id") if isinstance(identity, Mapping) else ""
        return str(asset_id)

    ordered = sorted((dict(record) for record in records), key=_key)
    return [json.loads(canonical_dumps(item)) for item in ordered]


def _canonicalize(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite number")
        raise ValueError("floats are not canonical in release evidence")
    if isinstance(value, Mapping):
        canonical: dict[str, Any] = {}
        for key, nested in value.items():
            if not isinstance(key, str):
                raise TypeError("object keys must be strings")
            canonical[key] = _canonicalize(nested)
        return canonical
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    raise TypeError(f"unsupported type {type(value).__name__}")


def _load_payload(raw: bytes | str | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, (bytes, bytearray)):
        try:
            text = bytes(raw).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EvidenceSchemaError("evidence is not valid UTF-8") from exc
    elif isinstance(raw, str):
        text = raw
    else:
        raise EvidenceSchemaError("evidence must be bytes, text, or an object")
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EvidenceSchemaError("malformed evidence JSON") from exc
    if not isinstance(loaded, dict):
        raise EvidenceSchemaError("evidence must be an object")
    return loaded


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EvidenceSchemaError(f"{label} must be an object")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise EvidenceSchemaError(f"{label} must be a list")
    return value


def _require_exact_keys(payload: Mapping[str, Any], keys: Sequence[str], label: str) -> None:
    extra = set(payload) - set(keys)
    missing = [key for key in keys if key not in payload]
    if extra or missing:
        raise EvidenceSchemaError(
            f"{label} keys are not canonical",
            context={"missing": missing, "extra": sorted(extra)},
        )


def _require_commit(value: Any) -> str:
    if not isinstance(value, str) or not _COMMIT_RE.fullmatch(value):
        raise EvidenceSchemaError("source commit must be a 40-64 character lowercase Git object ID")
    if value != value.lower():
        raise EvidenceSchemaError("source commit must be lowercase")
    return value


def _require_epoch(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EvidenceSchemaError("source_date_epoch must be a non-negative integer")
    return value


def _require_digest(value: Any) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise EvidenceSchemaError("digest must be a lowercase SHA-256")
    return value


def _canonical_name_error(value: Any) -> str | None:
    if not isinstance(value, str) or not value or value != value.strip():
        return "must be a non-empty canonical path"
    if value.startswith("/") or "\\" in value:
        return "must be a repository-relative POSIX path"
    if any(ord(char) < 32 for char in value):
        return "must not contain control characters"
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return "must not contain empty, dot, or parent path segments"
    if re.fullmatch(r"[A-Za-z]:", parts[0]):
        return "must not contain a Windows drive prefix"
    return None


def _require_name(value: Any) -> str:
    error = _canonical_name_error(value)
    if error is not None:
        raise EvidenceSchemaError(f"name {error}")
    return value


def _require_size(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EvidenceSchemaError("size must be a non-negative integer")
    return value


def _coerce_locator(value: Mapping[str, Any] | ArtifactLocator) -> ArtifactLocator:
    if isinstance(value, ArtifactLocator):
        return value
    _require_mapping(value, "locator")
    _require_exact_keys(value, _LOCATOR_KEYS, "locator")
    kind = value["kind"]
    uri = value["uri"]
    if not isinstance(kind, str) or kind not in LOCATOR_KINDS:
        raise EvidenceSchemaError("locator.kind is not a supported artifact lane")
    if not isinstance(uri, str) or not uri.strip():
        raise EvidenceSchemaError("locator.uri must be a non-empty reference")
    return ArtifactLocator(kind=kind, uri=uri.strip())


def _coerce_upload(value: Mapping[str, Any] | UploadMetadata) -> UploadMetadata:
    if isinstance(value, UploadMetadata):
        return value
    _require_mapping(value, "upload")
    present = set(value)
    if present != set(_UPLOAD_KEYS):
        raise EvidenceSchemaError(
            "partial upload metadata",
            context={"expected": list(_UPLOAD_KEYS), "present": sorted(present)},
        )
    status = value["status"]
    transferred = value["bytes_transferred"]
    digest = value["sha256"]
    if not isinstance(status, str) or not status:
        raise EvidenceSchemaError("upload.status must be a non-empty string")
    return UploadMetadata(
        status=status,
        bytes_transferred=_require_size(transferred),
        sha256=_require_digest(digest),
    )


def _coerce_file_ref(value: Mapping[str, Any] | FileRef) -> FileRef:
    if isinstance(value, FileRef):
        return value
    _require_mapping(value, "file")
    _require_exact_keys(value, _FILE_KEYS, "file")
    return FileRef(
        name=_require_name(value["name"]),
        sha256=_require_digest(value["sha256"]),
        size=_require_size(value["size"]),
    )


def _coerce_artifact(value: Mapping[str, Any] | ArtifactRecord) -> ArtifactRecord:
    if isinstance(value, ArtifactRecord):
        return value
    _require_mapping(value, "artifact")
    extra = set(value) - set(_ARTIFACT_KEYS) - _OPTIONAL_ARTIFACT_KEYS
    missing = [key for key in _ARTIFACT_KEYS if key not in value]
    if extra or missing:
        raise EvidenceSchemaError(
            "artifact record is not canonical",
            context={"missing": missing, "extra": sorted(extra)},
        )
    artifact_id = value["artifact_id"]
    if not isinstance(artifact_id, str) or not artifact_id:
        raise EvidenceSchemaError("artifact_id must be a non-empty string")
    asset_id = value.get("asset_id") or ""
    if not isinstance(asset_id, str):
        raise EvidenceSchemaError("asset_id must be a string")
    return ArtifactRecord(
        artifact_id=artifact_id,
        name=_require_name(value["name"]),
        sha256=_require_digest(value["sha256"]),
        size=_require_size(value["size"]),
        locator=_coerce_locator(value["locator"]),
        upload=_coerce_upload(value["upload"]),
        asset_id=asset_id,
    )


def _coerce_sbom(value: Mapping[str, Any] | SbomRecord) -> SbomRecord:
    if isinstance(value, SbomRecord):
        return value
    _require_mapping(value, "sbom")
    _require_exact_keys(value, _SBOM_KEYS, "sbom")
    return SbomRecord(
        name=_require_name(value["name"]),
        sha256=_require_digest(value["sha256"]),
        size=_require_size(value["size"]),
        locator=_coerce_locator(value["locator"]),
    )


def _coerce_provenance(value: Mapping[str, Any] | ProvenanceRef) -> ProvenanceRef:
    if isinstance(value, ProvenanceRef):
        return value
    _require_mapping(value, "provenance")
    _require_exact_keys(value, _PROVENANCE_KEYS, "provenance")
    version = value["schema_version"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise EvidenceSchemaError("provenance.schema_version must be an integer")
    return ProvenanceRef(
        schema_version=version,
        digest=_require_digest(value["digest"]),
        source_commit=_require_commit(value["source_commit"]),
    )


def _coerce_test(value: Mapping[str, Any] | TestEvidence) -> TestEvidence:
    if isinstance(value, TestEvidence):
        return value
    _require_mapping(value, "test_evidence")
    _require_exact_keys(value, _TEST_KEYS, "test_evidence")
    result = value["result"]
    if not isinstance(result, str) or not result.strip():
        raise EvidenceSchemaError("test evidence result must be a non-empty string")
    evidence_id = value["evidence_id"]
    if not isinstance(evidence_id, str) or not evidence_id:
        raise EvidenceSchemaError("test evidence id must be a non-empty string")
    return TestEvidence(
        evidence_id=evidence_id,
        name=_require_name(value["name"]),
        sha256=_require_digest(value["sha256"]),
        result=result.strip(),
    )


def _is_generated_package(name: str) -> bool:
    lowered = name.lower()
    return any(lowered.endswith(suffix) for suffix in GENERATED_PACKAGE_SUFFIXES)
