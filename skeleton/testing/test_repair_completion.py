import pytest
from skeleton.automation.repair_completion import require_repair_closure
def test_closed():require_repair_closure({"a":"retired","b":"quarantined"})
def test_open_blocks_completion():
 with pytest.raises(ValueError):require_repair_closure({"a":"validating"})
