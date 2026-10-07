import pytest
from skeleton.automation.build_acceptance import Acceptance
def test_all_five_required(): Acceptance(True,True,True,True,True).require_complete()
def test_ci_missing_blocks_completion():
 with pytest.raises(ValueError): Acceptance(True,True,False,True,True).require_complete()
