"""Offline contract tests for asset manifest, provenance, and dedupe.

These tests never generate assets, call models, open sockets, or touch Godot.
Caller-supplied bytes are cataloged in memory only.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import math
from pathlib import Path

import pytest

from skeleton.assets import (
    SCHEMA_VERSION,
    AssetManifest,
    AssetManifestError,
    AssetRecord,
    AssetRightsError,
    DigestDriftError,
    DuplicateIdentityError,
    DuplicateScanBoundError,
    LicenseMetadata,
    LineageError,
    LineageStep,
    SchemaCompatibilityError,
    SerializationError,
    SourceMetadata,
    TargetConstraints,
    canonical_content_identity,
    canonical_dumps,
    content_digest,
    content_fingerprint,
    detect_duplicates,
    fingerprint_similarity,
    migrate_manifest,
    parse_manifest,
    validate_lineage,
    validate_manifest,
    verify_content,
)
from skeleton.assets import manifest as manifest_mod


def _bytes(tag: str, *, size: int = 48) -> bytes:
    seed = tag.encode("utf-8")
    payload = (seed * ((size // len(seed)) + 1))[:size]
    return b"ASSET" + payload


def _license() -> LicenseMetadata:
    return LicenseMetadata(
        status="spdx",
        spdx="CC0-1.0",
        rights_holder="Apeloff1",
        attribution="Apeloff1",
    )


def _source(name: str = "hero.png") -> SourceMetadata:
    return SourceMetadata(
        origin=f"https://example.invalid/assets/{name}",
        revision="deadbeef",
        path=name,
    )


def _import_lineage(data: bytes, *extra: LineageStep) -> tuple[LineageStep, ...]:
    digest = content_digest(data)
    origin = LineageStep(step=0, operator="import", input_digest="", output_digest=digest)
    steps = [origin]
    for index, step in enumerate(extra, start=1):
        steps.append(
            LineageStep(
                step=index,
                operator=step.operator,
                input_digest=step.input_digest,
                output_digest=step.output_digest,
                parameters=step.parameters,
            )
        )
    if extra:
        steps[0] = LineageStep(
            step=0,
            operator="import",
            input_digest="",
            output_digest=extra[0].input_digest or digest,
        )
    return tuple(steps)


def _record(
    tag: str,
    *,
    asset_id: str | None = None,
    kind: str = "image",
    logical_name: str | None = None,
    release_marked: bool = False,
    data: bytes | None = None,
    lineage: tuple[LineageStep, ...] | None = None,
    targets: TargetConstraints | None = None,
    license: LicenseMetadata | None = None,
    source: SourceMetadata | None = None,
) -> tuple[AssetRecord, bytes]:
    payload = data if data is not None else _bytes(tag)
    record = AssetRecord.from_bytes(
        asset_id=asset_id or tag,
        kind=kind,
        data=payload,
        logical_name=logical_name or tag,
        media_type="application/octet-stream",
        source=source if source is not None else _source(f"{tag}.bin"),
        license=license if license is not None else _license(),
        lineage=lineage if lineage is not None else _import_lineage(payload),
        targets=targets,
        release_marked=release_marked,
    )
    return record, payload


def _manifest(*records: AssetRecord) -> AssetManifest:
    return validate_manifest(AssetManifest(schema_version=SCHEMA_VERSION, assets=records))


def test_schema_version_is_stable_and_exported():
    assert SCHEMA_VERSION == 1
    assert SCHEMA_VERSION == manifest_mod.SCHEMA_VERSION
    record, _ = _record("stable")
    manifest = _manifest(record)
    assert manifest.schema_version == 1
    payload = json.loads(manifest.serialize())
    assert payload["schema_version"] == 1
    assert set(payload) == {"schema_version", "assets"}


def test_canonical_content_identity_ignores_path_and_name():
    data = _bytes("hero")
    left, _ = _record("hero-a", logical_name="hero_idle", data=data, source=_source("idle.png"))
    right, _ = _record("hero-b", logical_name="hero_run", data=data, source=_source("run.png"))
    assert left.content.sha256 == right.content.sha256 == content_digest(data)
    assert left.content.canonical_identity == right.content.canonical_identity
    assert left.content.canonical_identity == canonical_content_identity(
        kind="image",
        content_sha256=content_digest(data),
    )
    assert left.identity.asset_id != right.identity.asset_id


def test_reproducible_serialization_is_order_independent():
    first, _ = _record("alpha")
    second, _ = _record("beta")
    left = _manifest(second, first)
    right = _manifest(first, second)
    assert left.serialize() == right.serialize()
    assert left.digest() == right.digest()
    restored = parse_manifest(left.serialize())
    assert restored.serialize() == left.serialize()
    swapped_keys = canonical_dumps({"b": 1, "a": {"y": 2, "x": 1}})
    assert swapped_keys == canonical_dumps({"a": {"x": 1, "y": 2}, "b": 1})
    assert swapped_keys == '{"a":{"x":1,"y":2},"b":1}'


def test_non_canonical_values_fail_closed():
    with pytest.raises(SerializationError):
        canonical_dumps({"x": math.nan})
    with pytest.raises(SerializationError):
        canonical_dumps({"x": math.inf})
    with pytest.raises(SerializationError):
        canonical_dumps({"pos": (1, 2)})
    with pytest.raises(SerializationError):
        canonical_dumps({1: "x"})


def test_direct_record_construction_cannot_bypass_content_schema_validation():
    data = _bytes("direct")
    valid, _ = _record("direct", data=data)

    with pytest.raises(AssetManifestError, match="size_bytes"):
        validate_manifest(
            AssetManifest(
                schema_version=SCHEMA_VERSION,
                assets=(
                    AssetRecord(
                        identity=valid.identity,
                        content=manifest_mod.ContentDescriptor(
                            sha256=valid.content.sha256,
                            size_bytes=-1,
                            media_type=valid.content.media_type,
                            canonical_identity=valid.content.canonical_identity,
                        ),
                        source=valid.source,
                        license=valid.license,
                        lineage=valid.lineage,
                        targets=valid.targets,
                        release_marked=False,
                        fingerprint=valid.fingerprint,
                    ),
                ),
            )
        )

    with pytest.raises(SerializationError, match="media_type"):
        validate_manifest(
            AssetManifest(
                schema_version=SCHEMA_VERSION,
                assets=(
                    AssetRecord(
                        identity=valid.identity,
                        content=manifest_mod.ContentDescriptor(
                            sha256=valid.content.sha256,
                            size_bytes=valid.content.size_bytes,
                            media_type="x" * (manifest_mod.MAX_STRING_CHARS + 1),
                            canonical_identity=valid.content.canonical_identity,
                        ),
                        source=valid.source,
                        license=valid.license,
                        lineage=valid.lineage,
                        targets=valid.targets,
                        release_marked=False,
                        fingerprint=valid.fingerprint,
                    ),
                ),
            )
        )

    malformed_release_flag = AssetRecord(
        identity=valid.identity,
        content=valid.content,
        source=valid.source,
        license=valid.license,
        lineage=valid.lineage,
        targets=valid.targets,
        release_marked="false",  # type: ignore[arg-type]
        fingerprint=valid.fingerprint,
    )
    with pytest.raises(SerializationError, match="release_marked"):
        validate_manifest(
            AssetManifest(
                schema_version=SCHEMA_VERSION,
                assets=(malformed_release_flag,),
            )
        )


def test_digest_drift_fails_closed_on_bytes_and_declared_identity():
    record, data = _record("drift")
    verify_content(record, data)
    with pytest.raises(DigestDriftError, match="content digest drifted"):
        verify_content(record, data + b"x")
    tampered = json.loads(_manifest(record).serialize())
    tampered["assets"][0]["content"]["sha256"] = hashlib.sha256(b"other").hexdigest()
    with pytest.raises(DigestDriftError, match="canonical content identity"):
        parse_manifest(tampered)
    with pytest.raises(DigestDriftError, match="content digest drifted"):
        parse_manifest(
            _manifest(record).serialize(),
            data_by_id={record.identity.asset_id: data + b"nope"},
        )


def test_byte_verification_map_must_cover_exact_manifest_identities():
    left, left_data = _record("left")
    right, right_data = _record("right")
    manifest = _manifest(left, right)

    verified = validate_manifest(
        manifest,
        data_by_id={
            left.identity.asset_id: left_data,
            right.identity.asset_id: right_data,
        },
    )
    assert len(verified.assets) == 2

    with pytest.raises(DigestDriftError, match="verification set"):
        validate_manifest(
            manifest,
            data_by_id={left.identity.asset_id: left_data},
        )

    with pytest.raises(DigestDriftError, match="verification set"):
        validate_manifest(
            manifest,
            data_by_id={
                left.identity.asset_id: left_data,
                right.identity.asset_id: right_data,
                "ghost": b"not-in-manifest",
            },
        )


def test_malformed_lineage_fails_closed():
    data = _bytes("lineage")
    digest = content_digest(data)
    other = content_digest(b"other-bytes")
    with pytest.raises(LineageError, match="contiguous"):
        validate_lineage(
            (
                LineageStep(step=1, operator="import", input_digest="", output_digest=digest),
            ),
            digest,
        )
    with pytest.raises(LineageError, match="does not follow"):
        validate_lineage(
            (
                LineageStep(step=0, operator="import", input_digest="", output_digest=other),
                LineageStep(step=1, operator="resize", input_digest=digest, output_digest=digest),
            ),
            digest,
        )
    with pytest.raises(LineageError, match="does not terminate"):
        validate_lineage(
            (LineageStep(step=0, operator="import", input_digest="", output_digest=other),),
            digest,
        )
    with pytest.raises(LineageError, match="repeats an earlier step"):
        validate_lineage(
            (
                LineageStep(step=0, operator="import", input_digest="", output_digest=other),
                LineageStep(step=1, operator="copy", input_digest=other, output_digest=other),
                LineageStep(step=2, operator="export", input_digest=other, output_digest=digest),
            ),
            digest,
        )
    with pytest.raises(SerializationError):
        validate_lineage(
            (LineageStep(step=0, operator="import", input_digest="", output_digest="not-a-digest"),),
            digest,
        )
    with pytest.raises(LineageError, match="missing input digest"):
        validate_lineage(
            (
                LineageStep(step=0, operator="import", input_digest="", output_digest=other),
                LineageStep(step=1, operator="resize", input_digest="", output_digest=digest),
            ),
            digest,
        )


def test_valid_lineage_chain_terminates_at_content_digest():
    raw = _bytes("raw-source", size=32)
    final = _bytes("quantized", size=32)
    raw_digest = content_digest(raw)
    final_digest = content_digest(final)
    lineage = (
        LineageStep(step=0, operator="import", input_digest="", output_digest=raw_digest),
        LineageStep(
            step=1,
            operator="quantize",
            input_digest=raw_digest,
            output_digest=final_digest,
            parameters=(("bits", 8),),
        ),
    )
    validate_lineage(lineage, final_digest)
    record, _ = _record("quantized", data=final, lineage=lineage, release_marked=True)
    assert record.lineage[-1].output_digest == record.content.sha256


def test_duplicate_identities_fail_closed():
    first, _ = _record("same-id", asset_id="hero")
    second, _ = _record("same-id-copy", asset_id="hero", data=_bytes("other"))
    with pytest.raises(DuplicateIdentityError, match="duplicate asset identity"):
        _manifest(first, second)
    payload = json.loads(_manifest(first).serialize())
    payload["assets"].append(json.loads(_manifest(second).serialize())["assets"][0])
    payload["assets"][1]["identity"]["asset_id"] = "hero"
    with pytest.raises(DuplicateIdentityError):
        parse_manifest(payload)


def test_schema_migration_from_legacy_documents():
    data = _bytes("legacy")
    digest = content_digest(data)
    fingerprint = content_fingerprint(data)
    legacy = {
        "assets": [
            {
                "id": "legacy-hero",
                "type": "image",
                "name": "Legacy Hero",
                "checksum": digest,
                "size": len(data),
                "source": "https://example.invalid/legacy-hero.png",
                "license": "CC0-1.0",
                "rights_holder": "Apeloff1",
                "fingerprint": fingerprint.value,
                "lineage": [
                    {"op": "import", "output": digest},
                ],
            }
        ]
    }
    migrated = migrate_manifest(legacy)
    assert migrated["schema_version"] == SCHEMA_VERSION
    manifest = parse_manifest(migrated, data_by_id={"legacy-hero": data})
    assert manifest.assets[0].identity.asset_id == "legacy-hero"
    assert manifest.assets[0].identity.kind == "image"
    assert manifest.assets[0].content.sha256 == digest
    assert manifest.assets[0].license.spdx == "CC0-1.0"
    assert manifest.assets[0].source.origin.endswith("legacy-hero.png")
    assert parse_manifest(manifest.serialize()).digest() == manifest.digest()


def test_unknown_schema_version_fails_closed():
    with pytest.raises(SchemaCompatibilityError, match="incompatible"):
        migrate_manifest({"schema_version": 99, "assets": []})
    with pytest.raises(SchemaCompatibilityError, match="must be an integer"):
        migrate_manifest({"schema_version": "1", "assets": []})
    empty = parse_manifest({"schema_version": 1, "assets": []})
    assert empty.assets == ()


def test_release_marked_missing_rights_or_source_fails_closed():
    data = _bytes("release")
    with pytest.raises(AssetRightsError, match="source origin"):
        AssetRecord.from_bytes(
            asset_id="released",
            kind="image",
            data=data,
            source=SourceMetadata(),
            license=_license(),
            lineage=_import_lineage(data),
            release_marked=True,
        )
    with pytest.raises(AssetRightsError, match="rights holder"):
        AssetRecord.from_bytes(
            asset_id="released",
            kind="image",
            data=data,
            source=_source(),
            license=LicenseMetadata(status="spdx", spdx="CC0-1.0", rights_holder=""),
            lineage=_import_lineage(data),
            release_marked=True,
        )
    with pytest.raises(AssetRightsError, match="unknown licensing"):
        AssetRecord.from_bytes(
            asset_id="released",
            kind="image",
            data=data,
            source=_source(),
            license=LicenseMetadata(status="unknown"),
            lineage=_import_lineage(data),
            release_marked=True,
        )


def test_non_release_assets_may_omit_optional_rights():
    data = _bytes("wip")
    record = AssetRecord.from_bytes(
        asset_id="wip",
        kind="image",
        data=data,
        source=SourceMetadata(),
        license=LicenseMetadata(status="unknown"),
        release_marked=False,
    )
    manifest = _manifest(record)
    assert manifest.assets[0].license.status == "unknown"
    assert manifest.assets[0].source.origin == ""


def test_exact_and_near_duplicate_hooks_are_deterministic_and_bounded():
    shared = _bytes("clone")
    left, _ = _record("clone-a", data=shared)
    right, _ = _record("clone-b", data=shared, logical_name="alias")
    similar_a, _ = _record("near-a", data=_bytes("tile", size=64))
    similar_b, _ = _record("near-b", data=_bytes("tile", size=64)[:-1] + b"!")
    distinct, _ = _record("unique", data=_bytes("unique-bytes", size=64), kind="audio")
    manifest = _manifest(right, distinct, similar_b, left, similar_a)
    first = detect_duplicates(manifest)
    second = detect_duplicates(manifest)
    assert first == second
    assert first.to_payload() == second.to_payload()
    assert len(first.exact) == 1
    assert first.exact[0].asset_ids == ("clone-a", "clone-b")
    assert first.exact[0].content_sha256 == content_digest(shared)
    assert similar_a.content.sha256 != similar_b.content.sha256
    assert fingerprint_similarity(similar_a.fingerprint, similar_b.fingerprint) == fingerprint_similarity(
        similar_b.fingerprint, similar_a.fingerprint
    )
    assert any(
        {pair.left_asset_id, pair.right_asset_id} == {"near-a", "near-b"} for pair in first.near
    )
    assert detect_duplicates(manifest, near_limit=1).near[0] == first.near[0]


def test_near_duplicate_scan_fails_closed_when_comparisons_exceed_bound(monkeypatch):
    monkeypatch.setattr(manifest_mod, "MAX_DEDUPE_COMPARISONS", 1)
    records = [_record(f"item-{index}", data=_bytes(f"item-{index}"))[0] for index in range(3)]
    manifest = _manifest(*records)
    with pytest.raises(DuplicateScanBoundError, match="comparison bound"):
        detect_duplicates(manifest)


def test_target_max_bytes_constraint_fails_closed():
    data = _bytes("oversized", size=80)
    with pytest.raises(AssetManifestError, match="max_bytes"):
        AssetRecord.from_bytes(
            asset_id="oversized",
            kind="image",
            data=data,
            source=_source(),
            license=_license(),
            targets=TargetConstraints(engines=("godot4",), formats=("png",), max_bytes=16),
        )


def test_round_trip_parse_preserves_release_marked_record():
    record, data = _record("ship", release_marked=True)
    encoded = _manifest(record).serialize()
    restored = parse_manifest(encoded, data_by_id={"ship": data})
    assert restored.assets[0].release_marked is True
    assert restored.assets[0].license.rights_holder == "Apeloff1"
    assert restored.digest() == _manifest(record).digest()


def test_module_stays_generation_and_godot_free():
    source = Path(inspect.getsourcefile(manifest_mod)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {
        "__future__",
        "collections",
        "hashlib",
        "json",
        "math",
        "dataclasses",
        "typing",
        "re",
        "skeleton",
    }
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name for alias in node.names]
            if isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            joined = " ".join(names).lower()
            for banned in ("openai", "godot", "requests", "httpx", "socket", "urllib"):
                assert banned not in joined
