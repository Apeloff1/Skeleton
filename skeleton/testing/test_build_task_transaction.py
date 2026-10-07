import pytest
from skeleton.automation.build_task_transaction import TaskTransaction
def test_transaction():assert TaskTransaction("t","a"*64).applied("b"*64).validated().accepted().phase=="accepted"
def test_skip_validation_rejected():
 with pytest.raises(ValueError):TaskTransaction("t","a"*64).accepted()
