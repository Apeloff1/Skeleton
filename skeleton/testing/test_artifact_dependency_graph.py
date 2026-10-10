import pytest
from skeleton.artifacts.dependency_graph import *
def test_edges_are_typed_and_version_specific():
 g=ArtifactGraph((ArtifactNode("a","1","build"),ArtifactNode("b","2","source")),(ArtifactDependency("a","1","b","2","requires"),));assert g.dependencies("a","1")[0].kind=="requires"
def test_wrong_version_and_cycles_fail_closed():
 with pytest.raises(ValueError):ArtifactGraph((ArtifactNode("a","1","x"),),(ArtifactDependency("a","1","a","2","x"),))
 with pytest.raises(ValueError):ArtifactGraph((ArtifactNode("a","1","x"),ArtifactNode("b","1","x")),(ArtifactDependency("a","1","b","1","x"),ArtifactDependency("b","1","a","1","x")))

def test_duplicate_nodes_and_untyped_edges_rejected():
 import pytest
 n=ArtifactNode("a","v","x")
 with pytest.raises(ValueError):ArtifactGraph((n,n),())
 with pytest.raises(ValueError):ArtifactGraph((n,), (ArtifactDependency("a","v","a","v",""),))

def test_empty_artifact_identity_rejected():
 import pytest
 with pytest.raises(ValueError):ArtifactGraph((ArtifactNode("","v","build"),),())
