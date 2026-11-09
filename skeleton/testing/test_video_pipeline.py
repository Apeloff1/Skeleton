from __future__ import annotations
import hashlib,pytest
from skeleton.video.pipeline import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
A=VideoAsset("VIDEO.1",S("src"),1920,1080,10000,300,100000)
def test_video_resource_admission_precedes_decode():assert VideoLimits(3000000,20000,500,200000).admit(A)
def test_long_or_frame_heavy_video_rejected():
 with pytest.raises(VideoError,match="decode limits"):VideoLimits(3000000,5000,500,200000).admit(A)
def test_sampling_budget_is_bounded():
 with pytest.raises(VideoError,match="budget"):sample_timestamps(VideoSegment("VIDEO.1",0,10000),100,50)
def test_frame_preserves_exact_source_timestamp():assert FrameSample("VIDEO.1",2500,3,S("frame")).validate(A,VideoSegment("VIDEO.1",2000,3000))
def test_timestamp_drift_outside_clip_rejected():
 with pytest.raises(VideoError,match="provenance"):FrameSample("VIDEO.1",3500,3,S("frame")).validate(A,VideoSegment("VIDEO.1",2000,3000))
