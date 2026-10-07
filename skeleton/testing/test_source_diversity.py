from skeleton.retrieval.source_diversity import *
def test_syndicated_copies_do_not_look_independent():
 i,s=diversity((SourceCluster("a",("1","2"),"o","root"),SourceCluster("b",("3",),"o","root")),(1,1,1),.5);assert i.independent_clusters==1 and s.score==1/3
def test_diversity_cannot_compensate_for_low_quality():assert diversity((SourceCluster("a",("1",),"o","r"),),(.1,),.5)[1].score==0

def test_duplicate_source_membership_rejected():
 import pytest
 cs=(SourceCluster("a",("s",),"o","l"),SourceCluster("b",("s",),"x","y"))
 with pytest.raises(ValueError):diversity(cs,(1,1),.5)
