import pytest
from skeleton.automation.build_progress import BuildProgress
def test_terminal_progress(): assert BuildProgress(2,2,0,0,0).terminal
def test_nonterminal_blocked(): assert not BuildProgress(2,1,0,1,0).terminal
def test_overcount_rejected():
 with pytest.raises(ValueError): BuildProgress(1,1,0,0,1)
