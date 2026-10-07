import pytest
from skeleton.artifacts.license_intelligence import *


def test_unknown_license_fails_closed():
    assert not compatible(
        (LicenseRecord("a", "1", None, ()),),
        True,
    ).compatible


def test_no_redistribution_obligation_blocks_distribution():
    record = LicenseRecord(
        "a",
        "1",
        "x",
        (LicenseObligation("no-redistribution", "yes"),),
    )
    assert not compatible((record,), True).compatible


def test_empty_record_set_not_declared_compatible():
    assert not compatible((), False).compatible


def test_conflicting_records_for_same_artifact_version_fail_closed():
    records = (
        LicenseRecord("a", "1", "MIT", ()),
        LicenseRecord("a", "1", "Apache-2.0", ()),
    )
    decision = compatible(records, True)
    assert not decision.compatible
    assert decision.reason == "conflicting license records"


def test_duplicate_obligation_and_empty_license_id_rejected():
    obligation = LicenseObligation("attribution", "required")
    with pytest.raises(ValueError):
        LicenseRecord("a", "1", "MIT", (obligation, obligation))
    with pytest.raises(ValueError):
        LicenseRecord("a", "1", "", ())
