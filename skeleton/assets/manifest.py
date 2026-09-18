"""Deterministic asset manifest, provenance, and duplicate-detection core.

This module catalogs caller-supplied asset bytes and metadata. It does not
generate images, audio, or models, call providers, upload releases, or import
Godot assets. Identity is content-addressed. Provenance is an explicit
transformation chain. Duplicate and near-duplicate hooks are bounded and
purely local.

Canonical JSON (sorted keys, tight separators, finite numbers only) is the
only serialization. Unknown schema versions, digest drift, malformed lineage,
duplicate identities, and missing rights on release-marked assets fail closed.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from skeleton.kernel.errors import KernelError

SCHEMA_VERSION = 1
LEGACY_SCHEMA_VERSION = 0

MAX_ASSETS = 512
MAX_LINEAGE_STEPS = 32
MAX_TOKEN_CHARS = 64
MAX_STRING_CHARS = 256
MAX_URI_CHARS = 512
MAX_PARAMETERS = 16
MAX_LIST_ITEMS = 32
MAX_FINGERPRINT_BYTES = 65536
MAX_SHINGLE_WINDOW = 4
MAX_DEDUPE_COMPARISONS = 8192
MAX_NEAR_DUPLICATE_PAIRS = 64
DEFAULT_NEAR_DUPLICATE_THRESHOLD = 0.90625  # Hamming distance <= 6 on 64 bits

ASSET_KINDS = frozenset(
    {"image", "audio", "model", "texture", "animation", "shader", "font", "other"}
)
LICENSE_STATUSES = frozenset({"spdx", "owner-controlled", "unknown"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_SPDX_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]*$")
_HEX16_RE = re.compile(r"^[0-9a-f]{16}$")

_ASSET_KEYS = (
    "identity",
    "content",
    "source",
    "license",
    "lineage",
    "targets",
    "release_marked",
    "fingerprint",
)
_IDENTITY_KEYS = ("asset_id", "kind", "logical_name")
_CONTENT_KEYS = ("sha256", "size_bytes", "media_type", "canonical_identity")
_SOURCE_KEYS = ("origin", "revision", "path")
_LICENSE_KEYS = ("status", "spdx", "rights_holder", "attribution")
_STEP_KEYS = ("step", "operator", "input_digest", "output_digest", "parameters")
_TARGET_KEYS = ("engines", "formats", "max_bytes", "constraints")
_FINGERPRINT_KEYS = ("algorithm", "value")
_MANIFEST_KEYS = ("schema_version", "assets")


class AssetManifestError(KernelError):
    code = "ASSET.MANIFEST"
    http_status = 400


class SchemaCompatibilityError(AssetManifestError):
    code = "ASSET.SCHEMA_INCOMPATIBLE"
    http_status = 422


class DigestDriftError(AssetManifestError):
    code = "ASSET.DIGEST_DRIFT"
    http_status = 409


class LineageError(AssetManifestError):
    code = "ASSET.LINEAGE"
    http_status = 422


class DuplicateIdentityError(AssetManifestError):
    code = "ASSET.DUPLICATE_IDENTITY"
    http_status = 409


class AssetRightsError(AssetManifestError):
    code = "ASSET.RIGHTS"
    http_status = 422


class SerializationError(AssetManifestError):
    code = "ASSET.SERIALIZATION"
    http_status = 400


class DuplicateScanBoundError(AssetManifestError):
    code = "ASSET.DEDUPE_BOUND"
    http_status = 409


@dataclass(frozen=True, slots=True)
class LineageStep:
    step: int
    operator: str
    input_digest: str
    output_digest: str
    parameters: tuple[tuple[str, Any], ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "operator": self.operator,
            "input_digest": self.input_digest,
            "output_digest": self.output_digest,
            "parameters": {key: value for key, value in self.parameters},
        }


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    origin: str = ""
    revision: str = ""
    path: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {"origin": self.origin, "revision": self.revision, "path": self.path}


@dataclass(frozen=True, slots=True)
class LicenseMetadata:
    status: str = "unknown"
    spdx: str = ""
    rights_holder: str = ""
    attribution: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "spdx": self.spdx,
            "rights_holder": self.rights_holder,
            "attribution": self.attribution,
        }


@dataclass(frozen=True, slots=True)
class TargetConstraints:
    engines: tuple[str, ...] = ()
    formats: tuple[str, ...] = ()
    max_bytes: int | None = None
    constraints: tuple[tuple[str, Any], ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "engines": list(self.engines),
            "formats": list(self.formats),
            "max_bytes": self.max_bytes,
            "constraints": {key: value for key, value in self.constraints},
        }


@dataclass(frozen=True, slots=True)
class AssetIdentity:
    asset_id: str
    kind: str
    logical_name: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "kind": self.kind,
            "logical_name": self.logical_name,
        }


@dataclass(frozen=True, slots=True)
class ContentDescriptor:
    sha256: str
    size_bytes: int
    media_type: str
    canonical_identity: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "media_type": self.media_type,
            "canonical_identity": self.canonical_identity,
        }


@dataclass(frozen=True, slots=True)
class ContentFingerprint:
    algorithm: str
    value: str

    def to_payload(self) -> dict[str, Any]:
        return {"algorithm": self.algorithm, "value": self.value}


@dataclass(frozen=True, slots=True)
class AssetRecord:
    identity: AssetIdentity
    content: ContentDescriptor
    source: SourceMetadata
    license: LicenseMetadata
    lineage: tuple[LineageStep, ...]
    targets: TargetConstraints
    release_marked: bool
    fingerprint: ContentFingerprint

    def to_payload(self) -> dict[str, Any]:
        return {
            "identity": self.identity.to_payload(),
            "content": self.content.to_payload(),
            "source": self.source.to_payload(),
            "license": self.license.to_payload(),
            "lineage": [step.to_payload() for step in self.lineage],
            "targets": self.targets.to_payload(),
            "release_marked": self.release_marked,
            "fingerprint": self.fingerprint.to_payload(),
        }

    @classmethod
    def from_bytes(
        cls,
        *,
        asset_id: str,
        kind: str,
        data: bytes,
        logical_name: str = "",
        media_type: str = "",
        source: SourceMetadata | None = None,
        license: LicenseMetadata | None = None,
        lineage: Iterable[LineageStep] = (),
        targets: TargetConstraints | None = None,
        release_marked: bool = False,
    ) -> AssetRecord:
        if not isinstance(data, (bytes, bytearray)):
            raise SerializationError("asset bytes must be bytes")
        payload = bytes(data)
        digest = content_digest(payload)
        if not isinstance(release_marked, bool):
            raise SerializationError("release_marked must be a boolean")
        record = cls(
            identity=_build_identity(asset_id, kind, logical_name or asset_id),
            content=_build_content(kind, digest, len(payload), media_type),
            source=source or SourceMetadata(),
            license=license or LicenseMetadata(),
            lineage=_bounded_lineage_steps(lineage),
            targets=targets or TargetConstraints(),
            release_marked=release_marked,
            fingerprint=content_fingerprint(payload),
        )
        return validate_record(record, data=payload)


@dataclass(frozen=True, slots=True)
class DuplicateCluster:
    content_sha256: str
    asset_ids: tuple[str, ...]
    kind: str
    match: str


@dataclass(frozen=True, slots=True)
class NearDuplicatePair:
    left_asset_id: str
    right_asset_id: str
    kind: str
    similarity: float
    hamming_distance: int


@dataclass(frozen=True, slots=True)
class DuplicateReport:
    exact: tuple[DuplicateCluster, ...]
    near: tuple[NearDuplicatePair, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "exact": [
                {
                    "content_sha256": cluster.content_sha256,
                    "asset_ids": list(cluster.asset_ids),
                    "kind": cluster.kind,
                    "match": cluster.match,
                }
                for cluster in self.exact
            ],
            "near": [
                {
                    "left_asset_id": pair.left_asset_id,
                    "right_asset_id": pair.right_asset_id,
                    "kind": pair.kind,
                    "similarity": pair.similarity,
                    "hamming_distance": pair.hamming_distance,
                }
                for pair in self.near
            ],
        }


@dataclass(frozen=True, slots=True)
class AssetManifest:
    schema_version: int
    assets: tuple[AssetRecord, ...]

    def to_payload(self) -> dict[str, Any]:
        ordered = tuple(sorted(self.assets, key=lambda record: record.identity.asset_id))
        return {
            "schema_version": self.schema_version,
            "assets": [record.to_payload() for record in ordered],
        }

    def serialize(self) -> str:
        return canonical_dumps(self.to_payload())

    def digest(self) -> str:
        return _sha256(self.serialize())


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
        raise SerializationError("value is not canonically serializable") from exc


def content_digest(data: bytes) -> str:
    if not isinstance(data, (bytes, bytearray)):
        raise SerializationError("content digest requires bytes")
    return hashlib.sha256(bytes(data)).hexdigest()


def canonical_content_identity(*, kind: str, content_sha256: str) -> str:
    """Stable identity for bytes of a given kind, independent of path or name."""

    normalized_kind = _require_kind(kind)
    digest = _require_digest(content_sha256)
    return _sha256(
        canonical_dumps(
            {
                "algorithm": "sha256",
                "content_sha256": digest,
                "kind": normalized_kind,
            }
        )
    )


def content_fingerprint(data: bytes) -> ContentFingerprint:
    """Bounded 64-bit SimHash over a prefix of the supplied bytes."""

    if not isinstance(data, (bytes, bytearray)):
        raise SerializationError("fingerprint requires bytes")
    value = f"{_simhash64(bytes(data)):016x}"
    return ContentFingerprint(algorithm="simhash64", value=value)


def fingerprint_similarity(left: ContentFingerprint, right: ContentFingerprint) -> float:
    distance = fingerprint_hamming(left, right)
    return 1.0 - (distance / 64.0)


def fingerprint_hamming(left: ContentFingerprint, right: ContentFingerprint) -> int:
    if left.algorithm != right.algorithm:
        raise AssetManifestError(
            "fingerprint algorithms do not match",
            context={"left": left.algorithm, "right": right.algorithm},
        )
    if left.algorithm != "simhash64":
        raise AssetManifestError(
            "unsupported fingerprint algorithm",
            context={"algorithm": left.algorithm},
        )
    _require_fingerprint_value(left.value)
    _require_fingerprint_value(right.value)
    return (int(left.value, 16) ^ int(right.value, 16)).bit_count()


def parse_manifest(raw: bytes | str | Mapping[str, Any], *, data_by_id: Mapping[str, bytes] | None = None) -> AssetManifest:
    payload = _load_payload(raw)
    migrated = migrate_manifest(payload)
    _require_exact_keys(migrated, _MANIFEST_KEYS, "manifest")
    assets = migrated["assets"]
    if not isinstance(assets, list):
        raise SerializationError("assets must be a list")
    if len(assets) > MAX_ASSETS:
        raise AssetManifestError(
            "manifest exceeds asset bound",
            context={"max_assets": MAX_ASSETS, "count": len(assets)},
        )
    records = tuple(_parse_record(item) for item in assets)
    manifest = AssetManifest(schema_version=SCHEMA_VERSION, assets=records)
    return validate_manifest(manifest, data_by_id=data_by_id)


def migrate_manifest(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Upgrade a supported legacy document to schema version 1.

    Unknown future versions fail closed. Version 1 documents are normalized
    through the same parser used for new manifests.
    """

    if not isinstance(payload, Mapping):
        raise SerializationError("manifest must be an object")
    version = payload.get("schema_version", LEGACY_SCHEMA_VERSION)
    if isinstance(version, bool) or not isinstance(version, int):
        raise SchemaCompatibilityError(
            "schema_version must be an integer",
            context={"schema_version": version},
        )
    if version == SCHEMA_VERSION:
        return dict(payload)
    if version != LEGACY_SCHEMA_VERSION:
        raise SchemaCompatibilityError(
            "incompatible asset manifest schema",
            context={"schema_version": version, "supported": SCHEMA_VERSION},
        )
    assets = payload.get("assets", [])
    if not isinstance(assets, list):
        raise SerializationError("legacy assets must be a list")
    migrated = [_migrate_legacy_asset(item) for item in assets]
    return {"schema_version": SCHEMA_VERSION, "assets": migrated}


