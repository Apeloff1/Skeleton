from skeleton.runtime.numa import *
def test_locality_preferred_when_valid():assert place((NUMANode(0,frozenset({1}),10),),NUMAAffinity(1,0),5)==NUMAPlacement(0,False)
def test_unknown_or_insufficient_locality_has_explicit_fallback():assert place((NUMANode(1,frozenset({2}),10),),NUMAAffinity(1,0),5).fallback

def test_negative_memory_and_duplicate_node_rejected():
 import pytest
 n=NUMANode(0,frozenset({0}),1)
 with pytest.raises(ValueError):place((n,n),NUMAAffinity(0,0),1)
 with pytest.raises(ValueError):place((n,),NUMAAffinity(0,0),-1)
