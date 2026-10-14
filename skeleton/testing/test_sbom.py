from __future__ import annotations

import hashlib

import pytest

from skeleton.ai.runtime.extensions.supply_chain.sbom import (
    SBOM,
    SBOMError,
    SoftwareComponent,
    VulnerabilityFinding,
)


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def component(component_id: str, scope: str) -> SoftwareComponent:
    return SoftwareComponent(
        component_id=component_id,
        name=component_id,
        version="1.0.0",
        scope=scope,
        artifact_digest=sha(component_id),
        license_id="Apache-2.0",
        package_url=f"pkg:pypi/{component_id}@1.0.0",
    )


def complete_sbom() -> SBOM:
    components=(
        component("direct-lib","direct"),
        component("transitive-lib","transitive"),
        component("native-lib","native"),
        component("container-base","container"),
    )
    finding=VulnerabilityFinding(
        finding_id="CVE-TEST-1",
        component_digest=components[1].digest,
        advisory_id="CVE-TEST-1",
        severity="high",
        status="fixed",
    )
    return SBOM(
        sbom_id="sbom-1",
        format="cyclonedx-json",
        build_artifact_digest=sha("release-artifact"),
        build_revision="a"*40,
        components=components,
        findings=(finding,),
    )


def test_sbom_binds_exact_build_and_all_required_component_scopes() -> None:
    sbom=complete_sbom()
    sbom.require_scope_coverage()
    assert sbom.build_artifact_digest==sha("release-artifact")
    assert sbom.scopes==("container","direct","native","transitive")
    assert len(sbom.digest)==64


def test_incomplete_sbom_scope_coverage_fails_closed() -> None:
    sbom=SBOM(
        sbom_id="partial",
        format="cyclonedx-json",
        build_artifact_digest=sha("release"),
        build_revision="b"*40,
        components=(component("direct-only","direct"),),
    )
    with pytest.raises(SBOMError,match="missing component scopes"):
        sbom.require_scope_coverage()


def test_vulnerability_must_reference_a_listed_component() -> None:
    with pytest.raises(SBOMError,match="unknown component"):
        SBOM(
            sbom_id="bad-finding",
            format="cyclonedx-json",
            build_artifact_digest=sha("release"),
            build_revision="c"*40,
            components=(component("direct-lib","direct"),),
            findings=(
                VulnerabilityFinding(
                    finding_id="finding",
                    component_digest=sha("not-a-component"),
                    advisory_id="ADV-1",
                    severity="critical",
                    status="open",
                ),
            ),
        )


def test_duplicate_component_identity_is_rejected() -> None:
    duplicate=component("same","direct")
    with pytest.raises(SBOMError,match="component ids"):
        SBOM(
            sbom_id="duplicate",
            format="cyclonedx-json",
            build_artifact_digest=sha("release"),
            build_revision="d"*40,
            components=(duplicate,duplicate),
        )


def test_unknown_sbom_format_is_rejected() -> None:
    with pytest.raises(SBOMError,match="cyclonedx-json"):
        SBOM(
            sbom_id="format",
            format="custom",
            build_artifact_digest=sha("release"),
            build_revision="e"*40,
            components=(component("direct-lib","direct"),),
        )