def validate_manifest(
    manifest: AssetManifest,
    *,
    data_by_id: Mapping[str, bytes] | None = None,
) -> AssetManifest:
    if manifest.schema_version != SCHEMA_VERSION:
        raise SchemaCompatibilityError(
            "incompatible asset manifest schema",
            context={"schema_version": manifest.schema_version, "supported": SCHEMA_VERSION},
        )
    if len(manifest.assets) > MAX_ASSETS:
        raise AssetManifestError(
            "manifest exceeds asset bound",
            context={"max_assets": MAX_ASSETS, "count": len(manifest.assets)},
        )
    seen: dict[str, str] = {}
    validated: list[AssetRecord] = []
    if data_by_id is not None:
        if not isinstance(data_by_id, Mapping):
            raise SerializationError("data_by_id must be a mapping")
        expected_ids = {record.identity.asset_id for record in manifest.assets}
        supplied_ids = set(data_by_id)
        missing_data = sorted(expected_ids - supplied_ids)
        extra_data = sorted(supplied_ids - expected_ids)
        if missing_data or extra_data:
            raise DigestDriftError(
                "asset byte verification set does not match manifest identities",
                context={"missing": missing_data, "extra": extra_data},
            )
    for record in manifest.assets:
        data = None if data_by_id is None else data_by_id[record.identity.asset_id]
        checked = validate_record(record, data=data)
        asset_id = checked.identity.asset_id
        if asset_id in seen:
            raise DuplicateIdentityError(
                "duplicate asset identity",
                context={"asset_id": asset_id},
            )
        seen[asset_id] = checked.content.canonical_identity
        validated.append(checked)
    return AssetManifest(schema_version=SCHEMA_VERSION, assets=tuple(validated))


