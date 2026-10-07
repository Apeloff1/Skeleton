from __future__ import annotations

from dataclasses import replace
import hashlib

import pytest

from skeleton.release.attribution import (
    AttributionEntry,
    ReleaseAttributionError,
    ReleaseAttributionManifest,
    qualify_release_attribution,
    render_release_notice,
)
from skeleton.release.qualification import ReleaseQualificationDecision


COMMIT = "a" * 40


def _release(**overrides: object) -> ReleaseQualificationDecision:
    values: dict[str, object] = {
        "accepted": True,
        "reasons": (),
        "source_commit": COMMIT,
        "release_evidence_digest": "1" * 64,
        "reproducibility_bundle_digest": "2" * 64,
        "reproducibility_evaluation_digest": "3" * 64,
        "dependency_evidence_digest": "4" * 64,
        "sbom_digest": "5" * 64,
        "provenance_digest": "6" * 64,
        "installer_metadata_digest": "7" * 64,
        "configuration_digest": "8" * 64,
        "lifecycle_receipt_digests": ("9" * 64,),
    }
    values.update(overrides)
    return ReleaseQualificationDecision(**values)


def _entries() -> tuple[AttributionEntry, ...]:
    return (
        AttributionEntry(
            component_id="Apeloff1/Skeleton",
            source_ref="repository:Apeloff1/Skeleton",
            license_path="LICENSE",
            license_digest="a" * 64,
            third_party=False,
        ),
        AttributionEntry(
            component_id="OpenAI/codex",
            source_ref="vendored:OpenAI/codex",
            license_path=(
                "skeleton/ai/research/external/OpenAI/codex/"
                "LICENSE.upstream.txt"
            ),
            license_digest="b" * 64,
            third_party=True,
        ),
    )


def _manifest(
    release: ReleaseQualificationDecision,
    entries: tuple[AttributionEntry, ...] | None = None,
) -> ReleaseAttributionManifest:
    rows = _entries() if entries is None else entries
    notice_digest = hashlib.sha256(
        render_release_notice(rows).encode("utf-8")
    ).hexdigest()
    return ReleaseAttributionManifest(
        source_commit=release.source_commit,
        release_qualification_digest=release.decision_digest,
        entries=rows,
        notice_digest=notice_digest,
    )


def _observed(
    entries: tuple[AttributionEntry, ...],
) -> dict[str, str]:
    return {
        item.license_path: item.license_digest
        for item in entries
    }


def _paths(
    entries: tuple[AttributionEntry, ...],
) -> tuple[str, ...]:
    return tuple(item.license_path for item in entries)


def test_exact_release_attribution_qualifies() -> None:
    release = _release()
    manifest = _manifest(release)

    decision = qualify_release_attribution(
        release_qualification=release,
        manifest=manifest,
        observed_license_digests=_observed(manifest.entries),
        discovered_license_paths=_paths(manifest.entries),
    )

    assert decision.accepted is True
    assert decision.reasons == ()
    assert decision.source_commit == COMMIT
    assert decision.entry_count == 2
    assert decision.notice_digest == manifest.notice_digest

    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "release_attribution_qualification"
    assert evidence.digest == decision.decision_digest


def test_notice_rendering_is_deterministic_across_entry_order() -> None:
    entries = _entries()

    assert render_release_notice(entries) == render_release_notice(
        tuple(reversed(entries))
    )


def test_release_qualification_must_be_accepted() -> None:
    release = _release(
        accepted=False,
        reasons=("forced-release-rejection",),
    )
    manifest = _manifest(release)

    decision = qualify_release_attribution(
        release_qualification=release,
        manifest=manifest,
        observed_license_digests=_observed(manifest.entries),
        discovered_license_paths=_paths(manifest.entries),
    )

    assert decision.accepted is False
    assert "release-qualification-rejected" in decision.reasons


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    (
        (
            "source_commit",
            "f" * 40,
            "attribution-source-commit-mismatch",
        ),
        (
            "release_qualification_digest",
            "0" * 64,
            "attribution-release-digest-mismatch",
        ),
    ),
)
def test_manifest_binds_exact_rel01_identity(
    field: str,
    value: str,
    reason: str,
) -> None:
    release = _release()
    manifest = replace(_manifest(release), **{field: value})

    decision = qualify_release_attribution(
        release_qualification=release,
        manifest=manifest,
        observed_license_digests=_observed(manifest.entries),
        discovered_license_paths=_paths(manifest.entries),
    )

    assert decision.accepted is False
    assert reason in decision.reasons


def test_exact_license_bytes_are_bound_by_digest() -> None:
    release = _release()
    manifest = _manifest(release)
    observed = _observed(manifest.entries)
    observed["LICENSE"] = "0" * 64

    decision = qualify_release_attribution(
        release_qualification=release,
        manifest=manifest,
        observed_license_digests=observed,
        discovered_license_paths=_paths(manifest.entries),
    )

    assert decision.accepted is False
    assert "license-digest-mismatch:LICENSE" in decision.reasons


def test_missing_observed_license_digest_blocks() -> None:
    release = _release()
    manifest = _manifest(release)
    observed = _observed(manifest.entries)
    del observed["LICENSE"]

    decision = qualify_release_attribution(
        release_qualification=release,
        manifest=manifest,
        observed_license_digests=observed,
        discovered_license_paths=_paths(manifest.entries),
    )

    assert decision.accepted is False
    assert "license-digest-missing:LICENSE" in decision.reasons


