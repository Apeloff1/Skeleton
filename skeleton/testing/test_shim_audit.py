"""Tests for shim audit starter."""
import pytest
from skeleton.repo_machine.shim_audit import audit_inventory, mark_migrated, ShimAuditError

def test_inventory():
    inv = audit_inventory()
    assert inv["count"] > 0
    assert inv["stored_prose"] == 0
    assert "skeleton.galaxy.*" in inv["known_shims"]

def test_mark_known():
    d = mark_migrated("skeleton.galaxy.*")
    assert len(d) == 64

def test_unknown_shim():
    with pytest.raises(ShimAuditError):
        mark_migrated("skeleton.unknown.*")