def validate_record(record: AssetRecord, *, data: bytes | None = None) -> AssetRecord:
    identity = record.identity
    _require_kind(identity.kind)
    _bounded_token("asset_id", identity.asset_id)
    _bounded_string("logical_name", identity.logical_name, allow_empty=True)

    content = record.content
    digest = _require_digest(content.sha256)
    _require_int("size_bytes", content.size_bytes, minimum=0)
    _bounded_string("media_type", content.media_type, allow_empty=True)
    expected_identity = canonical_content_identity(
        kind=identity.kind,
        content_sha256=digest,
    )
    if content.canonical_identity != expected_identity:
        raise DigestDriftError(
            "canonical content identity does not match kind and digest",
            context={"asset_id": identity.asset_id},
        )
    if not isinstance(record.release_marked, bool):
        raise SerializationError("release_marked must be a boolean")
    if data is not None:
        verify_content(record, data)
    _validate_source(record.source)
    _validate_license(record.license)
    _validate_targets(record.targets, record.content.size_bytes)
    _validate_fingerprint(record.fingerprint)
    validate_lineage(record.lineage, record.content.sha256)
    if record.release_marked:
        _require_release_rights(record)
    return record


def verify_content(record: AssetRecord, data: bytes) -> None:
    actual = content_digest(data)
    if actual != record.content.sha256:
        raise DigestDriftError(
            "content digest drifted from declared sha256",
            context={
                "asset_id": record.identity.asset_id,
                "declared": record.content.sha256,
                "actual": actual,
            },
        )
    if len(data) != record.content.size_bytes:
        raise DigestDriftError(
            "content size drifted from declared size_bytes",
            context={
                "asset_id": record.identity.asset_id,
                "declared": record.content.size_bytes,
                "actual": len(data),
            },
        )
    expected_fingerprint = content_fingerprint(data)
    if record.fingerprint != expected_fingerprint:
        raise DigestDriftError(
            "content fingerprint drifted from declared simhash",
            context={"asset_id": record.identity.asset_id},
        )


