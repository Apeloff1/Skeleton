from __future__ import annotations
import hashlib,pytest
from skeleton.vision.pipeline import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
def a(**kw):
 v=dict(asset_id="IMAGE.1",source_digest=S("source"),format="png",width=100,height=80,encoded_bytes=1000);v.update(kw);return ImageAsset(**v)
def test_decode_limits_checked_before_processing(): assert ImageLimits(200,200,20000,2000).admit(a())
def test_decompression_bomb_dimensions_rejected():
 with pytest.raises(VisionError,match="decode limits"): ImageLimits(200,200,20000,2000).admit(a(width=10000))
def test_region_preserves_source_coordinates_and_transform(): assert ImageRegion("IMAGE.1",10,20,30,40,S("crop")).validate(a())
def test_region_coordinate_drift_outside_source_rejected():
 with pytest.raises(VisionError,match="outside"): ImageRegion("IMAGE.1",90,20,30,40,S("crop")).validate(a())
def test_nonfinite_confidence_rejected():
 with pytest.raises(VisionError,match="confidence"): VisionResult(ImageRegion("IMAGE.1",0,0,1,1,S("t")),S("model"),float("nan"),S("result"))