from __future__ import annotations

import pytest

from skeleton.ai.runtime.deferred.research_evaluation import ReproductionBundle
from skeleton.ai.runtime.deferred.research_evaluation_assurance import (
    ResearchEvaluationAssuranceError,
    qualify_reproduction_package,
)


A = "a" * 64
B = "b" * 64
C = "c" * 64
HEAD = "d" * 40


def bundle() -> ReproductionBundle:
    return ReproductionBundle(
        "experiment-1",
        A,
        B,
        C,
        ("python", "-m", "experiment"),
    )


def test_reproduction_package_binds_revision_bundle_and_artifacts() -> None:
    evidence = qualify_reproduction_package(
        bundle(),
        revision_sha=HEAD,
        artifact_digests=(A, B),
    )
    assert evidence.revision_sha == HEAD
    assert evidence.artifact_digests == (A, B)
    assert evidence.secret_free is True
    assert evidence.external_side_effects is False
    assert len(evidence.digest) == 64


def test_reproduction_package_rejects_secret_presence() -> None:
    with pytest.raises(ResearchEvaluationAssuranceError, match="secrets"):
        qualify_reproduction_package(
            bundle(),
            revision_sha=HEAD,
            artifact_digests=(A,),
            secret_present=True,
        )
