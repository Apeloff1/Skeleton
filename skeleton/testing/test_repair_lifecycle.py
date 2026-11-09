import pytest
from skeleton.automation.repair_lifecycle import RepairLifecycle
def test_happy_lifecycle():
 x=RepairLifecycle("r").transition("admitted").transition("building").transition("validating").transition("accepted").transition("retired");assert x.state=="retired"
def test_illegal_skip_rejected():
 with pytest.raises(ValueError):RepairLifecycle("r").transition("accepted")
