import pytest
from skeleton.ai.technique_retirement import *


def test_consumer_blocks_retirement_until_migrated():
    with pytest.raises(PermissionError):
        retire(
            Technique("t", "v1", ("c",)),
            RetirementEvidence(
                "old",
                "new",
                "archive",
                frozenset(),
            ),
        )


def test_history_archive_is_preserved():
    receipt = retire(
        Technique("t", "v1", ()),
        RetirementEvidence(
            "old",
            "new",
            "archive",
            frozenset(),
        ),
    )
    assert receipt.evidence.archive == "archive"


def test_self_replacement_rejected():
    with pytest.raises(ValueError):
        retire(
            Technique("t", "1", ()),
            RetirementEvidence(
                "reason",
                "t",
                "archive",
                frozenset(),
            ),
        )


def test_duplicate_consumer_inventory_rejected_at_boundary():
    with pytest.raises(ValueError):
        Technique("t", "1", ("c", "c"))


def test_all_consumers_must_be_migrated_before_retirement():
    technique = Technique("t", "1", ("a", "b"))
    with pytest.raises(PermissionError):
        retire(
            technique,
            RetirementEvidence(
                "old",
                "new",
                "archive",
                frozenset({"a"}),
            ),
        )
    receipt = retire(
        technique,
        RetirementEvidence(
            "old",
            "new",
            "archive",
            frozenset({"a", "b"}),
        ),
    )
    assert receipt.retired
