import pytest
from skeleton.retrieval.embedding_lifecycle import *
def v(model="m",dim=2):return EmbeddingVersion(model,"v1",dim,"norm:v1")
def test_mixed_spaces_never_compare_silently():
 with pytest.raises(ValueError):comparable(EmbeddingRecord("a",v(),(1,2)),EmbeddingRecord("b",v("other"),(1,2)))
def test_dimension_and_retirement_fail_closed():
 with pytest.raises(ValueError):EmbeddingRecord("a",v(),(1,))
 with pytest.raises(ValueError):comparable(EmbeddingRecord("a",v(),(1,2),True),EmbeddingRecord("b",v(),(1,2)))

def test_invalid_dimension_and_nonfinite_vector_rejected():
 import pytest,math
 with pytest.raises(ValueError):EmbeddingVersion("m","v",0,"p")
 with pytest.raises(ValueError):EmbeddingRecord("r",EmbeddingVersion("m","v",1,"p"),(math.nan,))
