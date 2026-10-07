import pytest
from skeleton.automation.studio_validation_result import ValidationResult
def test_timeout_cannot_pass():
 with pytest.raises(ValueError): ValidationResult(("x",),True,None,True,"")
def test_output_is_bounded():
 with pytest.raises(ValueError): ValidationResult(("x",),False,1,False,"x"*12001)
