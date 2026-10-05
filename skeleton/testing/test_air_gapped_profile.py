from __future__ import annotations

from skeleton.ai.runtime.deferred.component_provider_assurance import (
    AirGapPackage,
    qualify_air_gap_install,
)
from skeleton.ai.runtime.deferred.research_evaluation import DeploymentProfile

A="a"*64
B="b"*64
C="c"*64
D="d"*64

def package()->AirGapPackage:
    return AirGapPackage(
        "pkg-1",(A,),B,("release-signer",),(C,),D,
    )

def test_air_gap_install_requires_trusted_package_and_zero_network()->None:
    evidence=qualify_air_gap_install(
        DeploymentProfile("airgap","air_gapped","local_only","secure-site"),
        package(),expected_trust_root_digest=D,install_passed=True,
    )
    assert evidence.trust_verified is True
    assert evidence.install_passed is True
    assert evidence.network_observed is False
    assert evidence.blockers==()
    assert evidence.production_authority is False

def test_air_gap_install_reports_trust_network_and_install_failures()->None:
    evidence=qualify_air_gap_install(
        DeploymentProfile("airgap","air_gapped","local_only","secure-site"),
        package(),expected_trust_root_digest="e"*64,install_passed=False,
        network_observed=True,
    )
    assert evidence.blockers==(
        "install-failed","network-observed","trust-root-mismatch",
    )
