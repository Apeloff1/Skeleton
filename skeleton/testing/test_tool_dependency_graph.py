import pytest
from skeleton.ai.tool_dependency_graph import *
def test_unavailable_version_detected_before_execution():assert not ToolGraph((ToolDependency("a","b","v2","requires"),),frozenset({("b","v1")})).validate().compatible
def test_cycle_detected():
 g=ToolGraph((ToolDependency("a","b","v1","r"),ToolDependency("b","a","v1","r")),frozenset({("a","v1"),("b","v1")}))
 with pytest.raises(ValueError):g.validate()

def test_unknown_dependency_kind_and_missing_source_fail():
 assert not ToolGraph((ToolDependency("a","b","1","mystery"),),frozenset({("a","1"),("b","1")})).validate().compatible
 assert not ToolGraph((ToolDependency("a","b","1","runtime"),),frozenset({("b","1")})).validate().compatible