def _bounded_lineage_steps(steps: Iterable[LineageStep]) -> tuple[LineageStep, ...]:
    if isinstance(steps, (str, bytes, bytearray)):
        raise LineageError("lineage must be an iterable of LineageStep values")
    bounded: list[LineageStep] = []
    try:
        iterator = iter(steps)
    except TypeError as exc:
        raise LineageError("lineage must be iterable") from exc
    for step in iterator:
        if len(bounded) >= MAX_LINEAGE_STEPS:
            raise LineageError(
                "lineage exceeds step bound",
                context={"max_steps": MAX_LINEAGE_STEPS},
            )
        if not isinstance(step, LineageStep):
            raise LineageError("lineage entries must be LineageStep values")
        bounded.append(step)
    return tuple(bounded)


def validate_lineage(steps: Sequence[LineageStep], content_sha256: str) -> None:
    if isinstance(steps, (str, bytes, bytearray)) or not isinstance(steps, Sequence):
        raise LineageError("lineage must be a sequence of LineageStep values")
    if any(not isinstance(step, LineageStep) for step in steps):
        raise LineageError("lineage entries must be LineageStep values")
    digest = _require_digest(content_sha256)
    if len(steps) > MAX_LINEAGE_STEPS:
        raise LineageError(
            "lineage exceeds step bound",
            context={"max_steps": MAX_LINEAGE_STEPS, "count": len(steps)},
        )
    if not steps:
        return
    previous_output: str | None = None
    seen_outputs: set[str] = set()
    for index, step in enumerate(steps):
        if step.step != index:
            raise LineageError(
                "lineage steps must be contiguous starting at 0",
                context={"expected": index, "actual": step.step},
            )
        operator = _bounded_token("operator", step.operator)
        output = _require_digest(step.output_digest)
        if step.input_digest:
            incoming = _require_digest(step.input_digest)
        else:
            if index != 0:
                raise LineageError(
                    "non-origin lineage step is missing input digest",
                    context={"step": index, "operator": operator},
                )
            incoming = ""
        if index == 0:
            previous_output = incoming or None
        elif incoming != previous_output:
            raise LineageError(
                "lineage input digest does not follow the previous output",
                context={"step": index, "operator": operator},
            )
        if output in seen_outputs:
            raise LineageError(
                "lineage output digest repeats an earlier step",
                context={"step": index, "output_digest": output},
            )
        seen_outputs.add(output)
        if incoming and incoming == output and step.parameters:
            # Identity transforms are allowed only as explicit no-ops without extra params.
            raise LineageError(
                "identity transform cannot carry parameters",
                context={"step": index, "operator": operator},
            )
        _frozen_parameters(dict(step.parameters))
        previous_output = output
    if previous_output != digest:
        raise LineageError(
            "lineage does not terminate at the content digest",
            context={"final_output": previous_output, "content_sha256": digest},
        )


def detect_duplicates(
    manifest: AssetManifest,
    *,
    near_threshold: float = DEFAULT_NEAR_DUPLICATE_THRESHOLD,
    near_limit: int = MAX_NEAR_DUPLICATE_PAIRS,
) -> DuplicateReport:
    """Return exact digest clusters and bounded near-duplicate pairs.

    Comparisons are deterministic: assets are ordered by asset_id, pairs are
    emitted in that order, and the scan fails closed if it would exceed the
    comparison bound rather than dropping candidates.
    """

    if near_threshold <= 0 or near_threshold > 1:
        raise AssetManifestError(
            "near-duplicate threshold must be in (0, 1]",
            context={"threshold": near_threshold},
        )
    limit = _require_int("near_limit", near_limit, minimum=1, maximum=MAX_NEAR_DUPLICATE_PAIRS)
    records = tuple(sorted(manifest.assets, key=lambda record: record.identity.asset_id))
    exact_groups: dict[tuple[str, str], list[str]] = {}
    for record in records:
        key = (record.identity.kind, record.content.sha256)
        exact_groups.setdefault(key, []).append(record.identity.asset_id)
    exact = tuple(
        DuplicateCluster(
            content_sha256=digest,
            asset_ids=tuple(asset_ids),
            kind=kind,
            match="content_sha256",
        )
        for (kind, digest), asset_ids in sorted(exact_groups.items())
        if len(asset_ids) > 1
    )

    by_kind: dict[str, list[AssetRecord]] = {}
    for record in records:
        by_kind.setdefault(record.identity.kind, []).append(record)
    comparisons = 0
    near: list[NearDuplicatePair] = []
    for kind in sorted(by_kind):
        group = by_kind[kind]
        count = len(group)
        needed = count * (count - 1) // 2
        if comparisons + needed > MAX_DEDUPE_COMPARISONS:
            raise DuplicateScanBoundError(
                "near-duplicate scan exceeds comparison bound",
                context={
                    "kind": kind,
                    "candidates": count,
                    "max_comparisons": MAX_DEDUPE_COMPARISONS,
                },
            )
        for left_index, left in enumerate(group):
            for right in group[left_index + 1 :]:
                comparisons += 1
                if left.content.sha256 == right.content.sha256:
                    continue
                distance = fingerprint_hamming(left.fingerprint, right.fingerprint)
                similarity = 1.0 - (distance / 64.0)
                if similarity + 1e-12 >= near_threshold:
                    near.append(
                        NearDuplicatePair(
                            left_asset_id=left.identity.asset_id,
                            right_asset_id=right.identity.asset_id,
                            kind=kind,
                            similarity=similarity,
                            hamming_distance=distance,
                        )
                    )
    near.sort(
        key=lambda pair: (
            pair.kind,
            pair.left_asset_id,
            pair.right_asset_id,
            -pair.similarity,
        )
    )
    return DuplicateReport(exact=exact, near=tuple(near[:limit]))


