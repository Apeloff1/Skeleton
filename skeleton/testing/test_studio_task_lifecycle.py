import pytest
from skeleton.automation.studio_task_lifecycle import TaskLifecycle
def test_happy_path():
 s=TaskLifecycle("x")
 for target in ("building","reviewing","validating","accepted"): s=s.transition(target)
 assert s.state=="accepted" and s.revision==4
def test_terminal_cannot_reopen():
 with pytest.raises(ValueError): TaskLifecycle("x","accepted").transition("building")
