import pytest
from skeleton.automation.build_composition import composition_digest
def test_order_independent():assert composition_digest((("b","2"),("a","1")))==composition_digest((("a","1"),("b","2")))
def test_duplicate_task_rejected():
 with pytest.raises(ValueError):composition_digest((("a","1"),("a","2")))
