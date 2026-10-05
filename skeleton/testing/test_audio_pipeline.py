from __future__ import annotations
import hashlib,pytest
from skeleton.audio.pipeline import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
A=AudioAsset("AUDIO.1",S("src"),48000,2,10000,1000)
def test_audio_decode_limits_precede_processing(): assert AudioLimits(20000,2,48000,2000).admit(A)
def test_oversized_codec_resource_profile_rejected():
 with pytest.raises(AudioError,match="decode limits"): AudioLimits(5000,2,48000,2000).admit(A)
def test_segment_preserves_source_time_offsets(): assert AudioSegment("AUDIO.1",100,900).validate(A)
def test_timestamp_drift_outside_source_rejected():
 with pytest.raises(AudioError,match="timeline"): AudioSegment("AUDIO.1",9000,11000).validate(A)
def test_result_separates_kind_confidence_and_model(): assert AudioResult(AudioSegment("AUDIO.1",0,100),AudioKind.SPEECH,.8,S("model")).kind is AudioKind.SPEECH