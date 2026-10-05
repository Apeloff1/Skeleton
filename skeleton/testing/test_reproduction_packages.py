from __future__ import annotations
import hashlib
import pytest
from skeleton.ai.runtime.extensions.artifacts.reproduction_package import ReproductionArtifact,ReproductionPackage,ReproductionPackageError

def d(x): return hashlib.sha256(x.encode()).hexdigest()

def test_reproduction_package_binds_revision_environment_commands_and_artifacts():
    package=ReproductionPackage(
        "pkg","exp-1","a"*40,d("env"),
        (
            ReproductionArtifact("config.json","config",d("cfg")),
            ReproductionArtifact("results.json","output",d("out")),
        ),
        ("python run.py --config config.json",),
        deterministic_seed=42,
    )
    assert package.production_authority is False
    assert len(package.digest)==64

def test_duplicate_artifact_identity_is_rejected():
    artifact=ReproductionArtifact("x","input",d("x"))
    with pytest.raises(ReproductionPackageError,match="identities must be unique"):
        ReproductionPackage("p","e","b"*40,d("env"),(artifact,artifact),("run",))

def test_revision_must_be_exact_git_sha():
    with pytest.raises(ReproductionPackageError,match="40-character"):
        ReproductionPackage("p","e","bad",d("env"),(ReproductionArtifact("x","input",d("x")),),("run",))

def test_reproduction_package_cannot_grant_production_authority():
    with pytest.raises(ReproductionPackageError,match="cannot grant"):
        ReproductionPackage("p","e","c"*40,d("env"),(ReproductionArtifact("x","input",d("x")),),("run",),production_authority=True)
