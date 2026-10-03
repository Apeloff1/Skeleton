import pytest
from skeleton.automation.build_gate import BuildGate
def test_publish_requires_patch_and_validation(): assert BuildGate(True,True).publishable
def test_hold_blocks(): assert not BuildGate(True,True,operator_hold=True).publishable
def test_require_fails_closed():
 with pytest.raises(ValueError): BuildGate(True,False).require_publishable()
