import pytest

from skeleton.data.lineage_governance import (
    GovernedLineage,
    LineageAsset,
    LineageGovernanceError,
)


def test_laundering_and_trust_upgrade_fail() -> None:
    lineage = GovernedLineage()
    lineage.register(LineageAsset("raw", "confidential", "untrusted"))
    with pytest.raises(LineageGovernanceError):
        lineage.transform(
            transformation_id="transform",
            version="1",
            environment_digest="a" * 64,
            inputs=["raw"],
            outputs=["derived"],
            classification="internal",
            trust="trusted",
        )


def test_deletion_propagates_transitively() -> None:
    lineage = GovernedLineage()
    lineage.register(LineageAsset("a", "internal", "trusted"))
    lineage.transform(
        transformation_id="ab",
        version="1",
        environment_digest="a" * 64,
        inputs=["a"],
        outputs=["b"],
        classification="internal",
        trust="trusted",
    )
    lineage.transform(
        transformation_id="bc",
        version="1",
        environment_digest="b" * 64,
        inputs=["b"],
        outputs=["c"],
        classification="internal",
        trust="trusted",
    )
    assert lineage.mark_deleted("a") == ("a", "b", "c")


def test_transform_replay_is_idempotent_but_rebind_fails() -> None:
    lineage = GovernedLineage()
    lineage.register(LineageAsset("a", "internal", "trusted"))
    first = lineage.transform(
        transformation_id="t",
        version="1",
        environment_digest="a" * 64,
        inputs=["a"],
        outputs=["b"],
        classification="internal",
        trust="trusted",
    )
    assert lineage.transform(
        transformation_id="t",
        version="1",
        environment_digest="a" * 64,
        inputs=["a"],
        outputs=["b"],
        classification="internal",
        trust="trusted",
    ) == first
    with pytest.raises(LineageGovernanceError, match="cannot be rebound"):
        lineage.transform(
            transformation_id="t",
            version="2",
            environment_digest="a" * 64,
            inputs=["a"],
            outputs=["b"],
            classification="internal",
            trust="trusted",
        )


def test_duplicate_input_identity_is_rejected() -> None:
    lineage = GovernedLineage()
    lineage.register(LineageAsset("a", "internal", "trusted"))
    with pytest.raises(LineageGovernanceError, match="invalid transform"):
        lineage.transform(
            transformation_id="t",
            version="1",
            environment_digest="a" * 64,
            inputs=["a", "a"],
            outputs=["b"],
            classification="internal",
            trust="trusted",
        )