def test_invalid_observed_license_digest_blocks() -> None:
    release = _release()
    manifest = _manifest(release)
    observed = _observed(manifest.entries)
    observed["LICENSE"] = "not-a-digest"

    decision = qualify_release_attribution(
        release_qualification=release,
        manifest=manifest,
        observed_license_digests=observed,
        discovered_license_paths=_paths(manifest.entries),
    )

    assert decision.accepted is False
    assert "license-digest-invalid:LICENSE" in decision.reasons


def test_unattributed_discovered_license_blocks() -> None:
    release = _release()
    manifest = _manifest(release)
    extra = (
        "skeleton/ai/research/external/Test/project/"
        "LICENSE.upstream.txt"
    )

    decision = qualify_release_attribution(
        release_qualification=release,
        manifest=manifest,
        observed_license_digests=_observed(manifest.entries),
        discovered_license_paths=(*_paths(manifest.entries), extra),
    )

    assert decision.accepted is False
    assert f"license-unattributed:{extra}" in decision.reasons


def test_stale_registry_license_blocks() -> None:
    release = _release()
    manifest = _manifest(release)

    decision = qualify_release_attribution(
        release_qualification=release,
        manifest=manifest,
        observed_license_digests=_observed(manifest.entries),
        discovered_license_paths=("LICENSE",),
    )

    assert decision.accepted is False
    assert any(
        reason.startswith("license-registry-stale:")
        for reason in decision.reasons
    )


def test_manifest_requires_exactly_one_first_party_root_license() -> None:
    release = _release()
    third_party_only = (
        AttributionEntry(
            component_id="OpenAI/codex",
            source_ref="vendored:OpenAI/codex",
            license_path=(
                "skeleton/ai/research/external/OpenAI/codex/"
                "LICENSE.upstream.txt"
            ),
            license_digest="b" * 64,
            third_party=True,
        ),
    )
    notice_digest = hashlib.sha256(
        render_release_notice(third_party_only).encode("utf-8")
    ).hexdigest()

    with pytest.raises(
        ReleaseAttributionError,
        match="exactly one first-party root license",
    ):
        ReleaseAttributionManifest(
            source_commit=release.source_commit,
            release_qualification_digest=release.decision_digest,
            entries=third_party_only,
            notice_digest=notice_digest,
        )


def test_first_party_and_third_party_scope_cannot_be_swapped() -> None:
    with pytest.raises(
        ReleaseAttributionError,
        match="root project license cannot be third-party",
    ):
        AttributionEntry(
            component_id="root",
            source_ref="repository:root",
            license_path="LICENSE",
            license_digest="a" * 64,
            third_party=True,
        )

    with pytest.raises(
        ReleaseAttributionError,
        match="first-party release license must be root LICENSE",
    ):
        AttributionEntry(
            component_id="vendor",
            source_ref="vendored:vendor",
            license_path="vendor/LICENSE.upstream.txt",
            license_digest="b" * 64,
            third_party=False,
        )


def test_manifest_rejects_notice_digest_substitution() -> None:
    release = _release()
    entries = _entries()

    with pytest.raises(
        ReleaseAttributionError,
        match="notice digest does not match deterministic notice",
    ):
        ReleaseAttributionManifest(
            source_commit=release.source_commit,
            release_qualification_digest=release.decision_digest,
            entries=entries,
            notice_digest="0" * 64,
        )


def test_manifest_rejects_duplicate_component_or_license_identity() -> None:
    release = _release()
    entries = _entries()

    duplicate_component = (
        entries[0],
        replace(
            entries[1],
            component_id=entries[0].component_id,
        ),
    )
    digest = hashlib.sha256(
        render_release_notice(duplicate_component).encode("utf-8")
    ).hexdigest()
    with pytest.raises(
        ReleaseAttributionError,
        match="component IDs must be unique",
    ):
        ReleaseAttributionManifest(
            source_commit=release.source_commit,
            release_qualification_digest=release.decision_digest,
            entries=duplicate_component,
            notice_digest=digest,
        )

    duplicate_path = (
        entries[0],
        replace(
            entries[1],
            license_path=entries[0].license_path,
            third_party=False,
        ),
    )
    digest = hashlib.sha256(
        render_release_notice(duplicate_path).encode("utf-8")
    ).hexdigest()
    with pytest.raises(
        ReleaseAttributionError,
        match="license paths must be unique",
    ):
        ReleaseAttributionManifest(
            source_commit=release.source_commit,
            release_qualification_digest=release.decision_digest,
            entries=duplicate_path,
            notice_digest=digest,
        )


def test_rejected_attribution_cannot_materialize_promotion_evidence() -> None:
    release = _release()
    manifest = _manifest(release)
    observed = _observed(manifest.entries)
    observed["LICENSE"] = "0" * 64

    decision = qualify_release_attribution(
        release_qualification=release,
        manifest=manifest,
        observed_license_digests=observed,
        discovered_license_paths=_paths(manifest.entries),
    )

    assert decision.accepted is False
    with pytest.raises(
        ReleaseAttributionError,
        match="cannot become promotion evidence",
    ):
        decision.accepted_evidence_ref()
