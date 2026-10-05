import pytest
from skeleton.retrieval.search_index_lifecycle import *
def test_index_is_derived_and_tracks_source_watermark():assert IndexLifecycle(SearchIndex("x","v1",IndexWatermark("src1",3))).index.derived
def test_authoritative_index_and_watermark_regression_rejected():
 with pytest.raises(ValueError):IndexLifecycle(SearchIndex("x","v1",IndexWatermark("s",1),False))
 with pytest.raises(ValueError):IndexLifecycle(SearchIndex("x","v1",IndexWatermark("s",3))).refresh(IndexWatermark("s",2))