def _build_identity(asset_id: str, kind: str, logical_name: str) -> AssetIdentity:
    return AssetIdentity(
        asset_id=_bounded_token("asset_id", asset_id),
        kind=_require_kind(kind),
        logical_name=_bounded_string("logical_name", logical_name, allow_empty=True),
    )


def _build_content(kind: str, digest: str, size_bytes: int, media_type: str) -> ContentDescriptor:
    sha256 = _require_digest(digest)
    size = _require_int("size_bytes", size_bytes, minimum=0)
    return ContentDescriptor(
        sha256=sha256,
        size_bytes=size,
        media_type=_bounded_string("media_type", media_type, allow_empty=True),
        canonical_identity=canonical_content_identity(kind=kind, content_sha256=sha256),
    )


def _parse_record(raw: Any) -> AssetRecord:
    if not isinstance(raw, Mapping):
        raise SerializationError("asset record must be an object")
    _require_exact_keys(raw, _ASSET_KEYS, "asset")
    identity_raw = raw["identity"]
    content_raw = raw["content"]
    source_raw = raw["source"]
    license_raw = raw["license"]
    lineage_raw = raw["lineage"]
    targets_raw = raw["targets"]
    fingerprint_raw = raw["fingerprint"]
    if not isinstance(raw["release_marked"], bool):
        raise SerializationError("release_marked must be a boolean")
    if not isinstance(identity_raw, Mapping):
        raise SerializationError("identity must be an object")
    if not isinstance(content_raw, Mapping):
        raise SerializationError("content must be an object")
    if not isinstance(source_raw, Mapping):
        raise SerializationError("source must be an object")
    if not isinstance(license_raw, Mapping):
        raise SerializationError("license must be an object")
    if not isinstance(lineage_raw, list):
        raise SerializationError("lineage must be a list")
    if not isinstance(targets_raw, Mapping):
        raise SerializationError("targets must be an object")
    if not isinstance(fingerprint_raw, Mapping):
        raise SerializationError("fingerprint must be an object")
    _require_exact_keys(identity_raw, _IDENTITY_KEYS, "identity")
    _require_exact_keys(content_raw, _CONTENT_KEYS, "content")
    _require_exact_keys(source_raw, _SOURCE_KEYS, "source")
    _require_exact_keys(license_raw, _LICENSE_KEYS, "license")
    _require_exact_keys(targets_raw, _TARGET_KEYS, "targets")
    _require_exact_keys(fingerprint_raw, _FINGERPRINT_KEYS, "fingerprint")
    identity = _build_identity(
        identity_raw["asset_id"],
        identity_raw["kind"],
        identity_raw["logical_name"],
    )
    content = ContentDescriptor(
        sha256=_require_digest(content_raw["sha256"]),
        size_bytes=_require_int("size_bytes", content_raw["size_bytes"], minimum=0),
        media_type=_bounded_string("media_type", content_raw["media_type"], allow_empty=True),
        canonical_identity=_require_digest(content_raw["canonical_identity"]),
    )
    source = SourceMetadata(
        origin=_bounded_uri("origin", source_raw["origin"], allow_empty=True),
        revision=_bounded_string("revision", source_raw["revision"], allow_empty=True),
        path=_bounded_uri("path", source_raw["path"], allow_empty=True),
    )
    license_meta = LicenseMetadata(
        status=_require_license_status(license_raw["status"]),
        spdx=_bounded_spdx(license_raw["spdx"], allow_empty=True),
        rights_holder=_bounded_string(
            "rights_holder", license_raw["rights_holder"], allow_empty=True
        ),
        attribution=_bounded_string(
            "attribution", license_raw["attribution"], allow_empty=True
        ),
    )
    lineage = tuple(_parse_step(item) for item in lineage_raw)
    engines = _bounded_token_list("engines", targets_raw["engines"])
    formats = _bounded_token_list("formats", targets_raw["formats"])
    max_bytes = targets_raw["max_bytes"]
    if max_bytes is not None:
        max_bytes = _require_int("max_bytes", max_bytes, minimum=1)
    if not isinstance(targets_raw["constraints"], Mapping):
        raise SerializationError("target constraints must be an object")
    targets = TargetConstraints(
        engines=engines,
        formats=formats,
        max_bytes=max_bytes,
        constraints=_frozen_parameters(targets_raw["constraints"]),
    )
    fingerprint = ContentFingerprint(
        algorithm=_bounded_token("algorithm", fingerprint_raw["algorithm"]),
        value=_require_fingerprint_value(fingerprint_raw["value"]),
    )
    return AssetRecord(
        identity=identity,
        content=content,
        source=source,
        license=license_meta,
        lineage=lineage,
        targets=targets,
        release_marked=raw["release_marked"],
        fingerprint=fingerprint,
    )


def _parse_step(raw: Any) -> LineageStep:
    if not isinstance(raw, Mapping):
        raise LineageError("lineage step must be an object")
    _require_exact_keys(raw, _STEP_KEYS, "lineage step")
    if not isinstance(raw["parameters"], Mapping):
        raise LineageError("lineage parameters must be an object")
    input_digest = raw["input_digest"]
    if input_digest not in ("", None):
        incoming = _require_digest(input_digest)
    else:
        incoming = ""
    return LineageStep(
        step=_require_int("step", raw["step"], minimum=0, maximum=MAX_LINEAGE_STEPS - 1),
        operator=_bounded_token("operator", raw["operator"]),
        input_digest=incoming,
        output_digest=_require_digest(raw["output_digest"]),
        parameters=_frozen_parameters(raw["parameters"]),
    )


def _migrate_legacy_asset(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise SerializationError("legacy asset must be an object")
    asset_id = raw.get("id") or raw.get("asset_id")
    kind = raw.get("type") or raw.get("kind") or "other"
    logical_name = raw.get("name") or raw.get("logical_name") or asset_id or ""
    digest = raw.get("sha256") or raw.get("checksum") or raw.get("digest")
    size = raw.get("size") or raw.get("size_bytes") or 0
    media_type = raw.get("media_type") or ""
    origin = ""
    revision = ""
    path = ""
    source = raw.get("source")
    if isinstance(source, str):
        origin = source
    elif isinstance(source, Mapping):
        origin = str(source.get("origin") or source.get("uri") or "")
        revision = str(source.get("revision") or "")
        path = str(source.get("path") or "")
    license_raw = raw.get("license")
    status = "unknown"
    spdx = ""
    rights_holder = str(raw.get("rights_holder") or "")
    attribution = str(raw.get("attribution") or "")
    if isinstance(license_raw, str) and license_raw.strip():
        status = "spdx"
        spdx = license_raw.strip()
    elif isinstance(license_raw, Mapping):
        status = str(license_raw.get("status") or "unknown")
        spdx = str(license_raw.get("spdx") or "")
        rights_holder = str(license_raw.get("rights_holder") or rights_holder)
        attribution = str(license_raw.get("attribution") or attribution)
    fingerprint_raw = raw.get("fingerprint")
    if isinstance(fingerprint_raw, Mapping):
        algorithm = str(fingerprint_raw.get("algorithm") or "simhash64")
        value = str(fingerprint_raw.get("value") or "")
    else:
        algorithm = "simhash64"
        value = str(fingerprint_raw or "0" * 16)
    lineage_raw = raw.get("lineage") or []
    if not isinstance(lineage_raw, list):
        raise SerializationError("legacy lineage must be a list")
    lineage = []
    for index, item in enumerate(lineage_raw):
        if not isinstance(item, Mapping):
            raise SerializationError("legacy lineage step must be an object")
        lineage.append(
            {
                "step": item.get("step", index),
                "operator": item.get("operator") or item.get("op") or "unknown",
                "input_digest": item.get("input_digest") or item.get("input") or "",
                "output_digest": item.get("output_digest") or item.get("output") or "",
                "parameters": item.get("parameters") or {},
            }
        )
    targets_raw = raw.get("targets") if isinstance(raw.get("targets"), Mapping) else {}
    record = {
        "identity": {
            "asset_id": asset_id,
            "kind": kind,
            "logical_name": logical_name,
        },
        "content": {
            "sha256": digest,
            "size_bytes": size,
            "media_type": media_type,
            "canonical_identity": canonical_content_identity(
                kind=str(kind),
                content_sha256=str(digest),
            )
            if isinstance(digest, str) and _SHA256_RE.fullmatch(digest)
            else digest,
        },
        "source": {"origin": origin, "revision": revision, "path": path},
        "license": {
            "status": status,
            "spdx": spdx,
            "rights_holder": rights_holder,
            "attribution": attribution,
        },
        "lineage": lineage,
        "targets": {
            "engines": list(targets_raw.get("engines") or raw.get("engines") or []),
            "formats": list(targets_raw.get("formats") or raw.get("formats") or []),
            "max_bytes": targets_raw.get("max_bytes", raw.get("max_bytes")),
            "constraints": dict(targets_raw.get("constraints") or {}),
        },
        "release_marked": bool(raw.get("release_marked", False)),
        "fingerprint": {"algorithm": algorithm, "value": value},
    }
    return record


def _load_payload(raw: bytes | str | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, (bytes, bytearray)):
        try:
            text = bytes(raw).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SerializationError("manifest is not valid UTF-8") from exc
    elif isinstance(raw, str):
        text = raw
    else:
        raise SerializationError("manifest must be bytes, text, or an object")
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SerializationError("malformed manifest JSON") from exc
    if not isinstance(loaded, dict):
        raise SerializationError("manifest must be an object")
    return loaded


def _require_release_rights(record: AssetRecord) -> None:
    if not record.source.origin:
        raise AssetRightsError(
            "release-marked asset is missing required source origin",
            context={"asset_id": record.identity.asset_id},
        )
    license_meta = record.license
    if license_meta.status == "unknown":
        raise AssetRightsError(
            "release-marked asset cannot have unknown licensing",
            context={"asset_id": record.identity.asset_id},
        )
    if license_meta.status == "spdx" and not license_meta.spdx:
        raise AssetRightsError(
            "release-marked asset is missing required SPDX identifier",
            context={"asset_id": record.identity.asset_id},
        )
    if not license_meta.rights_holder:
        raise AssetRightsError(
            "release-marked asset is missing required rights holder",
            context={"asset_id": record.identity.asset_id},
        )


def _validate_source(source: SourceMetadata) -> None:
    _bounded_uri("origin", source.origin, allow_empty=True)
    _bounded_string("revision", source.revision, allow_empty=True)
    _bounded_uri("path", source.path, allow_empty=True)


def _validate_license(license_meta: LicenseMetadata) -> None:
    _require_license_status(license_meta.status)
    _bounded_spdx(license_meta.spdx, allow_empty=True)
    if license_meta.status == "spdx" and not license_meta.spdx:
        raise AssetRightsError("SPDX license status requires an SPDX identifier")
    if license_meta.status != "spdx" and license_meta.spdx:
        raise AssetRightsError(
            "SPDX identifier is only valid when license status is spdx",
            context={"status": license_meta.status},
        )
    _bounded_string("rights_holder", license_meta.rights_holder, allow_empty=True)
    _bounded_string("attribution", license_meta.attribution, allow_empty=True)


def _validate_targets(targets: TargetConstraints, size_bytes: int) -> None:
    if not isinstance(targets, TargetConstraints):
        raise SerializationError("targets must be TargetConstraints")
    for label, values in (("engines", targets.engines), ("formats", targets.formats)):
        if not isinstance(values, tuple):
            raise SerializationError(f"{label} must be a tuple")
        if len(values) > MAX_LIST_ITEMS:
            raise SerializationError(
                f"{label} exceeds bound",
                context={"max_items": MAX_LIST_ITEMS},
            )
        normalized = tuple(
            _bounded_token(label[:-1], item)
            for item in values
        )
        if len(set(normalized)) != len(normalized):
            raise SerializationError(f"{label} contains duplicates")
    if targets.max_bytes is not None:
        _require_int("max_bytes", targets.max_bytes, minimum=1)
        if size_bytes > targets.max_bytes:
            raise AssetManifestError(
                "asset exceeds target max_bytes constraint",
                context={"size_bytes": size_bytes, "max_bytes": targets.max_bytes},
            )
    if not isinstance(targets.constraints, tuple):
        raise SerializationError("target constraints must be a tuple")
    if len(targets.constraints) > MAX_PARAMETERS:
        raise SerializationError(
            "target constraints exceed bound",
            context={"max_parameters": MAX_PARAMETERS},
        )
    seen: set[str] = set()
    for entry in targets.constraints:
        if not isinstance(entry, tuple) or len(entry) != 2:
            raise SerializationError("target constraint entries must be (name, value) pairs")
        key, value = entry
        token = _bounded_token("parameter", key)
        if token in seen:
            raise SerializationError("target constraints contain duplicate keys")
        seen.add(token)
        _canonicalize(value)


def _validate_fingerprint(fingerprint: ContentFingerprint) -> None:
    if fingerprint.algorithm != "simhash64":
        raise AssetManifestError(
            "unsupported fingerprint algorithm",
            context={"algorithm": fingerprint.algorithm},
        )
    _require_fingerprint_value(fingerprint.value)


def _simhash64(data: bytes) -> int:
    prefix = data[:MAX_FINGERPRINT_BYTES]
    vector = [0] * 64
    if not prefix:
        return 0
    if len(prefix) < MAX_SHINGLE_WINDOW:
        shingles: Iterable[bytes] = (prefix,)
    else:
        shingles = (
            prefix[index : index + MAX_SHINGLE_WINDOW]
            for index in range(len(prefix) - MAX_SHINGLE_WINDOW + 1)
        )
    for shingle in shingles:
        hashed = int.from_bytes(hashlib.blake2s(shingle, digest_size=8).digest(), "big")
        for bit in range(64):
            vector[bit] += 1 if (hashed >> bit) & 1 else -1
    value = 0
    for bit, score in enumerate(vector):
        if score >= 0:
            value |= 1 << bit
    return value


def _canonicalize(value: Any, *, depth: int = 0) -> Any:
    if depth > 8:
        raise SerializationError("canonical value exceeds nesting bound")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SerializationError("non-finite numbers are not canonical")
        return value
    if isinstance(value, str):
        if len(value) > MAX_URI_CHARS:
            raise SerializationError(
                "string exceeds bound",
                context={"max_chars": MAX_URI_CHARS},
            )
        return value
    if isinstance(value, list):
        if len(value) > MAX_ASSETS:
            raise SerializationError(
                "list exceeds bound",
                context={"max_items": MAX_ASSETS},
            )
        return [_canonicalize(item, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        if len(value) > 32:
            raise SerializationError(
                "object exceeds bound",
                context={"max_keys": 32},
            )
        canonical: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise SerializationError("object keys must be strings")
            canonical[key] = _canonicalize(item, depth=depth + 1)
        return canonical
    raise SerializationError(
        "unsupported canonical type",
        context={"type": type(value).__name__},
    )


def _frozen_parameters(values: Mapping[str, Any]) -> tuple[tuple[str, Any], ...]:
    if not isinstance(values, Mapping):
        raise SerializationError("parameters must be an object")
    if len(values) > MAX_PARAMETERS:
        raise SerializationError(
            "parameters exceed bound",
            context={"max_parameters": MAX_PARAMETERS},
        )
    frozen: list[tuple[str, Any]] = []
    for key in sorted(values):
        token = _bounded_token("parameter", key)
        frozen.append((token, _canonicalize(values[key])))
    return tuple(frozen)


def _bounded_token_list(name: str, values: Any) -> tuple[str, ...]:
    if not isinstance(values, list):
        raise SerializationError(f"{name} must be a list")
    if len(values) > MAX_LIST_ITEMS:
        raise SerializationError(
            f"{name} exceeds bound",
            context={"max_items": MAX_LIST_ITEMS},
        )
    tokens = tuple(_bounded_token(name, item) for item in values)
    if len(set(tokens)) != len(tokens):
        raise SerializationError(f"{name} contains duplicates")
    return tokens


def _bounded_token(name: str, value: Any, *, maximum: int = MAX_TOKEN_CHARS) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SerializationError(f"{name} must be a non-empty string")
    token = value.strip()
    if len(token) > maximum:
        raise SerializationError(
            f"{name} exceeds bound",
            context={"max_chars": maximum},
        )
    if not _TOKEN_RE.fullmatch(token):
        raise SerializationError(
            f"{name} is not a canonical token",
            context={"value": token},
        )
    return token


def _bounded_string(name: str, value: Any, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise SerializationError(f"{name} must be a string")
    if len(value) > MAX_STRING_CHARS:
        raise SerializationError(
            f"{name} exceeds bound",
            context={"max_chars": MAX_STRING_CHARS},
        )
    if not allow_empty and not value.strip():
        raise SerializationError(f"{name} must be a non-empty string")
    return value


def _bounded_uri(name: str, value: Any, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise SerializationError(f"{name} must be a string")
    if len(value) > MAX_URI_CHARS:
        raise SerializationError(
            f"{name} exceeds bound",
            context={"max_chars": MAX_URI_CHARS},
        )
    if not allow_empty and not value.strip():
        raise SerializationError(f"{name} must be a non-empty string")
    if value and any(ord(char) < 32 for char in value):
        raise SerializationError(f"{name} contains control characters")
    return value


def _bounded_spdx(value: Any, *, allow_empty: bool) -> str:
    if not isinstance(value, str):
        raise SerializationError("spdx must be a string")
    if not value:
        if allow_empty:
            return ""
        raise SerializationError("spdx must be a non-empty string")
    if len(value) > MAX_TOKEN_CHARS or not _SPDX_RE.fullmatch(value):
        raise SerializationError("spdx identifier is not canonical")
    return value


def _require_kind(value: Any) -> str:
    kind = _bounded_token("kind", value)
    if kind not in ASSET_KINDS:
        raise SerializationError(
            "unsupported asset kind",
            context={"kind": kind, "supported": sorted(ASSET_KINDS)},
        )
    return kind


def _require_license_status(value: Any) -> str:
    status = _bounded_token("license status", value)
    if status not in LICENSE_STATUSES:
        raise SerializationError(
            "unsupported license status",
            context={"status": status, "supported": sorted(LICENSE_STATUSES)},
        )
    return status


def _require_digest(value: Any) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise SerializationError("digest must be a 64-character lowercase hex sha256")
    return value


def _require_fingerprint_value(value: Any) -> str:
    if not isinstance(value, str) or not _HEX16_RE.fullmatch(value):
        raise SerializationError("fingerprint value must be a 16-character lowercase hex digest")
    return value


def _require_int(name: str, value: Any, *, minimum: int, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SerializationError(f"{name} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        raise AssetManifestError(
            f"{name} is outside the accepted range",
            context={"minimum": minimum, "maximum": maximum, "value": value},
        )
    return value


def _require_exact_keys(data: Mapping[str, Any], keys: Iterable[str], label: str) -> None:
    expected = tuple(keys)
    actual = tuple(data.keys())
    if set(actual) != set(expected):
        raise SerializationError(
            f"{label} keys are not exact",
            context={"expected": list(expected), "actual": sorted(str(item) for item in actual)},
        )


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
